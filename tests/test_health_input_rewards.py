"""Optional-input rewards use synthetic records and isolated in-memory databases."""

import asyncio
from datetime import date

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from tortoise import Tortoise

from app.apis.v1.health_routers import health_router
from app.dtos.health import (
    CurrentScreeningInputCreateRequest,
    HealthCheckupCreateRequest,
    HealthInputRewardClaimRequest,
)
from app.models.game import RewardTransaction, UserWallet
from app.models.health import Consent, CurrentScreeningInput, HealthCheckup
from app.models.users import User
from app.services.health_input_rewards import CARROTS_PER_FIELD, FIELDS, SOURCE, HealthInputRewardService
from tests.db_utils import init_sqlite_test_db

pytestmark = pytest.mark.asyncio(loop_scope="session")
DAY = date(2026, 10, 15)


@pytest_asyncio.fixture(loop_scope="session")
async def account():
    await init_sqlite_test_db()
    user = await User.create(email="optional-input@example.invalid", hashed_password="not-a-login")
    await Consent.create(user_id=user.id, version="1.0")
    try:
        yield user
    finally:
        await Tortoise.close_connections()


async def checkup(user, **values):
    request = HealthCheckupCreateRequest(
        checkup_date=DAY,
        height_cm=160,
        weight_kg=60,
        smoking_status="never",
        regular_exercise=False,
        current_drinker=False,
        exercise_days_per_week=0,
        exercise_minutes=0,
        **values,
    )
    return await HealthCheckup.create(
        user_id=user.id, eligibility_check_id=1, age=55, sex="female", bmi=23.44, **request.model_dump()
    )


async def snapshot(user, record, **values):
    request = CurrentScreeningInputCreateRequest(
        health_checkup_id=record.id, input_as_of_date=DAY, alcohol_frequency=1, **values
    )
    return await CurrentScreeningInput.create(user_id=user.id, **request.model_dump())


async def claim(user, record, current=None):
    return await HealthInputRewardService().claim(
        user,
        HealthInputRewardClaimRequest(checkup_id=record.id, current_screening_input_id=current.id if current else None),
    )


async def test_each_of_the_17_optional_fields_pays_100_once_and_education_is_shared(account):
    record = await checkup(
        account,
        waist_cm=80,
        systolic_bp=120,
        diastolic_bp=80,
        health_satisfaction_score=0,
        economic_satisfaction_score=50,
        overall_quality_of_life_score=70,
        cancer_diagnosis=False,
        chronic_lung_disease_diagnosis=False,
        liver_disease_diagnosis=False,
        cerebrovascular_disease_diagnosis=False,
        psychiatric_disease_diagnosis=False,
        education_level="code_4",
        household_structure="single_person",
        annual_household_income_10k_krw=0,
    )
    current = await snapshot(
        account, record, region=1, education="code_4", diabetes_family_history=False, hypertension_family_history=False
    )
    result = await claim(account, record, current)
    assert len(FIELDS) == 17
    assert result["earned_carrots"] == 17 * CARROTS_PER_FIELD
    assert len(result["rewarded_fields"]) == 17
    assert result["carrot_balance"] == 100 + 1700
    repeated = await claim(account, record, current)
    assert repeated["earned_carrots"] == 0
    assert repeated["checkup_reward_carrots"] == 1700
    assert repeated["carrot_balance"] == 1800
    assert await RewardTransaction.filter(user_id=account.id, source_type=SOURCE).count() == 17
    # The ledger records a field key and checkup ID, never the supplied health value.
    rows = await RewardTransaction.filter(source_type=SOURCE)
    assert {row.source_ref for row in rows} == {f"{record.id}:{field.key}" for field in FIELDS}


async def test_missing_unknown_and_required_answers_do_not_pay(account):
    record = await checkup(account, education_level="code_97", hypertension_diagnosis=False, marital_status="code_1")
    result = await claim(account, record)
    assert result["earned_carrots"] == 0
    assert result["eligible_fields"] == []
    assert result["carrot_balance"] == 100  # Existing once-only forest welcome, not an input reward.


