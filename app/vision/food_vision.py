from __future__ import annotations

import base64
import hashlib
import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import httpx

from app.core import config

_ALLOWED_CATEGORIES: set[str] = {"곡류", "채소", "과일", "단백질", "유제품", "혼합식", "확인불가"}

_SYSTEM_PROMPT = (
    "당신은 식사 사진을 보고 음식 카테고리, 채소 포함 여부, 접시에서 채소가 차지하는 "
    "대략적인 시각적 비율만 판별하는 보조 도구입니다. "
    "칼로리, 영양소 함량(g/mg 등), 체중 감량 효과, 치료 효과는 절대 계산하거나 언급하지 마세요. "
    "vegetable_ratio_percent는 무게나 열량이 아니라 사진에 보이는 면적 기준의 대략적인 시각적 추정치입니다. "
    "반드시 아래 JSON 스키마로만 답하세요. 설명 문장을 추가하지 마세요.\n"
    '{"predicted_category": "곡류|채소|과일|단백질|유제품|혼합식|확인불가", '
    '"contains_vegetable": true 또는 false, '
    '"vegetable_confidence": 0과 1 사이 숫자, '
    '"vegetable_ratio_percent": 0과 100 사이 숫자(접시에서 채소로 보이는 면적 비율 추정치), '
    '"detected_items": ["사진에서 보이는 음식 이름들"]}'
)


class FoodVisionError(RuntimeError):
    """이미지 인식 provider 호출에 실패했을 때 사용하는 예외입니다."""


class FoodVisionRuntimeError(FoodVisionError):
    """Local runtime failure with a safe, non-personal diagnostic code."""

    def __init__(self, reason_code: str):
        self.reason_code = reason_code
        super().__init__("Local food vision runtime unavailable")


@dataclass(frozen=True)
class FoodVisionResult:
    provider_kind: str
    predicted_category: str
    contains_vegetable: bool | None
    vegetable_confidence: float | None
    vegetable_ratio_percent: float | None = None
    detected_items: list[str] = field(default_factory=list)
    food_coverage_percent: float | None = None
    reliable: bool = True
    uncertainty_reasons: list[str] = field(default_factory=list)
    model_version: str | None = None
    decision_status: str | None = None


class FoodVisionProvider(Protocol):
    provider_kind: str

    async def analyze(self, image_bytes: bytes, mime_type: str, filename: str) -> FoodVisionResult: ...


class DevelopmentFoodVisionProvider:
    """실제 이미지 픽셀을 분석하지 않는 개발용 어댑터입니다.

    기존 /food-analyses 목업과 동일하게 파일명 키워드로 결정적인 결과를 돌려주어,
    provider 인터페이스와 챌린지 연동을 실제 Vision API 없이도 검증할 수 있게 합니다.
    운영 환경에서는 FOOD_VISION_PROVIDER=openai로 전환해서 사용하지 않습니다.
    """

    provider_kind = "development_mock"

    _KEYWORDS: dict[str, tuple[str, ...]] = {
        "곡류": ("rice", "bap", "bread", "noodle", "밥", "빵", "면"),
        "채소": ("vegetable", "salad", "greens", "veggie", "채소", "샐러드", "나물"),
        "과일": ("fruit", "apple", "banana", "과일", "사과", "바나나"),
        "단백질": ("meat", "fish", "egg", "tofu", "고기", "생선", "달걀", "두부"),
        "유제품": ("milk", "yogurt", "cheese", "우유", "요거트", "치즈"),
    }

    async def analyze(self, image_bytes: bytes, mime_type: str, filename: str) -> FoodVisionResult:
        del image_bytes, mime_type  # 실제 픽셀은 보지 않는 개발용 어댑터입니다.
        normalized = filename.casefold()
        matches = [category for category, words in self._KEYWORDS.items() if any(word in normalized for word in words)]
        category = matches[0] if len(matches) == 1 else "확인불가"
        contains_vegetable = category == "채소"
        confidence = 0.55 if matches else None
        ratio = 65.0 if contains_vegetable else (15.0 if matches else None)
        return FoodVisionResult(
            provider_kind=self.provider_kind,
            predicted_category=category,
            contains_vegetable=contains_vegetable,
            vegetable_confidence=confidence,
            vegetable_ratio_percent=ratio,
            detected_items=[category] if category != "확인불가" else [],
        )


