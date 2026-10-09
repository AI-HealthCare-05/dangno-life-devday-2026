from pathlib import Path

from app.main import app
from app.prediction.contracts import ACTIVE_MODEL

ROOT = Path(__file__).resolve().parents[1]


def test_legacy_entrypoint_uses_formal_application() -> None:
    from src.backend.main import app as compatibility_app

    assert compatibility_app is app
    paths = app.openapi()["paths"]
    assert "/api/v1/prediction-jobs" in paths
    assert "/api/v1/ai-jobs" not in paths


def test_home_has_accessibility_and_medical_notice() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert "본문으로 바로가기" in html
    assert "진단·처방" in html
    assert "간당간당 개발용 서비스" in html
    assert "DEVELOPMENT" not in html
    assert "확률 비공개" not in html
    assert "약을 끊으세요" not in html + script
    assert "약을 시작하세요" not in html + script


def test_reviewed_eligibility_and_failure_guidance_is_user_specific() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")
    styles = (ROOT / "src/frontend/styles.css").read_text(encoding="utf-8")

    for screen_code in ("E02", "E03", "D01", "E05"):
        assert screen_code in script
    for reason_code in (
        "UNDER_MINIMUM_SERVICE_AGE",
        "URGENT_MEDICAL_ATTENTION",
        "DIAGNOSED_DIABETES",
        "MODEL_AGE_OUT_OF_RANGE",
    ):
        assert reason_code in script
    assert "분석 실패는 당뇨병 위험도가 높다는 의미가 아닙니다." not in html
    assert "입력 내용 확인하기" in html
    assert "다시 시도하기" in html
    assert "증상이 있으면 의료기관 안내가 우선돼요." not in html
    assert "연령대는 별도 질문 없이 자동으로 구분합니다." not in html
    assert 'class="eligibility-profile-fields"' in html
    assert ".eligibility-profile-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))" in styles
    assert ".branch-result{max-width:none;width:100%" in styles
    assert '$("#eligibility-form").addEventListener("change", () => {' in script
    assert script.count('$("#eligibility-guidance").hidden = true;') >= 4


def test_emergency_questionnaire_matches_planned_two_stage_branches() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert "응급상황 사전 문진표" in html
    assert "1. 지금 긴급한 증상이 있나요?" in html
    assert 'id="open-emergency-questionnaire"' in html
    assert 'role="dialog" aria-modal="true"' in html
    assert "문진 결과 적용하기" in html
    assert "이 문진은 당뇨병을 진단하기 위한 검사가 아닙니다." in html
    assert 'name="urgent-symptom"' not in html
    assert 'name="same-day-symptom"' not in html
    assert html.count('name="urgent-summary"') == 3
    assert html.count('name="same-day-summary"') == 3
    assert "증상이 있습니다" in html
    assert "증상이 없습니다" in html
    assert "잘 모르겠습니다" in html
    assert "선택한 증상이 없습니다." not in html
    assert "심한 가슴 통증, 숨쉬기 매우 어려움, 의식이 흐려지는 등의 증상을 확인해 주세요." not in html
    assert "119에 전화하기" in html
    assert "현재 위치 확인하기" in html
    assert "주변 응급실 보기" in html
    assert 'id="emergency-facility-search"' in html
    assert 'id="emergency-address-form"' not in html
    assert 'id="emergency-address"' not in html
    assert 'id="emergency-facility-map"' not in html
    assert "api(`/emergency-facilities/nearby?" in script
    assert "renderEmergencyFacilities" in script
    assert "국립중앙의료원 응급의료기관 정보" in script
    assert "가까운 의료기관 찾기" in html
    assert "전화 상담 가능한 기관 보기" in html
    assert "의식이 없거나 삼키기 어려운 사람에게 음식이나 음료를 억지로 먹이지 마세요." in html
    assert "SAME_DAY_MEDICAL_ATTENTION" in script
    assert "has_urgent_warning_sign: false" in script
    assert 'params.get("preview") !== "emergency-questionnaire"' in script


