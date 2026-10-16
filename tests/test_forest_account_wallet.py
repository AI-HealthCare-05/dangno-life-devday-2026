"""Currency regressions: isolated DB, synthetic accounts, no real balances."""

import asyncio
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException
from pydantic import ValidationError
from tortoise import Tortoise

from app.dtos.forest import ForestWalletActionRequest
from app.models.challenge_v2 import ChallengeV2Assignment, ChallengeV2Day, ChallengeV2Reward, ChallengeV2Session
from app.models.forest import ForestAvatar
from app.models.game import RewardTransaction, UserWallet
from app.models.health import Challenge, ChallengeCycle, ChallengeLog, UserChallenge
from app.models.users import User
from app.repositories.game_repository import GameRepository
from app.repositories.health_repository import HealthRepository
from app.services import challenge_v2
from app.services.challenge_wallet import award_v3_completion
from app.services.challenges import ChallengeService
from app.services.forest_wallet import ForestWalletService
from tests.db_utils import init_sqlite_test_db

pytestmark = pytest.mark.asyncio(loop_scope="session")
DAY = date(2026, 10, 9)


@pytest_asyncio.fixture(loop_scope="session")
async def user(monkeypatch):
    await init_sqlite_test_db()
    monkeypatch.setattr("app.services.forest_wallet.forest_day", lambda: DAY.isoformat())
    user = await User.create(email="wallet-test@example.invalid", hashed_password="not-a-login")
    try:
        yield user
    finally:
        await Tortoise.close_connections()


async def trio(user):
    day = await ChallengeV2Day.create(user_id=user.id, assigned_date=DAY, eligibility_snapshot={})
    items = []
    for slot, domain in enumerate(("diet", "activity", "routine"), 1):
        goal = {"domain": domain, "proof_type": "T3", "target_sessions": 1, "required_uploads": 0}
        items.append(await ChallengeV2Assignment.create(day_id=day.id, slot=slot, goal=goal))
    return day, items


async def complete(user, day, item):
    await ChallengeV2Session.get_or_create(
        assignment_id=item.id,
        session_index=1,
        defaults={"performed_at": datetime.now(UTC), "values": {"done": True}},
    )
    await challenge_v2.aggregate(item, day, user)


async def test_trio_grants_10_each_plus_50_once_and_all_views_read_same_wallet(user):
    day, items = await trio(user)
    for item, balance in zip(items, (110, 120, 180), strict=True):
        await complete(user, day, item)
        assert (await ForestWalletService().snapshot(user))["carrot_balance"] == balance
    await asyncio.gather(*(challenge_v2.issue_reward(user, day, f"v2-slot:{day.id}:1", 10) for _ in range(5)))
    await challenge_v2.aggregate(items[-1], day, user)
    assert await ChallengeV2Reward.filter(day_id=day.id).count() == 4
    assert (await challenge_v2.day_payload(day))["carrot_balance"] == 180
    assert (await UserWallet.get(user_id=user.id)).carrot_balance == 180
    assert (await ForestAvatar.get(user_id=user.id)).carrot_balance == 100


async def test_unverified_photo_has_no_currency_reward(user):
    day, items = await trio(user)
    item = items[0]
    item.goal = {**item.goal, "proof_type": "T1", "required_uploads": 1}
    await item.save()
    await complete(user, day, item)
    await item.refresh_from_db()
    assert item.status != "completed"
    assert await ChallengeV2Reward.all().count() == 0
    assert (await ForestWalletService().snapshot(user))["carrot_balance"] == 100


async def test_legacy_rewards_before_and_after_welcome_are_migrated_without_double_credit(user):
    day, _ = await trio(user)
    await ForestAvatar.create(user_id=user.id, display_name="test", carrot_balance=130)
    welcome, _ = await GameRepository().credit(
        user.id, 110, "forest_welcome_bonus", str(user.id), f"forest-welcome:{user.id}"
    )
    for slot in (1, 2, 3):
        reward = await ChallengeV2Reward.create(
            user_id=user.id, day_id=day.id, source_key=f"v2-slot:{day.id}:{slot}", carrot_amount=10
        )
        reward.created_at = welcome.created_at + timedelta(seconds=-1 if slot == 1 else 1)
        await reward.save(update_fields=["created_at"])
    for _ in range(3):
        assert (await ForestWalletService().snapshot(user))["carrot_balance"] == 130
    await challenge_v2.issue_reward(user, day, f"v2-slot:{day.id}:2", 10)
    assert (await UserWallet.get(user_id=user.id)).carrot_balance == 130


