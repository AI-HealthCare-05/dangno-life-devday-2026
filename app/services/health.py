from __future__ import annotations

from datetime import UTC, date, datetime
from math import log1p

from fastapi import HTTPException, status

from app.core import config
from app.dtos.health import (
    ConsentCreateRequest,
    CurrentScreeningInputCreateRequest,
    EligibilityCreateRequest,
    HealthCheckupCreateRequest,
)
from app.models.health import Consent, CurrentScreeningInput, EligibilityCheck, FollowUpAction, HealthCheckup
from app.models.users import Gender, User
from app.prediction.contracts import ACTIVE_MODEL, PredictionFeatures, input_schema_document
from app.repositories.health_repository import HealthRepository


def age_on(reference_date: date, birth_date: date) -> int:
    return (
        reference_date.year
        - birth_date.year
        - ((reference_date.month, reference_date.day) < (birth_date.month, birth_date.day))
    )


def eligibility_payload(item: EligibilityCheck) -> dict[str, object]:
    reason_codes = set(item.reason_codes)
    if 14 <= item.age < 19 and "UNDER_MINIMUM_SERVICE_AGE" in reason_codes:
        reason_codes.remove("UNDER_MINIMUM_SERVICE_AGE")
        reason_codes.add("CHALLENGE_ONLY_AGE")
    has_safety_blocker = bool({"URGENT_MEDICAL_ATTENTION", "DIAGNOSED_DIABETES"} & reason_codes)
    has_consent = "CONSENT_REQUIRED" not in reason_codes
    challenge_eligible = item.age >= 14 and has_consent and not has_safety_blocker
    current_health_check_eligible = item.age >= 19 and item.service_eligible and not has_safety_blocker
    return {
        "eligibility_check_id": item.id,
        "age": item.age,
        "has_diabetes_diagnosis": item.has_diabetes_diagnosis,
        "has_urgent_warning_sign": item.has_urgent_warning_sign,
        "population_in_scope": item.population_in_scope,
        "service_eligible": item.service_eligible,
        "challenge_eligible": challenge_eligible,
        "current_health_check_eligible": current_health_check_eligible,
        "future_prediction_eligible": item.model_eligible,
        "target_segment": item.target_segment,
        "model_eligible": item.model_eligible,
        "reason_codes": sorted(reason_codes),
        "next_action": item.next_action,
        "active_model": {
            "model_key": item.model_key,
            "version": item.model_version,
            "min_age": ACTIVE_MODEL.min_age,
            "max_age": ACTIVE_MODEL.max_age,
            "feature_schema_version": item.feature_schema_version,
            "threshold_version": item.threshold_version,
        },
        "safety_copy_version": item.safety_copy_version,
        "created_at": item.created_at,
    }


def eligibility_reason_codes(
    *,
    age: int,
    has_consent: bool,
    has_diabetes_diagnosis: bool,
    has_urgent_warning_sign: bool,
    population_in_scope: bool,
) -> list[str]:
    checks = (
        (age < 14, "UNDER_MINIMUM_SERVICE_AGE"),
        (14 <= age < 19, "CHALLENGE_ONLY_AGE"),
        (not has_consent, "CONSENT_REQUIRED"),
        (has_diabetes_diagnosis, "DIAGNOSED_DIABETES"),
        (has_urgent_warning_sign, "URGENT_MEDICAL_ATTENTION"),
        (
            age < ACTIVE_MODEL.min_age or (ACTIVE_MODEL.max_age is not None and age > ACTIVE_MODEL.max_age),
            "MODEL_AGE_OUT_OF_RANGE",
        ),
        (not population_in_scope, "MODEL_POPULATION_OUT_OF_SCOPE"),
    )
    return [code for condition, code in checks if condition]