class OpenAIFoodVisionProvider:
    """OpenAI의 이미지 인식 가능한 Chat Completions API로 채소 포함 여부만 판별합니다."""

    provider_kind = "openai_vision"

    def __init__(self) -> None:
        if not config.OPENAI_API_KEY:
            raise FoodVisionError("OPENAI_API_KEY가 설정되어 있지 않습니다. .env에 키를 추가한 뒤 다시 시도해주세요.")
        self._api_key = config.OPENAI_API_KEY
        self._model = config.OPENAI_MODEL

    _SUPPORTED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

    async def analyze(self, image_bytes: bytes, mime_type: str, filename: str) -> FoodVisionResult:
        del filename
        if mime_type not in self._SUPPORTED_MIME_TYPES:
            raise FoodVisionError(
                "이 이미지 형식은 AI 인식이 지원하지 않습니다(HEIC 등). jpg·png·webp로 변환해서 다시 업로드해주세요."
            )
        encoded = base64.b64encode(image_bytes).decode("ascii")
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "이 식사 사진에 채소가 포함되어 있는지 판별해줘."},
                        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}},
                    ],
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": 300,
        }
        try:
            async with httpx.AsyncClient(timeout=config.FOOD_VISION_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
                response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise FoodVisionError("이미지 인식 요청이 시간 초과되었습니다. 잠시 후 다시 시도해주세요.") from exc
        except httpx.HTTPStatusError as exc:
            raise FoodVisionError(f"이미지 인식 provider 호출에 실패했습니다: {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise FoodVisionError("이미지 인식 provider에 연결할 수 없습니다.") from exc

        try:
            body = response.json()
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise FoodVisionError("이미지 인식 결과를 해석하지 못했습니다.") from exc
        return self._parse_review(content)

    def _parse_review(self, content: str) -> FoodVisionResult:
        try:
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise ValueError("The image review must be a JSON object")
            category = parsed.get("predicted_category", "확인불가")
            if category not in _ALLOWED_CATEGORIES:
                category = "확인불가"
            contains_vegetable = parsed.get("contains_vegetable")
            confidence = parsed.get("vegetable_confidence")
            ratio = parsed.get("vegetable_ratio_percent")
            detected_items = parsed.get("detected_items") or []
            if type(contains_vegetable) is not bool:
                raise ValueError("contains_vegetable must be a JSON boolean")
            if not (type(confidence) in (int, float) and 0 <= confidence <= 1 and math.isfinite(confidence)):
                raise ValueError("vegetable_confidence must be a finite number between zero and one")
            if ratio is not None and not (type(ratio) in (int, float) and 0 <= ratio <= 100 and math.isfinite(ratio)):
                raise ValueError("vegetable_ratio_percent must be a finite number between zero and one hundred")
            if not isinstance(detected_items, list) or not all(isinstance(item, str) for item in detected_items):
                raise ValueError("detected_items must be a list of strings")
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise FoodVisionError("이미지 인식 결과를 해석하지 못했습니다.") from exc

        return FoodVisionResult(
            provider_kind=self.provider_kind,
            predicted_category=category,
            contains_vegetable=contains_vegetable,
            vegetable_confidence=float(confidence),
            vegetable_ratio_percent=float(ratio) if ratio is not None else None,
            detected_items=detected_items[:10],
        )


def get_food_vision_provider() -> FoodVisionProvider:
    if config.FOOD_VISION_PROVIDER == "development":
        return DevelopmentFoodVisionProvider()
    if config.FOOD_VISION_PROVIDER == "openai":
        raise FoodVisionError(
            "OpenAI Vision 제공자는 비활성화되어 있습니다. FOOD_VISION_PROVIDER=local_kfood를 사용해 주세요."
        )
    if config.FOOD_VISION_PROVIDER == "local_kfood":
        return _cached_local_kfood_provider(_local_kfood_signature())
    raise FoodVisionError(f"지원하지 않는 FOOD_VISION_PROVIDER입니다: {config.FOOD_VISION_PROVIDER}")


def _local_kfood_signature() -> tuple[str, ...]:
    """Return every setting that changes the reusable local model runtime."""

    from app.vision.local_kfood import configured_model_paths

    classifier_path, meta_path, segmenter_path = configured_model_paths()
    return (
        str(Path(classifier_path).resolve()),
        str(Path(meta_path).resolve()),
        str(Path(segmenter_path).resolve()),
        str(Path(config.KFOOD_SEGMENTATION_CONFIG_PATH).resolve()),
        str(Path(config.KFOOD_DISH_VEGETABLES_PATH).resolve()),
        config.KFOOD_CLASSIFIER_SHA256.lower(),
        config.KFOOD_CLASSIFIER_META_SHA256.lower(),
        config.KFOOD_SEGMENTER_SHA256.lower(),
    )


@lru_cache(maxsize=4)
def _cached_local_kfood_provider(_signature: tuple[str, ...]) -> FoodVisionProvider:
    """Reuse the heavy Torch and TFLite runtimes across photo requests."""

    from app.vision.local_kfood import LocalKFoodVisionProvider

    return LocalKFoodVisionProvider()


def food_vision_is_configured() -> bool:
    if config.FOOD_VISION_PROVIDER != "local_kfood":
        return False
    if not (0 < config.FOOD_COVERAGE_PASS_THRESHOLD <= 1 and 0 < config.VEGETABLE_RATIO_PASS_THRESHOLD <= 1):
        return False
    try:
        # Construction verifies every artifact digest and parses both model
        # configuration files. The cached instance is then reused for inference.
        get_food_vision_provider()
    except FoodVisionError:
        return False
    return True


def sha256_digest(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()
