from __future__ import annotations

import asyncio
import hashlib
import json
import math
import threading
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

from app.core import config
from app.vision.food_vision import FoodVisionError, FoodVisionResult, FoodVisionRuntimeError


def runtime_load_error(exc: Exception) -> FoodVisionRuntimeError:
    if isinstance(exc, OSError) and getattr(exc, "winerror", None) in {4551, 577}:
        return FoodVisionRuntimeError("runtime_security_blocked")
    if isinstance(exc, ImportError):
        return FoodVisionRuntimeError("runtime_dependency_missing")
    return FoodVisionRuntimeError("runtime_load_failed")


def _verify_file(path: Path, expected_sha256: str, label: str) -> None:
    if not path.is_file():
        raise FoodVisionError(f"{label} 파일이 준비되지 않았습니다.")
    with path.open("rb") as file:
        actual = hashlib.file_digest(file, "sha256").hexdigest()
    if actual.lower() != expected_sha256.lower():
        raise FoodVisionError(f"{label} 체크섬이 일치하지 않습니다.")


def threshold_decision(food_coverage: float, vegetable_ratio: float, reliable: bool) -> str:
    if not all(math.isfinite(value) and 0 <= value <= 1 for value in (food_coverage, vegetable_ratio)):
        return "uncertain"
    if food_coverage < config.FOOD_COVERAGE_PASS_THRESHOLD:
        return "invalid_food_ratio"
    if not reliable:
        return "uncertain"
    if vegetable_ratio < config.VEGETABLE_RATIO_PASS_THRESHOLD:
        return "invalid_vegetable_ratio"
    return "valid"


def configured_model_paths() -> tuple[Path, Path, Path]:
    if config.KFOOD_DRIVE_FILE_ID.strip():
        bundle_dir = Path(config.KFOOD_BUNDLE_DIR)
        return bundle_dir / "best.pt", bundle_dir / "meta.json", bundle_dir / "1.tflite"
    return (
        Path(config.KFOOD_CLASSIFIER_PATH),
        Path(config.KFOOD_CLASSIFIER_META_PATH),
        Path(config.KFOOD_SEGMENTER_PATH),
    )


