import asyncio
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
import httpx

from app.core import config
from app.vision.food_vision import (
    FoodVisionError,
    FoodVisionResult,
    _cached_local_kfood_provider,
    food_vision_is_configured,
    get_food_vision_provider,
)
from app.vision.local_kfood import threshold_decision
from app.vision.openai_vlm import VLMUnavailableError, needs_vlm, supplement_with_vlm
from app.vision.photo_context import FoodPhotoContext


def _clear_vlm_review(**changes):
    return {
        "is_meal_photo": True,
        "challenge_relevant": True,
        "vegetables_clearly_visible": True,
        "vegetable_presence": "present" if changes.get("vegetables_clearly_visible", True) else "uncertain",
        "image_quality_adequate": True,
        "food_boundaries_clear": True,
        "vegetable_boundaries_clear": True,
        "multiple_images_or_screen_capture": False,
        "uncertainty_reasons": [],
        **changes,
    }


def test_ratio_thresholds_require_both_stages() -> None:
    assert threshold_decision(0.50, 0.30, True) == "valid"
    assert threshold_decision(0.4999, 0.90, True) == "invalid_food_ratio"
    assert threshold_decision(0.60, 0.90, True) == "valid"
    assert threshold_decision(0.90, 0.2999, True) == "invalid_vegetable_ratio"


def test_unreliable_result_never_completes() -> None:
    assert threshold_decision(0.90, 0.90, False) == "uncertain"


def test_invalid_numeric_result_is_uncertain() -> None:
    assert threshold_decision(float("nan"), 0.90, True) == "uncertain"
    assert threshold_decision(0.90, float("inf"), True) == "uncertain"


def test_threshold_contract_is_fifty_and_thirty_percent() -> None:
    assert config.FOOD_COVERAGE_PASS_THRESHOLD == 0.50
    assert config.VEGETABLE_RATIO_PASS_THRESHOLD == 0.30


def test_openai_provider_is_retained_but_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "FOOD_VISION_PROVIDER", "openai")

    with pytest.raises(FoodVisionError, match="비활성화"):
        get_food_vision_provider()


def _configure_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    classifier = tmp_path / "best.pt"
    metadata = tmp_path / "meta.json"
    segmenter = tmp_path / "1.tflite"
    segmentation = tmp_path / "seg_config.json"
    dishes = tmp_path / "dish_vegetables.json"
    classifier.write_bytes(b"classifier")
    metadata.write_text(
        json.dumps(
            {"classes": ["dish"], "backbone": "efficientnet_b0", "input_size": 224, "mean": [0, 0, 0], "std": [1, 1, 1]}
        ),
        encoding="utf-8",
    )
    segmenter.write_bytes(b"segmenter")
    segmentation.write_text(json.dumps({"bg_idx": [0], "veg_idx": [1]}), encoding="utf-8")
    dishes.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config, "FOOD_VISION_PROVIDER", "local_kfood")
    monkeypatch.setattr(config, "KFOOD_DRIVE_FILE_ID", "")
    monkeypatch.setattr(config, "KFOOD_CLASSIFIER_PATH", classifier)
    monkeypatch.setattr(config, "KFOOD_CLASSIFIER_META_PATH", metadata)
    monkeypatch.setattr(config, "KFOOD_SEGMENTER_PATH", segmenter)
    monkeypatch.setattr(config, "KFOOD_SEGMENTATION_CONFIG_PATH", segmentation)
    monkeypatch.setattr(config, "KFOOD_DISH_VEGETABLES_PATH", dishes)
    monkeypatch.setattr(config, "KFOOD_CLASSIFIER_SHA256", hashlib.sha256(classifier.read_bytes()).hexdigest())
    monkeypatch.setattr(config, "KFOOD_CLASSIFIER_META_SHA256", hashlib.sha256(metadata.read_bytes()).hexdigest())
    monkeypatch.setattr(config, "KFOOD_SEGMENTER_SHA256", hashlib.sha256(segmenter.read_bytes()).hexdigest())
    _cached_local_kfood_provider.cache_clear()


