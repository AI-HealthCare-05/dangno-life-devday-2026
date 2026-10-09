"""Collect a deterministic public-photo evaluation set; never changes model training data."""

import concurrent.futures
import csv
import hashlib
import io
import json
import random
import time
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs/food_photo_benchmark_20261009"
KFOOD = "Jiho0o0/kfood_image_englabel"
MMFOOD = "Humanbased-AI/MM-Food-100K"
EXCLUDED_RAW_RICE_ROWS = {8854, 55138, 62016, 48908, 73685, 10635, 48360, 5252, 67032, 2733}


def difference_hash(image):
    pixels = np.asarray(image.convert("L").resize((9, 8)))
    return int.from_bytes(np.packbits(pixels[:, 1:] > pixels[:, :-1]).tobytes(), "big")


def get(client, url, **kwargs):
    for attempt in range(3):
        try:
            response = client.get(url, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPError:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)
    raise RuntimeError("Unreachable")


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    client = httpx.Client(timeout=25, follow_redirects=True)
    revisions = {}
    for dataset in (KFOOD, MMFOOD):
        revisions[dataset] = get(client, "https://huggingface.co/api/datasets/" + dataset).json()["sha"]
    metadata_path = OUTPUT / "kfood_all_metadata.json"
    if metadata_path.exists():
        kfood_rows = json.loads(metadata_path.read_text(encoding="utf-8"))
    else:
        def page(offset):
            response = get(client, "https://datasets-server.huggingface.co/rows", params={
                "dataset": KFOOD, "config": "default", "split": "train", "offset": offset, "length": 100,
            })
            print("metadata page", offset, flush=True)
            return response.json()["rows"]
        with concurrent.futures.ThreadPoolExecutor(3) as pool:
            pages = list(pool.map(page, range(0, 2145, 100)))
        kfood_rows = [row for page_rows in pages for row in page_rows]
        metadata_path.write_text(json.dumps(kfood_rows), encoding="utf-8")
    csv_path = OUTPUT / "source_metadata.csv"
    if not csv_path.exists():
        csv_path.write_bytes(get(client, f"https://huggingface.co/datasets/{MMFOOD}/resolve/{revisions[MMFOOD]}/MM-Food-100K.csv").content)
    with csv_path.open(encoding="utf-8", newline="") as source:
        mmfood_rows = list(csv.DictReader(source))
    candidates = {"kimchi": [], "rice": []}
    for row in kfood_rows:
        label = row["row"]["label"]
        if "kimchi" in label.lower() and not any(term in label.lower() for term in ("stew", "jjigae", "fried", "pancake", "jeon", "bokkeum")):
            image = row["row"]["image"]
            candidates["kimchi"].append(dict(source_dataset=KFOOD, source_row=row["row_idx"], source_label=label, url=image["src"]))
    for index, row in enumerate(mmfood_rows):
        if row["dish_name"] in {"Cooked White Rice", "Steamed White Rice", "White Rice", "Plain Rice", "Cooked Rice", "Steamed Rice"}:
            candidates["rice"].append(dict(source_dataset=MMFOOD, source_row=index, source_label=row["dish_name"], url=row["image_url"]))
        elif row["dish_name"] == "Kimchi":
            candidates["kimchi"].append(dict(source_dataset=MMFOOD, source_row=index, source_label="Kimchi", url=row["image_url"]))
    print("candidate counts", {key: len(rows) for key, rows in candidates.items()}, flush=True)
    rng = random.Random(20261009)
    rows = []
    hashes = set()
    perceptual_hashes = []
    failures = []
    for group, choices in candidates.items():
        rng.shuffle(choices)
        folder = OUTPUT / "images" / group
        folder.mkdir(parents=True, exist_ok=True)
        for choice in choices:
            if sum(row["group"] == group for row in rows) == 100:
                break
            try:
                if choice["source_dataset"] == MMFOOD and choice["source_row"] in EXCLUDED_RAW_RICE_ROWS:
                    failures.append({"group": group, "source_row": choice["source_row"], "reason": "visually_screened_raw_rice"})
                    continue
                raw = get(client, choice["url"]).content
                with Image.open(io.BytesIO(raw)) as image:
                    image.load()
                    rgb = image.convert("RGB")
                    original_size = rgb.size
                    if min(original_size) < 128:
                        raise ValueError("resolution_below_128")
                    rgb.thumbnail((1600, 1600))
                    pixel_hash = hashlib.sha256(str(rgb.size).encode() + rgb.tobytes()).hexdigest()
                    if pixel_hash in hashes:
                        failures.append({"group": group, "source_row": choice["source_row"], "reason": "duplicate_pixels"})
                        continue
                    visual_hash = difference_hash(rgb)
                    if any((visual_hash ^ previous_hash).bit_count() <= 3 for previous_hash in perceptual_hashes):
                        failures.append({"group": group, "source_row": choice["source_row"], "reason": "near_duplicate_dhash_le_3"})
                        continue
                    output = io.BytesIO()
                    rgb.save(output, "JPEG", quality=85)
                content = output.getvalue()
                number = sum(row["group"] == group for row in rows) + 1
                path = folder / f"{group}-{number:03}.jpg"
                path.write_bytes(content)
                hashes.add(pixel_hash)
                perceptual_hashes.append(visual_hash)
                rows.append({**choice, "group": group, "source_revision": revisions[choice["source_dataset"]],
                             "path": path.relative_to(OUTPUT).as_posix(), "original_width": original_size[0],
                             "original_height": original_size[1], "sha256": hashlib.sha256(content).hexdigest(),
                             "pixel_sha256": pixel_hash, "dhash": f"{visual_hash:016x}"})
                (OUTPUT / "manifest.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
                if number % 10 == 0:
                    print("downloaded", group, number, flush=True)
            except (httpx.HTTPError, OSError, ValueError) as exc:
                failures.append({"group": group, "source_row": choice["source_row"], "reason": type(exc).__name__})
        print("finished group", group, sum(row["group"] == group for row in rows), flush=True)
    (OUTPUT / "collection_summary.json").write_text(json.dumps({
        "seed": 20261009, "candidate_counts": {key: len(value) for key, value in candidates.items()},
        "downloaded_counts": {key: sum(row["group"] == key for row in rows) for key in candidates},
        "unique_pixel_hashes": len(hashes), "minimum_dhash_distance": 4, "failures": failures, "revisions": revisions,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