def test_high_risk_prioritizes_medical_guidance_and_hides_internal_versions() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert "검사·상담 안내 보기" in script
    assert 'prediction.result_status === "approved"' in script
    assert 'prediction.promotion_status === "approved"' in script
    assert 'const challengeButton = $("#to-challenges")' in script
    assert (
        'challengeButton.textContent = requiresMedicalResultGuidance() ? "검사·상담 안내 보기" : content.next' in script
    )
    assert "const canDisplayRisk = isApprovedRisk || Boolean(developmentPreviewRisk)" in script
    assert 'renderPredictionStatus("succeeded", { resultAvailable: canDisplayRisk, showResult: true })' in script
    assert 'factors?.status === "approved"' in script
    assert "factors?.shap_claimed === true" in script
    assert '$("#risk-confirm-card").hidden = false' in script
    assert 'id="risk-traffic-light" role="img"' in html
    assert 'data-risk="pending"' in html
    assert 'id="risk-confirm-score"' not in html
    assert "숫자 점수는 표시하지 않아요" not in html
    assert "prediction.display_score" not in script
    assert "prediction.public_display_score" not in script
    assert "승인된 점수가 도착하면 표시합니다." not in script
    assert 'id="risk-confirm-short"' not in html
    assert 'id="risk-confirm-message"' not in html
    assert 'id="risk-preview-controls"' in html
    assert 'data-risk-preview="low"' in html
    assert 'data-risk-preview="caution"' not in html
    assert 'data-risk-preview="high"' in html
    assert "function setForecastRiskPreview(risk)" in script
    assert "normalizeRiskKey(prediction)" in script
    assert html.index('id="risk-confirm-card"') < html.index('id="future-risk-category"')
    assert 'id="result-unavailable"' in html
    assert "모델 검증 중" in script
    assert "medical-guidance-detail" in html + script
    assert 'id="facility-address-form"' in html
    assert 'id="facility-address"' in html
    assert 'id="medical-facility-map"' in html
    assert "coordinatesForAddress" in script
    assert "정보 확인일" in script
    assert 'id="model-version"' not in html
    assert "prediction.model_version" not in script
    assert "prediction.feature_schema_version" not in script
    assert "약 2년 뒤" not in html


def test_mvp_excludes_research_forecast_and_retains_separate_results() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")
    for panel in ("risk-forecast-panel", "age-risk-chart", "uncertainty-panel", "scenario-comparison-title"):
        assert f'id="{panel}"' not in html
    assert 'id="risk-confirm-card"' in html
    assert 'id="future-risk-category"' in html
    assert "/research/models/" not in script
    assert "isPublicRiskDisplayAllowed" in script


def test_rule_forecast_preview_is_local_opt_in_and_non_predictive() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert 'id="rule-forecast-preview"' not in html
    assert 'includes(params.get("preview")) || !isDemoEnvironment()' in script
    assert "tryRunJunhyukModelDemo" not in script
    assert "/research/models/" not in script
    assert "실제 모델을 호출하지 않았습니다" in script
    assert "운영 승인 결과가 아닙니다" in html


def test_together_shares_only_challenge_completion_status() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert "건강정보와 예측 결과는 공유하지 않습니다." in html
    assert "챌린지 수행 상태만 공유" in script
    assert "completed_days" in script
    assert "shared-member-progress" in script


def test_service_and_model_age_are_separately_explained() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")

    assert "만 14~18세는 생활습관 챌린지" in html
    assert "만 19~44세는 현재 건강 신호" in html
    assert "만 45세 이상은 미래 발병 위험" in html


def test_health_form_keeps_current_backend_smoking_field_and_rf25_field() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert 'name="smoking-status"' in html
    for value in ("never", "former", "current"):
        assert f'value="{value}"' in html
    assert 'const smokingStatus = selectedRadioValue("smoking-status")' in script
    assert "smoking_status: smokingStatus" in script
    assert 'current_smoker: smokingStatus === "current"' in script
    assert 'feature_schema_version: "klosa_stage3_25features_v1"' not in script