async def test_concurrent_retries_edits_new_records_and_deletion_cannot_farm_the_same_field(account):
    first = await checkup(account, waist_cm=90)
    results = await asyncio.gather(*(claim(account, first) for _ in range(5)))
    assert sum(result["earned_carrots"] for result in results) == 100
    first.waist_cm = None
    await first.save()
    assert (await claim(account, first))["earned_carrots"] == 0
    first.waist_cm = 92
    await first.save()
    assert (await claim(account, first))["earned_carrots"] == 0
    await first.delete()
    second = await checkup(account, waist_cm=89, health_satisfaction_score=0)
    result = await claim(account, second)
    assert result["earned_carrots"] == 100
    assert [row["key"] for row in result["rewarded_fields"]] == ["health_satisfaction_score"]
    assert result["carrot_balance"] == 300


async def test_snapshots_require_record_ownership_and_matching_parent_without_side_effects(account):
    other = await User.create(email="other-optional@example.invalid", hashed_password="not-a-login")
    foreign = await checkup(other, waist_cm=90)
    with pytest.raises(HTTPException) as exc:
        await claim(account, foreign)
    assert exc.value.status_code == 404
    own = await checkup(account, waist_cm=90)
    foreign_input = await snapshot(other, foreign, region=1)
    with pytest.raises(HTTPException) as exc:
        await claim(account, own, foreign_input)
    assert exc.value.status_code == 404
    assert await RewardTransaction.filter(user_id=account.id).count() == 0
    own_input = await snapshot(account, own, region=1, education="code_3", diabetes_family_history=False)
    result = await claim(account, own, own_input)
    assert result["earned_carrots"] == 400


async def test_withdrawn_consent_prevents_payment(account):
    record = await checkup(account, waist_cm=90)
    await Consent.filter(user_id=account.id).update(is_agreed=False)
    with pytest.raises(HTTPException) as exc:
        await claim(account, record)
    assert exc.value.status_code == 403
    assert await RewardTransaction.filter(user_id=account.id).count() == 0


async def test_failed_receipt_rolls_back_the_entire_award_then_can_retry(account, monkeypatch):
    record = await checkup(account, waist_cm=90, health_satisfaction_score=60)
    original = RewardTransaction.create

    async def fail_receipt(**values):
        if values.get("source_type") == SOURCE and values["source_ref"].endswith(":health_satisfaction_score"):
            raise RuntimeError("synthetic ledger failure")
        return await original(**values)

    monkeypatch.setattr(RewardTransaction, "create", fail_receipt)
    with pytest.raises(RuntimeError, match="ledger failure"):
        await claim(account, record)
    assert await RewardTransaction.filter(user_id=account.id).count() == 0
    assert await UserWallet.filter(user_id=account.id).count() == 0
    monkeypatch.setattr(RewardTransaction, "create", original)
    assert (await claim(account, record))["earned_carrots"] == 200


async def test_account_catalog_omits_values_and_does_not_create_a_wallet(account):
    status = await HealthInputRewardService().status(account)
    assert status["carrots_per_field"] == 100
    assert len(status["fields"]) == 17
    assert not any(row["claimed"] for row in status["fields"])
    assert not any("value" in row for row in status["fields"])
    assert await UserWallet.filter(user_id=account.id).count() == 0
    record = await checkup(account, waist_cm=90)
    await claim(account, record)
    status = await HealthInputRewardService().status(account)
    assert [row["key"] for row in status["fields"] if row["claimed"]] == ["waist_cm"]
    other = await User.create(email="separate-optional@example.invalid", hashed_password="not-a-login")
    assert not any(row["claimed"] for row in (await HealthInputRewardService().status(other))["fields"])


async def test_invalid_legacy_values_and_forged_reward_arguments_are_not_accepted(account):
    record = await checkup(account)
    record.waist_cm = 999
    record.health_satisfaction_score = -2
    record.systolic_bp = 80
    record.diastolic_bp = 120
    await record.save()
    assert (await claim(account, record))["earned_carrots"] == 0
    with pytest.raises(ValidationError):
        HealthInputRewardClaimRequest(checkup_id=record.id, amount=99999, fields=["height_cm"])


async def test_reward_routes_require_authentication(account):
    app = FastAPI()
    app.include_router(health_router, prefix="/api/v1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test.invalid") as client:
        assert (await client.get("/api/v1/health-input-rewards")).status_code == 401
        assert (await client.post("/api/v1/health-input-rewards/claim", json={"checkup_id": 1})).status_code == 401
    assert await UserWallet.filter(user_id=account.id).count() == 0
