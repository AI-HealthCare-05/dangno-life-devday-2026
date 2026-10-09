"""Verify explanations from approved local artifacts using synthetic inputs."""

import asyncio
import os
import sys
from datetime import date
from pathlib import Path
from time import perf_counter

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.update({k: v for k, v in dotenv_values(ROOT / ".env.local-mobile").items() if v is not None})


async def main():
    # Import configuration only after the local environment has been loaded.
    from app.core import config
    from app.services.ai_jobs import _demo_current_explanation, _demo_future_explanation
    from src.ml.inference.diabetes_current_screening import load_current_screening_model, predict_artifact

    loaded = load_current_screening_model(
        manifest_path=Path(config.CURRENT_SCREENING_MANIFEST_URI), model_path=config.CURRENT_SCREENING_MODEL_URI
    )
    inputs = dict(
        age=60,
        sex=2,
        height_cm=165,
        weight_kg=72,
        waist_cm=95,
        bmi=26.45,
        systolic_bp=135,
        diastolic_bp=85,
        current_smoker=0,
        education=3,
        region=1,
        diabetes_family_history=1,
        hypertension_family_history=0,
        alcohol_frequency=2,
    )
    started = perf_counter()
    current = await _demo_current_explanation(
        loaded,
        inputs,
        predict_artifact=predict_artifact,
        model_version=config.CURRENT_SCREENING_MODEL_VERSION,
        elevated=True,
        operational=True,
    )
    current_seconds = perf_counter() - started
    assert current.get("method") == "exact_grouped_shap_train_reference_v2"
    assert current.get("background_size") == 128
    print(f"Today reference calculation: {current_seconds:.2f}s; fixed 128-row Train reference")
    payload = dict(
        birth_date="1966-01-01",
        sex="female",
        height_cm=165,
        weight_kg=72,
        waist_cm=95,
        smoking_status="never",
        current_drinker=False,
        regular_exercise=True,
        exercise_days_per_week=3,
        exercise_minutes=20,
        previously_diagnosed_diabetes=False,
    )
    future = await _demo_future_explanation(
        payload,
        as_of_date=date(2026, 9, 30),
        model_version=config.PREDICTION_MODEL_VERSION,
        elevated=False,
        operational=True,
    )
    for label, result in [("Today", current), ("Tomorrow", future)]:
        assert result.get("additivity_verified") is True, (label, result.get("status"))
        assert result.get("display_allowed") is True, (label, result.get("selection_status"))
        assert len(result["items"]) == 3
        print(f"PASS {label}: approved actual SHAP, three factors, additivity verified")


if __name__ == "__main__":
    asyncio.run(main())
