from types import SimpleNamespace

from app.services.xai_presentation import input_label


def test_no_alcohol_and_unknown_inputs_remain_distinct():
    checkup = SimpleNamespace(current_drinker=False, bmi=24.5, hypertension_diagnosis=False)
    assert (
        input_label("alcohol_frequency", checkup, SimpleNamespace(alcohol_frequency=1)) == "최근 1년간 전혀 마시지 않음"
    )
    assert input_label("alcohol_frequency", checkup, SimpleNamespace(alcohol_frequency=8)) == "평생 음주 경험 없음"
    assert input_label("alcohol_frequency", checkup, None) == "입력하지 않음"
    assert input_label("hypertension_diagnosis", checkup) == "진단받지 않음"
    assert input_label("bmi", checkup) == "24.5"


def test_model_numbers_require_approval_and_finite_valid_saved_values():
    from app.services.xai_presentation import model_analysis_payload

    value = SimpleNamespace(internal_score=0.125, decision_threshold=0.1)
    assert model_analysis_payload(value, approved=False) is None
    result = model_analysis_payload(value, approved=True)
    assert result["model_score"] == 0.125
    assert abs(result["score_minus_threshold"] - 0.025) < 1e-12
    for bad in [None, True, float("nan"), float("inf"), -1, 2]:
        value.internal_score = bad
        assert model_analysis_payload(value, approved=True) is None


def test_complete_shap_graph_rejects_missing_invalid_duplicate_or_nonadditive_terms():
    from app.services.xai_presentation import shap_graph_payload

    value = dict(
        display_allowed=True,
        additivity_verified=True,
        shap_claimed=True,
        reference_value=0.1,
        score=0.115,
        all_items=[
            dict(feature="age", display_name="연령", contribution=0.02),
            dict(feature="bmi", display_name="BMI", contribution=-0.005),
            dict(feature="sex", display_name="성별", contribution=0.0),
        ],
    )
    result = shap_graph_payload(value)
    assert result["complete"] and len(result["items"]) == 3
    assert abs(result["contribution_sum"] - 0.015) < 1e-12
    for override in [
        dict(display_allowed=False),
        dict(additivity_verified=False),
        dict(all_items=None),
        dict(score=0.9),
        dict(all_items=value["all_items"] + [value["all_items"][0]]),
        dict(all_items=[dict(feature="age", contribution=float("nan"))]),
    ]:
        assert shap_graph_payload({**value, **override}) is None
