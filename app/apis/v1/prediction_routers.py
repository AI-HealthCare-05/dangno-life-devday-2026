from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.apis.responses import envelope
from app.core import config
from app.dependencies.security import get_request_user
from app.dtos.ai_jobs import prediction_job_response
from app.dtos.health import PredictionJobCreateRequest
from app.models.health import Prediction, PredictionRiskCurvePoint
from app.models.model_registry import ModelRegistry
from app.models.prediction_jobs import PredictionJob
from app.models.users import User
from app.prediction.contracts import ACTIVE_MODEL, CURRENT_SCREENING_MODEL, CURRENT_SCREENING_MODEL_KEY
from app.prediction.errors import ModelNotReadyError, classify_ml_input_error
from app.repositories.health_repository import HealthRepository
from app.services.ai_jobs import create_prediction_job, get_prediction_job
from app.services.xai_presentation import input_label, model_analysis_payload, shap_graph_payload

prediction_router = APIRouter(tags=["Prediction"])

# ML artifacts retain the historical internal value ``caution``.  The v5.6
# public API contract uses low/moderate/high and the Korean UI label remains
# 낮음/주의/높음.  Convert only at the public boundary so an old persisted row
# and a newly computed row serialize identically.
RISK_LABELS = {"low": "낮음", "moderate": "주의", "high": "높음"}


def public_risk_category(value: str | None) -> str | None:
    return "moderate" if value == "caution" else value


PUBLIC_DISCLAIMER = "이 결과는 당뇨병 진단이 아닌 미래 발병 위험 선별 및 건강교육 정보입니다."
DEVELOPMENT_DISCLAIMER = (
    "개발용 추론 연결은 완료되었지만 검토된 임계값이 없어 개인 위험 범주와 확률을 제공하지 않습니다."
)


@prediction_router.get("/models/active")
async def active_models(model_key: str | None = None) -> dict[str, object]:
    if model_key == CURRENT_SCREENING_MODEL_KEY:
        return envelope(
            {
                "items": [
                    {
                        **CURRENT_SCREENING_MODEL.model_dump(),
                        "threshold_approved": CURRENT_SCREENING_MODEL.threshold_is_approved,
                        "public_result_available": CURRENT_SCREENING_MODEL.threshold_is_approved,
                        "artifact_status": (
                            "digest_declared" if CURRENT_SCREENING_MODEL.model_artifact_digest else "not_configured"
                        ),
                    }
                ]
            }
        )
    if model_key is None or model_key == ACTIVE_MODEL.model_key:
        return envelope(
            {
                "items": [
                    {
                        **ACTIVE_MODEL.model_dump(),
                        "threshold_approved": ACTIVE_MODEL.threshold_is_approved,
                        "public_result_available": ACTIVE_MODEL.threshold_is_approved,
                        "artifact_status": "digest_declared"
                        if ACTIVE_MODEL.model_artifact_digest
                        else "not_configured",
                    }
                ]
            }
        )
    # diabetes_lifetime_risk 등 ACTIVE_MODEL(정적 상수) 밖의 model_key는 DB 기반
    # ModelRegistry에서만 조회한다 — 아직 승인된 모델이 없으면 빈 목록을 반환한다
    # (미등록 모델을 있는 것처럼 응답하지 않기 위함).
    registry_entry = await ModelRegistry.active_for(model_key)
    if registry_entry is None:
        return envelope({"items": []})
    return envelope(
        {
            "items": [
                {
                    "model_key": registry_entry.model_key,
                    "version": registry_entry.model_version,
                    "model_type": registry_entry.model_type,
                    "promotion_status": registry_entry.promotion_status,
                    "feature_schema_version": registry_entry.feature_schema_version,
                    "target_definition_version": registry_entry.target_definition_version,
                    "calibration_version": registry_entry.calibration_version,
                    "threshold_version": registry_entry.threshold_version,
                    "min_age": registry_entry.min_age,
                    "max_age": registry_entry.max_age,
                    "model_population": registry_entry.model_population,
                    "outcome_definition": registry_entry.outcome_definition,
                    "threshold_approved": registry_entry.promotion_status == "approved",
                    "public_result_available": registry_entry.promotion_status == "approved",
                    "artifact_status": "verified" if registry_entry.artifact_sha256 else "not_configured",
                }
            ]
        }
    )