def eligibility_next_action(
    request: EligibilityCreateRequest,
    *,
    model_eligible: bool,
    current_health_check_eligible: bool,
    challenge_eligible: bool,
) -> str:
    if request.has_urgent_warning_sign:
        return "urgent_medical_guidance"
    if request.has_diabetes_diagnosis:
        return "clinician_guidance"
    if model_eligible:
        return "health_checkup_input"
    if current_health_check_eligible:
        return "current_health_checkup_input"
    if challenge_eligible:
        return "challenge_selection"
    return "public_information"


class HealthService:
    def __init__(self) -> None:
        self.repo = HealthRepository()

    async def create_consent(self, user: User, request: ConsentCreateRequest) -> Consent:
        return await self.repo.create_consent(user_id=user.id, **request.model_dump())

    async def withdraw_consent(self, user: User, consent_id: int) -> Consent:
        consent = await self.repo.get_consent(consent_id, user.id)
        if consent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="동의 기록을 찾을 수 없습니다.")
        if consent.withdrawn_at is None:
            consent.is_agreed = False
            consent.withdrawn_at = datetime.now(UTC)
            await consent.save(update_fields=["is_agreed", "withdrawn_at", "updated_at"])
            await self.repo.stop_active_cycles(user.id, "CONSENT_WITHDRAWN")
        return consent

    async def create_current_screening_input(
        self, user: User, request: CurrentScreeningInputCreateRequest
    ) -> CurrentScreeningInput:
        if await self.repo.active_consent(user.id) is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CONSENT_REQUIRED")
        checkup = await self.repo.get_checkup(request.health_checkup_id, user.id)
        if checkup is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="건강정보 기록을 찾을 수 없습니다.")
        return await self.repo.create_current_screening_input(user_id=user.id, **request.model_dump())

    async def check_eligibility(self, user: User, request: EligibilityCreateRequest) -> EligibilityCheck:
        if user.birthday is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="적합성 확인 전에 건강정보 입력 단계에서 생년월일을 등록해 주세요.",
            )
        if request.birth_date is not None and request.birth_date != user.birthday:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="회원 프로필의 생년월일과 입력값이 다릅니다. 프로필을 먼저 수정해 주세요.",
            )
        age = age_on(date.today(), user.birthday)
        active_consent = await self.repo.active_consent(user.id)
        reason_codes = eligibility_reason_codes(
            age=age,
            has_consent=active_consent is not None,
            has_diabetes_diagnosis=request.has_diabetes_diagnosis,
            has_urgent_warning_sign=request.has_urgent_warning_sign,
            population_in_scope=request.population_in_scope,
        )

        has_consent = active_consent is not None
        service_eligible = age >= 19 and has_consent
        challenge_eligible = (
            age >= 14 and has_consent and not (request.has_diabetes_diagnosis or request.has_urgent_warning_sign)
        )
        current_health_check_eligible = service_eligible and not (
            request.has_diabetes_diagnosis or request.has_urgent_warning_sign
        )
        target_segment = (
            "full_prediction_45_plus" if age >= 45 else "current_signal_19_44" if age >= 19 else "challenge_only_14_18"
        )
        model_blockers = {
            "UNDER_MINIMUM_SERVICE_AGE",
            "CHALLENGE_ONLY_AGE",
            "CONSENT_REQUIRED",
            "DIAGNOSED_DIABETES",
            "URGENT_MEDICAL_ATTENTION",
            "MODEL_AGE_OUT_OF_RANGE",
            "MODEL_POPULATION_OUT_OF_SCOPE",
        }
        model_eligible = not any(code in model_blockers for code in reason_codes)
        next_action = eligibility_next_action(
            request,
            model_eligible=model_eligible,
            current_health_check_eligible=current_health_check_eligible,
            challenge_eligible=challenge_eligible,
        )

        item = await self.repo.create_eligibility(
            user_id=user.id,
            age=age,
            has_diabetes_diagnosis=request.has_diabetes_diagnosis,
            has_urgent_warning_sign=request.has_urgent_warning_sign,
            population_in_scope=request.population_in_scope,
            service_eligible=service_eligible,
            target_segment=target_segment,
            model_eligible=model_eligible,
            reason_codes=reason_codes,
            next_action=next_action,
            model_key=ACTIVE_MODEL.model_key,
            model_version=ACTIVE_MODEL.version,
            feature_schema_version=ACTIVE_MODEL.feature_schema_version,
            threshold_version=ACTIVE_MODEL.threshold_version,
            safety_copy_version=config.SAFETY_COPY_VERSION,
        )
        priority_code = next(
            (code for code in ("URGENT_MEDICAL_ATTENTION", "DIAGNOSED_DIABETES") if code in reason_codes), None
        )
        if priority_code is not None:
            existing_actions = await self.repo.list_follow_ups(user.id)
            has_same_open_action = any(
                action.reason_code == priority_code and action.acknowledged_at is None for action in existing_actions
            )
            if not has_same_open_action:
                await FollowUpAction.create(
                    user_id=user.id,
                    trigger_source="eligibility_check",
                    trigger_entity_id=item.id,
                    reason_code=priority_code,
                    safety_copy_version=config.SAFETY_COPY_VERSION,
                )
            await self.repo.stop_active_cycles(user.id, priority_code)
        return item

    async def create_checkup(self, user: User, request: HealthCheckupCreateRequest) -> HealthCheckup:
        consent = await self.repo.active_consent(user.id)
        eligibility = await self.repo.latest_eligibility(user.id)
        if consent is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="건강정보 처리 동의가 필요합니다.")
        if eligibility is None or not eligibility.service_eligible:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="현재 건강 신호를 확인할 수 있는 적합성 확인을 먼저 완료해 주세요.",
            )
        if eligibility.has_diabetes_diagnosis or eligibility.has_urgent_warning_sign:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="의료기관 안내를 먼저 확인해 주세요.")
        if request.feature_schema_version != ACTIVE_MODEL.feature_schema_version:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error_code": "FEATURE_SCHEMA_VERSION_MISMATCH",
                    "expected": ACTIVE_MODEL.feature_schema_version,
                },
            )
        if user.gender not in {Gender.FEMALE, Gender.MALE}:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"error_code": "ML_INPUT_MISSING", "message": "예측 전에 프로필 성별을 입력해 주세요."},
            )
        bmi = round(request.weight_kg / ((request.height_cm / 100) ** 2), 2)
        sex = "female" if user.gender == Gender.FEMALE else "male"
        if eligibility.model_eligible:
            PredictionFeatures(
                age=eligibility.age,
                bmi=bmi,
                sex=sex,
                log_household_income=(
                    log1p(request.annual_household_income_10k_krw)
                    if request.annual_household_income_10k_krw is not None
                    else None
                ),
                **request.model_dump(
                    exclude={
                        "checkup_type",
                        "checkup_date",
                        "height_cm",
                        "weight_kg",
                        "waist_cm",
                        "systolic_bp",
                        "diastolic_bp",
                        "self_rated_health",
                        "meal_count_yesterday",
                        "annual_household_income_10k_krw",
                        "feature_schema_version",
                    }
                ),
            )
        return await self.repo.create_checkup(
            user_id=user.id,
            eligibility_check_id=eligibility.id,
            age=eligibility.age,
            sex=sex,
            bmi=bmi,
            **request.model_dump(),
        )

    async def update_checkup(self, user: User, checkup_id: int, request: HealthCheckupCreateRequest) -> HealthCheckup:
        item = await self.repo.get_checkup(checkup_id, user.id)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="건강정보 기록을 찾을 수 없습니다.")
        if await self.repo.checkup_has_prediction(checkup_id, user.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error_code": "CHECKUP_ALREADY_PREDICTED",
                    "message": "예측에 사용된 건강정보는 수정할 수 없습니다. 재평가 기록을 새로 입력해 주세요.",
                },
            )
        if request.feature_schema_version != ACTIVE_MODEL.feature_schema_version:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "error_code": "FEATURE_SCHEMA_VERSION_MISMATCH",
                    "expected": ACTIVE_MODEL.feature_schema_version,
                },
            )
        bmi = round(request.weight_kg / ((request.height_cm / 100) ** 2), 2)
        if item.age >= ACTIVE_MODEL.min_age:
            PredictionFeatures(
                age=item.age,
                bmi=bmi,
                sex=item.sex,
                log_household_income=(
                    log1p(request.annual_household_income_10k_krw)
                    if request.annual_household_income_10k_krw is not None
                    else None
                ),
                **request.model_dump(
                    exclude={
                        "checkup_type",
                        "checkup_date",
                        "height_cm",
                        "weight_kg",
                        "waist_cm",
                        "systolic_bp",
                        "diastolic_bp",
                        "self_rated_health",
                        "meal_count_yesterday",
                        "annual_household_income_10k_krw",
                        "feature_schema_version",
                    }
                ),
            )
        for field, value in request.model_dump().items():
            setattr(item, field, value)
        item.bmi = bmi
        await item.save()
        return item

    @staticmethod
    def features_for(checkup: HealthCheckup) -> PredictionFeatures:
        if checkup.smoking_status is None or checkup.exercise_days_per_week is None or checkup.exercise_minutes is None:
            raise ValueError("기존 8변수 건강정보는 RF25 추론에 사용할 수 없습니다. 건강정보를 다시 입력해 주세요.")
        return PredictionFeatures(
            age=checkup.age,
            sex=checkup.sex,
            bmi=checkup.bmi,
            smoking_status=checkup.smoking_status,
            current_drinker=checkup.current_drinker,
            regular_exercise=checkup.regular_exercise,
            exercise_days_per_week=checkup.exercise_days_per_week,
            exercise_minutes=checkup.exercise_minutes,
            hypertension_diagnosis=checkup.hypertension_diagnosis,
            cancer_diagnosis=checkup.cancer_diagnosis,
            chronic_lung_disease_diagnosis=checkup.chronic_lung_disease_diagnosis,
            liver_disease_diagnosis=checkup.liver_disease_diagnosis,
            heart_disease_diagnosis=checkup.heart_disease_diagnosis,
            cerebrovascular_disease_diagnosis=checkup.cerebrovascular_disease_diagnosis,
            psychiatric_disease_diagnosis=checkup.psychiatric_disease_diagnosis,
            arthritis_rheumatism_diagnosis=checkup.arthritis_rheumatism_diagnosis,
            log_household_income=(
                log1p(checkup.annual_household_income_10k_krw)
                if checkup.annual_household_income_10k_krw is not None
                else None
            ),
            education_level=checkup.education_level,
            marital_status=checkup.marital_status,
            household_structure=checkup.household_structure,
            health_satisfaction_score=checkup.health_satisfaction_score,
            economic_satisfaction_score=checkup.economic_satisfaction_score,
            overall_quality_of_life_score=checkup.overall_quality_of_life_score,
            depressed_feeling_last_week=checkup.depressed_feeling_last_week,
            sleep_difficulty_last_week=checkup.sleep_difficulty_last_week,
        )

    @staticmethod
    def inference_payload(
        user: User,
        checkup: HealthCheckup,
        *,
        previously_diagnosed_diabetes: bool,
    ) -> dict[str, object]:
        """Build the raw RF25 API contract without persisting it in PredictionJob."""
        if user.birthday is None or user.gender not in {Gender.FEMALE, Gender.MALE}:
            raise ValueError("ML_INPUT_MISSING")
        if checkup.smoking_status is None or checkup.exercise_days_per_week is None or checkup.exercise_minutes is None:
            raise ValueError("ML_INPUT_MISSING")
        return {
            "birth_date": user.birthday.isoformat(),
            "sex": "female" if user.gender == Gender.FEMALE else "male",
            "height_cm": checkup.height_cm,
            "weight_kg": checkup.weight_kg,
            "smoking_status": checkup.smoking_status,
            "current_drinker": checkup.current_drinker,
            "regular_exercise": checkup.regular_exercise,
            "exercise_days_per_week": checkup.exercise_days_per_week,
            "exercise_minutes": checkup.exercise_minutes,
            "previously_diagnosed_diabetes": previously_diagnosed_diabetes,
            "annual_household_income_10k_krw": checkup.annual_household_income_10k_krw,
            "health_satisfaction_score": checkup.health_satisfaction_score,
            "economic_satisfaction_score": checkup.economic_satisfaction_score,
            "overall_quality_of_life_score": checkup.overall_quality_of_life_score,
            "hypertension_diagnosis": checkup.hypertension_diagnosis,
            "cancer_diagnosis": checkup.cancer_diagnosis,
            "chronic_lung_disease_diagnosis": checkup.chronic_lung_disease_diagnosis,
            "liver_disease_diagnosis": checkup.liver_disease_diagnosis,
            "heart_disease_diagnosis": checkup.heart_disease_diagnosis,
            "cerebrovascular_disease_diagnosis": checkup.cerebrovascular_disease_diagnosis,
            "psychiatric_disease_diagnosis": checkup.psychiatric_disease_diagnosis,
            "arthritis_rheumatism_diagnosis": checkup.arthritis_rheumatism_diagnosis,
            "education_level": checkup.education_level,
            "marital_status": checkup.marital_status,
            "household_structure": checkup.household_structure,
            "depressed_feeling_last_week": checkup.depressed_feeling_last_week,
            "sleep_difficulty_last_week": checkup.sleep_difficulty_last_week,
        }

    @staticmethod
    def current_screening_payload(
        checkup: HealthCheckup,
        screening_input: CurrentScreeningInput | None = None,
    ) -> dict[str, object | None]:
        """Map stored user inputs to the KNHANES screening contract.

        Fields not collected by the MVP remain missing and are handled by the
        fitted preprocessing pipeline. They are never guessed from unrelated
        user attributes.
        """
        return {
            "age": checkup.age,
            "height_cm": checkup.height_cm,
            "weight_kg": checkup.weight_kg,
            "waist_cm": checkup.waist_cm,
            "bmi": checkup.bmi,
            "walking_days": (
                screening_input.walking_days if screening_input is not None else checkup.exercise_days_per_week
            ),
            "energy_kcal": screening_input.energy_kcal if screening_input is not None else None,
            "protein_g": screening_input.protein_g if screening_input is not None else None,
            "fat_g": screening_input.fat_g if screening_input is not None else None,
            "carbohydrate_g": screening_input.carbohydrate_g if screening_input is not None else None,
            "sodium_mg": screening_input.sodium_mg if screening_input is not None else None,
            "sex": 1 if checkup.sex == "male" else 2,
            "region": screening_input.region if screening_input is not None else None,
            "urban": screening_input.urban if screening_input is not None else None,
            "education": (None if checkup.education_level in {None, "code_97"} else int(checkup.education_level[-1])),
            "income_quartile": None,
            "household_income_quartile": None,
            "hypertension_family_history": (
                screening_input.hypertension_family_history if screening_input is not None else None
            ),
            "diabetes_family_history": (
                screening_input.diabetes_family_history if screening_input is not None else None
            ),
            "current_smoker": checkup.current_smoker,
            "alcohol_frequency": screening_input.alcohol_frequency if screening_input is not None else None,
            "aerobic_activity": checkup.regular_exercise,
            "systolic_bp": getattr(checkup, "systolic_bp", None),
            "diastolic_bp": getattr(checkup, "diastolic_bp", None),
        }

    @staticmethod
    def input_schema() -> dict[str, object]:
        return input_schema_document()