def test_health_form_uses_rf25_exercise_detail_contract() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert 'id="exercise-days"' in html
    assert 'min="0" max="7"' in html
    assert 'id="exercise-minutes"' in html
    assert 'min="0" max="720"' in html
    assert "exercise_days_per_week:" in script
    assert "exercise_minutes:" in script
    assert 'id="fasting-glucose"' not in html
    assert 'id="meal-count"' not in html
    assert 'id="walking-days"' not in html
    assert 'id="alcohol-frequency" required' in html
    assert '<option value="1" selected>최근 1년간 전혀 마시지 않음</option>' in html
    assert '<option value="8">비해당(평생 음주 경험 없음)</option>' in html
    assert 'id="region"' in html
    assert 'id="diabetes-family-history"' in html
    assert 'id="hypertension-family-history"' in html
    assert 'education: nullableSelectValue("education-level")' not in script
    assert '<option value="code_97">' not in html
    assert '<option value="code_2">별거</option>' in html
    assert '<option value="code_4">사별 또는 실종</option>' in html
    assert '<option value="code_1" selected>잠깐 또는 없음(하루 미만)</option>' in html
    assert '<option value="code_4">항상(5~7일)</option>' in html
    assert 'moderate: "주의"' in script
    assert 'days.value = "0"' in script
    assert 'minutes.value = "0"' in script
    assert '<select id="smoking-status" name="smoking-status" required>' in html
    assert "운동하지 않는 경우에는 두 값이 자동으로 0으로 저장됩니다." not in html
    assert html.index('id="smoking-status-title"') < html.index('id="current-drinker-title"')
    lifestyle = html.split('id="lifestyle-input-panel"', 1)[1].split('id="health-review-panel"', 1)[0]
    assert (
        lifestyle.index('id="smoking-status-title"')
        < lifestyle.index('id="current-drinker-title"')
        < lifestyle.index('for="alcohol-frequency"')
        < lifestyle.index('for="health-satisfaction-score"')
    )
    assert "days.disabled = !isRegularExercise" in script
    assert 'card.classList.toggle("disabled", !isRegularExercise)' in script
    assert 'id="regular-exercise" name="regular-exercise" type="radio" value="true" required' in lifestyle
    assert 'value="true" checked' not in lifestyle.split('id="regular-exercise-title"', 1)[1].split("</div>", 2)[0]


def test_login_resume_syncs_active_health_consent_before_health_gates() -> None:
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")
    resume = script.split("async function resumeAuthenticatedAccount()", 1)[1].split(
        '$("#login-form").addEventListener("submit"', 1
    )[0]

    assert 'const consents = await api("/consents")' in resume
    assert resume.index("syncHealthConsentState(consents)") < resume.index(
        "if (!profileSaved || !hasHealthDataConsent(consents))"
    )
    assert 'state.healthConsentStatus === "active"' in script


def test_health_submit_refreshes_consent_before_blocking_reanalysis() -> None:
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")
    consent_guard = script.split("async function ensureActiveHealthConsent", 1)[1].split(
        "function showAccountRecovery", 1
    )[0]
    submit_handler = script.split('$("#health-form").addEventListener("submit"', 1)[1].split(
        '$("#retry-analysis").addEventListener', 1
    )[0]
    onboarding_handler = script.split('$$("[data-onboarding-step]").forEach', 1)[1].split('$("#profile-edit")', 1)[0]

    assert "await refreshHealthConsentState()" in consent_guard
    assert 'if (state.healthConsentStatus === "active") return true;' in consent_guard
    assert "openHealthConsentSettings({ blockedAction: actionLabel });" in consent_guard
    assert 'if (!await ensureActiveHealthConsent("건강정보 저장")) return;' in submit_handler
    assert 'if (targetStep >= 4 && !await ensureActiveHealthConsent("건강정보 입력")) return;' in onboarding_handler


def test_dashboard_health_edit_enters_reanalysis_flow_immediately_after_save() -> None:
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")
    dashboard_edit = script.split("async function openDashboardHealthEdit()", 1)[1].split(
        "function hydrateSavedHealthForm", 1
    )[0]
    submit_handler = script.split('$("#health-form").addEventListener("submit"', 1)[1].split(
        '$("#retry-analysis").addEventListener', 1
    )[0]
    local_save = submit_handler.split("if (isLocalPreview())", 1)[1].split("} else {", 1)[0]
    remote_save = submit_handler.split("const payload = healthCheckupPayload();", 1)[1].split(
        "if (state.currentHealthOnly)", 1
    )[0]

    assert "state.returningUser = true;" in dashboard_edit
    assert 'api("/eligibility-checks/latest")' in dashboard_edit
    assert "syncReturningEligibilityState(latestEligibility)" in dashboard_edit
    assert "openReturningUserHealthEdit();" in dashboard_edit
    assert local_save.index("if (shouldRequestPrediction) showStep(5);") < local_save.index(
        "await saveCurrentScreeningInputSnapshot();"
    )
    assert remote_save.index("if (shouldRequestPrediction) showStep(5);") < remote_save.index(
        "await saveCurrentScreeningInputSnapshot();"
    )


