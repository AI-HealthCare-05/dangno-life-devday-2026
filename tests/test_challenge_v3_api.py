"""V3 challenge API regressions using isolated SQLite and in-process HTTP only."""

from __future__ import annotations

import asyncio
import io
import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from PIL import Image
from tortoise import Tortoise

from app.core import config
from app.core.db.databases import TORTOISE_APP_MODELS
from app.main import app
from app.models.health import (
    Challenge,
    ChallengeCycle,
    ChallengeLog,
    ChallengeVerification,
    ChallengeVerificationEvent,
    Consent,
    EligibilityCheck,
    UserChallenge,
)
from app.models.users import User
from app.services import challenge_proofs, challenges
from app.services.challenge_catalog import CATALOG_VERSION, recommend_codes
from app.services.challenge_proofs import challenge_today
from app.services.jwt import JwtService
from app.vision.food_vision import FoodVisionError, FoodVisionResult, OpenAIFoodVisionProvider


def image_bytes(color="green", *, exif=False):
    image = Image.new("RGB", (24, 24), color)
    output = io.BytesIO()
    if exif:
        metadata = Image.Exif()
        metadata[270] = "private-test-location-and-description"
        image.save(output, format="JPEG", exif=metadata)
    else:
        image.save(output, format="PNG")
    return output.getvalue()


