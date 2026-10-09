import asyncio
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from ai_worker.core import config
from ai_worker.model_loader import load_model
from app.prediction import get_prediction_provider
from app.prediction.contracts import ACTIVE_MODEL, CURRENT_SCREENING_MODEL

MEDICAL_NOTICE = "이 결과는 시스템 연동 확인 또는 위험 선별 보조용이며 진단·처방이 아닙니다."


def _release_explanation(explanation: dict[str, Any], *, operational: bool) -> dict[str, Any]:
    """Apply the independent XAI release gate without changing SHAP values."""
    from src.ml.inference.shap_explanations import has_displayable_selection

    released = dict(explanation)
    allowed = (
        operational
        and config.XAI_DISPLAY_ALLOWED
        and released.get("shap_claimed") is True
        and released.get("additivity_verified") is True
        and has_displayable_selection(released)
    )
    released["status"] = "approved" if allowed else released.get("status", "unavailable")
    released["display_allowed"] = allowed
    return released


async def preload_configured_models() -> None:
    """Fail worker readiness when an explicitly selected artifact is invalid."""
    if not config.MODEL_PRELOAD_ENABLED:
        return
    if config.PREDICTION_PROVIDER == "artifact":
        from app.prediction.providers import load_standard_model

        await asyncio.to_thread(load_standard_model)
    if config.CURRENT_SCREENING_RUNTIME == "shared8-waist":
        from src.ml.inference.research_models import load_shared8

        await asyncio.to_thread(load_shared8, config.ML_SHARED8_MODEL_URI)
    elif config.CURRENT_SCREENING_RUNTIME in {"v061", "today14"}:
        from src.ml.inference.diabetes_current_screening import load_current_screening_model

        await asyncio.to_thread(
            load_current_screening_model,
            manifest_path=Path(config.CURRENT_SCREENING_MANIFEST_URI),
            model_path=config.CURRENT_SCREENING_MODEL_URI,
        )
    else:
        raise RuntimeError(f"지원하지 않는 CURRENT_SCREENING_RUNTIME입니다: {config.CURRENT_SCREENING_RUNTIME}")
    if config.TOMORROW_RUNTIME == "rf25":
        from src.ml.inference.research_models import load_tomorrow_rf25

        await asyncio.to_thread(load_tomorrow_rf25, config.ML_RF25_MODEL_URI)
    elif config.TOMORROW_RUNTIME != "standard":
        raise RuntimeError(f"지원하지 않는 TOMORROW_RUNTIME입니다: {config.TOMORROW_RUNTIME}")