def test_dashboard_health_history_controls_and_today_risk_summary_are_wired() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")
    dashboard_router = (ROOT / "app/apis/v1/dashboard_routers.py").read_text(encoding="utf-8")

    assert 'id="dashboard-risk-image"' in html
    assert 'id="dashboard-find-nearby-medical-facilities"' in html
    assert 'id="health-history-pagination"' in html
    assert 'id="health-history-filter"' in html
    assert "data-health-history-edit=" in script
    assert "data-health-history-delete=" in script
    assert "data-health-history-result=" in script
    assert 'method: "DELETE"' in script
    assert "async function openSavedAnalysisResult(checkupId)" in script
    assert "const pageSize = 10;" in script
    assert 'card.model_key === "diabetes_current_screening"' in script
    assert "latest_prediction_for_model_key(user.id, CURRENT_SCREENING_MODEL_KEY)" in dashboard_router
    assert 'method: editingId ? "PATCH" : "POST"' in script
    assert 'error.code !== "CHECKUP_ALREADY_PREDICTED"' in script
    assert 'checkup_type: "reassessment"' in script
    assert "hyeoldangi-face-${imageRisk}.png" in script


def test_follow_up_flow_keeps_session_and_returns_results_to_review() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")
    intro_script = (ROOT / "src/frontend/intro-retro-app.js").read_text(encoding="utf-8")
    retro_intro_script = (ROOT / "src/frontend/retro-intro.js").read_text(encoding="utf-8")
    retro_intro_css = (ROOT / "src/frontend/retro-intro.css").read_text(encoding="utf-8")

    assert 'id="height" type="number" min="120" max="220" step="0.1"' in html
    assert "if (state.step === 6)" in script
    assert 'showHealthInputPanel("review")' in script
    assert '"챌린지 실천이 기록됐습니다."' in script
    assert "async function restoreIntroSession()" in intro_script
    auth_session = (ROOT / "src/frontend/auth-session.js").read_text(encoding="utf-8")
    assert "window.GandangAuthSession.resolve" in intro_script
    assert 'fetchImpl("/api/v1/auth/token/refresh", options)' in auth_session
    assert 'fetchImpl("/api/v1/users/me"' in auth_session
    assert 'Authorization: "Bearer " + token' in auth_session
    assert 'window.addEventListener("pageshow"' in intro_script
    assert "showWorkspaceNav = isLoggedIn && !needsAccountSetup" in intro_script
    assert "if (introRouteNav) introRouteNav.hidden = true;" in intro_script
    assert 'classList.toggle("intro-authenticated"' in intro_script
    assert "window.location.assign(`/?workspace=${encodeURIComponent(destination)}`);" in intro_script
    assert "openModernWorkspace(button.dataset.topWorkspace);" in intro_script
    assert "async function openRequestedWorkspace()" in script
    assert 'params.get("workspace")' in script
    assert 'window.history.replaceState({}, "",' in script
    assert ".intro-authenticated:has(.retro-intro) .topbar" in retro_intro_css
    navigation_css = (ROOT / "src/frontend/navigation.css").read_text(encoding="utf-8")
    intro_html = (ROOT / "src/frontend/intro-retro.html").read_text(encoding="utf-8")
    assert "/static/navigation.css" in intro_html
    assert 'id="font-toggle"' in intro_html
    assert ".font-toggle-button" in navigation_css
    assert "routeNav.hidden = true;" in retro_intro_script
    assert 'window.setTimeout(clearMessage, kind === "success" ? 6000 : 4000)' in script
    assert "window.setTimeout(clearMessage, 2000)" in intro_script


def test_mvp_exposes_returning_login_and_extended_dashboard_actions() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    for label in (
        "이메일로 초대",
        "초대 코드로 초대",
        "워치 연결하기",
        "근거 자료에서 찾기",
        "결과통보서 업로드",
        "PDF로 받기",
    ):
        assert label in html
    assert "기존 계정으로 로그인해 주세요" in script
    assert "accept-shared" in script
    assert "cheer-shared" in script
    assert "[hidden]{display:none!important}" in (ROOT / "src/frontend/styles.css").read_text(encoding="utf-8")


def test_invite_method_starts_unselected_and_reveals_only_requested_panel() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert 'id="relation-type"' not in html
    assert 'id="invite-nickname"' not in html
    assert 'id="invite-tab-email" type="button" aria-expanded="false"' in html
    assert 'id="invite-tab-code" type="button" aria-expanded="false"' in html
    assert 'id="invite-form"' in html and 'data-invite-panel="email" hidden' in html
    assert 'id="invite-panel-code"' in html and 'data-invite-panel="code" hidden' in html
    assert "panel.hidden = !selected" in script
    assert 'button.addEventListener("click", () => setInviteMode(button.dataset.inviteMode))' in script


