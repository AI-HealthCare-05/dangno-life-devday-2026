from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from ai_worker.core import config as worker_config
from ai_worker.handlers import run_task
from app.apis.v1.prediction_routers import prediction_payload
from app.dtos.auth import SignUpRequest
from app.dtos.engagement import InvitationCreateRequest, SharedChallengeCreateRequest
from app.dtos.health import FeedbackCreateRequest
from app.main import app
from app.prediction.contracts import ACTIVE_MODEL, KLOSA_FEATURE_SCHEMA, PredictionFeatures, input_schema_document
from app.prediction.providers import DevelopmentPredictionProvider
from app.services.engagement import BARRIER_SUGGESTIONS, EDUCATION_CATALOG, ENCOURAGEMENT_TEXT
from app.services.health import eligibility_payload, eligibility_reason_codes

VALID_FEATURES = {
    "age": 61,
    "sex": "female",
    "bmi": 25.3,
    "smoking_status": "never",
    "current_drinker": False,
    "regular_exercise": True,
    "exercise_days_per_week": 3,
    "exercise_minutes": 40,
    "hypertension_diagnosis": None,
    "cancer_diagnosis": None,
    "chronic_lung_disease_diagnosis": None,
    "liver_disease_diagnosis": None,
    "heart_disease_diagnosis": None,
    "cerebrovascular_disease_diagnosis": None,
    "psychiatric_disease_diagnosis": None,
    "arthritis_rheumatism_diagnosis": None,
    "log_household_income": None,
    "education_level": None,
    "marital_status": None,
    "household_structure": None,
    "health_satisfaction_score": None,
    "economic_satisfaction_score": None,
    "overall_quality_of_life_score": None,
    "depressed_feeling_last_week": None,
    "sleep_difficulty_last_week": None,
}

VALID_RF25_INPUT = {
    "birth_date": "1965-01-15",
    "sex": "female",
    "height_cm": 160,
    "weight_kg": 62,
    "smoking_status": "never",
    "current_drinker": False,
    "regular_exercise": True,
    "exercise_days_per_week": 3,
    "exercise_minutes": 40,
    "previously_diagnosed_diabetes": False,
}


def test_formal_app_exposes_only_prediction_job_path_in_openapi() -> None:
    visible_paths = set(app.openapi()["paths"])
    assert "/api/v1/prediction-jobs" in visible_paths
    assert "/api/v1/prediction-jobs/{job_id}" in visible_paths
    assert "/api/v1/ai-jobs" not in visible_paths


def test_share_documents_endpoints_are_exposed() -> None:
    visible_paths = set(app.openapi()["paths"])
    assert "/api/v1/health-checkups/{checkup_id}" in visible_paths
    assert "/api/v1/feedback" in visible_paths


def test_behavior_change_and_together_endpoints_are_exposed() -> None:
    visible_paths = set(app.openapi()["paths"])
    assert "/api/v1/weekly-reports/current" in visible_paths
    assert "/api/v1/education-contents" in visible_paths
    assert "/api/v1/invitations" in visible_paths
    assert "/api/v1/connections" in visible_paths
    assert "/api/v1/shared-challenge-groups" in visible_paths


def test_shared_challenge_rejects_invalid_period_and_duplicate_members() -> None:
    with pytest.raises(ValidationError, match="종료일"):
        SharedChallengeCreateRequest.model_validate(
            {
                "title": "가족 걷기",
                "challenge_id": 1,
                "start_date": "2026-08-22",
                "end_date": "2026-08-21",
                "common_goal": "각자 주 5일 실천",
                "owner_goal": "하루 30분 걷기",
                "members": [{"user_id": 2, "personal_goal": "하루 10분 걷기"}],
            }
        )


def test_invitation_and_social_templates_do_not_share_health_data() -> None:
    invitation = InvitationCreateRequest(invitee_email="family@example.com", relation_type="family")
    assert invitation.relation_type == "family"
    assert set(ENCOURAGEMENT_TEXT) == {"cheer", "great_job", "keep_going", "together"}


