"""Diagnosis events stay separate from measurements and block their calendar day."""
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from tortoise import Tortoise

from app.core import config
from app.core.db.databases import TORTOISE_APP_MODELS
from app.dependencies.security import get_request_user
from app.main import app
from app.models.health import Consent, EligibilityCheck, FollowUpAction, HealthCheckup, HealthDiagnosisRecord, Prediction
from app.models.users import User
from app.services.health_diagnosis import backfill_legacy_diagnoses, diagnosed_on, diagnosis_records, service_today

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def diagnosis_client(monkeypatch):
    monkeypatch.setattr(config, "DEMO_MODE", True)
    monkeypatch.setattr(config, "CHALLENGE_V2_ENABLED", False)
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": TORTOISE_APP_MODELS}, timezone="Asia/Seoul")
    await Tortoise.generate_schemas()
    user = await User.create(email="diagnosis@example.invalid", hashed_password="unused",
                             birthday=date(1975, 1, 1), gender="FEMALE")
    await Consent.create(user_id=user.id, version="test")
    app.dependency_overrides[get_request_user] = lambda: user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api/v1/") as client:
            yield client, user
    finally:
        app.dependency_overrides.clear()
        await Tortoise.close_connections()


async def answer(client, diagnosed=True, urgent=False):
    response = await client.post("eligibility-checks", json={
        "birth_date": "1975-01-01", "has_diabetes_diagnosis": diagnosed,
        "has_urgent_warning_sign": urgent, "population_in_scope": True,
    })
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def seed_checkup(user, eligibility_id, day):
    return await HealthCheckup.create(
        user_id=user.id, eligibility_check_id=eligibility_id, checkup_date=day,
        age=51, sex="female", height_cm=160, weight_kg=60, bmi=23.4,
        smoking_status="never", regular_exercise=False, current_drinker=False,
        exercise_days_per_week=0, exercise_minutes=0, feature_schema_version="test",
    )


async def seed_prediction(user, checkup):
    return await Prediction.create(
        job_id=str(uuid4()), user_id=user.id, health_checkup_id=checkup.id,
        input_as_of_date=checkup.checkup_date, model_key="diabetes_current_screening",
        outcome_definition="test", result_status="approved", model_version="test",
        feature_schema_version="test", input_schema_version="test", preprocessing_version="test",
        target_definition_version="test", calibration_version="test", threshold_version="test",
        model_population="test", disclaimer="test",
    )


async def test_diagnosis_is_persisted_without_fake_measurements_and_deduplicated_per_day(diagnosis_client):
    client, user = diagnosis_client
    saved = await answer(client)
    assert saved["diagnosis_record"]["label"] == "당뇨병 진단"
    assert saved["diagnosis_record"]["record_date"] == service_today().isoformat()
    assert saved["diagnosis_record"]["source"] == "self_report"
    assert saved["diagnosis_record"]["analysis_allowed"] is False
    await answer(client)
    latest = (await client.get("eligibility-checks/latest")).json()["data"]
    assert latest["has_diabetes_diagnosis"] is True
    history = (await client.get("health-checkups")).json()["data"]
    assert history["items"] == []
    assert len(history["diagnosis_records"]) == 1
    assert len((await client.get("diagnosis-records")).json()["data"]["items"]) == 1
    assert await EligibilityCheck.filter(user_id=user.id, has_diabetes_diagnosis=True).count() == 2
    assert await HealthCheckup.all().count() == 0
    assert await diagnosis_records(user.id + 1) == []


