"""Create a private representative reference from the exact frozen training CSV."""

import hashlib
import json
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.update({k: v for k, v in dotenv_values(ROOT / ".env.local-mobile").items() if v is not None})


TRAINING_CSV_SHA256 = "70c2e4a0d71e883a4181589bfb3042413f6f6e13104756b88d24e103e195ddfa"


def main():
    # Import configuration only after the local environment has been loaded.
    from app.core import config
    from src.ml.inference.diabetes_current_screening import load_current_screening_model
    from src.ml.preprocessing.xai_reference import select_reference

    source = (
        Path(sys.argv[1])
        if len(sys.argv) > 1
        else ROOT.parent / "data/processed/official_v1/knhanes_cleaned_2016_2024.csv"
    )
    raw = source.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    if hashlib.sha256(raw).hexdigest() != TRAINING_CSV_SHA256:
        raise ValueError("Source does not match the frozen model's training CSV")
    loaded = load_current_screening_model(
        manifest_path=Path(config.CURRENT_SCREENING_MANIFEST_URI), model_path=config.CURRENT_SCREENING_MODEL_URI
    )
    split = loaded.artifact["config"]["split_contract"]
    columns = list(
        dict.fromkeys(
            [
                *loaded.manifest["features"],
                "split",
                "survey_year",
                "survey_weight",
                "eligible_diabetes_undiagnosed",
                "cohort_19_plus",
                "target_diabetes_clinical",
            ]
        )
    )
    background, train_count = select_reference(
        pd.read_csv(source, usecols=columns), features=loaded.manifest["features"], train_years=split["train"]
    )
    destination = ROOT / "models/artifacts/xai/today-train-reference-v2/background.csv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    background.to_csv(destination, index=False, float_format="%.12g", lineterminator="\n")
    manifest = dict(
        schema_version=1,
        reference_version="today-train-reference-v2",
        train_only=True,
        model_version=loaded.manifest["model_version"],
        model_artifact_sha256=loaded.manifest["artifact_sha256"],
        source_normalized_sha256=TRAINING_CSV_SHA256,
        train_years=split["train"],
        excluded_years=split["validation"] + split["test"],
        eligible_train_count=train_count,
        sampling="survey-weighted year/sex stratified; without replacement",
        seed=20261001,
        sample_size=len(background),
        features=loaded.manifest["features"],
        artifact_local_path=destination.relative_to(ROOT).as_posix(),
        artifact_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
        baseline_label="학습 자료의 대표 표본 기준 (2016–2020년)",
        git_policy="reference rows stay outside Git",
    )
    registry = ROOT / "models/registry/xai/today-train-reference-v2.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Provisioned {len(background)} private reference rows from {train_count} eligible Train rows; source/model hashes verified."
    )


if __name__ == "__main__":
    main()