@prediction_router.post("/prediction-jobs", status_code=status.HTTP_202_ACCEPTED)
async def enqueue_prediction_job(
    request: PredictionJobCreateRequest,
    user: Annotated[User, Depends(get_request_user)],
) -> dict[str, object]:
    try:
        job = await create_prediction_job(user, request)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error_code": str(exc), "message": "현재 상태에서는 예측 작업을 생성할 수 없습니다."},
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error_code": classify_ml_input_error(exc),
                "message": "모델 입력 계약을 확인해 주세요.",
                "retryable": False,
            },
        ) from exc
    except ModelNotReadyError as exc:
        # ModelNotReadyError는 RuntimeError의 서브클래스이므로 반드시 아래 일반
        # RuntimeError 처리보다 먼저 잡아야 한다.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error_code": "MODEL_NOT_READY", "message": str(exc), "retryable": False},
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    data = prediction_job_response(job).model_dump()
    data["status_url"] = f"/api/v1/prediction-jobs/{job.job_id}"
    return envelope(data)


@prediction_router.get("/prediction-jobs/{job_id}")
async def read_prediction_job(
    job_id: str,
    user: Annotated[User, Depends(get_request_user)],
) -> dict[str, object]:
    job = await get_prediction_job(job_id, user.id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="예측 작업을 찾을 수 없습니다.")
    return envelope(prediction_job_response(job).model_dump())


def prediction_payload(item: Prediction) -> dict[str, object]:
    public_result_available = (
        item.result_status == "approved"
        and item.threshold_version != "unapproved"
        and item.decision_threshold is not None
        and getattr(item, "operational_model_activated", False) is True
        and getattr(item, "display_allowed", False) is True
    )
    promotion_status = "approved" if public_result_available else "development_only"
    public_category = public_risk_category(item.risk_category) if public_result_available else None
    local_preview_available = (
        config.ENV.value == "local"
        and getattr(item, "preview_only", False) is True
        and getattr(item, "display_allowed", False) is False
        and getattr(item, "operational_model_activated", False) is False
        and public_risk_category(getattr(item, "preview_signal_level", None)) in RISK_LABELS
    )
    is_current_screening = item.model_key == CURRENT_SCREENING_MODEL_KEY
    screening_signal = public_category == "high" if is_current_screening and public_category else None
    return {
        "prediction_id": item.id,
        "checkup_id": item.health_checkup_id,
        "input_as_of_date": item.input_as_of_date,
        "model_key": item.model_key,
        "prediction_type": "current_screening" if is_current_screening else "future_incidence",
        "task_type": getattr(item, "task_type", None),
        "threshold_scope": getattr(item, "threshold_scope", None),
        "outcome_definition": item.outcome_definition,
        "result_status": item.result_status,
        "promotion_status": promotion_status,
        "risk_category": public_category,
        "risk_category_label": RISK_LABELS.get(public_category) if public_category else None,
        "preview_signal_level": public_risk_category(getattr(item, "preview_signal_level", None))
        if local_preview_available
        else None,
        "preview_signal_label": RISK_LABELS.get(public_risk_category(getattr(item, "preview_signal_level", None)))
        if local_preview_available
        else None,
        "preview_only": local_preview_available,
        "display_allowed": getattr(item, "display_allowed", True) if public_result_available else False,
        "operational_model_activated": getattr(item, "operational_model_activated", True)
        if public_result_available
        else False,
        "screening_signal_detected": screening_signal,
        "screening_result_label": ("검사 권고" if screening_signal else "현재 위험 신호 낮음")
        if screening_signal is not None
        else None,
        "model_version": item.model_version,
        "feature_schema_version": item.feature_schema_version,
        "input_schema_version": item.input_schema_version,
        "preprocessing_version": item.preprocessing_version,
        "target_definition_version": item.target_definition_version,
        "calibration_version": item.calibration_version,
        "model_artifact_digest": item.model_artifact_digest,
        "threshold_version": item.threshold_version,
        "decision_threshold": item.decision_threshold if public_result_available else None,
        "output_status": item.output_status,
        "model_population": item.model_population,
        "predicted_at": item.predicted_at,
        "disclaimer": (
            "현재 당뇨 관련 위험 신호를 선별하는 건강교육용 결과이며 진단이 아닙니다."
            if is_current_screening and public_category
            else PUBLIC_DISCLAIMER
            if public_category
            else DEVELOPMENT_DISCLAIMER
        ),
        "age_risk_forecast": item.age_risk_forecast if public_result_available or local_preview_available else None,
        "raw_probability_exposed": False,
        "model_analysis": model_analysis_payload(item, approved=public_result_available),
    }