async def eligible_user(email):
    user = await User.create(email=email, hashed_password="test-fixture-not-a-login-password")
    await Consent.create(user_id=user.id, version="1.0", is_agreed=True)
    await EligibilityCheck.create(
        user_id=user.id,
        age=60,
        service_eligible=True,
        target_segment="adult",
        model_eligible=True,
        next_action="challenge",
        model_key="test",
        model_version="test",
        feature_schema_version="test",
        threshold_version="test",
        safety_copy_version="test",
    )
    token = str(JwtService().create_access_token(user))
    return user, {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(loop_scope="function")
async def api(monkeypatch):
    # No external DB, Redis, image service, real account or credentials are used.
    monkeypatch.setattr(config, "FOOD_VISION_PROVIDER", "development")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": TORTOISE_APP_MODELS}, timezone="Asia/Seoul")
    await Tortoise.generate_schemas()
    try:
        user, headers = await eligible_user("v3-owner@example.com")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield SimpleNamespace(client=client, user=user, headers=headers)
    finally:
        await Tortoise.close_connections()


async def catalog(api):
    response = await api.client.get("/api/v1/challenges", params={"catalog_version": CATALOG_VERSION})
    assert response.status_code == 200, response.text
    return {item["code"]: item for item in response.json()["data"]["items"]}


async def start_cycle(api, *, focus="balanced", difficulty="easy", rotation=0):
    items = await catalog(api)
    response = await api.client.post(
        "/api/v1/challenge-cycles",
        headers=api.headers,
        json={
            "start_date": challenge_today().isoformat(),
            "challenge_ids": [items[code]["challenge_id"] for code in recommend_codes(focus, difficulty, rotation)],
            "catalog_version": CATALOG_VERSION,
            "focus": focus,
            "difficulty": difficulty,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def submit_photo(
    api, item, *, actual=1, content=None, proof_date=None, headers=None, filename="private-salad.png", confirmed=False,
    photo_context=None,
):
    return await api.client.post(
        f"/api/v1/user-challenges/{item['user_challenge_id']}/photo-verifications",
        headers=headers or api.headers,
        data={
            "verification_date": (proof_date or challenge_today()).isoformat(),
            "actual_value": str(actual),
            "confirmed": str(confirmed).lower(),
            **(photo_context or {}),
        },
        files={"file": (filename, image_bytes() if content is None else content, "image/png")},
    )


def find_item(cycle, domain):
    return next(item for item in cycle["user_challenges"] if item["domain"] == domain)


def local_result(decision: str) -> FoodVisionResult:
    values = {
        "valid": (68.0, 34.0, True),
        "invalid_food_ratio": (42.0, 40.0, True),
        "invalid_vegetable_ratio": (68.0, 18.0, True),
        "uncertain": (68.0, 34.0, False),
    }
    food, vegetable, reliable = values[decision]
    return FoodVisionResult(
        "local_kfood_cv",
        "채소" if decision == "valid" else "확인불가",
        decision == "valid",
        None,
        vegetable_ratio_percent=vegetable,
        food_coverage_percent=food,
        reliable=reliable,
        uncertainty_reasons=[] if reliable else ["segmentation_unreliable_for_dish"],
        model_version="test-kfood-v1",
        decision_status=decision,
    )


@pytest.mark.asyncio
async def test_catalog_opt_in_legacy_compatibility_and_repeat_reads_do_not_rewrite_existing_rows(api):
    legacy = await api.client.get("/api/v1/challenges")
    assert legacy.status_code == 200
    legacy_items = legacy.json()["data"]["items"]
    assert all(not item["code"].startswith("v3_") for item in legacy_items)
    original = await Challenge.get(id=legacy_items[0]["challenge_id"])
    original.title = "기존 사이클 목표는 보존"
    await original.save(update_fields=["title"])
    v3 = await catalog(api)
    assert len(v3) == 13
    count = await Challenge.all().count()
    for _ in range(2):
        assert await catalog(api) == v3
        await api.client.get("/api/v1/challenges")
    await original.refresh_from_db()
    assert original.title == "기존 사이클 목표는 보존"
    assert await Challenge.all().count() == count


@pytest.mark.asyncio
async def test_recommendations_apply_preference_keep_water_and_hide_unavailable_ai_review(api, monkeypatch):
    for focus, difficulty in [("balanced", "easy"), ("diet", "advanced"), ("activity", "moderate")]:
        response = await api.client.get(
            "/api/v1/challenge-recommendations",
            headers=api.headers,
            params={"catalog_version": CATALOG_VERSION, "focus": focus, "difficulty": difficulty, "rotation": 1},
        )
        assert response.status_code == 200, response.text
        body = response.json()["data"]
        assert len(body["items"]) == 3 and body["items"][0]["domain"] == "hydration"
        assert body["photo_review_available"] is False
        assert body["demo_photo_submission_only"] is False
        assert all(item["verification_type"] != 1 for item in body["items"])
        assert body["policy"]["focus"] == focus and body["policy"]["difficulty"] == difficulty
        assert body["personalized"] is False and body["preference_applied"] is True
    monkeypatch.setattr(config, "FOOD_VISION_PROVIDER", "local_kfood")
    monkeypatch.setattr(challenges, "food_vision_is_configured", lambda: True)
    response = await api.client.get(
        "/api/v1/challenge-recommendations",
        headers=api.headers,
        params={"catalog_version": CATALOG_VERSION, "rotation": 1},
    )
    assert response.json()["data"]["items"][1]["verification_type"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params", [{"focus": "unknown"}, {"difficulty": "hard"}, {"rotation": -1}, {"rotation": 1_000_001}]
)
async def test_invalid_preference_queries_are_rejected(api, params):
    response = await api.client.get(
        "/api/v1/challenge-recommendations",
        headers=api.headers,
        params={"catalog_version": CATALOG_VERSION, **params},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_demo_allows_both_diet_choices_without_claiming_photo_review(api, monkeypatch):
    monkeypatch.setattr(config, "DEMO_MODE", True)
    items = await catalog(api)
    ids = [items[code]["challenge_id"] for code in ("v3_hydration_choice", "v3_vegetable_easy", "v3_walk_easy")]
    response = await api.client.post(
        "/api/v1/challenge-cycles",
        headers=api.headers,
        json={
            "start_date": challenge_today().isoformat(),
            "challenge_ids": ids,
            "catalog_version": CATALOG_VERSION,
            "focus": "balanced",
            "difficulty": "easy",
        },
    )
    assert response.status_code == 201, response.text
    selected = find_item(response.json()["data"], "fiber_diet")
    photo = await submit_photo(api, selected, content=image_bytes())
    assert photo.status_code == 201, photo.text
    assert "자동 판정하지 않았" in photo.json()["data"]["notice"]


@pytest.mark.asyncio
async def test_v3_requires_three_domains_correct_difficulty_and_version(api):
    items = await catalog(api)
    ids = [items[code]["challenge_id"] for code in recommend_codes("balanced", "easy")]
    base = {"start_date": challenge_today().isoformat(), "catalog_version": CATALOG_VERSION}
    malformed = [
        {**base, "challenge_ids": ids[:1]},
        {**base, "challenge_ids": [ids[0], ids[0], ids[2]]},
        {**base, "challenge_ids": [ids[1], ids[2], items["v3_indoor_aerobic_easy"]["challenge_id"]]},
        {**base, "challenge_ids": ids, "difficulty": "advanced"},
        {"start_date": base["start_date"], "challenge_ids": ids},
    ]
    for request in malformed:
        response = await api.client.post("/api/v1/challenge-cycles", headers=api.headers, json=request)
        assert response.status_code == 422, response.text
    assert await ChallengeCycle.all().count() == 0
    cycle = await start_cycle(api)
    assert len(cycle["user_challenges"]) == 3
    assert await ChallengeCycle.all().count() == 1


@pytest.mark.asyncio
async def test_legacy_single_selection_and_its_original_payload_remain_supported(api):
    result = await api.client.get("/api/v1/challenges")
    legacy = result.json()["data"]["items"][0]
    response = await api.client.post(
        "/api/v1/challenge-cycles",
        headers=api.headers,
        json={"start_date": challenge_today().isoformat(), "challenge_ids": [legacy["challenge_id"]]},
    )
    assert response.status_code == 201, response.text
    old_cycle = response.json()["data"]
    selected = old_cycle["user_challenges"][0]
    await catalog(api)
    read = await api.client.get(f"/api/v1/challenge-cycles/{old_cycle['cycle_id']}", headers=api.headers)
    assert read.json()["data"]["user_challenges"] == old_cycle["user_challenges"]
    saved = await api.client.put(
        f"/api/v1/user-challenges/{selected['user_challenge_id']}/logs/{challenge_today()}",
        headers=api.headers,
        json={"is_completed": True, "value": 1},
    )
    assert saved.status_code == 200


@pytest.mark.asyncio
async def test_type2_accepts_real_image_without_ai_and_duplicate_does_not_change_proof_or_quantity(api, monkeypatch):
    cycle = await start_cycle(api)
    item = find_item(cycle, "fiber_diet")
    forbidden_provider = AsyncMock(side_effect=AssertionError("Type2 must not invoke AI"))
    monkeypatch.setattr(challenge_proofs, "get_food_vision_provider", forbidden_provider)
    first = await submit_photo(api, item, content=image_bytes(exif=True))
    assert first.status_code == 201, first.text
    assert first.json()["data"]["challenge_completed"] is True
    verification = await ChallengeVerification.get(id=first.json()["data"]["verification_id"])
    original_digest = verification.evidence_digest
    assert len(original_digest) == 64 and verification.evidence_ref == "v3:server-photo"
    assert "private" not in verification.evidence_ref
    second = await submit_photo(api, item, actual=2, content=image_bytes("blue"))
    assert second.status_code == 201, second.text
    assert second.json()["data"]["already_recorded"] is True
    await verification.refresh_from_db()
    assert verification.evidence_digest == original_digest
    assert await ChallengeVerification.all().count() == 1
    assert await ChallengeVerificationEvent.all().count() == 1
    log = await ChallengeLog.get(user_challenge_id=item["user_challenge_id"])
    assert log.is_completed and log.value == 1 and log.source == "photo_v3"
    forbidden_provider.assert_not_called()


@pytest.mark.asyncio
async def test_type3_uses_check_and_type2_cannot_bypass_upload_with_completed_log(api):
    cycle = await start_cycle(api)
    for item in cycle["user_challenges"]:
        result = await api.client.put(
            f"/api/v1/user-challenges/{item['user_challenge_id']}/logs/{challenge_today()}",
            headers=api.headers,
            json={"is_completed": True, "value": 999, "note": "evidence_ref:trusted-photo"},
        )
        assert result.status_code == (200 if item["verification_type"] == 3 else 422), result.text
    assert await ChallengeLog.filter(is_completed=True).count() == 1
    water_photo = await submit_photo(api, find_item(cycle, "hydration"))
    assert water_photo.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [b"", b"not-an-image", b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"])
async def test_invalid_image_cannot_count_as_photo_evidence(api, content):
    cycle = await start_cycle(api)
    result = await submit_photo(api, find_item(cycle, "fiber_diet"), content=content)
    assert result.status_code == 422, result.text
    assert await ChallengeVerification.all().count() == 0
    assert await ChallengeLog.all().count() == 0


@pytest.mark.asyncio
async def test_under_goal_future_outside_cycle_and_nonfinite_quantities_do_not_complete(api):
    cycle = await start_cycle(api, difficulty="advanced")
    diet = find_item(cycle, "fiber_diet")
    activity = find_item(cycle, "aerobic_activity")
    for item, actual in [(diet, 2), (activity, 29), (activity, float("nan")), (activity, float("inf"))]:
        response = await submit_photo(api, item, actual=actual)
        assert response.status_code == 422, response.text
    for proof_date in [challenge_today() + timedelta(days=1), challenge_today() - timedelta(days=1)]:
        response = await submit_photo(api, diet, actual=3, proof_date=proof_date)
        assert response.status_code == 422
    assert await ChallengeVerification.all().count() == 0
    assert await ChallengeLog.all().count() == 0


@pytest.mark.asyncio
async def test_other_user_and_withdrawn_consent_cannot_record(api):
    cycle = await start_cycle(api)
    item = find_item(cycle, "fiber_diet")
    _, other_headers = await eligible_user("v3-other@example.com")
    result = await submit_photo(api, item, headers=other_headers)
    assert result.status_code == 404
    await Consent.filter(user_id=api.user.id).update(is_agreed=False, withdrawn_at=datetime.now(UTC))
    result = await submit_photo(api, item)
    assert result.status_code == 403
    water = find_item(cycle, "hydration")
    result = await api.client.put(
        f"/api/v1/user-challenges/{water['user_challenge_id']}/logs/{challenge_today()}",
        headers=api.headers,
        json={"is_completed": True},
    )
    assert result.status_code == 403
    assert await ChallengeLog.all().count() == 0


@pytest.mark.asyncio
async def test_stopped_cycle_and_new_medical_exclusion_do_not_accept_photo(api):
    cycle = await start_cycle(api)
    item = find_item(cycle, "fiber_diet")
    await EligibilityCheck.filter(user_id=api.user.id).update(has_urgent_warning_sign=True)
    assert (await submit_photo(api, item)).status_code == 403
    await EligibilityCheck.filter(user_id=api.user.id).update(has_urgent_warning_sign=False)
    await ChallengeCycle.filter(id=cycle["cycle_id"]).update(status="stopped")
    assert (await submit_photo(api, item)).status_code == 409
    assert await ChallengeLog.all().count() == 0


@pytest.mark.asyncio
async def test_type1_development_mock_is_fail_closed_even_for_salad_filename(api, monkeypatch):
    monkeypatch.setattr(config, "FOOD_VISION_PROVIDER", "local_kfood")
    monkeypatch.setattr(challenges, "food_vision_is_configured", lambda: True)
    cycle = await start_cycle(api, rotation=1)
    item = find_item(cycle, "fiber_diet")
    assert item["verification_type"] == 1
    bypass = await api.client.put(
        f"/api/v1/user-challenges/{item['user_challenge_id']}/logs/{challenge_today()}",
        headers=api.headers,
        json={"is_completed": True, "value": 1},
    )
    assert bypass.status_code == 422
    monkeypatch.setattr(config, "FOOD_VISION_PROVIDER", "development")
    response = await submit_photo(api, item, filename="salad-vegetable.png")
    assert response.status_code == 503, response.text
    assert await ChallengeVerification.all().count() == 0
    assert await ChallengeLog.all().count() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "expected"),
    [
        ("valid", "needs_confirmation"),
        ("invalid_food_ratio", "rejected"),
        ("invalid_vegetable_ratio", "rejected"),
        ("uncertain", "needs_review"),
    ],
)
async def test_type1_provider_review_is_limited_to_vegetables_and_uncertainty_does_not_complete(
    api, monkeypatch, decision, expected
):
    monkeypatch.setattr(config, "FOOD_VISION_PROVIDER", "local_kfood")
    monkeypatch.setattr(challenges, "food_vision_is_configured", lambda: True)
    provider = SimpleNamespace(
        provider_kind="local_kfood_cv",
        analyze=AsyncMock(return_value=local_result(decision)),
    )
    monkeypatch.setattr(challenge_proofs, "get_food_vision_provider", lambda: provider)
    cycle = await start_cycle(api, rotation=1)
    item = find_item(cycle, "fiber_diet")
    response = await submit_photo(api, item, content=image_bytes(exif=True))
    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["review_status"] == expected
    assert body["challenge_completed"] is (expected == "accepted")
    assert await ChallengeLog.filter(is_completed=True).count() == int(expected == "accepted")
    assert await ChallengeVerificationEvent.all().count() == 1
    sent_photo, mime, filename = provider.analyze.call_args.args
    assert mime == "image/jpeg" and filename == "challenge.jpg"
    with Image.open(io.BytesIO(sent_photo)) as cleaned:
        assert not cleaned.getexif()
    assert b"private-test-location" not in sent_photo
    assert "fiber" not in body and "nutrients" not in body


@pytest.mark.asyncio
async def test_type1_provider_error_leaves_no_completion(api, monkeypatch):
    monkeypatch.setattr(config, "FOOD_VISION_PROVIDER", "local_kfood")
    monkeypatch.setattr(challenges, "food_vision_is_configured", lambda: True)
    provider = SimpleNamespace(
        provider_kind="local_kfood_cv", analyze=AsyncMock(side_effect=FoodVisionError("offline test failure"))
    )
    monkeypatch.setattr(challenge_proofs, "get_food_vision_provider", lambda: provider)
    cycle = await start_cycle(api, rotation=1)
    response = await submit_photo(api, find_item(cycle, "fiber_diet"))
    assert response.status_code == 502, response.text
    assert await ChallengeLog.all().count() == 0
    assert await ChallengeVerification.all().count() == 0


def test_challenge_today_is_seoul_date_at_utc_day_boundary(monkeypatch):
    fixed = datetime(2026, 9, 8, 15, 5, tzinfo=UTC)

    class FixedDateTime:
        @staticmethod
        def now(tz):
            assert tz == ZoneInfo("Asia/Seoul")
            return fixed.astimezone(tz)

    monkeypatch.setattr(challenge_proofs, "datetime", FixedDateTime)
    assert challenge_today() == date(2026, 9, 9)


@pytest.mark.asyncio
async def test_photo_uses_seoul_business_date_for_today_and_future_validation(api, monkeypatch):
    business_day = date(2030, 2, 4)
    monkeypatch.setattr(challenge_proofs, "challenge_today", lambda: business_day)
    items = await catalog(api)
    cycle = await ChallengeCycle.create(
        user_id=api.user.id,
        cycle_number=1,
        start_date=business_day,
        end_date=business_day + timedelta(days=27),
        status="active",
    )
    selected = await UserChallenge.create(
        user_id=api.user.id, cycle_id=cycle.id, challenge_id=items["v3_wholegrain_easy"]["challenge_id"]
    )
    item = {"user_challenge_id": selected.id}
    accepted = await submit_photo(api, item, proof_date=business_day)
    assert accepted.status_code == 201, accepted.text
    rejected = await submit_photo(api, item, proof_date=business_day + timedelta(days=1))
    assert rejected.status_code == 422, rejected.text


@pytest.mark.asyncio
async def test_v3_cycle_status_and_check_logs_share_the_seoul_business_date(api, monkeypatch):
    business_day = date(2030, 2, 4)
    monkeypatch.setattr(challenges, "challenge_today", lambda: business_day)
    monkeypatch.setattr(challenge_proofs, "challenge_today", lambda: business_day)
    items = await catalog(api)
    response = await api.client.post(
        "/api/v1/challenge-cycles",
        headers=api.headers,
        json={
            "start_date": business_day.isoformat(),
            "challenge_ids": [items[code]["challenge_id"] for code in recommend_codes("balanced", "easy")],
            "catalog_version": CATALOG_VERSION,
        },
    )
    assert response.status_code == 201, response.text
    cycle = response.json()["data"]
    assert cycle["status"] == "active"
    water = find_item(cycle, "hydration")
    saved = await api.client.put(
        f"/api/v1/user-challenges/{water['user_challenge_id']}/logs/{business_day}",
        headers=api.headers,
        json={"is_completed": True, "value": 1},
    )
    assert saved.status_code == 200, saved.text
    future = await api.client.put(
        f"/api/v1/user-challenges/{water['user_challenge_id']}/logs/{business_day + timedelta(days=1)}",
        headers=api.headers,
        json={"is_completed": True, "value": 1},
    )
    assert future.status_code == 422


@pytest.mark.asyncio
async def test_type1_selection_is_not_available_without_real_review_configuration(api):
    items = await catalog(api)
    response = await api.client.post(
        "/api/v1/challenge-cycles",
        headers=api.headers,
        json={
            "start_date": challenge_today().isoformat(),
            "challenge_ids": [items[code]["challenge_id"] for code in recommend_codes("balanced", "easy", 1)],
            "catalog_version": CATALOG_VERSION,
        },
    )
    assert response.status_code == 503, response.text
    assert await ChallengeCycle.all().count() == 0


@pytest.mark.asyncio
async def test_late_rejected_review_cannot_overwrite_concurrent_accepted_proof(api, monkeypatch):
    monkeypatch.setattr(config, "FOOD_VISION_PROVIDER", "local_kfood")
    monkeypatch.setattr(challenges, "food_vision_is_configured", lambda: True)
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def analyze(*_):
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            await asyncio.wait_for(release.wait(), timeout=5)
            return local_result("invalid_vegetable_ratio")
        return local_result("valid")

    provider = SimpleNamespace(provider_kind="local_kfood_cv", analyze=analyze)
    monkeypatch.setattr(challenge_proofs, "get_food_vision_provider", lambda: provider)
    cycle = await start_cycle(api, rotation=1)
    item = find_item(cycle, "fiber_diet")
    late_rejection = asyncio.create_task(submit_photo(api, item, actual=2, content=image_bytes("red")))
    await asyncio.wait_for(started.wait(), timeout=5)
    try:
        draft = await submit_photo(api, item, content=image_bytes("blue"))
        assert draft.status_code == 201, draft.text
        assert draft.json()["data"]["review_status"] == "needs_confirmation"
        accepted = await submit_photo(api, item, content=image_bytes("blue"), confirmed=True)
        assert accepted.status_code == 201, accepted.text
        assert accepted.json()["data"]["challenge_completed"] is True
        original = await ChallengeVerification.get(id=accepted.json()["data"]["verification_id"])
        accepted_digest = original.evidence_digest
    finally:
        release.set()
    repeated = await asyncio.wait_for(late_rejection, timeout=5)
    assert repeated.status_code == 201, repeated.text
    assert repeated.json()["data"]["already_recorded"] is True
    await original.refresh_from_db()
    assert original.review_status == "accepted" and original.evidence_digest == accepted_digest
    assert await ChallengeVerification.all().count() == 1
    assert await ChallengeVerificationEvent.all().count() == 2
    assert (await ChallengeLog.get(user_challenge_id=item["user_challenge_id"])).value == 1


@pytest.mark.asyncio
async def test_consent_withdrawal_during_external_review_prevents_commit(api, monkeypatch):
    monkeypatch.setattr(config, "FOOD_VISION_PROVIDER", "local_kfood")
    monkeypatch.setattr(challenges, "food_vision_is_configured", lambda: True)

    async def analyze(*_):
        await Consent.filter(user_id=api.user.id).update(is_agreed=False, withdrawn_at=datetime.now(UTC))
        return local_result("valid")

    provider = SimpleNamespace(provider_kind="local_kfood_cv", analyze=analyze)
    monkeypatch.setattr(challenge_proofs, "get_food_vision_provider", lambda: provider)
    cycle = await start_cycle(api, rotation=1)
    response = await submit_photo(api, find_item(cycle, "fiber_diet"))
    assert response.status_code == 403, response.text
    assert await ChallengeVerification.all().count() == 0
    assert await ChallengeLog.all().count() == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"contains_vegetable": "false"},
        {"contains_vegetable": "true"},
        {"contains_vegetable": 1},
        {"contains_vegetable": None},
        {"vegetable_confidence": True},
        {"vegetable_confidence": "0.9"},
        {"vegetable_confidence": float("nan")},
        {"vegetable_confidence": float("inf")},
        {"vegetable_confidence": 1.1},
        {"vegetable_confidence": -0.1},
        {"vegetable_ratio_percent": float("inf")},
        {"vegetable_ratio_percent": True},
        {"detected_items": "salad"},
        {"detected_items": [{"name": "salad"}]},
    ],
)
def test_photo_review_parser_rejects_coercible_or_nonfinite_json_fields(changes):
    provider = object.__new__(OpenAIFoodVisionProvider)
    payload = {"contains_vegetable": True, "vegetable_confidence": 0.8, "detected_items": ["salad"]}
    with pytest.raises(FoodVisionError):
        provider._parse_review(json.dumps({**payload, **changes}))