def test_demo_controls_and_invite_placeholders_are_environment_safe() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert 'class="status-demo-panel" aria-label="분석 결과 상태 확인용" hidden' in html
    assert "statusPanel.hidden = !isDemoEnvironment()" in script
    assert '<strong id="forest-invite-code">7F K3 Q1</strong>' not in html
    assert '<strong id="forest-invite-code">초대 코드 발급 준비 중</strong>' in html
    assert 'id="copy-invite-code" type="button" disabled' in html
    assert 'codeNode.dataset.copyValue = isDemo ? "DEMO-CODE" : ""' in script
    assert "로컬 화면 확인용 코드입니다. 실제 초대에는 사용할 수 없어요." in script
    assert "실제 초대 코드 API가 연결되면 여기에서 확인할 수 있어요." in html + script


def test_invite_api_response_is_rendered_as_text_not_html() -> None:
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert "function renderInviteCodeResult(result = {})" in script
    assert "codeNode.textContent = inviteCode" in script
    assert "codeNode.dataset.copyValue = inviteCode" in script
    assert "renderInviteCodeResult(result)" in script
    assert "box.innerHTML = `<div><strong>초대 이메일을 보낼 준비가 되었습니다" not in script


def test_frontend_uses_current_backend_signup_profile_and_prediction_contract() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert 'id="display-name"' not in html
    assert 'name: $("#display-name").value' not in script
    assert 'id="signup-birth-date" type="date"' in html
    assert 'id="signup-gender" required' in html
    assert 'email, password, terms_agreed: $("#personal-consent").checked' not in script
    assert "birth_date: birthDate" in script
    user_router = (ROOT / "app/apis/v1/user_routers.py").read_text(encoding="utf-8")
    # The backend deliberately exposes both documented profile and forest aliases.
    assert 'api("/users/me", { method: "PATCH"' in script
    assert '@user_router.patch("/me",' in user_router
    assert '@user_router.patch("/me/profile",' in user_router
    assert 'birthday: $("#eligibility-birth-date").value' in script
    assert '$("#eligibility-birth-date").value = birthDate' in script
    assert 'state.token = state.token || "local-demo-token"' not in script
    assert 'const isDemoEnvironment = () => ["localhost", "127.0.0.1", "::1"]' in script
    assert "if (!isDemoEnvironment()) return;" in script
    assert "API 연결 전이라 로컬 화면 확인 모드로 계속합니다." not in script
    assert "API 연결 전이라 기존 회원 화면 확인 모드로 로그인했습니다." not in script
    assert 'data-demo-status="timeout"' not in html
    assert 'data-demo-status="model_not_ready"' not in html
    assert 'renderPredictionStatus("failed", {' in script
    assert 'errorCode: isTimeout ? "TIMEOUT"' in script
    assert "await requestPredictionModel(modelKey)" in script
    assert '"diabetes_current_screening"' in script
    assert '"diabetes_incidence"' in script
    assert "state.currentScreeningPrediction" in script


def test_signup_and_existing_login_use_separate_forms() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert 'id="sidebar-signup"' in html
    assert 'id="sidebar-login"' in html
    assert 'id="signup-form"' in html
    assert 'id="login-form" class="login-form" hidden' in html
    assert 'id="login-email" type="email"' in html
    assert 'id="login-password" type="password"' in html
    assert "생년월일과 성별은 가입할 때 저장한 정보를 불러옵니다." in html
    assert '$("#login-form").addEventListener("submit"' in script
    assert 'email: $("#login-email").value, password: $("#login-password").value' in script
    assert '$("#login-existing")' not in script


def test_challenge_grid_opens_rag_custom_challenge_without_manual_editor() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert 'id="custom-challenge-editor"' not in html
    assert 'id="custom-challenge-title"' not in html
    assert 'id="rag-challenge-generator"' in html
    assert 'id="close-rag-challenge"' in html
    assert "맞춤 챌린지 추가" in script
    assert 'id="open-rag-challenge"' in script
    assert "function customChallengeSlot()" in script
    assert "function closeRagChallengeGenerator" in script
    assert 'button.classList.toggle("active", active)' in script
    assert "function renderChallengeChoices()" in script
    assert "맞춤 챌린지는 저장 API가 연결된 뒤 시작할 수 있어요." in script


def test_lifestyle_summary_uses_expandable_cards_without_result_feedback_form() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert html.count('class="lifestyle-summary-toggle"') == 4
    assert html.count('aria-expanded="false"') >= 4
    assert 'id="feedback-form"' not in html
    assert "결과 안내가 이해하기 쉬웠나요?" not in html
    assert '$("#lifestyle-summary-grid")?.addEventListener("click"' in script
    assert 'button.setAttribute("aria-expanded", String(expanded))' in script


