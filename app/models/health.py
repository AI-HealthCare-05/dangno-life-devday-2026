from tortoise import fields
from tortoise.models import Model


class Consent(Model):
    id = fields.BigIntField(primary_key=True)
    user_id = fields.BigIntField(db_index=True)
    consent_item = fields.CharField(max_length=50, default="health_data")
    version = fields.CharField(max_length=30)
    is_agreed = fields.BooleanField(default=True)
    agreed_at = fields.DatetimeField(auto_now_add=True)
    withdrawn_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "consents"


class EligibilityCheck(Model):
    id = fields.BigIntField(primary_key=True)
    user_id = fields.BigIntField(db_index=True)
    age = fields.IntField()
    has_diabetes_diagnosis = fields.BooleanField(default=False)
    has_urgent_warning_sign = fields.BooleanField(default=False)
    population_in_scope = fields.BooleanField(default=True)
    service_eligible = fields.BooleanField()
    target_segment = fields.CharField(max_length=50)
    model_eligible = fields.BooleanField()
    reason_codes = fields.JSONField(default=list)
    next_action = fields.CharField(max_length=80)
    model_key = fields.CharField(max_length=100)
    model_version = fields.CharField(max_length=100)
    feature_schema_version = fields.CharField(max_length=100)
    threshold_version = fields.CharField(max_length=100)
    safety_copy_version = fields.CharField(max_length=50)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "eligibility_checks"


class HealthDiagnosisRecord(Model):
    """Editable diagnosis assertions; eligibility answers remain an audit log."""
    id = fields.BigIntField(primary_key=True)
    user_id = fields.BigIntField(db_index=True)
    record_date = fields.DateField(db_index=True)
    source_checkup_id = fields.BigIntField(null=True, db_index=True)
    eligibility_check_id = fields.BigIntField(null=True)
    eligibility_check_ids = fields.JSONField(default=list)
    is_active = fields.BooleanField(default=True)
    deleted_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "health_diagnosis_records"
        unique_together = (("user_id", "record_date"),)


class HealthCheckup(Model):
    id = fields.BigIntField(primary_key=True)
    user_id = fields.BigIntField(db_index=True)
    eligibility_check_id = fields.BigIntField(db_index=True)
    checkup_type = fields.CharField(max_length=20, default="initial")
    checkup_date = fields.DateField()
    age = fields.IntField()
    sex = fields.CharField(max_length=10)
    height_cm = fields.FloatField()
    weight_kg = fields.FloatField()
    bmi = fields.FloatField()
    waist_cm = fields.FloatField(null=True)
    systolic_bp = fields.IntField(null=True)
    diastolic_bp = fields.IntField(null=True)
    self_rated_health = fields.CharField(max_length=20, null=True)
    meal_count_yesterday = fields.IntField(null=True)
    regular_exercise = fields.BooleanField()
    current_smoker = fields.BooleanField(null=True)
    smoking_status = fields.CharField(max_length=10, null=True)
    current_drinker = fields.BooleanField()
    exercise_days_per_week = fields.FloatField(null=True)
    exercise_minutes = fields.FloatField(null=True)
    annual_household_income_10k_krw = fields.FloatField(null=True)
    health_satisfaction_score = fields.FloatField(null=True)
    economic_satisfaction_score = fields.FloatField(null=True)
    overall_quality_of_life_score = fields.FloatField(null=True)
    hypertension_diagnosis = fields.BooleanField(null=True)
    cancer_diagnosis = fields.BooleanField(null=True)
    chronic_lung_disease_diagnosis = fields.BooleanField(null=True)
    liver_disease_diagnosis = fields.BooleanField(null=True)
    heart_disease_diagnosis = fields.BooleanField(null=True)
    cerebrovascular_disease_diagnosis = fields.BooleanField(null=True)
    psychiatric_disease_diagnosis = fields.BooleanField(null=True)
    arthritis_rheumatism_diagnosis = fields.BooleanField(null=True)
    education_level = fields.CharField(max_length=50, null=True)
    marital_status = fields.CharField(max_length=50, null=True)
    household_structure = fields.CharField(max_length=50, null=True)
    depressed_feeling_last_week = fields.CharField(max_length=20, null=True)
    sleep_difficulty_last_week = fields.CharField(max_length=20, null=True)
    feature_schema_version = fields.CharField(max_length=100)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "health_checkups"


