"""A bad final Drive artifact must never replace an already installed model."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


def test_bad_last_checksum_preserves_installed_cv_models(monkeypatch, tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/provision-cv-google-drive.py"
    spec = importlib.util.spec_from_file_location("cv_delivery", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    config_dir = tmp_path / "configs/model_delivery"
    config_dir.mkdir(parents=True)
    registry_dir = tmp_path / "models/registry/food_vision"
    registry_dir.mkdir(parents=True)
    digest = hashlib.sha256(b"verified").hexdigest()
    config = {
        "files": [
            {"name": "best.pt", "file_id": "classifier", "registry_section": "classifier", "digest_key": "sha256"},
            {"name": "meta.json", "file_id": "metadata", "registry_section": "classifier", "digest_key": "meta_sha256"},
            {"name": "1.tflite", "file_id": "bad-segmenter", "registry_section": "segmenter", "digest_key": "sha256"},
        ]
    }
    (config_dir / "google_drive_cv.json").write_text(json.dumps(config))
    (registry_dir / "kfood-vegetable-v1.json").write_text(
        json.dumps({"classifier": {"sha256": digest, "meta_sha256": digest}, "segmenter": {"sha256": digest}})
    )
    installed = tmp_path / "models/artifacts/food_vision/kfood/best.pt"
    installed.parent.mkdir(parents=True)
    installed.write_bytes(b"existing-approved-model")
    installations = []
    helpers = {
        "download": lambda file_id, target: target.write_bytes(
            b"corrupt" if file_id == "bad-segmenter" else b"verified"
        ),
        "sha256": lambda target: hashlib.sha256(target.read_bytes()).hexdigest(),
        "atomic_install": lambda source, target: installations.append(target),
    }
    monkeypatch.setattr(module.runpy, "run_path", lambda path: helpers)
    with pytest.raises(ValueError, match="checksum mismatch"):
        module.main()
    assert installations == []
    assert installed.read_bytes() == b"existing-approved-model"
