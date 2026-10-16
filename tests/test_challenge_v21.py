import asyncio
import io
from datetime import date, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from PIL import Image
from tortoise import Tortoise

from app.core import config
from app.core.db.databases import TORTOISE_APP_MODELS
from app.dependencies.security import get_request_user
from app.dtos.challenge_v2 import V2Preferences, V2Replacement, V2Review, V2SessionInput
from app.main import app
from app.models.challenge_v2 import ChallengeV2Review
from app.models.forest import ForestAvatar
from app.models.game import UserWallet
from app.models.health import ChallengeCycle, Consent, EligibilityCheck
from app.models.users import User
from app.services import challenge_v2 as svc
from app.services import challenge_v2_evidence as photos
from app.services.challenge_v2_catalog import catalog, eligible, mix_valid, select_plan

pytestmark = pytest.mark.asyncio(loop_scope="session")
NOW = datetime(2026, 9, 3, 23, 0, tzinfo=svc.KST)


def full_pref(**overrides):
    return V2Preferences(
        **dict(
            {
                "max_difficulty": "H",
                "safety_confirmed": True,
                "exercise_allowed": True,
                "dietary_changes_allowed": True,
                "photo_consent": True,
                "photo_accessible": True,
                "planned_meals": 3,
                "sugary_drink_opportunities": 3,
                "fluid_restriction": False,
                "swallowing_restriction": False,
                "therapeutic_diet": False,
                "food_allergy": False,
                "transition_consent": True,
            },
            **overrides,
        )
    )


@pytest_asyncio.fixture(loop_scope="session")
async def db(monkeypatch):
    monkeypatch.setattr(config, "DEMO_MODE", True)
    monkeypatch.setattr(config, "CHALLENGE_V2_REVIEWER_IDS", [])
    monkeypatch.setattr(svc, "now_kst", lambda: NOW)
    monkeypatch.setattr(photos, "now_kst", lambda: NOW)
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": TORTOISE_APP_MODELS}, timezone="Asia/Seoul")
    await Tortoise.generate_schemas()
    user = await User.create(
        email="v2-test@example.com", hashed_password="not-a-login", gender="FEMALE", birthday=date(1970, 1, 1)
    )
    await Consent.create(user_id=user.id, version="test")
    await EligibilityCheck.create(
        user_id=user.id,
        age=56,
        service_eligible=True,
        target_segment="test",
        model_eligible=True,
        next_action="continue",
        model_key="test",
        model_version="test",
        feature_schema_version="test",
        threshold_version="test",
        safety_copy_version="test",
    )
    try:
        yield user
    finally:
        app.dependency_overrides.clear()
        await Tortoise.close_connections()


async def direct_card(user, code, slot=1, day=None):
    if not await svc.Enrollment.filter(user_id=user.id).exists():
        await svc.enroll(user, full_pref())
    day = day or await svc.Day.create(user_id=user.id, assigned_date=NOW.date(), eligibility_snapshot={})
    item = await svc.Assignment.create(day_id=day.id, slot=slot, goal=next(x for x in catalog() if x["code"] == code))
    return item, day


def log(at=NOW - timedelta(minutes=30), **values):
    return V2SessionInput(performed_at=at, done=True, **values)


def image_bytes(color="green"):
    stream = io.BytesIO()
    Image.new("RGB", (32, 32), color).save(stream, format="PNG")
    return stream.getvalue()