def test_high_risk_medical_guidance_opens_only_after_cta_click() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")
    styles = (ROOT / "src/frontend/styles.css").read_text(encoding="utf-8")

    assert 'id="medical-guidance-detail" class="notice safety medical-guidance-alert"' in html
    assert html.index('id="medical-guidance-detail"') > html.index('id="future-risk-category"')
    assert html.index('id="medical-guidance-detail"') < html.index('id="to-challenges"')
    assert 'next: "검사·상담 안내 보기"' in script
    assert '$("#medical-guidance-detail").hidden = true;' in script
    assert 'const guidance = $("#medical-guidance-detail");' in script
    assert "guidance.hidden = false;" in script
    assert "guidance.focus({ preventScroll: true });" in script
    assert "if (requiresMedicalResultGuidance())" in script
    assert 'return $("#risk-confirm-card")?.dataset.risk === "high"' in script
    assert ".notice.safety.medical-guidance-alert" in styles
    assert "border-left:8px solid #b83f36" not in styles
    assert "border:2px solid #d35f55;border-radius:20px" in styles
    assert ".medical-guidance-alert>span{background:#b83f36;color:#fff}" in styles


def test_notion_challenges_are_grouped_into_selectable_habit_categories() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert 'id="challenge-category-panel"' in html
    assert 'id="challenge-detail-list"' in html
    assert 'id="challenge-selection-count"' in html
    for category in ("움직이기", "건강하게 먹기", "기록하기"):
        assert category in script
    for mascot in (
        "hyeoldangi-challenge-walking.png",
        "hyeoldangi-challenge-meal.png",
        "hyeoldangi-daily-record.png",
    ):
        assert mascot in script
    for challenge in (
        "빠르게 걷기",
        "30분마다 일어나기",
        "채소 먼저 먹기",
        "통곡물·잡곡 선택",
        "7~8시간 수면 기록",
        "생활습관 돌아보기",
        "무가당 음료 주 5일",
        "채소 먹기 주 5일",
        "통곡물 선택 주 3회",
        "체중 추이 확인",
    ):
        assert challenge in script
    assert 'api("/challenges")' in script
    assert "state.selectedChallengeIds" in script
    assert "state.challengeRecommendationsPersonalized = result.personalized === true" in script
    assert "state.challengeRecommendationsPersonalized && recommendationIds.has" in script
    assert "챌린지는 최대 3개까지 선택할 수 있어요." in script


def test_frontend_distinguishes_api_errors_without_demo_fallback() -> None:
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    expected_status_codes = {
        401: "UNAUTHENTICATED",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        503: "MODEL_NOT_READY",
        504: "TIMEOUT",
    }
    for status, code in expected_status_codes.items():
        assert f'if (status === {status}) return "{code}";' in script
    assert 'if (status >= 500) return "SERVER_ERROR";' in script
    for code in (*expected_status_codes.values(), "SERVER_ERROR", "NETWORK_ERROR"):
        assert code in script
    assert "네트워크 연결을 확인한 뒤 다시 시도해 주세요." in script
    assert "챌린지 목록을 불러오지 못했습니다." in script
    assert "현재 선택할 수 있는 챌린지가 없습니다." in script
    assert "기본 예시를 표시합니다." not in script


def test_rf25_ml_errors_have_safe_actionable_frontend_guidance() -> None:
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")
    styles = (ROOT / "src/frontend/styles.css").read_text(encoding="utf-8")

    expected_guidance = {
        "ML_INPUT_MISSING": "필수 건강정보를 확인해 주세요",
        "ML_INPUT_OUT_OF_RANGE": "건강정보의 입력값을 확인해 주세요",
        "ML_POPULATION_UNSUPPORTED": "현재 연령은 미래 발병 예측 대상이 아닙니다",
        "ML_POPULATION_INELIGIBLE": "현재는 미래 발병 예측을 진행하지 않습니다",
        "ML_MODEL_UNAVAILABLE": "현재 예측 모델을 준비하고 있습니다",
        "ML_MODEL_CONTRACT_ERROR": "예측 모델 연결을 점검하고 있습니다",
    }
    assert "const predictionFailureGuidance = {" in script
    for error_code, user_title in expected_guidance.items():
        assert error_code in script
        assert user_title in script

    assert "fallbackApiErrorMessage(resolvedCode)" in script
    assert "failureGuidance?.message || error.message" in script
    assert "실패는 높은 위험을 의미하지 않습니다." not in script
    assert "임의 점수나 위험 범주를 표시하지 않습니다." in script
    assert "점수·확률·위험 범주를 만들거나 표시하지 않습니다." in script
    for error_code in ("ML_MODEL_UNAVAILABLE", "ML_MODEL_CONTRACT_ERROR"):
        assert f'data-error-code="{error_code}"' in styles


