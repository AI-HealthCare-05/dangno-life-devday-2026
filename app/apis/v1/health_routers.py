from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.apis.responses import envelope
from app.dependencies.security import get_request_user
from app.dtos.health import (
    ConsentCreateRequest,
    CurrentScreeningInputCreateRequest,
    EligibilityCreateRequest,
    HealthCheckupCreateRequest,
    HealthInputRewardClaimRequest,
)
from app.models.users import User
from app.repositories.health_repository import HealthRepository
from app.services.health import HealthService, eligibility_payload
from app.services.health_diagnosis import (
    DIAGNOSIS_BLOCK_CODE,
    attach_diagnosis_context,
    delete_diagnosis_record,
    diagnosis_records,
)
from app.services.health_input_rewards import HealthInputRewardService

health_router = APIRouter(tags=["Health domain"])


@health_router.get("/health-input-rewards")
async def health_input_reward_status(user: Annotated[User, Depends(get_request_user)]) -> dict[str, object]:
    return envelope(await HealthInputRewardService().status(user))


@health_router.post("/health-input-rewards/claim")
async def claim_health_input_rewards(
    request: HealthInputRewardClaimRequest,
    user: Annotated[User, Depends(get_request_user)],
) -> dict[str, object]:
    return envelope(await HealthInputRewardService().claim(user, request))


@health_router.get("/consents")
async def list_consents(user: Annotated[User, Depends(get_request_user)]) -> dict[str, object]:
    items = await HealthRepository().list_consents(user.id)
    return envelope(
        {
            "items": [
                {
                    "consent_id": item.id,
                    "consent_item": item.consent_item,
                    "version": item.version,
                    "is_agreed": item.is_agreed,
                    "agreed_at": item.agreed_at,
                    "withdrawn_at": item.withdrawn_at,
                }
                for item in items
            ]
        }
    )


@health_router.post("/consents", status_code=status.HTTP_201_CREATED)
async def create_consent(
    request: ConsentCreateRequest,
    user: Annotated[User, Depends(get_request_user)],
) -> dict[str, object]:
    item = await HealthService().create_consent(user, request)
    return envelope(
        {
            "consent_id": item.id,
            "consent_item": item.consent_item,
            "version": item.version,
            "is_agreed": item.is_agreed,
            "agreed_at": item.agreed_at,
        }
    )


@health_router.patch("/consents/{consent_id}/withdraw")
async def withdraw_consent(
    consent_id: int,
    user: Annotated[User, Depends(get_request_user)],
) -> dict[str, object]:
    item = await HealthService().withdraw_consent(user, consent_id)
    return envelope({"consent_id": item.id, "is_agreed": item.is_agreed, "withdrawn_at": item.withdrawn_at})


@health_router.post("/eligibility-checks")
async def check_eligibility(
    request: EligibilityCreateRequest,
    user: Annotated[User, Depends(get_request_user)],
) -> dict[str, object]:
    item = await HealthService().check_eligibility(user, request)
    return envelope(eligibility_payload(item))


@health_router.get("/eligibility-checks/latest")
async def latest_eligibility(user: Annotated[User, Depends(get_request_user)]) -> dict[str, object]:
    item = await HealthRepository().latest_eligibility(user.id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="적합성 확인 기록을 찾을 수 없습니다.")
    await attach_diagnosis_context(item)
    return envelope(eligibility_payload(item))


@health_router.get("/health-checkups/input-schema")
async def health_input_schema() -> dict[str, object]:
    return envelope(HealthService.input_schema())


@health_router.post("/current-screening-inputs", status_code=status.HTTP_201_CREATED)
async def create_current_screening_input(
    request: CurrentScreeningInputCreateRequest,
    user: Annotated[User, Depends(get_request_user)],
) -> dict[str, object]:
    item = await HealthService().create_current_screening_input(user, request)
    return envelope(
        {
            "current_screening_input_id": item.id,
            "health_checkup_id": item.health_checkup_id,
            "input_as_of_date": item.input_as_of_date,
            "created_at": item.created_at,
        }
    )


@health_router.post("/health-checkups", status_code=status.HTTP_201_CREATED)
async def create_health_checkup(
    request: HealthCheckupCreateRequest,
    user: Annotated[User, Depends(get_request_user)],
) -> dict[str, object]:
    item = await HealthService().create_checkup(user, request)
    return envelope(
        {
            "checkup_id": item.id,
            "bmi": item.bmi,
            "feature_schema_version": item.feature_schema_version,
            "created_at": item.created_at,
            "validation": {"status": "valid", "validated_at": datetime.now(UTC)},
        }
    )


