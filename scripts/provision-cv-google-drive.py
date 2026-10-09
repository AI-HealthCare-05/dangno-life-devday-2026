"""Install the existing Drive CV files with the same checksum/atomic delivery policy."""

import json
import runpy
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    helpers = runpy.run_path(str(ROOT / "scripts/provision-models-google-drive.py"))
    delivery = json.loads((ROOT / "configs/model_delivery/google_drive_cv.json").read_text(encoding="utf-8"))
    registry = json.loads((ROOT / "models/registry/food_vision/kfood-vegetable-v1.json").read_text(encoding="utf-8"))
    destination = ROOT / "models/artifacts/food_vision/kfood"
    with tempfile.TemporaryDirectory(prefix="cv-drive-") as directory:
        staged = []
        for entry in delivery["files"]:
            name = entry["name"]
            if name not in {"best.pt", "meta.json", "1.tflite"}:
                raise ValueError("Unsupported CV model filename")
            path = Path(directory) / name
            helpers["download"](entry["file_id"], path)
            expected = registry[entry["registry_section"]][entry["digest_key"]]
            if helpers["sha256"](path) != expected:
                raise ValueError(f"CV registry checksum mismatch: {name}")
            staged.append((path, destination / name))
        # Verify every file before replacing any installed artifact.
        for source, target in staged:
            helpers["atomic_install"](source, target)
            print(f"OK {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