async def reviewer(monkeypatch):
    staff = await User.create(
        email="review@example.com",
        hashed_password="not-a-login",
        gender="MALE",
        birthday=date(1970, 1, 1),
        is_admin=True,
    )
    monkeypatch.setattr(config, "CHALLENGE_V2_REVIEWER_IDS", [staff.id])
    return staff


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("balanced", {"routine": "E", "diet": "M", "activity": "H"}),
        ("activity_focus", {"diet": "E", "routine": "M", "activity": "H"}),
        ("diet_focus", {"activity": "E", "routine": "M", "diet": "H"}),
    ],
)
async def test_joint_constraints_and_modes(mode, expected):
    plan = select_plan(full_pref(mode=mode), 1, review_available=True)
    assert {x["domain"]: x["difficulty"] for x in plan["items"]} == expected
    assert {x["domain"] for x in plan["items"]} == {"diet", "activity", "routine"}
    assert mix_valid(plan["items"])
    assert plan["proof_mix_exception_reason"] == []


async def test_equally_ranked_catalog_choices_vary_by_day_but_stay_stable_within_day():
    daily = [
        tuple(x["code"] for x in select_plan(full_pref(), ordinal, review_available=True)["items"])
        for ordinal in range(1, 15)
    ]
    assert len(set(daily)) > 1
    assert select_plan(full_pref(), 8, review_available=True) == select_plan(full_pref(), 8, review_available=True)


async def test_custom_family_choices_are_honored_across_all_three_domains():
    plan = select_plan(
        full_pref(diet_family="D02", activity_family="A02", routine_family="R01"), 1, review_available=True
    )
    assert {item["domain"]: item["family_id"] for item in plan["items"]} == {
        "diet": "D02",
        "activity": "A02",
        "routine": "H02",
    }


async def test_daily_plan_always_includes_water_challenge_when_available():
    for mode in ["balanced", "activity_focus", "diet_focus"]:
        plan = select_plan(full_pref(mode=mode, routine_family="R01"), 3, review_available=True)
        assert any(item["family_id"] == "H02" for item in plan["items"])


async def test_drink_nonconsumer_same_difficulty_substitute():
    result = select_plan(full_pref(sugary_drink_opportunities=0), 1, review_available=True)
    assert [x["code"] for x in result["items"]] == ["H02-E", "D01-M", "A01-H"]
    assert result["substitutions"][0]["reason"] == "no_eligible_existing_drink_opportunity"
    assert mix_valid(result["items"])
    for flag in ["fluid_restriction", "swallowing_restriction", "therapeutic_diet"]:
        assert all(
            x["family_id"] != "H01" for x in select_plan(full_pref(**{flag: True}), 1, review_available=True)["items"]
        )


async def test_no_provider_no_photo_safe_exception_and_no_chairs():
    result = select_plan(full_pref(), 1)
    assert "real_visual_review_unavailable" in result["proof_mix_exception_reason"]
    assert all(x["proof_type"] != "T1" for x in result["items"])
    result = select_plan(V2Preferences(), 1)
    assert all(
        x["proof_type"] == "T3" and x["difficulty"] == "E" and x["domain"] != "activity" for x in result["items"]
    )
    assert not any(eligible(x, full_pref(), True) for x in catalog() if x["family_id"] == "A03")


async def test_weekly_limits_and_no_family_repeats():
    recent = [{"family_id": f} for f in ["D01", "A01", "H01", "R01"] for _ in range(5)]
    result = select_plan(full_pref(), 7, recent, True)
    assert not {x["family_id"] for x in result["items"]} & {"D01", "A01", "H01", "R01"}
    assert len({x["family_id"] for x in result["items"]}) == len(result["items"])


async def test_today_stable_and_old_wallet_preserved(db):
    await ForestAvatar.create(user_id=db.id, display_name="기존", carrot_balance=987)
    await svc.enroll(db, full_pref())
    results = await asyncio.gather(*(svc.today(db, True) for _ in range(4)))
    assert len({x["day_id"] for x in results}) == 1
    assert await svc.Day.all().count() == 1
    assert (await ForestAvatar.get(user_id=db.id)).carrot_balance == 987