@pytest.mark.parametrize("content", ["[]", "null", "not json", '{"contains_vegetable": true}'])
def test_photo_review_parser_rejects_missing_or_malformed_object(content):
    provider = object.__new__(OpenAIFoodVisionProvider)
    with pytest.raises(FoodVisionError):
        provider._parse_review(content)


def test_photo_review_parser_preserves_real_boolean_false_and_finite_confidence():
    provider = object.__new__(OpenAIFoodVisionProvider)
    parsed = provider._parse_review('{"contains_vegetable": false, "vegetable_confidence": 0.9}')
    assert parsed.contains_vegetable is False and parsed.vegetable_confidence == 0.9
    assert parsed.provider_kind == "openai_vision"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason,expected",
    [
        ("runtime_security_blocked", "보안 설정"),
        ("runtime_dependency_missing", "준비되지"),
        ("runtime_load_failed", "실행하지 못"),
    ],
)
async def test_runtime_unavailable_reports_server_problem_without_proof_or_log(api, monkeypatch, reason, expected):
    from app.vision.food_vision import FoodVisionRuntimeError

    monkeypatch.setattr(config, "FOOD_VISION_PROVIDER", "local_kfood")
    monkeypatch.setattr(config, "OPENAI_VLM_FALLBACK_ENABLED", False)
    monkeypatch.setattr(challenges, "food_vision_is_configured", lambda: True)
    provider = SimpleNamespace(
        provider_kind="local_kfood_cv", analyze=AsyncMock(side_effect=FoodVisionRuntimeError(reason))
    )
    monkeypatch.setattr(challenge_proofs, "get_food_vision_provider", lambda: provider)
    cycle = await start_cycle(api, rotation=1)
    response = await submit_photo(api, find_item(cycle, "fiber_diet"))
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["error_code"] == "PHOTO_REVIEW_UNAVAILABLE"
    assert expected in detail["message"]
    assert detail["retryable"] is False
    assert await ChallengeLog.all().count() == 0
    assert await ChallengeVerification.all().count() == 0
    assert await ChallengeVerificationEvent.all().count() == 0


