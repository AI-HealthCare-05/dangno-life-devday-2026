"""Compare real local CV and semantic VLM on a manifest of public photos.

This is a diagnostic evaluation, not a mask-accuracy benchmark or model training.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import time
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path

from fastapi import UploadFile

async def evaluate(folder: Path, concurrency: int = 3) -> dict:
    import torch

    from app.core import config
    from app.services.challenge_proofs import sanitized_photo
    from app.vision.food_vision import FoodVisionError, get_food_vision_provider
    from app.vision.openai_vlm import VLM_REVIEW_POLICY_VERSION, OpenAIVegetableVerifier, apply_vlm_review
    from app.vision.photo_context import FoodPhotoContext

    torch.set_num_threads(2)
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    entries_by_hash = {entry["sha256"]: entry for entry in manifest}
    results_path = folder / "results.jsonl"
    previous = {}
    if results_path.exists():
        for line in results_path.read_text(encoding="utf-8").splitlines():
            if line:
                row = json.loads(line)
                if row["sha256"] in entries_by_hash and row.get("policy_version") == VLM_REVIEW_POLICY_VERSION:
                    entry = entries_by_hash[row["sha256"]]
                    row.update({key: entry[key] for key in ("path", "source_dataset", "source_row", "source_label", "group")})
                    previous[row["sha256"]] = row
    provider = get_food_vision_provider()
    verifier = OpenAIVegetableVerifier()
    semaphore = asyncio.Semaphore(concurrency)
    rows = list(previous.values())

    async def one(entry):
        if entry["sha256"] in previous:
            return
        async with semaphore:
            path = (folder / entry["path"]).resolve()
            if not path.is_relative_to(folder.resolve()):
                raise ValueError("Image path escapes benchmark folder")
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != entry["sha256"]:
                raise ValueError("Image hash differs from collected manifest")
            photo = await sanitized_photo(UploadFile(file=io.BytesIO(content)))
            started = time.monotonic()
            cv_result = await provider.analyze(photo, "image/jpeg", "public-benchmark.jpg")
            cv_seconds = time.monotonic() - started
            # Conditions are hints, not image/mask ground truth. Rice backgrounds
            # vary, so white-on-white is left unknown rather than fabricated.
            context = FoodPhotoContext("yes", "unsure", "unsure") if entry["group"] == "kimchi" else FoodPhotoContext("no", "unsure", "unsure")
            started = time.monotonic()
            try:
                review = await verifier.verify(photo, context)
                combined = apply_vlm_review(cv_result, review)
                error = None
            except FoodVisionError as exc:
                error = getattr(exc, "reason_code", "vlm_service_unavailable")
                review = None
                combined = replace(cv_result, reliable=False, decision_status="uncertain", uncertainty_reasons=[*cv_result.uncertainty_reasons, error])
            row = {
                "path": entry["path"], "sha256": entry["sha256"], "group": entry["group"],
                "source_dataset": entry["source_dataset"], "source_row": entry["source_row"],
                "source_label": entry["source_label"], "photo_context": context.as_dict(),
                "policy_version": VLM_REVIEW_POLICY_VERSION,
                "cv": asdict(cv_result), "vlm": review, "combined": asdict(combined),
                "vlm_error": error, "cv_seconds": round(cv_seconds, 3),
                "vlm_seconds": round(time.monotonic() - started, 3),
            }
            rows.append(row)
            with results_path.open("a", encoding="utf-8") as output:
                output.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(json.dumps({"completed": len(rows), "total": len(manifest), "group": row["group"], "cv": cv_result.decision_status, "combined": combined.decision_status, "error": error}), flush=True)

    await asyncio.gather(*(one(entry) for entry in manifest))
    rows.sort(key=lambda row: row["path"])
    (folder / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {
        "model": config.OPENAI_VLM_MODEL, "policy_version": VLM_REVIEW_POLICY_VERSION, "count": len(rows), "concurrency": concurrency,
        "thresholds": {"food_percent": config.FOOD_COVERAGE_PASS_THRESHOLD * 100,
                       "vegetable_percent": config.VEGETABLE_RATIO_PASS_THRESHOLD * 100},
        "groups": {},
        "limitations": ["Source dish labels are not pixel-mask or certification ground truth.",
                        "Training overlap with the approved CV classifier is unknown.",
                        "No model training, threshold tuning or actual user challenge records are changed."],
    }
    for group in sorted({row["group"] for row in rows}):
        selected = [row for row in rows if row["group"] == group]
        reviews = [row["vlm"] for row in selected if row["vlm"] is not None]
        summary["groups"][group] = {
            "count": len(selected), "cv_decisions": dict(Counter(row["cv"]["decision_status"] for row in selected)),
            "combined_decisions": dict(Counter(row["combined"]["decision_status"] for row in selected)),
            "cv_unreliable": sum(not row["cv"]["reliable"] for row in selected),
            "cv_top1": dict(Counter(row["cv"]["detected_items"][0] for row in selected)),
            "vlm_successes": len(reviews), "vlm_failures": dict(Counter(row["vlm_error"] for row in selected if row["vlm_error"])),
            "vlm_vegetables_visible": sum(review["vegetables_clearly_visible"] for review in reviews),
            "vlm_vegetable_presence": dict(Counter(review["vegetable_presence"] for review in reviews)),
            "vlm_food_boundary_unclear": sum(not review["food_boundaries_clear"] for review in reviews),
            "vlm_vegetable_boundary_unclear": sum(not review["vegetable_boundaries_clear"] for review in reviews),
            "cv_to_vlm_transitions": dict(Counter(row["cv"]["decision_status"] + " -> " + row["combined"]["decision_status"] for row in selected)),
        }
    (folder / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main():
    from scripts.local_mobile_settings import load_local_mobile_settings

    root = Path(__file__).resolve().parents[3]
    load_local_mobile_settings(root)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, default=root / "outputs/food_photo_benchmark_20261009")
    parser.add_argument("--concurrency", type=int, choices=range(1, 5), default=3)
    args = parser.parse_args()
    summary = asyncio.run(evaluate(args.folder, args.concurrency))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