async def test_today_migrates_old_duplicate_domains_without_deleting_history(db):
    user = await User.create(
        email="v2-domain-migration@example.com",
        hashed_password="not-a-login",
        gender="FEMALE",
        birthday=date(1970, 1, 1),
    )
    await Consent.create(user_id=user.id, version="test")
    await EligibilityCheck.create(
        user_id=user.id,
        age=56,
        service_eligible=True,
        target_segment="test",
        model_eligible=True,
        next_action="continue",
        model_key="test",
        model_version="test",
        feature_schema_version="test",
        threshold_version="test",
        safety_copy_version="test",
    )
    await svc.enroll(user, full_pref())
    day = await svc.Day.create(user_id=user.id, assigned_date=NOW.date(), eligibility_snapshot={}, policy_version="2.1")
    old_codes = ["D01-E", "D02-M", "H01-H"]
    old = [
        await svc.Assignment.create(day_id=day.id, slot=slot, goal=next(x for x in catalog() if x["code"] == code))
        for slot, code in enumerate(old_codes, 1)
    ]
    result = await svc.today(user, True)
    assert {item["goal"]["domain"] for item in result["items"]} == {"diet", "activity", "routine"}
    assert result["policy_version"] == svc.DOMAIN_MIX_POLICY_VERSION
    old_after = [await svc.Assignment.get(id=item.id) for item in old]
    assert all(item.status == "replaced" for item in old_after)
    assert await svc.Assignment.filter(day_id=day.id).count() == 6


async def test_walk_per_session_t2_upload_then_completion_and_overlap(db):
    item, day = await direct_card(db, "A01-M")
    result = await svc.record_session(db, item.id, 1, log(quantity=5))
    assert result["completed"] == 0
    await photos.upload(db, item.id, 1, image_bytes(), "proof.png", "image/png")
    assert await svc.Reward.all().count() == 0
    with pytest.raises(HTTPException) as error:
        await svc.record_session(db, item.id, 2, log(quantity=5))
    assert error.value.status_code == 409
    result = await svc.record_session(db, item.id, 2, log(at=NOW - timedelta(minutes=10), quantity=5))
    assert result["completed"] == 1 and result["items"][0]["verification_status"] == "not_required"
    assert result["items"][0]["total_quantity"] == 10


async def test_zero_hydration_intervals_no_volume_bonus_idempotent(db):
    item, day = await direct_card(db, "H02-M")
    morning = log(at=NOW.replace(hour=10), intake_ml=0)
    afternoon = log(at=NOW.replace(hour=15), intake_ml=120)
    await svc.record_session(db, item.id, 1, morning)
    result = await svc.record_session(db, item.id, 2, afternoon)
    await asyncio.gather(*(svc.record_session(db, item.id, 2, afternoon) for _ in range(4)))
    assert result["items"][0]["intake_ml"] == 120
    assert await svc.Reward.all().count() == 2  # one slot + daily chest
    assert (await UserWallet.get(user_id=db.id)).carrot_balance == 160
    assert (await ForestAvatar.get(user_id=db.id)).carrot_balance == 100  # legacy snapshot is no longer spendable
    with pytest.raises(HTTPException):
        await svc.record_session(db, item.id, 2, log(at=NOW.replace(hour=15), intake_ml=2000))


async def test_confirmed_personal_water_goal_uses_one_cup_check_and_idempotent_reward(db):
    pref = full_pref(routine_family="H02", water_goal_status="confirmed", personal_drink_goal_ml=750)
    plan = select_plan(pref, 1, review_available=True)
    water = next(item for item in plan["items"] if item["family_id"] == "H02")
    assert water["goal_unit"] == "cup"
    assert water["water_cup_ml"] == 200
    assert water["water_goal_cups"] == 4
    assert water["target_sessions"] == 1

    await svc.enroll(db, pref)
    day = await svc.Day.create(user_id=db.id, assigned_date=NOW.date(), eligibility_snapshot={})
    item = await svc.Assignment.create(day_id=day.id, slot=1, goal=water)
    with pytest.raises(HTTPException):
        await svc.record_session(db, item.id, 1, log(quantity=3, intake_ml=600))
    result = await svc.record_session(db, item.id, 1, log(quantity=4, intake_ml=800))
    await asyncio.gather(*(svc.record_session(db, item.id, 1, log(quantity=4, intake_ml=800)) for _ in range(3)))
    assert result["items"][0]["completed_sessions"] == 1
    assert result["items"][0]["intake_ml"] == 800
    assert await svc.Reward.all().count() == 2