def test_behavior_change_templates_are_bounded_and_medically_safe() -> None:
    assert len(EDUCATION_CATALOG) == 4
    assert "의료진" in BARRIER_SUGGESTIONS["physical_discomfort"][1]


def test_signup_minimizes_optional_identity_collection() -> None:
    SignUpRequest.model_validate(
        {
            "email": "minimal@example.com",
            "password": "Prototype123!",
            "terms_agreed": True,
        }
    )
    assert "name" not in SignUpRequest.model_fields
    assert "phone_number" not in SignUpRequest.model_fields


def test_fastapi_container_applies_migrations_before_serving() -> None:
    start_script = Path("app/start-fastapi.sh").read_text(encoding="utf-8")
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "aerich upgrade" in start_script
    assert "python -m app.core.db.upgrade_demo_sqlite" in start_script
    assert "app/start-fastapi.sh" in compose


def test_prediction_feedback_requires_owned_context_reference() -> None:
    with pytest.raises(ValidationError, match="prediction_id"):
        FeedbackCreateRequest(context_type="prediction", rating=4)
    valid = FeedbackCreateRequest(context_type="prediction", prediction_id=3, rating=4)
    assert valid.rating == 4


def test_feature_contract_matches_pr4_klosa_schema_and_rejects_extra_fields() -> None:
    features = PredictionFeatures.model_validate(VALID_FEATURES)
    assert tuple(features.as_model_record()) == KLOSA_FEATURE_SCHEMA
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PredictionFeatures.model_validate({**VALID_FEATURES, "future_diabetes_diagnosis": True})


def test_input_schema_names_leakage_fields_as_excluded() -> None:
    schema = input_schema_document()
    assert schema["feature_schema_version"] == "klosa_stage3_25features_education4_v2"
    assert "future_wave_measurements" in schema["excluded_leakage_fields"]


@pytest.mark.asyncio
async def test_development_provider_does_not_fabricate_probability_or_category() -> None:
    result = await DevelopmentPredictionProvider().predict(VALID_RF25_INPUT, as_of_date=date(2026, 8, 31))
    assert result.internal_score is None
    assert result.risk_category is None
    assert result.promotion_status == "development_only"


@pytest.mark.asyncio
async def test_worker_development_inference_returns_versioned_safe_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker_config, "TOMORROW_RUNTIME", "standard")
    result = await run_task(
        "diabetes_incidence",
        {"input": VALID_RF25_INPUT, "as_of_date": "2026-08-31"},
    )
    assert result["risk_category"] is None
    assert result["internal_score"] is None
    assert result["feature_schema_version"] == ACTIVE_MODEL.feature_schema_version
    assert "진단·처방이 아닙니다" in result["medical_notice"]


def test_eligibility_exposes_challenge_only_tier_for_age_14_to_18() -> None:
    reasons = eligibility_reason_codes(
        age=17,
        has_consent=False,
        has_diabetes_diagnosis=True,
        has_urgent_warning_sign=True,
        population_in_scope=False,
    )
    assert set(reasons) == {
        "CHALLENGE_ONLY_AGE",
        "CONSENT_REQUIRED",
        "DIAGNOSED_DIABETES",
        "URGENT_MEDICAL_ATTENTION",
        "MODEL_AGE_OUT_OF_RANGE",
        "MODEL_POPULATION_OUT_OF_SCOPE",
    }


def test_eligibility_blocks_signup_age_below_14() -> None:
    reasons = eligibility_reason_codes(
        age=13,
        has_consent=True,
        has_diabetes_diagnosis=False,
        has_urgent_warning_sign=False,
        population_in_scope=True,
    )
    assert set(reasons) == {"UNDER_MINIMUM_SERVICE_AGE", "MODEL_AGE_OUT_OF_RANGE"}