def test_local_model_preview_shows_category_without_exposing_numeric_score() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert 'id="development-preview-notice"' in html
    assert "개발 확인용 결과 화면입니다" in html
    assert "job.development_preview_risk_category" in script
    assert "developmentPreviewRiskCategory" in script
    assert "개발 확인용 위험 범주만 표시합니다." in script
    assert "job.development_preview_internal_score" not in script
    assert '$("#risk-preview-controls").hidden = !isDemoEnvironment();' in script


def test_medical_facility_ui_has_safe_empty_permission_and_failure_states() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert 'id="facility-address-form"' in html
    assert 'id="facility-address"' in html
    assert 'id="medical-facility-map"' in html
    assert "coordinatesForAddress" in script
    assert "resetFacilitySearchUi" in script
    assert "위치 권한이 허용되지 않았어요" in script
    assert "근처 의료기관을 찾지 못했어요" in script
    assert "의료기관 정보를 불러오지 못했어요" in script
    assert "정보 확인일" in script


def test_signup_and_login_block_duplicate_requests_while_busy() -> None:
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert "function setFormBusy(form, activeButton, busyLabel)" in script
    assert 'form.setAttribute("aria-busy", "true")' in script
    assert "buttons.forEach((button) => { button.disabled = true; })" in script
    assert '"가입 처리 중…"' in script
    assert '"로그인 중…"' in script
    assert script.count("releaseBusy();") >= 2


def test_remaining_user_actions_block_duplicate_requests_while_busy() -> None:
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert "function setButtonBusy(button, busyLabel)" in script
    assert 'button.setAttribute("aria-busy", "true")' in script
    assert 'button.removeAttribute("aria-busy")' in script
    for busy_label in (
        "이용 가능 확인 중…",
        "챌린지 시작 중…",
        "기록 저장 중…",
        "오늘 기록 저장 중…",
        "초대 코드 만드는 중…",
        "워치 기록 저장 중…",
        "PDF 화면 여는 중…",
    ):
        assert busy_label in script
    assert script.count("finally { releaseBusy(); }") >= 8


def test_active_challenge_conflict_resumes_current_cycle_recording() -> None:
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert "error.status === 409" in script
    assert 'error.message.includes("진행 중인 4주 챌린지")' in script
    assert 'const currentCycle = await api("/challenge-cycles/current")' in script
    assert "renderCycle(currentCycle)" in script
    assert "await openChallengeTab()" in script
    assert "이미 진행 중인 4주 챌린지를 불러왔어요" in script


def test_challenge_step_navigation_loads_cards_and_guards_start_button() -> None:
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert "async function goStepFromNav(step)" in script
    assert "if (step === 7)" in script
    assert "await openChallengeTab()" in script
    assert "function showChallengeSelectionView()" in script
    assert 'cycle = await api("/challenge-cycles/current")' in script
    assert "챌린지 목록을 불러오고 있어요." in script
    assert 'const startButton = $("#start-challenge")' in script
    assert "startButton.disabled = true" in script
    assert "if (!result.medical_guidance_required_first) startButton.disabled = false" in script


def test_returning_user_routes_from_persisted_eligibility_state() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert 'id="returning-route-note"' not in html
    assert 'api("/eligibility-checks/latest")' in script
    assert "syncReturningEligibilityState(latestEligibility)" in script
    assert 'beginReturningEligibility("challenges")' in script
    assert 'beginReturningEligibility("health")' in script
    assert "state.requiresEligibility = !eligibility" in script
    assert 'id="challenge-follow-up"' in html
    assert 'api("/follow-up-actions")' in script
    assert "state.openFollowUpActionIds.map((actionId)" in script
    assert "api(`/follow-up-actions/${actionId}/acknowledge`" in script
    assert "if (state.currentHealthOnly)" in script
    assert "if (state.returningUser && shouldRunPredictionAfterHealthEdit())" in script
    assert 'return "저장하고 다시 분석하기"' in script
    assert "실제 모델을 호출하지 않았습니다" in script
    assert "if (state.cycle?.user_challenges?.length)" in script
    assert "이어서 4주 생활습관 챌린지를 선택해 주세요" in script