class LocalKFoodVisionProvider:
    """Korean-food classifier plus a local TFLite food segmenter.

    Ratios are visible pixel-area estimates, never weight, calories, nutrients,
    or evidence of actual consumption.
    """

    provider_kind = "local_kfood_cv"

    def __init__(self) -> None:
        self._classifier_path, self._meta_path, self._segmenter_path = configured_model_paths()
        self._seg_config_path = Path(config.KFOOD_SEGMENTATION_CONFIG_PATH)
        self._dish_map_path = Path(config.KFOOD_DISH_VEGETABLES_PATH)
        _verify_file(self._classifier_path, config.KFOOD_CLASSIFIER_SHA256, "한식 분류 모델")
        _verify_file(self._meta_path, config.KFOOD_CLASSIFIER_META_SHA256, "한식 분류 모델 메타데이터")
        _verify_file(self._segmenter_path, config.KFOOD_SEGMENTER_SHA256, "음식 세그멘터")
        try:
            self._meta = json.loads(self._meta_path.read_text(encoding="utf-8"))
            seg_config = json.loads(self._seg_config_path.read_text(encoding="utf-8"))
            self._dish_map = json.loads(self._dish_map_path.read_text(encoding="utf-8"))
            self._classes = self._meta["classes"]
            self._bg_indices = [int(value) for value in seg_config["bg_idx"]]
            self._veg_indices = [int(value) for value in seg_config["veg_idx"]]
            self._unreliable = set(seg_config.get("seg_unreliable_dishes", []))
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise FoodVisionError("로컬 음식 모델 설정을 읽지 못했습니다.") from exc
        self._lock = threading.Lock()
        self._classifier = None
        self._interpreter = None

    def _load(self):
        if self._classifier is not None and self._interpreter is not None:
            return self._classifier, self._interpreter
        try:
            import timm
            import torch
            from ai_edge_litert.interpreter import Interpreter

            classifier = timm.create_model(self._meta["backbone"], pretrained=False, num_classes=len(self._classes))
            state = torch.load(self._classifier_path, map_location="cpu", weights_only=True)
            classifier.load_state_dict(state)
            classifier.eval()
            interpreter = Interpreter(model_path=str(self._segmenter_path))
            interpreter.allocate_tensors()
        except (ImportError, OSError, RuntimeError, KeyError, ValueError) as exc:
            raise runtime_load_error(exc) from exc
        self._classifier, self._interpreter = classifier, interpreter
        return classifier, interpreter

    def _classify(self, image: Image.Image) -> list[tuple[str, float]]:
        import torch
        from torchvision import transforms

        classifier, _ = self._load()
        size = int(self._meta["input_size"])
        transform = transforms.Compose(
            [
                transforms.Resize(int(size * 1.14)),
                transforms.CenterCrop(size),
                transforms.ToTensor(),
                transforms.Normalize(self._meta["mean"], self._meta["std"]),
            ]
        )
        with torch.inference_mode():
            probabilities = classifier(transform(image)[None]).softmax(-1)[0]
        confidence, indices = probabilities.topk(min(3, probabilities.numel()))
        return [(self._classes[index], float(value)) for value, index in zip(confidence, indices, strict=True)]

    def _segment(self, image: Image.Image) -> np.ndarray:
        _, interpreter = self._load()
        input_detail = interpreter.get_input_details()[0]
        output_details = interpreter.get_output_details()
        size = tuple(int(value) for value in input_detail["shape"][1:3])
        pixels = np.asarray(image.resize(size[::-1])).astype(input_detail["dtype"])
        interpreter.set_tensor(input_detail["index"], pixels[None, ...])
        interpreter.invoke()
        for output in output_details:
            tensor = np.squeeze(interpreter.get_tensor(output["index"]))
            if tensor.ndim == 3:
                return tensor.argmax(axis=-1).astype(np.int64)
            if tensor.ndim == 2:
                return tensor.astype(np.int64)
        raise FoodVisionError("세그멘터 출력에서 픽셀 마스크를 찾지 못했습니다.")

    def _analyze_sync(self, image_bytes: bytes) -> FoodVisionResult:
        try:
            image = Image.open(BytesIO(image_bytes)).convert("RGB")
        except OSError as exc:
            raise FoodVisionError("분석할 사진을 읽지 못했습니다.") from exc
        with self._lock:
            mask = self._segment(image)
            predictions = self._classify(image)
        food = ~np.isin(mask, self._bg_indices)
        food_pixels = int(food.sum())
        food_coverage = food_pixels / mask.size
        vegetable_pixels = int((np.isin(mask, self._veg_indices) & food).sum())
        vegetable_ratio = vegetable_pixels / food_pixels if food_pixels else 0.0
        dish = predictions[0][0] if predictions else None
        reasons: list[str] = []
        if dish in self._unreliable:
            reasons.append("segmentation_unreliable_for_dish")
        baked_share = float(((mask == 11) & food).sum()) / food_pixels if food_pixels else 0.0
        if baked_share > 0.30:
            reasons.append("possible_seasoned_vegetable_misclassification")
        reliable = not reasons
        decision = threshold_decision(food_coverage, vegetable_ratio, reliable)
        return FoodVisionResult(
            provider_kind=self.provider_kind,
            predicted_category="채소" if decision == "valid" else "확인불가",
            contains_vegetable=decision == "valid",
            vegetable_confidence=None,
            vegetable_ratio_percent=vegetable_ratio * 100,
            detected_items=[name for name, _ in predictions],
            food_coverage_percent=food_coverage * 100,
            reliable=reliable,
            uncertainty_reasons=reasons,
            model_version=f"kfood-efficientnet-b0-{self._meta.get('test_top1', 'unknown')}",
            decision_status=decision,
        )

    async def analyze(self, image_bytes: bytes, mime_type: str, filename: str) -> FoodVisionResult:
        del mime_type, filename
        return await asyncio.to_thread(self._analyze_sync, image_bytes)