async def test_existing_same_day_results_and_all_analysis_entrypoints_are_blocked(diagnosis_client):
    client, user = diagnosis_client
    eligible = await answer(client, False)
    today = await seed_checkup(user, eligible["eligibility_check_id"], service_today())
    past = await seed_checkup(user, eligible["eligibility_check_id"], service_today() - timedelta(days=1))
    prediction = await seed_prediction(user, today)
    old_prediction = await seed_prediction(user, past)
    await answer(client)
    # A later contradictory answer never deletes the recorded day or unlocks it.
    changed = await answer(client, False)
    assert changed["model_eligible"] is False
    assert changed["current_health_check_eligible"] is False
    assert changed["analysis_blocked_for_date"] is True
    assert "DIABETES_DIAGNOSIS_RECORDED" in changed["reason_codes"]
    history = (await client.get("health-checkups")).json()["data"]
    rows = {item["checkup_id"]: item for item in history["items"]}
    assert rows[today.id]["analysis_allowed"] is False
    assert rows[past.id]["analysis_allowed"] is True
    assert (await client.get(f"health-checkups/{today.id}")).json()["data"]["analysis_allowed"] is False
    for suffix in ("", "/risk-factors", "/risk-curve"):
        response = await client.get(f"predictions/{prediction.id}{suffix}")
        assert response.status_code == 403
        assert response.json()["detail"]["error_code"] == "DIABETES_DIAGNOSIS_RECORDED"
    assert (await client.get(f"predictions/{old_prediction.id}")).status_code == 200
    predictions = (await client.get("predictions")).json()["data"]["items"]
    assert [item["prediction_id"] for item in predictions] == [old_prediction.id]
    for model_key in ("diabetes_current_screening", "diabetes_incidence"):
        response = await client.post("prediction-jobs", json={"checkup_id": today.id, "model_key": model_key})
        assert response.status_code == 403
        assert response.json()["detail"]["error_code"] == "DIABETES_DIAGNOSIS_RECORDED"
    response = await client.post("current-screening-inputs", json={
        "health_checkup_id": today.id, "input_as_of_date": service_today().isoformat(), "alcohol_frequency": 1,
    })
    assert response.status_code == 403
    payload = {"checkup_date": service_today().isoformat(), "height_cm": 160, "weight_kg": 60,
               "smoking_status": "never", "regular_exercise": False, "current_drinker": False,
               "exercise_days_per_week": 0, "exercise_minutes": 0}
    assert (await client.post("health-checkups", json=payload)).status_code == 403
    assert (await client.patch(f"health-checkups/{today.id}", json=payload)).status_code == 403
    cards = (await client.get("dashboard/summary")).json()["data"]["risk_cards"]
    assert all(card["checkup_id"] != today.id for card in cards)
    # Removing a measurement does not remove its separately persisted diagnosis day.
    assert (await client.delete(f"health-checkups/{today.id}")).status_code == 200
    assert len((await client.get("diagnosis-records")).json()["data"]["items"]) == 1


async def test_diagnosis_day_uses_korean_midnight_not_utc_date(diagnosis_client):
    client, user = diagnosis_client
    saved = await answer(client)
    event = await EligibilityCheck.get(id=saved["eligibility_check_id"])
    event.created_at = datetime(2026, 10, 14, 15, 1, tzinfo=UTC)  # Oct 15 in Korea.
    await event.save(update_fields=["created_at"])
    await HealthDiagnosisRecord.all().delete()
    await backfill_legacy_diagnoses()
    assert await diagnosed_on(user.id, date(2026, 10, 15))
    assert not await diagnosed_on(user.id, date(2026, 10, 14))
    assert (await diagnosis_records(user.id))[0]["record_date"] == "2026-10-15"


async def test_urgent_guidance_keeps_priority_while_still_recording_diagnosis(diagnosis_client):
    client, _ = diagnosis_client
    result = await answer(client, True, True)
    assert result["next_action"] == "urgent_medical_guidance"
    assert result["diagnosis_record"]["record_type"] == "diabetes_diagnosis"
    assert result["model_eligible"] is False


async def test_new_day_eligibility_does_not_erase_the_previous_diagnosis_day(diagnosis_client):
    client, _ = diagnosis_client
    saved = await answer(client)
    event = await EligibilityCheck.get(id=saved["eligibility_check_id"])
    event.created_at -= timedelta(days=1)
    await event.save(update_fields=["created_at"])
    await HealthDiagnosisRecord.filter(user_id=event.user_id).update(record_date=service_today() - timedelta(days=1))
    result = await answer(client, False)
    assert result["model_eligible"] is True
    records = (await client.get("diagnosis-records")).json()["data"]["items"]
    assert len(records) == 1
    assert records[0]["record_date"] == (service_today() - timedelta(days=1)).isoformat()

async def test_re_recording_old_health_links_diagnosis_to_original_date_and_hides_its_analysis(diagnosis_client):
    client, user = diagnosis_client
    first = await answer(client, False)
    day = service_today() - timedelta(days=14)
    checkup = await seed_checkup(user, first["eligibility_check_id"], day)
    prediction = await seed_prediction(user, checkup)
    response = await client.post("eligibility-checks", json={
        "has_diabetes_diagnosis": True, "health_checkup_id": checkup.id, "record_date": day.isoformat(),
    })
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["record_date"] == day.isoformat()
    assert data["diagnosis_record"]["source_checkup_id"] == checkup.id
    assert data["diagnosis_record"]["record_date"] == day.isoformat()
    assert not await diagnosed_on(user.id, service_today())
    rows = (await client.get("health-checkups")).json()["data"]["items"]
    assert rows[0]["analysis_allowed"] is False
    assert (await client.get(f"predictions/{prediction.id}")).status_code == 403
    assert (await client.get("predictions")).json()["data"]["items"] == []


async def test_diagnosis_can_be_corrected_to_no_without_erasing_audit_answers(diagnosis_client):
    client, user = diagnosis_client
    saved = await answer(client)
    record_id = saved["diagnosis_record"]["diagnosis_record_id"]
    response = await client.post("eligibility-checks", json={
        "has_diabetes_diagnosis": False, "diagnosis_record_id": record_id,
    })
    assert response.status_code == 200, response.text
    assert response.json()["data"]["model_eligible"] is True
    assert response.json()["data"]["diagnosis_record"] is None
    assert (await client.get("diagnosis-records")).json()["data"]["items"] == []
    assert await EligibilityCheck.filter(user_id=user.id, has_diabetes_diagnosis=True).count() == 1
    await backfill_legacy_diagnoses()
    assert await diagnosis_records(user.id) == []