async def test_unconfirmed_water_goal_does_not_publish_numeric_cups():
    plan = select_plan(full_pref(routine_family="H02"), 1, review_available=True)
    water = next(item for item in plan["items"] if item["family_id"] == "H02")
    assert water["water_goal_status"] == "unconfirmed"
    assert water["water_goal_cups"] is None
    assert water["goal_unit"] == "record"
    with pytest.raises(ValueError):
        full_pref(water_goal_status="confirmed", personal_drink_goal_ml=None)


async def test_t1_pending_manual_late_review_and_single_reward(db, monkeypatch):
    staff = await reviewer(monkeypatch)
    item, day = await direct_card(db, "D01-M")
    await svc.record_session(db, item.id, 1, log(note="오이·두부·밥"))
    result = await photos.upload(db, item.id, 1, image_bytes(), "proof.png", "image/png")
    assert result["items"][0]["verification_status"] == "pending" and result["completed"] == 0
    assert await svc.Reward.all().count() == 0
    proof = await photos.Evidence.get(assignment_id=item.id)
    verdict = V2Review(
        status="passed",
        criteria_results={k: True for k in item.goal["visual_criteria"]},
        reason="보이는 식품 구성 확인",
        viewed_evidence=True,
        generation=1,
    )
    monkeypatch.setattr(svc, "now_kst", lambda: NOW + timedelta(days=1))
    monkeypatch.setattr(photos, "now_kst", lambda: NOW + timedelta(days=1))
    result = await photos.review_photo(staff, proof.id, verdict)
    await photos.review_photo(staff, proof.id, verdict)
    assert result["date"] == "2026-09-03" and result["completed"] == 1
    assert await svc.Reward.all().count() == 2
    assert await ChallengeV2Review.all().count() == 1


async def test_inconclusive_no_fake_pass_expiry_and_unauthorized(db, monkeypatch):
    staff = await reviewer(monkeypatch)
    item, _ = await direct_card(db, "D01-E")
    await svc.record_session(db, item.id, 1, log(note="혼합요리"))
    await photos.upload(db, item.id, 1, image_bytes(), "meal.png", "image/png")
    proof = await photos.Evidence.get(assignment_id=item.id)
    request = V2Review(
        status="inconclusive",
        criteria_results={"vegetable_visible": False},
        reason="가려져 판단 곤란",
        viewed_evidence=True,
        generation=1,
    )
    with pytest.raises(HTTPException):
        await photos.review_photo(db, proof.id, request)
    result = await photos.review_photo(staff, proof.id, request)
    assert result["completed"] == 0 and not result["chest_issued"]
    stranger = await User.create(
        email="other@example.com", hashed_password="none", gender="MALE", birthday=date(1970, 1, 1)
    )
    with pytest.raises(HTTPException) as error:
        await photos.read_photo(stranger, proof.id)
    assert error.value.status_code == 404
    monkeypatch.setattr(photos, "now_kst", lambda: NOW + timedelta(days=8))
    await photos.purge_expired()
    assert (await photos.Evidence.get(id=proof.id)).content is None
    assert await svc.Reward.all().count() == 0