class CurrentScreeningInput(Model):
    id = fields.BigIntField(primary_key=True)
    user_id = fields.BigIntField(db_index=True)
    health_checkup_id = fields.BigIntField(db_index=True)
    input_as_of_date = fields.DateField()
    walking_days = fields.FloatField(null=True)
    energy_kcal = fields.FloatField(null=True)
    protein_g = fields.FloatField(null=True)
    fat_g = fields.FloatField(null=True)
    carbohydrate_g = fields.FloatField(null=True)
    sodium_mg = fields.FloatField(null=True)
    region = fields.CharField(max_length=20, null=True)
    urban = fields.CharField(max_length=20, null=True)
    education = fields.CharField(max_length=30, null=True)
    income_quartile = fields.CharField(max_length=10, null=True)
    household_income_quartile = fields.CharField(max_length=10, null=True)
    hypertension_family_history = fields.BooleanField(null=True)
    diabetes_family_history = fields.BooleanField(null=True)
    alcohol_frequency = fields.CharField(max_length=30, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "current_screening_inputs"


class Prediction(Model):
    id = fields.BigIntField(primary_key=True)
    job_id = fields.CharField(max_length=36, unique=True)
    user_id = fields.BigIntField(db_index=True)
    health_checkup_id = fields.BigIntField(db_index=True)
    input_as_of_date = fields.DateField()
    model_key = fields.CharField(max_length=100)
    outcome_definition = fields.CharField(max_length=120)
    result_status = fields.CharField(max_length=40)
    risk_category = fields.CharField(max_length=20, null=True)
    internal_score = fields.FloatField(null=True)
    model_version = fields.CharField(max_length=100)
    feature_schema_version = fields.CharField(max_length=100)
    input_schema_version = fields.CharField(max_length=100)
    preprocessing_version = fields.CharField(max_length=100)
    target_definition_version = fields.CharField(max_length=100)
    calibration_version = fields.CharField(max_length=100)
    model_artifact_digest = fields.CharField(max_length=128, null=True)
    threshold_version = fields.CharField(max_length=100)
    decision_threshold = fields.FloatField(null=True)
    class_probabilities = fields.JSONField(null=True)
    output_status = fields.CharField(max_length=80, default="uncalibrated_research_probability_only")
    model_population = fields.CharField(max_length=120)
    explanation_status = fields.CharField(max_length=40, default="not_available")
    disclaimer = fields.TextField()
    predicted_at = fields.DatetimeField(auto_now_add=True)
    # v3.0 연령별 당뇨 위험 전망(생존곡선). 점추정(diabetes_incidence)에는 해당 없음.
    risk_curve_status = fields.CharField(max_length=20, default="not_applicable")
    output_definition_version = fields.CharField(max_length=100, null=True)
    # 나이별 위험 전망(그래프)용 표시 데이터. scenarios/uncertainty는 REQ-PRED-012
    # 검증 전까지 비워둔다 — is_active 없는 시나리오를 인과관계처럼 노출하지 않기 위함.
    age_risk_forecast = fields.JSONField(null=True)
    task_type = fields.CharField(max_length=80, null=True)
    threshold_scope = fields.CharField(max_length=100, null=True)
    display_allowed = fields.BooleanField(default=False)
    operational_model_activated = fields.BooleanField(default=False)
    preview_only = fields.BooleanField(default=False)
    preview_signal_level = fields.CharField(max_length=20, null=True)

    class Meta:
        table = "predictions"


class PredictionRiskCurvePoint(Model):
    """One (age, cumulative_risk) point of a survival-curve prediction (API-LIFE-004)."""

    id = fields.BigIntField(primary_key=True)
    prediction_id = fields.BigIntField(db_index=True)
    age = fields.IntField()
    cumulative_risk = fields.FloatField()
    lower = fields.FloatField()
    upper = fields.FloatField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "prediction_risk_curve_points"
        unique_together = (("prediction_id", "age"),)


class PredictionScenario(Model):
    """baseline / lifestyle_improved comparison line for a risk curve (REQ-PRED-012).

    `is_active` stays False until a scenario method is separately validated —
    the API must not surface an unvalidated scenario as if it were causal.
    """

    id = fields.BigIntField(primary_key=True)
    prediction_id = fields.BigIntField(db_index=True)
    scenario = fields.CharField(max_length=30)
    scenario_definition_version = fields.CharField(max_length=100)
    is_active = fields.BooleanField(default=False)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "prediction_scenarios"


class RiskFactor(Model):
    id = fields.BigIntField(primary_key=True)
    prediction_id = fields.BigIntField(db_index=True)
    factor_name = fields.CharField(max_length=100)
    display_name = fields.CharField(max_length=100)
    impact_direction = fields.CharField(max_length=20)
    importance_score = fields.FloatField()
    display_order = fields.IntField()
    is_modifiable = fields.BooleanField(default=False)
    message = fields.TextField()
    explanation_version = fields.CharField(max_length=100)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "risk_factors"


class Challenge(Model):
    id = fields.BigIntField(primary_key=True)
    code = fields.CharField(max_length=50, unique=True)
    title = fields.CharField(max_length=100)
    category = fields.CharField(max_length=30)
    daily_goal = fields.CharField(max_length=50)
    frequency = fields.CharField(max_length=20, null=True)
    target_count = fields.IntField(null=True)
    definition_version = fields.CharField(max_length=20, default="v1")
    description = fields.TextField()
    safety_copy = fields.TextField()
    source_title = fields.CharField(max_length=200)
    source_url = fields.CharField(max_length=500)
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "challenges"


class ChallengeCycle(Model):
    id = fields.BigIntField(primary_key=True)
    user_id = fields.BigIntField(db_index=True)
    prediction_id = fields.BigIntField(null=True, db_index=True)
    cycle_number = fields.IntField()
    start_date = fields.DateField()
    end_date = fields.DateField()
    status = fields.CharField(max_length=20, default="active", db_index=True)
    ended_reason = fields.CharField(max_length=80, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "challenge_cycles"


class UserChallenge(Model):
    id = fields.BigIntField(primary_key=True)
    user_id = fields.BigIntField(db_index=True)
    cycle_id = fields.BigIntField(db_index=True)
    challenge_id = fields.BigIntField(db_index=True)
    frequency = fields.CharField(max_length=20, null=True)
    target_count = fields.IntField(null=True)
    title_snapshot = fields.CharField(max_length=100, null=True)
    definition_version = fields.CharField(max_length=20, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "user_challenges"


class ChallengeLog(Model):
    id = fields.BigIntField(primary_key=True)
    user_id = fields.BigIntField(db_index=True)
    user_challenge_id = fields.BigIntField(db_index=True)
    log_date = fields.DateField()
    is_completed = fields.BooleanField()
    value = fields.FloatField(null=True)
    source = fields.CharField(max_length=30, default="self_report")
    note = fields.CharField(max_length=200, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "challenge_logs"
        unique_together = (("user_challenge_id", "log_date"),)


class ChallengeVerification(Model):
    id = fields.BigIntField(primary_key=True)
    user_id = fields.BigIntField(db_index=True)
    user_challenge_id = fields.BigIntField(db_index=True)
    verification_date = fields.DateField(db_index=True)
    verification_type = fields.CharField(max_length=20)
    evidence_ref = fields.CharField(max_length=500, null=True)
    evidence_digest = fields.CharField(max_length=64, null=True)
    location_accuracy_m = fields.FloatField(null=True)
    review_status = fields.CharField(max_length=20, default="accepted", db_index=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "challenge_verifications"
        unique_together = (("user_challenge_id", "verification_date"),)


class ChallengeVerificationEvent(Model):
    id = fields.BigIntField(primary_key=True)
    verification_id = fields.BigIntField(db_index=True)
    user_id = fields.BigIntField(db_index=True)
    event_type = fields.CharField(max_length=30)
    review_status = fields.CharField(max_length=20)
    evidence_digest = fields.CharField(max_length=64, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "challenge_verification_events"


class DailyChallengeReward(Model):
    id = fields.BigIntField(primary_key=True)
    user_id = fields.BigIntField(db_index=True)
    reward_date = fields.DateField(db_index=True)
    carrot_amount = fields.IntField(default=55)
    claimed_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "daily_challenge_rewards"
        unique_together = (("user_id", "reward_date"),)


class FollowUpAction(Model):
    id = fields.BigIntField(primary_key=True)
    user_id = fields.BigIntField(db_index=True)
    trigger_source = fields.CharField(max_length=30)
    trigger_entity_id = fields.BigIntField()
    action_type = fields.CharField(max_length=50, default="medical_guidance")
    reason_code = fields.CharField(max_length=80)
    priority = fields.CharField(max_length=20, default="high")
    safety_copy_version = fields.CharField(max_length=50)
    acknowledged_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "follow_up_actions"


class Feedback(Model):
    id = fields.BigIntField(primary_key=True)
    user_id = fields.BigIntField(db_index=True)
    context_type = fields.CharField(max_length=30)
    prediction_id = fields.BigIntField(null=True, db_index=True)
    recommendation_id = fields.BigIntField(null=True, db_index=True)
    rating = fields.IntField()
    comment = fields.CharField(max_length=500, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "feedbacks"
