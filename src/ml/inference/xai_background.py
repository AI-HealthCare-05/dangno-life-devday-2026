"""Load a checksum-bound, Train-only reference without exposing training rows."""

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST = ROOT / "models/registry/xai/today-train-reference-v2.json"


@lru_cache(maxsize=4)
def load_today_background(model_version, model_digest, manifest_path=DEFAULT_MANIFEST):
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if (
        manifest["model_version"] != model_version
        or manifest["model_artifact_sha256"] != model_digest
        or manifest.get("train_only") is not True
        or set(manifest["train_years"]) & set(manifest["excluded_years"])
    ):
        raise ValueError("Reference/model/split contract mismatch")
    artifact = (ROOT / manifest["artifact_local_path"]).resolve()
    if not artifact.is_relative_to(ROOT / "models/artifacts"):
        raise ValueError("Reference must remain in the private artifact directory")
    if hashlib.sha256(artifact.read_bytes()).hexdigest() != manifest["artifact_sha256"]:
        raise ValueError("Reference checksum mismatch")
    frame = pd.read_csv(artifact)
    if list(frame.columns) != manifest["features"] or len(frame) != manifest["sample_size"]:
        raise ValueError("Reference shape mismatch")
    return frame, manifest


def explain_today_with_reference(frame, score_batch, *, model_version, model_digest, elevated):
    from src.ml.inference.shap_explanations import explain_today

    background, manifest = load_today_background(model_version, model_digest)
    result = explain_today(frame, score_batch, model_version=model_version, elevated=elevated, background=background)
    result.update(
        reference_version=manifest["reference_version"],
        reference_sha256=manifest["artifact_sha256"],
        baseline_label=manifest["baseline_label"],
    )
    return result