async def test_mime_limits_exif_and_external_url():
    raw = image_bytes()
    for filename, mime in [("x.svg", "image/svg+xml"), ("x.jpg", "image/jpeg"), ("x.png", "text/html")]:
        with pytest.raises(HTTPException):
            photos.sanitize_photo(raw, filename, mime)
    with pytest.raises(HTTPException):
        photos.sanitize_photo(b"https://evil.example/image.png", "x.png", "image/png")
    with pytest.raises(HTTPException) as exc:
        photos.sanitize_photo(b"0" * (photos.MAX_BYTES + 1), "x.png", "image/png")
    assert exc.value.status_code == 413
    image = Image.new("RGB", (10, 10))
    exif = Image.Exif()
    exif[315] = "private-person"
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    clean, _ = photos.sanitize_photo(buffer.getvalue(), "x.jpg", "image/jpeg")
    assert not Image.open(io.BytesIO(clean)).getexif()


async def test_ownership_duplicate_photo_and_withdrawal(db):
    one, day = await direct_card(db, "D03-E")
    two, _ = await direct_card(db, "A01-E", 2, day)
    await photos.upload(db, one.id, 1, image_bytes(), "meal.png", "image/png")
    await photos.upload(db, one.id, 1, image_bytes(), "meal.png", "image/png")
    with pytest.raises(HTTPException) as error:
        await photos.upload(db, two.id, 1, image_bytes(), "meal.png", "image/png")
    assert error.value.status_code == 409
    assert await photos.Evidence.all().count() == 1
    await svc.enroll(db, full_pref(photo_consent=False))
    assert (await photos.Evidence.first()).content is None


@pytest.mark.parametrize("field", ["has_diabetes_diagnosis", "has_urgent_warning_sign"])
async def test_server_safety_every_mutation(db, field):
    item, _ = await direct_card(db, "H02-E")
    await EligibilityCheck.filter(user_id=db.id).update(**{field: True})
    with pytest.raises(HTTPException) as error:
        await svc.record_session(db, item.id, 1, log(at=NOW.replace(hour=10), intake_ml=0))
    assert error.value.status_code == 403


async def test_legacy_cycle_next_day_and_no_retroactive_changes(db):
    old = await ChallengeCycle.create(
        user_id=db.id,
        prediction_id=1,
        cycle_number=1,
        start_date=NOW.date(),
        end_date=NOW.date() + timedelta(days=27),
        status="active",
    )
    result = await svc.enroll(db, full_pref())
    assert result["starts_on"] == "2026-09-04"
    assert not (await svc.today(db, True))["items"]
    assert (await ChallengeCycle.get(id=old.id)).status == "active"


async def test_replacement_retains_history_and_rechecks_safety(db):
    item, day = await direct_card(db, "A01-M")
    await svc.record_session(db, item.id, 1, log(quantity=5))
    await svc.enroll(db, full_pref(photo_consent=False))
    result = await svc.replace(db, item.id, V2Replacement(template_code="A01-M-C", reason="accessibility"))
    assert result["items"][0]["goal"]["code"] == "A01-M-C"
    assert await svc.Session.filter(assignment_id=item.id).count() == 1
    assert (await svc.Assignment.get(id=item.id)).status == "replaced"
    assert "replacement_accessibility" in result["proof_mix_exception_reason"]


async def test_api_dashboard_same_plan_and_extra_fields_rejected(db):
    app.dependency_overrides[get_request_user] = lambda: db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.put("/api/v1/challenge-v2/preferences", json=full_pref().model_dump())
        assert response.status_code == 200
        response = await client.post("/api/v1/challenge-v2/today")
        assert response.status_code == 200
        day = response.json()["data"]
        summary = (await client.get("/api/v1/dashboard/summary")).json()["data"]
        assert summary["daily_challenge_v2"]["items"] == day["items"]
        response = await client.put(
            f"/api/v1/challenge-v2/assignments/{day['items'][0]['id']}/sessions/1",
            json={"performed_at": NOW.isoformat(), "done": True, "is_completed": True},
        )
        assert response.status_code == 422