@pytest.mark.asyncio
async def test_meal_context_goes_to_vlm_without_exif_and_needs_same_answers_to_confirm(api, monkeypatch):
    from app.vision.openai_vlm import OpenAIVegetableVerifier

    monkeypatch.setattr(config, "FOOD_VISION_PROVIDER", "local_kfood")
    monkeypatch.setattr(config, "OPENAI_VLM_FALLBACK_ENABLED", True)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-only-key")
    monkeypatch.setattr(challenges, "food_vision_is_configured", lambda: True)
    provider = SimpleNamespace(provider_kind="local_kfood_cv", analyze=AsyncMock(return_value=local_result("valid")))
    monkeypatch.setattr(challenge_proofs, "get_food_vision_provider", lambda: provider)
    calls = []

    async def verify(_self, photo, context):
        calls.append(context.as_dict())
        assert b"private-test-location" not in photo
        with Image.open(io.BytesIO(photo)) as image:
            assert not image.getexif()
        return {
            "is_meal_photo": True, "challenge_relevant": True, "vegetables_clearly_visible": True,
            "vegetable_presence": "present",
            "image_quality_adequate": True, "food_boundaries_clear": True, "vegetable_boundaries_clear": True,
            "multiple_images_or_screen_capture": False, "uncertainty_reasons": [],
        }

    monkeypatch.setattr(OpenAIVegetableVerifier, "verify", verify)
    item = find_item(await start_cycle(api, rotation=1), "fiber_diet")
    answers = dict(contains_kimchi="yes", strong_seasoning="no", white_food_on_white="unsure")
    response = await submit_photo(api, item, content=image_bytes(exif=True), photo_context=answers)
    assert response.json()["data"]["review_status"] == "needs_confirmation"
    assert await ChallengeLog.all().count() == 0
    draft = await ChallengeVerification.first()
    initial_digest = draft.evidence_digest
    changed = {**answers, "white_food_on_white": "no"}
    response = await submit_photo(api, item, content=image_bytes(exif=True), confirmed=True, photo_context=changed)
    assert response.json()["data"]["review_status"] == "needs_confirmation"
    assert await ChallengeLog.all().count() == 0
    draft = await ChallengeVerification.first()
    assert draft.evidence_digest != initial_digest
    response = await submit_photo(api, item, content=image_bytes(exif=True), confirmed=True, photo_context=changed)
    assert response.json()["data"]["review_status"] == "accepted"
    assert await ChallengeLog.filter(is_completed=True).count() == 1
    assert calls == [answers, changed, changed]
    response = await submit_photo(api, item, confirmed=True, photo_context=changed)
    assert response.json()["data"]["already_recorded"] is True
    assert await ChallengeLog.filter(is_completed=True).count() == 1
    assert len(calls) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["contains_kimchi", "strong_seasoning", "white_food_on_white"])