def checkup_payload(item: object, diagnosis_dates: set[str] | None = None) -> dict[str, object]:
    blocked = item.checkup_date.isoformat() in (diagnosis_dates or set())
    return {
        "record_type": "health_checkup",
        "analysis_allowed": not blocked,
        "prediction_allowed": not blocked,
        "analysis_block_reason": DIAGNOSIS_BLOCK_CODE if blocked else None,
        "checkup_id": item.id,
        "checkup_type": item.checkup_type,
        "checkup_date": item.checkup_date,
        "height_cm": item.height_cm,
        "weight_kg": item.weight_kg,
        "bmi": item.bmi,
        "waist_cm": item.waist_cm,
        "systolic_bp": item.systolic_bp,
        "diastolic_bp": item.diastolic_bp,
        "self_rated_health": item.self_rated_health,
        "meal_count_yesterday": item.meal_count_yesterday,
        "regular_exercise": item.regular_exercise,
        "smoking_status": item.smoking_status,
        "current_drinker": item.current_drinker,
        "exercise_days_per_week": item.exercise_days_per_week,
        "exercise_minutes": item.exercise_minutes,
        "annual_household_income_10k_krw": item.annual_household_income_10k_krw,
        "health_satisfaction_score": item.health_satisfaction_score,
        "economic_satisfaction_score": item.economic_satisfaction_score,
        "overall_quality_of_life_score": item.overall_quality_of_life_score,
        "hypertension_diagnosis": item.hypertension_diagnosis,
        "cancer_diagnosis": item.cancer_diagnosis,
        "chronic_lung_disease_diagnosis": item.chronic_lung_disease_diagnosis,
        "liver_disease_diagnosis": item.liver_disease_diagnosis,
        "heart_disease_diagnosis": item.heart_disease_diagnosis,
        "cerebrovascular_disease_diagnosis": item.cerebrovascular_disease_diagnosis,
        "psychiatric_disease_diagnosis": item.psychiatric_disease_diagnosis,
        "arthritis_rheumatism_diagnosis": item.arthritis_rheumatism_diagnosis,
        "education_level": item.education_level,
        "marital_status": item.marital_status,
        "household_structure": item.household_structure,
        "depressed_feeling_last_week": item.depressed_feeling_last_week,
        "sleep_difficulty_last_week": item.sleep_difficulty_last_week,
        "feature_schema_version": item.feature_schema_version,
        "created_at": item.created_at,
    }


@health_router.get("/health-checkups")
async def list_health_checkups(user: Annotated[User, Depends(get_request_user)]) -> dict[str, object]:
    items = await HealthRepository().list_checkups(user.id)
    diagnoses = await diagnosis_records(user.id)
    dates = {item["record_date"] for item in diagnoses}
    return envelope({"items": [checkup_payload(item, dates) for item in items], "diagnosis_records": diagnoses})


@health_router.get("/diagnosis-records")
async def list_diagnosis_records(user: Annotated[User, Depends(get_request_user)]) -> dict[str, object]:
    return envelope({"items": await diagnosis_records(user.id)})


@health_router.delete("/diagnosis-records/{record_id}")
async def remove_diagnosis_record(record_id: int, user: Annotated[User, Depends(get_request_user)]) -> dict[str, object]:
    return envelope(await delete_diagnosis_record(user.id, record_id))


@health_router.get("/health-checkups/{checkup_id}")
async def get_health_checkup(
    checkup_id: int,
    user: Annotated[User, Depends(get_request_user)],
) -> dict[str, object]:
    item = await HealthRepository().get_checkup(checkup_id, user.id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="건강정보 기록을 찾을 수 없습니다.")
    dates = {record["record_date"] for record in await diagnosis_records(user.id)}
    return envelope(checkup_payload(item, dates))


@health_router.patch("/health-checkups/{checkup_id}")
async def update_health_checkup(
    checkup_id: int,
    request: HealthCheckupCreateRequest,
    user: Annotated[User, Depends(get_request_user)],
) -> dict[str, object]:
    item = await HealthService().update_checkup(user, checkup_id, request)
    return envelope(checkup_payload(item))


@health_router.delete("/health-checkups/{checkup_id}", status_code=status.HTTP_200_OK)
async def delete_health_checkup(
    checkup_id: int,
    user: Annotated[User, Depends(get_request_user)],
) -> dict[str, object]:
    deleted = await HealthRepository().delete_checkup(checkup_id, user.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="건강정보 기록을 찾을 수 없습니다.")
    return envelope({"checkup_id": checkup_id, "deleted": True})
