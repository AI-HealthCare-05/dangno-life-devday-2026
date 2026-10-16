from __future__ import annotations

from datetime import date, datetime
from typing import Any

from tortoise.transactions import in_transaction

from app.models.health import (
    Challenge,
    ChallengeCycle,
    ChallengeLog,
    ChallengeVerification,
    ChallengeVerificationEvent,
    Consent,
    CurrentScreeningInput,
    DailyChallengeReward,
    EligibilityCheck,
    Feedback,
    FollowUpAction,
    HealthCheckup,
    HealthDiagnosisRecord,
    Prediction,
    PredictionRiskCurvePoint,
    PredictionScenario,
    RiskFactor,
    UserChallenge,
)
from app.models.prediction_jobs import PredictionJob


class HealthRepository:
    async def active_consent(self, user_id: int) -> Consent | None:
        return await Consent.filter(user_id=user_id, is_agreed=True, withdrawn_at=None).order_by("-agreed_at").first()

    async def create_consent(self, **values: Any) -> Consent:
        return await Consent.create(**values)

    async def list_consents(self, user_id: int) -> list[Consent]:
        return await Consent.filter(user_id=user_id).order_by("-created_at")

    async def get_consent(self, consent_id: int, user_id: int) -> Consent | None:
        return await Consent.get_or_none(id=consent_id, user_id=user_id)

    async def create_eligibility(self, **values: Any) -> EligibilityCheck:
        return await EligibilityCheck.create(**values)

    async def latest_eligibility(self, user_id: int) -> EligibilityCheck | None:
        return await EligibilityCheck.filter(user_id=user_id).order_by("-created_at", "-id").first()

    async def create_checkup(self, **values: Any) -> HealthCheckup:
        return await HealthCheckup.create(**values)

    async def get_checkup(self, checkup_id: int, user_id: int) -> HealthCheckup | None:
        return await HealthCheckup.get_or_none(id=checkup_id, user_id=user_id)

    async def list_checkups(self, user_id: int) -> list[HealthCheckup]:
        return await HealthCheckup.filter(user_id=user_id).order_by("-checkup_date", "-id")

    async def latest_checkup(self, user_id: int) -> HealthCheckup | None:
        return await HealthCheckup.filter(user_id=user_id).order_by("-checkup_date", "-id").first()

    async def create_current_screening_input(self, **values: Any) -> CurrentScreeningInput:
        return await CurrentScreeningInput.create(**values)

    async def get_current_screening_input(self, input_id: int, user_id: int) -> CurrentScreeningInput | None:
        return await CurrentScreeningInput.get_or_none(id=input_id, user_id=user_id)

    async def checkup_has_prediction(self, checkup_id: int, user_id: int) -> bool:
        return await Prediction.filter(health_checkup_id=checkup_id, user_id=user_id).exists()

    async def delete_checkup(self, checkup_id: int, user_id: int) -> bool:
        """Delete one owned health record and its derived analysis data."""
        item = await self.get_checkup(checkup_id, user_id)
        if item is None:
            return False
        predictions = await Prediction.filter(health_checkup_id=checkup_id, user_id=user_id)
        prediction_ids = [prediction.id for prediction in predictions]
        async with in_transaction() as connection:
            if prediction_ids:
                await PredictionRiskCurvePoint.filter(prediction_id__in=prediction_ids).using_db(connection).delete()
                await PredictionScenario.filter(prediction_id__in=prediction_ids).using_db(connection).delete()
                await RiskFactor.filter(prediction_id__in=prediction_ids).using_db(connection).delete()
                await (
                    ChallengeCycle.filter(user_id=user_id, prediction_id__in=prediction_ids)
                    .using_db(connection)
                    .update(prediction_id=None)
                )
                await (
                    Feedback.filter(user_id=user_id, prediction_id__in=prediction_ids)
                    .using_db(connection)
                    .update(prediction_id=None)
                )
                await Prediction.filter(id__in=prediction_ids, user_id=user_id).using_db(connection).delete()
            await PredictionJob.filter(health_checkup_id=checkup_id, user_id=user_id).using_db(connection).delete()
            await (
                CurrentScreeningInput.filter(health_checkup_id=checkup_id, user_id=user_id)
                .using_db(connection)
                .delete()
            )
            await HealthCheckup.filter(id=checkup_id, user_id=user_id).using_db(connection).delete()
        return True

    async def get_prediction(self, prediction_id: int, user_id: int) -> Prediction | None:
        return await Prediction.get_or_none(id=prediction_id, user_id=user_id)

    async def latest_prediction(self, user_id: int) -> Prediction | None:
        return await Prediction.filter(user_id=user_id).order_by("-predicted_at", "-id").first()

    async def list_predictions(self, user_id: int) -> list[Prediction]:
        return await Prediction.filter(user_id=user_id).order_by("-predicted_at", "-id")

    async def risk_curve_points(self, prediction_id: int) -> list[PredictionRiskCurvePoint]:
        """API-LIFE-004: ordered (age, cumulative_risk) points for a lifetime-risk prediction."""
        return await PredictionRiskCurvePoint.filter(prediction_id=prediction_id).order_by("age")

    async def risk_factors(self, prediction_id: int) -> list[RiskFactor]:
        return await RiskFactor.filter(prediction_id=prediction_id).order_by("display_order", "id")

    async def latest_prediction_for_model_key(self, user_id: int, model_key: str) -> Prediction | None:
        return await Prediction.filter(user_id=user_id, model_key=model_key).order_by("-predicted_at", "-id").first()

    async def active_cycle(self, user_id: int) -> ChallengeCycle | None:
        return await ChallengeCycle.filter(user_id=user_id, status__in=["scheduled", "active"]).order_by("-id").first()

    async def get_cycle(self, cycle_id: int, user_id: int) -> ChallengeCycle | None:
        return await ChallengeCycle.get_or_none(id=cycle_id, user_id=user_id)

    async def cycle_for_date(self, user_id: int, target_date: date) -> ChallengeCycle | None:
        return (
            await ChallengeCycle.filter(user_id=user_id, start_date__lte=target_date, end_date__gte=target_date)
            .order_by("-id")
            .first()
        )

    async def list_user_challenges(self, cycle_id: int, user_id: int) -> list[UserChallenge]:
        return await UserChallenge.filter(cycle_id=cycle_id, user_id=user_id).order_by("id")

    async def get_user_challenge(self, user_challenge_id: int, user_id: int) -> UserChallenge | None:
        return await UserChallenge.get_or_none(id=user_challenge_id, user_id=user_id)

    async def logs_for_cycle(self, cycle_id: int, user_id: int) -> list[ChallengeLog]:
        user_challenges = await self.list_user_challenges(cycle_id, user_id)
        ids = [item.id for item in user_challenges]
        if not ids:
            return []
        return await ChallengeLog.filter(user_id=user_id, user_challenge_id__in=ids).order_by("log_date", "id")

    async def logs_for_user_challenge(
        self, user_challenge_id: int, user_id: int, start_date: date | None, end_date: date | None
    ) -> list[ChallengeLog]:
        query = ChallengeLog.filter(user_challenge_id=user_challenge_id, user_id=user_id)
        if start_date is not None:
            query = query.filter(log_date__gte=start_date)
        if end_date is not None:
            query = query.filter(log_date__lte=end_date)
        return await query.order_by("log_date")

    async def upsert_log(
        self, *, user_challenge_id: int, user_id: int, log_date: date, values: dict[str, Any]
    ) -> ChallengeLog:
        item, _ = await ChallengeLog.update_or_create(
            defaults={"user_id": user_id, **values},
            user_challenge_id=user_challenge_id,
            log_date=log_date,
        )
        return item

    async def record_verification_event(self, verification: ChallengeVerification) -> ChallengeVerificationEvent:
        return await ChallengeVerificationEvent.create(
            verification_id=verification.id,
            user_id=verification.user_id,
            event_type="submitted",
            review_status=verification.review_status,
            evidence_digest=verification.evidence_digest,
        )

    async def upsert_verification(
        self, *, user_challenge_id: int, user_id: int, verification_date: date, values: dict[str, Any]
    ) -> ChallengeVerification:
        item, _ = await ChallengeVerification.update_or_create(
            defaults={"user_id": user_id, **values},
            user_challenge_id=user_challenge_id,
            verification_date=verification_date,
        )
        return item

    async def completed_challenge_ids_for_date(self, cycle_id: int, user_id: int, log_date: date) -> set[int]:
        selected = await self.list_user_challenges(cycle_id, user_id)
        selected_ids = [item.id for item in selected]
        if not selected_ids:
            return set()
        logs = await ChallengeLog.filter(
            user_id=user_id,
            user_challenge_id__in=selected_ids,
            log_date=log_date,
            is_completed=True,
        )
        return {item.user_challenge_id for item in logs}

    async def get_daily_reward(self, user_id: int, reward_date: date) -> DailyChallengeReward | None:
        return await DailyChallengeReward.get_or_none(user_id=user_id, reward_date=reward_date)

    async def claim_daily_reward(
        self, user_id: int, reward_date: date, carrot_amount: int
    ) -> tuple[DailyChallengeReward, bool]:
        return await DailyChallengeReward.get_or_create(
            user_id=user_id,
            reward_date=reward_date,
            defaults={"carrot_amount": carrot_amount},
        )

    async def open_follow_up(self, user_id: int) -> FollowUpAction | None:
        items = await self.open_follow_ups(user_id)
        return items[0] if items else None

    async def open_follow_ups(self, user_id: int) -> list[FollowUpAction]:
        items = await FollowUpAction.filter(user_id=user_id, acknowledged_at=None).order_by("-created_at", "-id")
        if not any(item.reason_code == "DIAGNOSED_DIABETES" for item in items):
            return items
        latest = await self.latest_eligibility(user_id)
        if latest is None or latest.has_diabetes_diagnosis:
            return items
        if await HealthDiagnosisRecord.filter(user_id=user_id, is_active=True).exists():
            return items
        # An explicit later No plus removal/correction of every diagnosis assertion
        # supersedes that assertion's guidance. Preserve its audit and acknowledgement.
        return [item for item in items if not (
            item.reason_code == "DIAGNOSED_DIABETES"
            and item.trigger_source == "eligibility_check"
            and item.trigger_entity_id < latest.id
        )]

    async def list_follow_ups(self, user_id: int) -> list[FollowUpAction]:
        return await FollowUpAction.filter(user_id=user_id).order_by("-created_at", "-id")

    async def get_follow_up(self, action_id: int, user_id: int) -> FollowUpAction | None:
        return await FollowUpAction.get_or_none(id=action_id, user_id=user_id)

    async def stop_active_cycles(self, user_id: int, reason: str) -> int:
        return await ChallengeCycle.filter(user_id=user_id, status__in=["scheduled", "active"]).update(
            status="terminated", ended_reason=reason
        )

    async def count_cycles(self, user_id: int) -> int:
        return await ChallengeCycle.filter(user_id=user_id).count()

    async def challenge_map(self, challenge_ids: list[int] | None = None) -> dict[int, Challenge]:
        query = Challenge.filter(is_active=True)
        if challenge_ids is not None:
            query = query.filter(id__in=challenge_ids)
        return {item.id: item for item in await query.order_by("id")}

    async def acknowledge_follow_up(self, item: FollowUpAction, at: datetime) -> FollowUpAction:
        item.acknowledged_at = at
        await item.save(update_fields=["acknowledged_at"])
        return item

    async def create_feedback(self, **values: Any) -> Feedback:
        return await Feedback.create(**values)

    async def list_feedback(self, user_id: int) -> list[Feedback]:
        return await Feedback.filter(user_id=user_id).order_by("-created_at", "-id")