async def test_revoked_photo_cannot_complete_after_reconsent(db):
    item, _ = await direct_card(db, "D03-E")
    await photos.upload(db, item.id, 1, image_bytes(), "meal.png", "image/png")
    await svc.enroll(db, full_pref(photo_consent=False))
    await svc.enroll(db, full_pref())
    result = await svc.record_session(db, item.id, 1, log(note="밥과 채소 기록"))
    assert result["completed"] == 0
    assert await svc.Reward.all().count() == 0


async def test_midnight_new_assignment_and_reject_old_log(db, monkeypatch):
    await svc.enroll(db, full_pref())
    before = await svc.today(db, True)
    monkeypatch.setattr(svc, "now_kst", lambda: NOW + timedelta(hours=2))
    after = await svc.today(db, True)
    assert before["day_id"] != after["day_id"]
    assert after["date"] == "2026-09-04"
    with pytest.raises(HTTPException) as error:
        await svc.record_session(db, before["items"][0]["id"], 1, log())
    assert error.value.status_code == 409


async def test_upload_api_limit_and_cross_owner(db):
    item, _ = await direct_card(db, "D03-E")
    app.dependency_overrides[get_request_user] = lambda: db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        path = f"/api/v1/challenge-v2/assignments/{item.id}/evidence/1"
        assert (await client.put(path, files={"photo": ("x.png", b"not a picture", "image/png")})).status_code == 422
        assert (await client.put(path, content=b"a" * (11 * 1024 * 1024 + 1))).status_code == 413
        assert (await client.put(path, json={"url": "https://example.com/photo"})).status_code == 422
        assert (await client.put(path, files={"photo": ("x.png", image_bytes(), "image/png")})).status_code == 200
        proof = await photos.Evidence.get(assignment_id=item.id)
        stranger = await User.create(
            email="stranger@example.com", hashed_password="none", gender="MALE", birthday=date(1970, 1, 1)
        )
        app.dependency_overrides[get_request_user] = lambda: stranger
        assert (await client.get(f"/api/v1/challenge-v2/evidence/{proof.id}")).status_code == 404
        assert (await client.get("/api/v1/challenge-v2/history/2026-09-03")).status_code == 404


async def test_pixel_limit_and_false_review_cannot_pass(db, monkeypatch):
    monkeypatch.setattr(photos, "MAX_PIXELS", 4)
    with pytest.raises(HTTPException):
        photos.sanitize_photo(image_bytes(), "x.png", "image/png")
    monkeypatch.setattr(photos, "MAX_PIXELS", 16_000_000)
    staff = await reviewer(monkeypatch)
    item, _ = await direct_card(db, "D01-E")
    await svc.record_session(db, item.id, 1, log(note="구성 확인"))
    await photos.upload(db, item.id, 1, image_bytes(), "x.png", "image/png")
    proof = await photos.Evidence.get(assignment_id=item.id)
    with pytest.raises(HTTPException) as error:
        await photos.review_photo(
            staff,
            proof.id,
            V2Review(
                status="passed",
                criteria_results={"vegetable_visible": False},
                reason="불충족",
                viewed_evidence=True,
                generation=1,
            ),
        )
    assert error.value.status_code == 422
    assert await svc.Reward.all().count() == 0


async def test_content_disabled_and_followup_enforced(db, monkeypatch):
    from app.models.health import FollowUpAction

    await FollowUpAction.create(
        user_id=db.id,
        trigger_source="test",
        trigger_entity_id=1,
        action_type="medical_consultation",
        reason_code="test",
        priority="high",
        safety_copy_version="test",
    )
    with pytest.raises(HTTPException) as error:
        await svc.enroll(db, full_pref())
    assert error.value.status_code == 403
    monkeypatch.setattr(config, "DEMO_MODE", False)
    monkeypatch.setattr(config, "CHALLENGE_V2_ENABLED", False)
    with pytest.raises(HTTPException) as error:
        await svc.today(db, True)
    assert error.value.status_code == 503