async def test_account_balances_and_request_ids_are_isolated_and_daily_actions_follow_kst(user, monkeypatch):
    other = await User.create(email="wallet-other@example.invalid", hashed_password="not-a-login")
    action = ForestWalletActionRequest(action="water", request_id=uuid4())
    service = ForestWalletService()
    results = await asyncio.gather(*(service.perform(user, action) for _ in range(5)))
    assert sum(result["amount"] for result in results) == 10
    assert (await service.perform(user, ForestWalletActionRequest(action="water", request_id=uuid4())))["amount"] == 0
    assert (await service.snapshot(other))["carrot_balance"] == 100
    assert (await service.perform(other, action))["carrot_balance"] == 110
    monkeypatch.setattr("app.services.forest_wallet.forest_day", lambda: "2026-10-10")
    assert (await service.perform(user, action))["carrot_balance"] == 120


async def test_rabbit_retry_is_durable_and_pet_spending_cannot_overdraw(user):
    service = ForestWalletService()
    catch = ForestWalletActionRequest(action="rabbit_catch", request_id=uuid4())
    assert (await service.perform(user, catch))["carrot_balance"] == 101
    assert (await ForestWalletService().perform(user, catch))["amount"] == 0
    await GameRepository().credit(user.id, -99, "test", "seed", "test-small-balance")

    async def feed():
        return await service.perform(user, ForestWalletActionRequest(action="pet_feed", request_id=uuid4()))

    results = await asyncio.gather(*(feed() for _ in range(3)), return_exceptions=True)
    assert sum(isinstance(result, HTTPException) and result.status_code == 409 for result in results) == 1
    assert (await service.snapshot(user))["carrot_balance"] == 0
    with pytest.raises(ValidationError):
        ForestWalletActionRequest(action="rabbit_catch", request_id=uuid4(), amount=9999)


async def test_ledger_failure_rolls_back_balance(user, monkeypatch):
    await ForestWalletService().snapshot(user)

    async def fail(**kwargs):
        raise RuntimeError("synthetic receipt failure")

    monkeypatch.setattr(RewardTransaction, "create", fail)
    with pytest.raises(RuntimeError):
        await GameRepository().credit(user.id, 10, "test", "failure", "test-rollback")
    assert (await UserWallet.get(user_id=user.id)).carrot_balance == 100


async def test_service_and_forest_share_domain_receipts_and_daily_bonus(user):
    service = ChallengeService()
    await service.ensure_catalog("evidence-v3")
    cycle = await ChallengeCycle.create(
        user_id=user.id, cycle_number=1, start_date=DAY, end_date=DAY + timedelta(days=27)
    )
    # Resolve the real catalog's diet/activity codes rather than inventing metadata.
    catalog = await Challenge.filter(code__startswith="v3_")
    from app.services.challenge_catalog import metadata_for

    chosen = [next(item for item in catalog if item.category == domain) for domain in ("diet", "activity")]
    chosen.append(next(item for item in catalog if metadata_for(item.code)["domain"] == "hydration"))
    selected = [await UserChallenge.create(user_id=user.id, cycle_id=cycle.id, challenge_id=item.id) for item in chosen]
    for item in selected:
        await ChallengeLog.create(user_id=user.id, user_challenge_id=item.id, log_date=DAY, is_completed=True)
        reward = await award_v3_completion(user, item, DAY, HealthRepository())
        assert reward["earned_carrots"] == 10
    assert (await UserWallet.get(user_id=user.id)).carrot_balance == 180
    day, items = await trio(user)
    for item in items:
        await complete(user, day, item)
    assert (await UserWallet.get(user_id=user.id)).carrot_balance == 180
    assert all(row.carrot_amount == 0 for row in await ChallengeV2Reward.all())
    assert (await service.claim_daily_reward(user, DAY))["carrot_balance"] == 180