async def run_task_with_timeout(task_type: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    return await asyncio.wait_for(run_task(task_type, payload), timeout=timeout_seconds)


async def _augment_with_risk_curve(
    provider: Any,
    response: dict[str, Any],
    model_input: dict[str, Any],
    as_of_date: date,
) -> None:
    """Attach a same-model, age-shifted risk curve when the base result is approved.

    No separate survival model is trained here; see
    src.ml.inference.diabetes_standard.predict_age_curve. Failures are
    swallowed on purpose — the curve is a supplementary addition and must
    never fail the primary approved prediction.
    """
    if response.get("promotion_status") != "approved":
        return
    try:
        curve_points = await provider.predict_curve(model_input, as_of_date=as_of_date)
        if curve_points:
            response["risk_curve_points"] = curve_points
            response["output_definition_version"] = "rf25_same_model_age_shift_approximation_v1"
            response["age_risk_forecast"] = _build_age_risk_forecast(curve_points)
    except Exception:
        # The curve/forecast is a supplementary addition and must never
        # fail the primary approved prediction, so any failure here
        # (including in the display-shape conversion) is swallowed.
        response.pop("risk_curve_points", None)
        response.pop("age_risk_forecast", None)


def _build_age_risk_forecast(curve_points: list[dict[str, Any]]) -> dict[str, Any]:
    """Descriptive age-curve display payload only.

    scenarios/uncertainty are intentionally left empty: REQ-PRED-012 keeps
    PredictionScenario.is_active False until a scenario method is
    separately validated, so an unvalidated "lifestyle improvement"
    comparison must not be surfaced here as if it were causal.
    """
    return {
        "status": "approved",
        "public_display_approved": True,
        "points": [
            {
                "display_label": (
                    f"{point['years_from_now']}년 후 ({point['age']}세)"
                    if "years_from_now" in point
                    else f"{point['age']}세"
                ),
                "display_percent": round(float(point["risk_score"]) * 100, 1),
            }
            for point in curve_points
        ],
        "scenarios": {},
        "uncertainty": {},
    }


async def _run_s2_future_model(model_input: dict[str, Any], as_of_date: date) -> dict[str, Any]:
    from src.ml.inference.research_models import load_ensemble, predict_research_model

    output = await asyncio.to_thread(
        predict_research_model,
        "first-interval",
        model_input,
        as_of_date=as_of_date,
        model_path=config.ML_FIRST_INTERVAL_MODEL_URI,
    )
    preview_points = [
        {
            "display_label": f"{point['horizon_years']}년 후 ({point['projected_age']}세)",
            "signal_level": "high" if point["screening_signal_detected"] else "low",
        }
        for point in output["curve"]
        if point["horizon_years"] in {2, 4, 6}
    ]
    first_point = output["curve"][0]
    return {
        "model_key": output["model_key"],
        "task_type": output["task_type"],
        "threshold_scope": output["threshold_scope"],
        "outcome_definition": "future_cumulative_incidence_research_signal",
        "internal_score": first_point["cumulative_risk_signal"],
        "risk_category": None,
        "preview_signal_level": "high" if first_point["screening_signal_detected"] else "low",
        "preview_only": True,
        "display_allowed": False,
        "operational_model_activated": False,
        "model_version": output["model_version"],
        "feature_schema_version": output["feature_schema_version"],
        "input_schema_version": output["input_schema_version"],
        "preprocessing_version": "standard-api-frame-v1",
        "target_definition_version": output["output_definition_version"],
        "calibration_version": output["calibration_version"],
        "model_artifact_digest": load_ensemble(config.ML_FIRST_INTERVAL_MODEL_URI).manifest["artifact_sha256"],
        "threshold_version": output["threshold_version"],
        "decision_threshold": None,
        "promotion_status": "research_candidate_only",
        "output_status": output["output_status"],
        "model_population": "undiagnosed_klosa_age_45_105",
        "explanation_status": "not_available",
        "risk_curve_status": output["risk_curve_status"],
        "age_risk_forecast": {
            "status": "research_candidate_only",
            "preview_only": True,
            "display_allowed": False,
            "risk_curve_status": output["risk_curve_status"],
            "calibration_status": "research_only",
            "points": preview_points,
            "scenarios": {},
            "uncertainty": {},
        },
        "research_output": output,
        "medical_notice": output["disclaimer"],
    }


async def _run_rf25_future_model(model_input: dict[str, Any], as_of_date: date) -> dict[str, Any]:
    """Run RF25 and expose categories only through the explicit release gate."""

    from src.ml.inference.research_models import predict_research_model

    output = await asyncio.to_thread(
        predict_research_model,
        "tomorrow-rf25",
        model_input,
        as_of_date=as_of_date,
        model_path=config.ML_RF25_MODEL_URI,
    )
    operational = (
        ACTIVE_MODEL.threshold_is_approved
        and output.get("promotion_status") == "approved"
        and output.get("operational_model_activated") is True
        and output["model_version"] == ACTIVE_MODEL.version
        and output["artifact_sha256"] == ACTIVE_MODEL.model_artifact_digest
    )
    explanation = _release_explanation(output.get("explanation", {}), operational=operational)
    return {
        "model_key": ACTIVE_MODEL.model_key,
        "task_type": "future_incidence_risk_screening",
        "threshold_scope": "future_incidence_2y",
        "outcome_definition": ACTIVE_MODEL.outcome_definition,
        "internal_score": (output["risk_score_internal"] if "risk_score_internal" in output else output["risk_score"]),
        "risk_category": output["risk_category"] if operational else None,
        "preview_only": not operational,
        "display_allowed": operational,
        "operational_model_activated": operational,
        "model_version": output["model_version"],
        "feature_schema_version": output["feature_schema_version"],
        "input_schema_version": output["input_schema_version"],
        "preprocessing_version": ACTIVE_MODEL.preprocessing_version,
        "target_definition_version": ACTIVE_MODEL.target_definition_version,
        "calibration_version": ACTIVE_MODEL.calibration_version,
        "model_artifact_digest": output["artifact_sha256"],
        "threshold_version": output["threshold_version"],
        "decision_threshold": output.get("decision_threshold") if operational else None,
        "promotion_status": "approved" if operational else "research_candidate_only",
        "output_status": (
            "screening_not_diagnosis" if operational else "research_candidate_not_operationally_approved"
        ),
        "model_population": "undiagnosed_klosa_age_45_105",
        "explanation": explanation,
        "explanation_status": explanation.get("status", "not_available"),
        "medical_notice": output["disclaimer"],
    }


async def _run_reduced_current_model(
    model_input: dict[str, Any],
    as_of_date_raw: Any,
    model: str = "shared7",
) -> dict[str, Any]:
    if not isinstance(as_of_date_raw, str):
        raise ValueError("S2 diabetes_current_screening payload에는 as_of_date가 필요합니다.")
    try:
        as_of_date = date.fromisoformat(as_of_date_raw)
    except ValueError as exc:
        raise ValueError("as_of_date must use YYYY-MM-DD") from exc
    from src.ml.inference.research_models import predict_research_model

    output = await asyncio.to_thread(
        predict_research_model,
        model,
        model_input,
        as_of_date=as_of_date,
        model_path=config.ML_SHARED8_MODEL_URI if model == "shared8-waist" else config.ML_SHARED7_MODEL_URI,
    )
    signal_level = "high" if output["screening_signal_detected"] else "low"
    return {
        "model_key": output["model_key"],
        "task_type": output["task_type"],
        "threshold_scope": output["threshold_scope"],
        "outcome_definition": "current_diabetes_research_screening_signal",
        "internal_score": output["risk_score_internal"],
        "risk_category": None,
        "screening_signal_detected": None,
        "preview_signal_level": signal_level,
        "preview_only": True,
        "display_allowed": False,
        "operational_model_activated": False,
        "model_version": output["model_version"],
        "feature_schema_version": output["feature_schema_version"],
        "input_schema_version": output["input_schema_version"],
        "preprocessing_version": (
            "shared8-waist-train-estimator-standard-api-frame-v1"
            if model == "shared8-waist"
            else "shared7-standard-api-frame-v1"
        ),
        "target_definition_version": "current-diabetes-screening-research-v1",
        "calibration_version": output["calibration_version"],
        "model_artifact_digest": output["artifact_sha256"],
        "threshold_version": output["threshold_version"],
        "decision_threshold": None,
        "promotion_status": "research_candidate_only",
        "output_status": output["output_status"],
        "model_population": "knhanes_age_19_plus_research",
        "explanation_status": output.get("explanation_status", "not_available"),
        "risk_curve_status": "not_applicable",
        "research_output": output,
        "medical_notice": output["disclaimer"],
    }


async def run_task(task_type: str, payload: dict[str, Any]) -> dict[str, Any]:  # noqa: C901
    if task_type == "demo_inference":
        await asyncio.sleep(0.5)
        return {
            "is_demo": True,
            "pipeline": "redis-stream-consumer-group",
            "received_fields": sorted(payload),
            "processed_at": datetime.now(UTC).isoformat(),
            "medical_notice": MEDICAL_NOTICE,
        }

    if task_type == "model_inference":
        features = payload.get("features")
        if not isinstance(features, list) or not features:
            raise ValueError("model_inference payload에는 비어 있지 않은 features 배열이 필요합니다.")
        model = load_model()
        prediction = await asyncio.to_thread(model.predict, [features])
        result: dict[str, Any] = {
            "prediction": prediction[0].item() if hasattr(prediction[0], "item") else prediction[0],
            "is_demo": False,
            "medical_notice": MEDICAL_NOTICE,
        }
        if hasattr(model, "predict_proba"):
            probabilities = await asyncio.to_thread(model.predict_proba, [features])
            result["probabilities"] = probabilities[0].tolist()
        return result

    if task_type == "diabetes_incidence":
        model_input = payload.get("input")
        as_of_date_raw = payload.get("as_of_date")
        if not isinstance(model_input, dict) or not isinstance(as_of_date_raw, str):
            raise ValueError("diabetes_incidence payload에는 input 객체와 as_of_date가 필요합니다.")
        try:
            as_of_date = date.fromisoformat(as_of_date_raw)
        except ValueError as exc:
            raise ValueError("as_of_date must use YYYY-MM-DD") from exc
        if config.TOMORROW_RUNTIME == "rf25":
            return await _run_rf25_future_model(model_input, as_of_date)
        if config.S2_MODEL_RUNTIME_ENABLED:
            return await _run_s2_future_model(model_input, as_of_date)
        provider = get_prediction_provider()
        result = await provider.predict(model_input, as_of_date=as_of_date)
        response: dict[str, Any] = {
            "model_key": "diabetes_incidence",
            "outcome_definition": "next_observation_new_diabetes_diagnosis",
            "internal_score": result.internal_score,
            "risk_category": result.risk_category,
            "model_version": result.model_version,
            "feature_schema_version": result.feature_schema_version,
            "input_schema_version": result.input_schema_version,
            "preprocessing_version": result.preprocessing_version,
            "target_definition_version": result.target_definition_version,
            "calibration_version": result.calibration_version,
            "model_artifact_digest": result.model_artifact_digest,
            "threshold_version": result.threshold_version,
            "decision_threshold": result.decision_threshold,
            "promotion_status": result.promotion_status,
            "explanation_status": result.explanation_status,
            "display_allowed": result.display_allowed,
            "operational_model_activated": result.operational_model_activated,
            "input_as_of_date": as_of_date.isoformat(),
            "medical_notice": MEDICAL_NOTICE,
        }
        await _augment_with_risk_curve(provider, response, model_input, as_of_date)
        return response

    if task_type == "diabetes_current_screening":
        model_input = payload.get("input")
        if not isinstance(model_input, dict):
            raise ValueError("diabetes_current_screening payload에는 input 객체가 필요합니다.")
        if config.CURRENT_SCREENING_RUNTIME == "shared8-waist":
            return await _run_reduced_current_model(model_input, payload.get("as_of_date"), "shared8-waist")
        if config.S2_MODEL_RUNTIME_ENABLED:
            return await _run_reduced_current_model(model_input, payload.get("as_of_date"))
        from src.ml.inference.diabetes_current_screening import (
            load_current_screening_model,
            predict_with_loaded_current_model,
        )

        loaded = await asyncio.to_thread(
            load_current_screening_model,
            manifest_path=Path(config.CURRENT_SCREENING_MANIFEST_URI),
            model_path=config.CURRENT_SCREENING_MODEL_URI,
        )
        # The service payload is a versioned superset shared by Today and
        # Tomorrow.  Select the immutable manifest contract at the worker
        # boundary so adding optional service inputs never breaks an older
        # artifact and a new 14-feature artifact receives all declared fields.
        contracted_input = {name: model_input.get(name) for name in loaded.manifest["features"]}
        output = await asyncio.to_thread(predict_with_loaded_current_model, loaded, contracted_input)
        operational = (
            CURRENT_SCREENING_MODEL.threshold_is_approved
            and loaded.manifest.get("operational_model_activated") is True
            and output["model_version"] == CURRENT_SCREENING_MODEL.version
            and loaded.manifest.get("artifact_sha256") == CURRENT_SCREENING_MODEL.model_artifact_digest
        )
        signal = bool(output["screening_signal_detected"])
        from src.ml.inference.shap_explanations import safe_explanation
        from src.ml.inference.xai_background import explain_today_with_reference
        from src.ml.modeling.knhanes_current_screening import predict_artifact

        frame = pd.DataFrame([contracted_input], columns=loaded.manifest["features"])
        explanation = await asyncio.to_thread(
            safe_explanation,
            explain_today_with_reference,
            frame,
            lambda candidates: predict_artifact(loaded.artifact, candidates),
            model_version=output["model_version"],
            model_digest=loaded.manifest["artifact_sha256"],
            elevated=signal,
        )
        explanation = _release_explanation(explanation, operational=operational)
        return {
            "model_key": CURRENT_SCREENING_MODEL.model_key,
            "outcome_definition": CURRENT_SCREENING_MODEL.outcome_definition,
            "internal_score": output["risk_score_internal"],
            "risk_category": ("high" if signal else "low") if operational else None,
            "screening_signal_detected": signal if operational else None,
            "model_version": output["model_version"],
            "feature_schema_version": output["feature_schema_version"],
            "input_schema_version": CURRENT_SCREENING_MODEL.input_schema_version,
            "preprocessing_version": CURRENT_SCREENING_MODEL.preprocessing_version,
            "target_definition_version": CURRENT_SCREENING_MODEL.target_definition_version,
            "calibration_version": CURRENT_SCREENING_MODEL.calibration_version,
            "model_artifact_digest": loaded.manifest.get("artifact_sha256"),
            "threshold_version": output["threshold_version"],
            "decision_threshold": loaded.manifest.get("threshold") if operational else None,
            "promotion_status": "approved" if operational else "development_only",
            "output_status": "screening_not_diagnosis" if operational else "screening_model_pending_approval",
            "display_allowed": operational,
            "operational_model_activated": operational,
            "model_population": CURRENT_SCREENING_MODEL.model_population,
            "explanation": explanation,
            "explanation_status": explanation.get("status", "not_available"),
            "medical_notice": "현재 당뇨 관련 위험 신호 선별 결과이며 진단·처방이 아닙니다.",
        }

    raise ValueError(f"지원하지 않는 task_type입니다: {task_type}")