async def test_photo_context_rejects_non_tristate_answers(api, monkeypatch, field):
    monkeypatch.setattr(challenges, "food_vision_is_configured", lambda: True)
    item = find_item(await start_cycle(api, rotation=1), "fiber_diet")
    response = await submit_photo(api, item, photo_context={field: "true"})
    assert response.status_code == 422
    assert await ChallengeVerification.all().count() == 0


@pytest.mark.asyncio
async def test_vlm_failure_on_flagged_valid_cv_never_completes(api, monkeypatch):
    from app.vision.openai_vlm import OpenAIVegetableVerifier, VLMUnavailableError

    monkeypatch.setattr(config, "FOOD_VISION_PROVIDER", "local_kfood")
    monkeypatch.setattr(config, "OPENAI_VLM_FALLBACK_ENABLED", True)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-only-key")
    monkeypatch.setattr(challenges, "food_vision_is_configured", lambda: True)
    provider = SimpleNamespace(provider_kind="local_kfood_cv", analyze=AsyncMock(return_value=local_result("valid")))
    monkeypatch.setattr(challenge_proofs, "get_food_vision_provider", lambda: provider)
    monkeypatch.setattr(OpenAIVegetableVerifier, "verify", AsyncMock(side_effect=VLMUnavailableError("vlm_timeout", "private")))
    item = find_item(await start_cycle(api, rotation=1), "fiber_diet")
    response = await submit_photo(api, item, confirmed=True, photo_context={"contains_kimchi": "yes"})
    assert response.json()["data"]["review_status"] == "needs_review"
    assert response.json()["data"]["challenge_completed"] is False
    assert await ChallengeLog.all().count() == 0
    assert "시간이 초과" in response.json()["data"]["notice"]