@prediction_router.get("/predictions/latest")
async def latest_prediction(user: Annotated[User, Depends(get_request_user)]) -> dict[str, object]:
    item = await HealthRepository().latest_prediction(user.id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="예측 결과를 찾을 수 없습니다.")
    return envelope(prediction_payload(item))


@prediction_router.get("/predictions")
async def list_predictions(user: Annotated[User, Depends(get_request_user)]) -> dict[str, object]:
    items = await HealthRepository().list_predictions(user.id)
    return envelope({"items": [prediction_payload(item) for item in items]})


@prediction_router.get("/predictions/changes")
async def prediction_changes(user: Annotated[User, Depends(get_request_user)]) -> dict[str, object]:
    items = await HealthRepository().list_predictions(user.id)
    if len(items) < 2:
        return envelope({"available": False, "first": None, "latest": None, "change": None})
    latest = items[0]
    first = next(
        (
            item
            for item in reversed(items)
            if item.model_key == latest.model_key and item.outcome_definition == latest.outcome_definition
        ),
        None,
    )
    if first is None or first.id == latest.id:
        return envelope({"available": False, "first": None, "latest": None, "change": None})
    return envelope(
        {
            "available": True,
            "first": prediction_payload(first),
            "latest": prediction_payload(latest),
            "change": None,
            "notice": "예측 변화는 진단이나 치료 효과를 의미하지 않습니다.",
        }
    )


@prediction_router.get("/predictions/{prediction_id}")
async def read_prediction(
    prediction_id: int,
    user: Annotated[User, Depends(get_request_user)],
) -> dict[str, object]:
    item = await HealthRepository().get_prediction(prediction_id, user.id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="예측 결과를 찾을 수 없습니다.")
    return envelope(prediction_payload(item))


def _risk_curve_summary(points: list[PredictionRiskCurvePoint]) -> dict[str, float | None] | None:
    """Provisional +2/+5/+10-year lookup relative to the curve's first (current-age) point.

    TODO: confirm against the final API-LIFE-004 spec once 양준혁 delivers the
    survival-model output contract — this nearest-age approximation may need
    to change to an exact-age lookup or interpolation.
    """
    if not points:
        return None
    base_age = points[0].age
    by_age = {p.age: p.cumulative_risk for p in points}

    def nearest(target_age: int) -> float | None:
        if not by_age:
            return None
        closest = min(by_age, key=lambda age: abs(age - target_age))
        return by_age[closest]

    return {
        "risk_2y": nearest(base_age + 2),
        "risk_5y": nearest(base_age + 5),
        "risk_10y": nearest(base_age + 10),
    }


@prediction_router.get("/predictions/{prediction_id}/risk-curve")
async def read_risk_curve(
    prediction_id: int,
    user: Annotated[User, Depends(get_request_user)],
) -> dict[str, object]:
    """API-LIFE-004: 연령별 당뇨 위험 전망(생존곡선) 조회.

    risk_curve_status가 "available"이 아니면(현재는 생존모델이 없어 항상
    "not_applicable") 빈 결과와 상태만 반환한다 — 검증되지 않은 곡선을 있는
    것처럼 노출하지 않기 위함이다.
    """
    repo = HealthRepository()
    item = await repo.get_prediction(prediction_id, user.id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="예측 결과를 찾을 수 없습니다.")
    if item.risk_curve_status != "available":
        return envelope(
            {
                "prediction_id": item.id,
                "status": item.risk_curve_status,
                "points": [],
                "summary": None,
                "message": "연령별 위험 전망은 승인된 생존모델 결과가 준비된 이후에만 제공됩니다.",
            }
        )
    points = await repo.risk_curve_points(item.id)
    return envelope(
        {
            "prediction_id": item.id,
            "status": item.risk_curve_status,
            "model_key": item.model_key,
            "output_definition_version": item.output_definition_version,
            "points": [
                {"age": p.age, "cumulative_risk": p.cumulative_risk, "lower": p.lower, "upper": p.upper} for p in points
            ],
            "summary": _risk_curve_summary(points),
            "disclaimer": "이 전망은 별도의 생존모델이 아니라 동일 모델을 연령만 다르게 반복 계산한 근사 추정치이며, 개인의 확정된 미래를 의미하지 않습니다.",
        }
    )