def test_service_target_matches_active_klosa_minimum_age() -> None:
    assert ACTIVE_MODEL.min_age == 45


def test_unapproved_prediction_never_exposes_internal_score_as_public_probability() -> None:
    item = SimpleNamespace(
        id=9,
        health_checkup_id=4,
        input_as_of_date=date(2026, 8, 31),
        model_key="diabetes_incidence",
        outcome_definition="next_observation_new_diabetes_diagnosis",
        result_status="development_only",
        risk_category="high",
        internal_score=0.99,
        model_version="candidate-v0",
        input_schema_version="klosa-diabetes-input-v1",
        feature_schema_version="klosa-diabetes-incident-v1",
        preprocessing_version="unapproved",
        target_definition_version="next-observation-new-diabetes-v1",
        calibration_version="unapproved",
        model_artifact_digest="",
        threshold_version="unapproved",
        decision_threshold=None,
        output_status="uncalibrated_research_probability_only",
        model_population="baseline_undiagnosed_age_45_plus",
        predicted_at=datetime.now(UTC),
        age_risk_forecast=None,
        operational_model_activated=True,
        display_allowed=True,
    )
    public = prediction_payload(item)
    assert public["risk_category"] is None
    assert public["promotion_status"] == "development_only"
    assert public["raw_probability_exposed"] is False
    assert "internal_score" not in public
    assert public["model_analysis"] is None
    assert "probability" not in public


def test_approved_caution_prediction_uses_v56_public_moderate_category() -> None:
    item = SimpleNamespace(
        id=10,
        health_checkup_id=5,
        input_as_of_date=date(2026, 8, 31),
        model_key="diabetes_incidence",
        outcome_definition="next_observation_new_diabetes_diagnosis",
        result_status="approved",
        risk_category="caution",
        internal_score=0.02,
        model_version="rf25-tuned-spec40-v1",
        input_schema_version="diabetes-incidence-api-25features-v1",
        feature_schema_version="klosa_stage3_25features_v1",
        preprocessing_version="train-median-indicator-mode-onehot-v1",
        target_definition_version="next-observation-new-diabetes-v1",
        calibration_version="unapproved",
        model_artifact_digest="abc",
        threshold_version="validation-spec043-caution-recall090-v1",
        decision_threshold=0.021153602801262862,
        output_status="approved",
        model_population="undiagnosed_klosa_age_45_105",
        predicted_at=datetime.now(UTC),
        age_risk_forecast=None,
        operational_model_activated=True,
        display_allowed=True,
    )
    public = prediction_payload(item)
    assert public["risk_category"] == "moderate"
    assert public["risk_category_label"] == "주의"
    assert public["model_analysis"]["model_score"] == 0.02


@pytest.mark.parametrize("diagnosed, urgent", [(False, False), (True, False), (False, True)])
def test_eligibility_payload_restores_saved_answers(diagnosed: bool, urgent: bool) -> None:
    reasons = (["DIAGNOSED_DIABETES"] if diagnosed else []) + (["URGENT_MEDICAL_ATTENTION"] if urgent else [])
    item = SimpleNamespace(
        id=9,
        age=51,
        has_diabetes_diagnosis=diagnosed,
        has_urgent_warning_sign=urgent,
        population_in_scope=True,
        reason_codes=reasons,
        service_eligible=not reasons,
        model_eligible=not reasons,
        target_segment="test",
        next_action="test",
        model_key="test",
        model_version="test",
        feature_schema_version="test",
        threshold_version="test",
        safety_copy_version="test",
        created_at=datetime.now(UTC),
    )
    payload = eligibility_payload(item)
    assert payload["has_diabetes_diagnosis"] is diagnosed
    assert payload["has_urgent_warning_sign"] is urgent
    assert payload["population_in_scope"] is True
    if diagnosed or urgent:
        assert payload["current_health_check_eligible"] is False
        assert payload["challenge_eligible"] is False