def test_food_vision_readiness_verifies_artifact_digests(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_runtime(monkeypatch, tmp_path)
    assert food_vision_is_configured() is True

    _cached_local_kfood_provider.cache_clear()
    (tmp_path / "best.pt").write_bytes(b"tampered")
    assert food_vision_is_configured() is False


def test_local_provider_is_reused_between_requests(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _configure_runtime(monkeypatch, tmp_path)
    assert get_food_vision_provider() is get_food_vision_provider()


def _result(food: float, vegetable: float, reliable: bool = True) -> FoodVisionResult:
    return FoodVisionResult(
        provider_kind="local_kfood_cv",
        predicted_category="확인불가",
        contains_vegetable=False,
        vegetable_confidence=None,
        food_coverage_percent=food,
        vegetable_ratio_percent=vegetable,
        reliable=reliable,
        model_version="local-v1",
        decision_status="uncertain",
    )


def test_vlm_is_only_used_for_borderline_or_unreliable_results() -> None:
    assert needs_vlm(_result(45, 40))
    assert needs_vlm(_result(70, 25))
    assert needs_vlm(_result(70, 40, False))
    assert not needs_vlm(_result(70, 40))
    assert not needs_vlm(_result(30, 10))


@pytest.mark.parametrize("name", ["contains_kimchi", "strong_seasoning", "white_food_on_white"])
@pytest.mark.parametrize("answer", ["yes", "unsure"])
def test_user_photo_conditions_trigger_supplement_without_changing_cv(name, answer):
    context = FoodPhotoContext(**{**dict.fromkeys(FoodPhotoContext().as_dict(), "no"), name: answer})
    result = _result(70, 40)
    assert needs_vlm(result, context)
    assert result.food_coverage_percent == 70
    assert result.vegetable_ratio_percent == 40
    assert not needs_vlm(result, FoodPhotoContext("no", "no", "no"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "food,vegetable,reliable,expected",
    [(70, 40, True, "valid"), (70, 40, False, "uncertain"), (48, 80, True, "uncertain"),
     (80, 28, True, "uncertain"), (30, 10, True, "uncertain"), (None, 40, True, "uncertain"),
     (float("nan"), 40, True, "uncertain"), (80, float("inf"), True, "uncertain"),
     (-1, 40, True, "uncertain"), (101, 40, True, "uncertain")],
)
async def test_vlm_requires_reliable_cv_area_even_with_user_flags(monkeypatch, food, vegetable, reliable, expected):
    async def verify(_self, _image, context):
        assert context.white_food_on_white == "yes"
        return _clear_vlm_review()

    monkeypatch.setattr("app.vision.openai_vlm.OpenAIVegetableVerifier.verify", verify)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")
    result = await supplement_with_vlm(_result(food, vegetable, reliable), b"image", FoodPhotoContext("no", "no", "yes"))
    assert result.decision_status == expected
    assert result.reliable is (expected == "valid")
    assert result.vegetable_ratio_percent == vegetable


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes,expected",
    [({"food_boundaries_clear": False}, "uncertain"),
     ({"vegetable_boundaries_clear": False}, "uncertain"),
     ({"image_quality_adequate": False}, "uncertain"),
     ({"vegetables_clearly_visible": False}, "uncertain"),
     ({"uncertainty_reasons": ["food overlap"]}, "uncertain"),
     ({"vegetable_presence": "absent", "vegetables_clearly_visible": False}, "invalid_vegetable_content"),
     ({"multiple_images_or_screen_capture": True}, "invalid_photo_content"),
     ({"is_meal_photo": False}, "invalid_photo_content")],
)
async def test_vlm_ambiguity_or_semantic_disagreement_never_passes(monkeypatch, changes, expected):
    async def verify(_self, _image, _context):
        return _clear_vlm_review(**changes)

    monkeypatch.setattr("app.vision.openai_vlm.OpenAIVegetableVerifier.verify", verify)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")
    result = await supplement_with_vlm(_result(70, 40), b"image", FoodPhotoContext("yes", "no", "no"))
    assert result.decision_status == expected
    assert not result.reliable


@pytest.mark.asyncio
async def test_vlm_does_not_erase_cv_uncertainty(monkeypatch):
    async def verify(_self, _image, _context):
        return _clear_vlm_review()

    monkeypatch.setattr("app.vision.openai_vlm.OpenAIVegetableVerifier.verify", verify)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")
    result = await supplement_with_vlm(
        replace(_result(70, 40, False), uncertainty_reasons=["segmentation_unreliable_for_dish"]), b"image"
    )
    assert result.decision_status == "uncertain"
    assert "segmentation_unreliable_for_dish" in result.uncertainty_reasons


def test_disabled_vlm_with_reported_conditions_cannot_pass(monkeypatch):
    from app.services.challenge_proofs import _supplement_review

    monkeypatch.setattr(config, "OPENAI_VLM_FALLBACK_ENABLED", False)
    result = asyncio.run(_supplement_review(replace(_result(70, 40), decision_status="valid"), b"image", FoodPhotoContext()))
    assert result.decision_status == "uncertain"
    assert "vlm_disabled" in result.uncertainty_reasons


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [None, "coerced_boolean", "invalid_presence", "presence_mismatch", "incomplete", "missing_boundary"])
async def test_responses_contract_and_invalid_structured_output_fail_closed(monkeypatch, change):
    from app.vision.openai_vlm import OpenAIVegetableVerifier

    review = _clear_vlm_review()
    status = "completed"
    if change == "coerced_boolean":
        review["is_meal_photo"] = "true"
    elif change == "invalid_presence":
        review["vegetable_presence"] = []
    elif change == "presence_mismatch":
        review["vegetable_presence"] = "absent"
    elif change == "incomplete":
        status = "incomplete"
    elif change == "missing_boundary":
        del review["food_boundaries_clear"]

    def respond(request):
        payload = json.loads(request.content)
        assert payload["store"] is False
        assert payload["text"]["format"]["strict"] is True
        assert payload["text"]["format"]["schema"]["additionalProperties"] is False
        assert request.url == "https://api.openai.com/v1/responses"
        assert '"white_food_on_white": "yes"' in payload["input"][0]["content"][0]["text"]
        assert "test-only-key" not in request.content.decode()
        return httpx.Response(200, json={"status": status, "output": [{"content": [{"type": "output_text", "text": json.dumps(review)}]}]})

    original_client = httpx.AsyncClient
    monkeypatch.setattr("app.vision.openai_vlm.httpx.AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs))
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-only-key")
    verifier = OpenAIVegetableVerifier()
    if change is None:
        assert await verifier.verify(b"sanitized-image", FoodPhotoContext("no", "no", "yes")) == review
    else:
        with pytest.raises(VLMUnavailableError) as error:
            await verifier.verify(b"sanitized-image", FoodPhotoContext("no", "no", "yes"))
        assert error.value.reason_code == "vlm_response_invalid"


def test_enabled_vlm_fallback_is_applied_without_per_submission_consent(monkeypatch: pytest.MonkeyPatch) -> None:
    local_result = _result(48, 28)
    supplemented = replace(_result(50, 30), decision_status="valid")
    calls = []

    async def analyze(_photo, _mime_type, _filename):
        return local_result

    async def supplement(result, photo, _context=None):
        calls.append((result, photo))
        return supplemented

    monkeypatch.setattr(config, "FOOD_VISION_PROVIDER", "local_kfood")
    monkeypatch.setattr(config, "OPENAI_VLM_FALLBACK_ENABLED", True)
    monkeypatch.setattr(
        "app.services.challenge_proofs.get_food_vision_provider",
        lambda: SimpleNamespace(provider_kind="local_kfood_cv", analyze=analyze),
    )
    monkeypatch.setattr("app.vision.openai_vlm.supplement_with_vlm", supplement)

    from app.services.challenge_proofs import _review

    status, _notice, result = asyncio.run(_review(b"image", 1))
    assert status == "needs_confirmation"
    assert result is supplemented
    assert calls == [(local_result, b"image")]


@pytest.mark.asyncio
async def test_vlm_visibility_does_not_override_area_thresholds(monkeypatch: pytest.MonkeyPatch) -> None:
    async def verify(_self, _image, _context=None):
        return {
            "is_meal_photo": True,
            "challenge_relevant": True,
            "vegetables_clearly_visible": True,
            "vegetable_presence": "present",
            "image_quality_adequate": True,
            "food_boundaries_clear": True,
            "vegetable_boundaries_clear": True,
            "multiple_images_or_screen_capture": False,
            "uncertainty_reasons": [],
        }

    monkeypatch.setattr("app.vision.openai_vlm.OpenAIVegetableVerifier.verify", verify)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")
    result = await supplement_with_vlm(_result(48, 28), b"image")
    assert result.decision_status == "uncertain"
    assert result.provider_kind == "local_kfood_openai_vlm"
    assert result.food_coverage_percent == 48
    assert result.vegetable_ratio_percent == 28
    assert "cv_area_not_verified" in result.uncertainty_reasons


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason_code",
    [
        "vlm_configuration_incomplete",
        "vlm_timeout",
        "vlm_connection_failed",
        "vlm_rate_limited",
        "vlm_service_unavailable",
        "vlm_response_invalid",
    ],
)
async def test_vlm_unavailable_reason_is_preserved_for_user_guidance(
    monkeypatch: pytest.MonkeyPatch, reason_code: str
) -> None:
    async def verify(_self, _image, _context=None):
        raise VLMUnavailableError(reason_code, "internal detail")

    monkeypatch.setattr("app.vision.openai_vlm.OpenAIVegetableVerifier.verify", verify)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")
    result = await supplement_with_vlm(_result(48, 28), b"image")
    assert result.decision_status == "uncertain"
    assert reason_code in result.uncertainty_reasons


def test_vlm_unavailable_notice_distinguishes_disabled_and_runtime_causes(monkeypatch: pytest.MonkeyPatch) -> None:
    async def analyze(_photo, _mime_type, _filename):
        return _result(48, 28)

    monkeypatch.setattr(config, "FOOD_VISION_PROVIDER", "local_kfood")
    monkeypatch.setattr(config, "OPENAI_VLM_FALLBACK_ENABLED", False)
    monkeypatch.setattr(
        "app.services.challenge_proofs.get_food_vision_provider",
        lambda: SimpleNamespace(provider_kind="local_kfood_cv", analyze=analyze),
    )

    from app.services.challenge_proofs import _review

    status, notice, result = asyncio.run(_review(b"image", 1))
    assert status == "needs_review"
    assert "비활성화" in notice
    assert "로컬 모델 결과만 사용" in notice
    assert "vlm_disabled" in result.uncertainty_reasons


@pytest.mark.parametrize(
    ("reason_code", "expected"),
    [
        ("vlm_configuration_incomplete", "설정이 완료되지 않아"),
        ("vlm_timeout", "요청 시간이 초과되어"),
        ("vlm_connection_failed", "연결할 수 없어"),
        ("vlm_rate_limited", "요청이 많아"),
        ("vlm_service_unavailable", "일시적으로 사용할 수 없어"),
        ("vlm_response_invalid", "결과를 확인할 수 없어"),
    ],
)
def test_vlm_runtime_failure_notice_is_cause_specific(
    monkeypatch: pytest.MonkeyPatch, reason_code: str, expected: str
) -> None:
    local_result = _result(48, 28)

    async def analyze(_photo, _mime_type, _filename):
        return local_result

    async def supplement(result, _photo, _context=None):
        return replace(result, uncertainty_reasons=[reason_code])

    monkeypatch.setattr(config, "FOOD_VISION_PROVIDER", "local_kfood")
    monkeypatch.setattr(config, "OPENAI_VLM_FALLBACK_ENABLED", True)
    monkeypatch.setattr(
        "app.services.challenge_proofs.get_food_vision_provider",
        lambda: SimpleNamespace(provider_kind="local_kfood_cv", analyze=analyze),
    )
    monkeypatch.setattr("app.vision.openai_vlm.supplement_with_vlm", supplement)

    from app.services.challenge_proofs import _review

    status, notice, _result_value = asyncio.run(_review(b"image", 1))
    assert status == "needs_review"
    assert expected in notice
    assert "로컬 모델 결과만 사용" in notice


@pytest.mark.parametrize(
    "kind,reason",
    [
        ("blocked", "runtime_security_blocked"),
        ("missing", "runtime_dependency_missing"),
        ("other", "runtime_load_failed"),
    ],
)
def test_runtime_load_errors_have_safe_diagnostic_codes(kind, reason):
    from app.vision.local_kfood import runtime_load_error

    if kind == "blocked":
        error = OSError("private DLL path")
        error.winerror = 4551
    elif kind == "missing":
        error = ImportError("private module path")
    else:
        error = RuntimeError("private model detail")
    classified = runtime_load_error(error)
    assert classified.reason_code == reason
    assert "private" not in str(classified)