@prediction_router.get("/predictions/{prediction_id}/risk-factors")
async def read_risk_factors(
    prediction_id: int,
    user: Annotated[User, Depends(get_request_user)],
) -> dict[str, object]:
    item = await HealthRepository().get_prediction(prediction_id, user.id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="예측 결과를 찾을 수 없습니다.")
    approved = (
        item.display_allowed is True
        and item.operational_model_activated is True
        and item.explanation_status == "approved"
    )
    factors = await HealthRepository().risk_factors(item.id) if approved else []
    job = await PredictionJob.get_or_none(job_id=item.job_id, user_id=user.id) if approved else None
    explanation = (job.result or {}).get("explanation", {}) if job else {}
    contract_valid = (
        approved
        and explanation.get("status") == "approved"
        and explanation.get("display_allowed") is True
        and explanation.get("shap_claimed") is True
        and explanation.get("additivity_verified") is True
        and bool(factors)
    )
    if not contract_valid:
        return envelope(
            {
                "prediction_id": item.id,
                "status": item.explanation_status,
                "method": None,
                "explanation_version": None,
                "output_space": None,
                "additive_to_score": None,
                "reference_value": None,
                "items": [],
                "message": "검증된 설명 방법이 준비되기 전에는 위험·보호 요인을 표시하지 않습니다.",
                "shap_claimed": False,
                "display_allowed": False,
            }
        )
    contributions = {factor["feature"]: factor["contribution"] for factor in explanation["items"]}
    repository = HealthRepository()
    checkup = await repository.get_checkup(item.health_checkup_id, user.id)
    screening_id = (job.request_payload or {}).get("current_screening_input_id")
    screening = await repository.get_current_screening_input(screening_id, user.id) if screening_id else None
    return envelope(
        {
            "prediction_id": item.id,
            "status": "approved",
            "method": explanation["method"],
            "explanation_version": explanation["explanation_version"],
            "model_version": explanation["model_version"],
            "output_space": explanation["output_space"],
            "additive_to_score": explanation["additive_to_score"],
            "additivity_verified": explanation["additivity_verified"],
            "reference_value": explanation["reference_value"],
            "selection_policy": explanation["selection_policy"],
            "selection_status": explanation["selection_status"],
            "baseline_label": explanation.get("baseline_label")
            or (
                "학습 자료에 기록된 트리 분포 기준"
                if explanation["method"] == "treeshap_tree_path_dependent_v1"
                else "입력 정보가 비어 있는 상태 기준 (이전 계산 방식)"
                if explanation["method"] == "exact_grouped_shap_missing_reference_v1"
                else "모델의 저장된 비교 기준"
            ),
            "reference_version": explanation.get("reference_version"),
            "shap_graph": shap_graph_payload(explanation),
            "items": [
                {
                    "factor_name": factor.factor_name,
                    "display_name": factor.display_name,
                    "direction": factor.impact_direction,
                    "input_value_label": input_label(factor.factor_name, checkup, screening),
                    "contribution": contributions.get(factor.factor_name),
                    "absolute_contribution": factor.importance_score,
                    "modifiable": factor.is_modifiable,
                    "message": "비교 기준에 따른 모델의 계산 결과이며, 건강습관 변경의 효과를 뜻하지 않습니다.",
                    "display_order": factor.display_order,
                }
                for factor in factors
            ],
            "message": "각 요인은 다른 입력과 함께 계산된 모델 설명이며 원인이나 진단을 뜻하지 않습니다.",
            "shap_claimed": True,
            "display_allowed": True,
        }
    )