def test_report_does_not_present_sample_progress_as_user_data() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    for sample_value in ("8/21~8/27", "5일 연속 잘하고 계세요!", "4주 동안 총 18번", "전체 완료율</small><strong>64%"):
        assert sample_value not in html
    assert 'id="report-week-period">기간 확인 중' in html
    assert 'id="report-week-days"' in html and 'aria-label="요일별 실천 현황" hidden' in html
    assert "지난 4주" in html
    assert "전체" in html
    assert "현재 선택한 리포트 화면을 그대로 PDF 저장 화면으로 엽니다" in script
    assert "prepareReportPrint(period)" in script
    assert "지난 4주·전체 PDF는 연결 준비 중입니다" not in script
    assert "다른 기간의 파일을 대신 내려받지 않습니다" not in script
    assert "detailedReport.challenge_details || []" in script
    assert "주간 기록을 확인할 수 없어요" in script
    assert "건강교육을 불러오지 못했어요" in script
    assert "답 확인 중…" in script
    assert "정답입니다. 교육 콘텐츠를 완료했습니다." not in script
    assert "다시 확인해 볼까요? · 정답:" in script
    assert "교육 내용 다시 보기" in script
    assert "completed: 5, planned: 7" not in script


def test_dashboard_is_split_into_tasks_and_lifestyle_map_is_non_diagnostic() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    for workspace in ("home", "challenge", "report", "together", "tools"):
        assert f'data-workspace-panel="{workspace}"' in html
    for label in ("홈", "챌린지", "리포트", "함께하기", "건강도구"):
        assert f">{label}</button>" in html
    assert "오늘 할 일부터 확인하세요" in html
    assert 'id="today-task-title"' in html
    assert 'id="today-task-description"' in html
    assert 'id="today-record-action"' in html
    assert "function renderTodayTaskStatus()" in script
    assert "오늘 할 일을 모두 기록했어요" in script
    assert "가족·친구 목록을 불러오지 못했어요." in script
    assert "공동 챌린지를 불러오지 못했어요." in script
    assert "실제 4주 집계 API" not in html
    assert "전체 기간 이력 API" not in html
    assert "건강도구" in html
    assert "내 생활습관 지도" in html
    assert "지도 보기" in html
    assert "지도 닫기" in html
    assert "체형이나 건강 위험을 판정하지 않습니다." in html
    assert "3D 생활습관 안내 캐릭터" in html


def test_forest_return_accepts_resume_and_workspace_links() -> None:
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert 'requestedView.get("resume") !== "together"' in script
    assert 'requestedView.get("workspace")' in script
    assert 'showWorkspace(requestedWorkspace || "together"' in script
    assert "lifestyle-avatar-female-60.webp" in html
    assert '"male" : "female"' in script
    assert "ageBand" in script
    assert "Math.floor(age / 10) * 10" in script
    assert "syncLifestyleAvatar" in script
    assert "avatar-width-scale" in script
    assert "avatar-height-scale" in script
    assert "입력값을 반영한 참고 표현" in script
    assert "updateLifestyleMap" in script
    assert "체형 기록" in html + script
    assert 'id="workspace-top-nav" aria-label="로그인 후 주요 메뉴"' in html
    assert html.count("data-workspace-panel=") >= 5
    assert html.count('role="region"') >= 5
    assert 'button.setAttribute("aria-selected", String(selected))' in script
    assert "selectedPanel.focus({ preventScroll: true })" in script


def test_local_forecast_preview_opens_safe_result_layout() -> None:
    script = (ROOT / "src/frontend/app.js").read_text(encoding="utf-8")

    assert "function resumeForecastPreview()" in script
    assert 'includes(params.get("preview")) || !isDemoEnvironment()' in script
    assert 'result_status: "development_only"' in script
    assert "renderMvpResultPreview();" in script
    assert "display_allowed: false" in script
    assert "operational_model_activated: false" in script
    assert "실제 모델을 호출하지 않았습니다" in script
    assert "resumeForecastPreview();" in script


def test_only_reviewed_diabetes_contract_is_active() -> None:
    assert ACTIVE_MODEL.model_key == "diabetes_incidence"
    assert ACTIVE_MODEL.outcome_definition == "next_observation_new_diabetes_diagnosis"
    assert ACTIVE_MODEL.observation_horizon == "approximately_2_years_next_klosa_wave"
    assert ACTIVE_MODEL.threshold_is_approved is True
    assert ACTIVE_MODEL.operational_model_activated is True