async def test_corrected_diagnosis_guidance_does_not_block_home_or_new_challenge(diagnosis_client):
    client, user = diagnosis_client
    saved = await answer(client)
    action = await FollowUpAction.filter(user_id=user.id).get()
    response = await client.post("eligibility-checks", json={
        "has_diabetes_diagnosis": False,
        "diagnosis_record_id": saved["diagnosis_record"]["diagnosis_record_id"],
    })
    assert response.status_code == 200, response.text
    assert (await client.get("dashboard/summary")).json()["data"]["next_action"] is None
    actions = (await client.get("follow-up-actions")).json()["data"]["items"]
    assert actions[0]["blocking"] is False
    assert actions[0]["acknowledged_at"] is None
    await action.refresh_from_db()
    assert action.acknowledged_at is None  # Never invent a user acknowledgement.
    recommendations = (await client.get(
        "challenge-recommendations?catalog_version=evidence-v3&focus=balanced&difficulty=easy"
    )).json()["data"]
    assert recommendations["medical_guidance_required_first"] is False
    started = await client.post("challenge-cycles", json={
        "start_date": service_today().isoformat(), "catalog_version": "evidence-v3",
        "focus": "balanced", "difficulty": "easy",
        "challenge_ids": [item["challenge_id"] for item in recommendations["items"]],
    })
    assert started.status_code == 201, started.text


async def test_later_no_keeps_guidance_when_an_active_diagnosis_remains(diagnosis_client):
    client, _ = diagnosis_client
    await answer(client)
    await answer(client, False)
    actions = (await client.get("follow-up-actions")).json()["data"]["items"]
    assert actions[0]["blocking"] is True
    summary = (await client.get("dashboard/summary")).json()["data"]
    assert summary["next_action"]["reason_code"] == "DIAGNOSED_DIABETES"


async def test_diagnosis_correction_does_not_supersede_urgent_guidance(diagnosis_client):
    client, _ = diagnosis_client
    saved = await answer(client)
    await answer(client, True, True)
    response = await client.post("eligibility-checks", json={
        "has_diabetes_diagnosis": False,
        "diagnosis_record_id": saved["diagnosis_record"]["diagnosis_record_id"],
    })
    assert response.status_code == 200, response.text
    actions = (await client.get("follow-up-actions")).json()["data"]["items"]
    assert {item["reason_code"] for item in actions if item["blocking"]} == {"URGENT_MEDICAL_ATTENTION"}


async def test_deleted_diagnosis_does_not_reappear_after_import_or_restart(diagnosis_client):
    client, user = diagnosis_client
    await answer(client)
    record = (await client.get("diagnosis-records")).json()["data"]["items"][0]
    record_id = record["diagnosis_record_id"]
    assert (await client.delete(f"diagnosis-records/{record_id}")).status_code == 200
    assert (await client.delete(f"diagnosis-records/{record_id}")).status_code == 404
    await backfill_legacy_diagnoses()
    await backfill_legacy_diagnoses()
    assert await diagnosis_records(user.id) == []
    assert await EligibilityCheck.filter(user_id=user.id, has_diabetes_diagnosis=True).count() == 1
    # A fresh, explicit eligibility answer is required for new analysis.
    assert (await answer(client, False))["model_eligible"] is True


async def test_other_accounts_cannot_edit_or_delete_diagnosis_context(diagnosis_client):
    client, user = diagnosis_client
    other = await User.create(email="other@example.invalid", hashed_password="unused")
    foreign = await HealthDiagnosisRecord.create(user_id=other.id, record_date=service_today())
    before = await EligibilityCheck.all().count()
    response = await client.post("eligibility-checks", json={
        "has_diabetes_diagnosis": False, "diagnosis_record_id": foreign.id,
    })
    assert response.status_code == 404
    assert (await client.delete(f"diagnosis-records/{foreign.id}")).status_code == 404
    assert await EligibilityCheck.all().count() == before
    assert (await HealthDiagnosisRecord.get(id=foreign.id)).is_active is True


async def test_legacy_diagnosis_date_can_be_corrected_without_import_resurrection(diagnosis_client):
    client, user = diagnosis_client
    saved = await answer(client)
    record_id = saved["diagnosis_record"]["diagnosis_record_id"]
    day = service_today() - timedelta(days=14)
    response = await client.post("eligibility-checks", json={
        "has_diabetes_diagnosis": True, "diagnosis_record_id": record_id, "record_date": day.isoformat(),
    })
    assert response.status_code == 200, response.text
    await backfill_legacy_diagnoses()
    records = await diagnosis_records(user.id)
    assert len(records) == 1
    assert records[0]["record_date"] == day.isoformat()
    assert not await diagnosed_on(user.id, service_today())
