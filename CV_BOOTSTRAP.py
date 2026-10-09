"""Install checksum-pinned CV artifacts and verify real CPU inference."""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import io
import os
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent
FILES = (
    ("best.pt", "14UI-dnUCUvyDQ8kVlYlWtDrx7dViBm9M", "4c4df6ba2b9d3daf77f7ffe107285df17a360342729177d15465ba9872d42726"),
    ("meta.json", "1Q7JuQzge_H_b20XfBbgOrQ_jWHJeFA-1", "a193e1faf4e7c266e0ba4481451ded587fcd01cfc7d89c60d834bac63e14e0b3"),
    ("1.tflite", "1Q0bXcvJZO95075quDJsVR2xENgS-3Vcp", "edb7df52467afd02a502d7765ca7ac82e63ad86082c72e18135764f1b1817b52"),
)
MAX_BYTES = 128 * 1024 * 1024


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def download(file_id, target):
    request = urllib.request.Request(
        f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t",
        headers={"User-Agent": "DangNO-CV-bootstrap/1.0"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        if response.headers.get_content_type() == "text/html":
            raise RuntimeError("Drive did not return a model file")
        total = 0
        with target.open("wb") as output:
            while block := response.read(1024 * 1024):
                total += len(block)
                if total > MAX_BYTES:
                    raise RuntimeError("CV file exceeds download limit")
                output.write(block)


def provision(destination):
    destination.mkdir(parents=True, exist_ok=True)
    if all((destination / n).is_file() and digest(destination / n) == sha for n, _, sha in FILES):
        return
    if shutil.disk_usage(destination).free < 512 * 1024 * 1024:
        raise RuntimeError("At least 512 MiB free space required for artifact staging")
    with tempfile.TemporaryDirectory(prefix=".cv-stage-", dir=destination.parent) as staging:
        staged = Path(staging)
        for name, file_id, sha in FILES:
            download(file_id, staged / name)
            if digest(staged / name) != sha:
                raise RuntimeError(f"CV checksum mismatch: {name}")
        # All checksums must pass before replacing any artifact.
        for name, _, _ in FILES:
            os.replace(staged / name, destination / name)


def verify():
    sys.path.insert(0, str(ROOT))
    from app.core import config
    from app.vision.food_vision import food_vision_is_configured, get_food_vision_provider
    if config.FOOD_VISION_PROVIDER != "local_kfood" or not food_vision_is_configured():
        raise RuntimeError("Local CV configuration or artifact verification failed")
    import torch
    torch.set_num_threads(1)
    provider = get_food_vision_provider()
    provider._load()
    from PIL import Image
    image = io.BytesIO()
    Image.new("RGB", (256, 256), (240, 240, 240)).save(image, format="PNG")
    # Local synthetic image: checks model execution, not food-recognition accuracy.
    result = asyncio.run(provider.analyze(image.getvalue(), "image/png", "cv-runtime-smoke.png"))
    print("CV_INFERENCE_OK", result.provider_kind)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    from app.vision.local_kfood import configured_model_paths
    classifier, metadata, segmenter = configured_model_paths()
    if len({p.parent.resolve() for p in (classifier, metadata, segmenter)}) != 1:
        raise RuntimeError("CV artifacts must share one directory")
    if not args.check_only:
        provision(classifier.parent.resolve())
    verify()


if __name__ == "__main__":
    main()
