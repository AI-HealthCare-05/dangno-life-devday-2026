"""One account reward per saved optional field; never store its health value in the ledger."""

from dataclasses import dataclass

from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError
from tortoise.transactions import in_transaction

from app.dtos.health import CurrentScreeningInputCreateRequest, HealthCheckupCreateRequest
from app.models.game import RewardTransaction
from app.models.health import Consent, CurrentScreeningInput, HealthCheckup
from app.repositories.forest_repository import ForestRepository
from app.repositories.game_repository import GameRepository
from app.services.forest_wallet import ForestWalletService

CARROTS_PER_FIELD = 100
SOURCE = "optional_health_input"


@dataclass(frozen=True)
class OptionalField:
    key: str
    input_id: str
    label: str
    current_input: bool = False

    def known(self, checkup, current):
        record = current if self.current_input else checkup
        attribute = self.key
        schema = CurrentScreeningInputCreateRequest if self.current_input else HealthCheckupCreateRequest
        value = getattr(record, attribute, None)
        # Education is shared by both models and earns one reward, even when
        # the current-model snapshot is the only place that contains its answer.
        if self.key == "education_level" and value is None and current is not None:
            value, attribute, schema = current.education, "education", CurrentScreeningInputCreateRequest
        if value is None or value == "code_97":
            return False
        if self.key in {"systolic_bp", "diastolic_bp"}:
            if checkup.systolic_bp is not None and checkup.diastolic_bp is not None:
                if checkup.systolic_bp <= checkup.diastolic_bp:
                    return False
        if self.key == "region" and isinstance(value, str):
            if not value.isdigit():
                return False
            value = int(value)
        try:
            TypeAdapter(schema.model_fields[attribute].rebuild_annotation()).validate_python(value, strict=True)
        except (ValidationError, ValueError, TypeError):
            return False
        return True  # False and numeric zero are known answers, not missing data.


FIELDS = (
    OptionalField("waist_cm", "waist", "허리둘레"),
    OptionalField("systolic_bp", "systolic", "수축기혈압"),
    OptionalField("diastolic_bp", "diastolic", "이완기혈압"),
    OptionalField("health_satisfaction_score", "health-satisfaction-score", "건강 만족도"),
    OptionalField("economic_satisfaction_score", "economic-satisfaction-score", "경제 만족도"),
    OptionalField("overall_quality_of_life_score", "overall-quality-of-life-score", "삶의 질"),
    OptionalField("cancer_diagnosis", "cancer-diagnosis", "암 진단 여부"),
    OptionalField("chronic_lung_disease_diagnosis", "chronic-lung-disease-diagnosis", "만성 폐질환 진단 여부"),
    OptionalField("liver_disease_diagnosis", "liver-disease-diagnosis", "간질환 진단 여부"),
    OptionalField("cerebrovascular_disease_diagnosis", "cerebrovascular-disease-diagnosis", "뇌혈관질환 진단 여부"),
    OptionalField("psychiatric_disease_diagnosis", "psychiatric-disease-diagnosis", "정신과 질환 진단 여부"),
    OptionalField("diabetes_family_history", "diabetes-family-history", "당뇨 가족력", True),
    OptionalField("hypertension_family_history", "hypertension-family-history", "고혈압 가족력", True),
    OptionalField("education_level", "education-level", "최종 학력"),
    OptionalField("region", "region", "거주 지역", True),
    OptionalField("household_structure", "household-structure", "가구 형태"),
    OptionalField("annual_household_income_10k_krw", "annual-household-income", "연간 가구소득"),
)


def receipt_key(user_id, key):
    return f"optional-health:{user_id}:{key}"


class HealthInputRewardService:
    async def status(self, user):
        claimed = set(
            await RewardTransaction.filter(
                user_id=user.id, idempotency_key__in=[receipt_key(user.id, field.key) for field in FIELDS]
            ).values_list("idempotency_key", flat=True)
        )
        return {
            "user_id": user.id,
            "carrots_per_field": CARROTS_PER_FIELD,
            "fields": [
                {
                    "key": field.key,
                    "input_id": field.input_id,
                    "label": field.label,
                    "claimed": receipt_key(user.id, field.key) in claimed,
                }
                for field in FIELDS
            ],
        }

    async def claim(self, user, request):
        granted = []
        async with in_transaction() as connection:
            consent = (
                await Consent.filter(user_id=user.id, is_agreed=True, withdrawn_at=None)
                .using_db(connection)
                .select_for_update()
                .order_by("-agreed_at")
                .first()
            )
            if consent is None:
                raise HTTPException(403, "건강정보 처리 동의가 필요합니다.")
            checkup = (
                await HealthCheckup.filter(id=request.checkup_id, user_id=user.id)
                .using_db(connection)
                .select_for_update()
                .first()
            )
            if checkup is None:
                raise HTTPException(404, "건강정보 기록을 찾을 수 없습니다.")
            inputs = CurrentScreeningInput.filter(health_checkup_id=checkup.id, user_id=user.id)
            if request.current_screening_input_id is not None:
                inputs = inputs.filter(id=request.current_screening_input_id)
            current = await inputs.using_db(connection).select_for_update().order_by("-id").first()
            if request.current_screening_input_id is not None and current is None:
                raise HTTPException(404, "저장된 현재 건강정보를 찾을 수 없습니다.")
            eligible = [field for field in FIELDS if field.known(checkup, current)]
            await ForestRepository().avatar(user)
            for field in eligible:
                transaction, created = await GameRepository().credit(
                    user.id,
                    CARROTS_PER_FIELD,
                    SOURCE,
                    f"{checkup.id}:{field.key}",
                    receipt_key(user.id, field.key),
                    using_db=connection,
                )
                if created:
                    granted.append({"key": field.key, "label": field.label, "amount": transaction.amount})
            # A lost response may follow a successful commit. This stable total
            # lets a retry confirm the original grant without paying it again.
            checkup_receipts = (
                await RewardTransaction.filter(
                    user_id=user.id, source_type=SOURCE, source_ref__startswith=f"{checkup.id}:"
                )
                .using_db(connection)
                .select_for_update()
            )
            checkup_total = sum(row.amount for row in checkup_receipts)
        return {
            **await ForestWalletService().snapshot(user),
            "checkup_id": checkup.id,
            "earned_carrots": sum(field["amount"] for field in granted),
            "carrots_per_field": CARROTS_PER_FIELD,
            "rewarded_fields": granted,
            "eligible_fields": [field.key for field in eligible],
            "checkup_reward_carrots": checkup_total,
            "already_claimed_fields": [field.key for field in eligible if field.key not in {f["key"] for f in granted}],
        }
