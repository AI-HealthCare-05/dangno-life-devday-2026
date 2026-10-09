import hashlib
import json

import pandas as pd
import pytest

from src.ml.inference import xai_background
from src.ml.inference.shap_explanations import explain_today
from src.ml.preprocessing.xai_reference import select_reference


def test_reference_selection_never_uses_heldout_or_ineligible_rows():
    rows = [
        dict(
            age=i,
            sex=1 + i % 2,
            split="train",
            survey_year=2016,
            eligible_diabetes_undiagnosed=True,
            cohort_19_plus=True,
            target_diabetes_clinical=0,
            survey_weight=1,
        )
        for i in range(20)
    ]
    rows += [
        {**rows[0], "age": 999, "split": "test", "survey_year": 2023},
        {**rows[0], "age": 998, "split": "train", "survey_year": 2021},
        {**rows[0], "age": 997, "eligible_diabetes_undiagnosed": False},
    ]
    data = pd.DataFrame(rows)
    result, count = select_reference(data, features=["age", "sex"], train_years=[2016], sample_size=8)
    assert count == 20 and len(result) == 8
    assert list(result.columns) == ["age", "sex"]
    assert result.age.max() < 20
    assert result.equals(select_reference(data, features=["age", "sex"], train_years=[2016], sample_size=8)[0])


def test_empirical_reference_exact_shap_is_additive_and_groups_body_inputs():
    background = pd.DataFrame(
        [
            dict(age=0.0, sex=1.0, height_cm=160.0, weight_kg=60.0, bmi=23.0),
            dict(age=2.0, sex=0.0, height_cm=180.0, weight_kg=80.0, bmi=25.0),
        ]
    )
    frame = pd.DataFrame([dict(age=3.0, sex=1.0, height_cm=170.0, weight_kg=70.0, bmi=24.0)])

    def score(rows):
        assert rows[["height_cm", "weight_kg", "bmi"]].drop_duplicates().shape[0] <= 3
        return (rows.age * 0.1 + rows.sex * 0.2 + rows.age * rows.sex * 0.05 + rows.bmi * 0.001).to_numpy()

    result = explain_today(frame, score, model_version="synthetic", elevated=True, background=background)
    assert result["method"] == "exact_grouped_shap_train_reference_v2"
    assert result["reference_value"] == pytest.approx(score(background).mean())
    assert result["reference_value"] + sum(i["contribution"] for i in result["all_items"]) == pytest.approx(
        score(frame)[0]
    )
    contributions = {item["feature"]: item["contribution"] for item in result["all_items"]}
    assert contributions == pytest.approx({"age": 0.2875, "sex": 0.1625, "body_measurements": 0.0})
    assert result["additivity_verified"] is True and result["display_allowed"] is False
    assert result == explain_today(frame, score, model_version="synthetic", elevated=True, background=background)


def test_missing_reference_does_not_silently_fall_back_to_all_missing(monkeypatch, tmp_path):
    with pytest.raises(FileNotFoundError):
        xai_background.load_today_background("model", "digest", tmp_path / "missing.json")


def test_reference_loader_checks_model_split_and_file_integrity(monkeypatch, tmp_path):
    monkeypatch.setattr(xai_background, "ROOT", tmp_path)
    artifact = tmp_path / "models/artifacts/reference.csv"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("age\n50\n60\n", encoding="utf-8")
    manifest = dict(
        model_version="model",
        model_artifact_sha256="digest",
        train_only=True,
        train_years=[2016],
        excluded_years=[2023],
        artifact_local_path="models/artifacts/reference.csv",
        artifact_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
        features=["age"],
        sample_size=2,
    )
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    xai_background.load_today_background.cache_clear()
    assert len(xai_background.load_today_background("model", "digest", path)[0]) == 2
    with pytest.raises(ValueError):
        xai_background.load_today_background("different-model", "digest", path)
    artifact.write_text("age\n70\n80\n", encoding="utf-8")
    xai_background.load_today_background.cache_clear()
    with pytest.raises(ValueError, match="checksum"):
        xai_background.load_today_background("model", "digest", path)
    xai_background.load_today_background.cache_clear()
