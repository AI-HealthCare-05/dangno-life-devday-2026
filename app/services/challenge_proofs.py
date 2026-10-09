"""V3 photo submission: server-validated images, no raw image retention or fake AI success."""

from __future__ import annotations

import io
import json
import logging
import math
from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from tortoise.transactions import in_transaction

from app.core import config
from app.models.health import Challenge, ChallengeCycle, ChallengeLog, ChallengeVerification, UserChallenge
from app.services.challenge_catalog import metadata_for
from app.vision.food_vision import (
    FoodVisionError,
    FoodVisionRuntimeError,
    food_vision_is_configured,
    get_food_vision_provider,
    sha256_digest,
)
from app.vision.photo_context import FoodPhotoContext

logger = logging.getLogger(__name__)

_VLM_UNAVAILABLE_NOTICES = {
    "vlm_disabled": "VLM 보완 기능이 현재 비활성화되어 로컬 모델 결과만 사용했어요.",
    "vlm_configuration_incomplete": "VLM 보완 설정이 완료되지 않아 로컬 모델 결과만 사용했어요.",
    "vlm_timeout": "VLM 보완 요청 시간이 초과되어 로컬 모델 결과만 사용했어요.",
    "vlm_connection_failed": "VLM 보완 서비스에 연결할 수 없어 로컬 모델 결과만 사용했어요.",
    "vlm_rate_limited": "VLM 보완 요청이 많아 현재 사용할 수 없어 로컬 모델 결과만 사용했어요.",
    "vlm_service_unavailable": "VLM 보완 서비스를 일시적으로 사용할 수 없어 로컬 모델 결과만 사용했어요.",
    "vlm_response_invalid": "VLM 보완 결과를 확인할 수 없어 로컬 모델 결과만 사용했어요.",
}


def challenge_today():
    return datetime.now(ZoneInfo("Asia/Seoul")).date()


async def sanitized_photo(file: UploadFile) -> bytes:
    try:
        raw = await file.read(config.FOOD_PHOTO_MAX_BYTES + 1)
    finally:
        await file.close()
    if not raw or len(raw) > config.FOOD_PHOTO_MAX_BYTES:
        raise HTTPException(status_code=422, detail="사진은 비어 있지 않은 8MB 이하 파일이어야 합니다.")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in {"PNG", "JPEG", "WEBP"} or image.width * image.height > 12_000_000:
                raise HTTPException(status_code=422, detail="1200만 화소 이하 JPG·PNG·WEBP 사진을 사용해 주세요.")
            image.load()
            clean = image.convert("RGB")
            clean.thumbnail((1600, 1600))
            output = io.BytesIO()
            clean.save(output, format="JPEG", quality=85)
            return output.getvalue()  # EXIF/location and the original filename are not sent or retained.
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(status_code=422, detail="읽을 수 있는 사진 파일이 아닙니다.") from exc


async def _context(service, user, selected_id, proof_date, *, for_update=False):
    # Lock an existing parent row so simultaneous first submissions cannot both
    # create a proof, and a late rejected review cannot overwrite an acceptance.
    if for_update:
        selected = await UserChallenge.filter(id=selected_id, user_id=user.id).select_for_update().first()
    else:
        selected = await service.repo.get_user_challenge(selected_id, user.id)
    if selected is None:
        raise HTTPException(status_code=404, detail="선택한 챌린지를 찾을 수 없습니다.")
    if for_update:
        cycle = await ChallengeCycle.filter(id=selected.cycle_id, user_id=user.id).select_for_update().first()
    else:
        cycle = await service.repo.get_cycle(selected.cycle_id, user.id)
    await service._v3_health_permission(user)
    if cycle is None or cycle.status not in {"active", "scheduled"}:
        raise HTTPException(status_code=409, detail="진행 중인 챌린지가 아닙니다.")
    if not cycle.start_date <= proof_date <= min(cycle.end_date, challenge_today()):
        raise HTTPException(status_code=422, detail="챌린지 기간 안의 오늘 또는 과거 날짜만 기록할 수 있습니다.")
    challenge = await Challenge.get(id=selected.challenge_id)
    metadata = metadata_for(challenge.code)
    if not metadata or metadata["verification_type"] not in {1, 2}:
        raise HTTPException(status_code=422, detail="사진 제출형 챌린지가 아닙니다.")
    return metadata


async def _review(
    photo: bytes, verification_type: int, photo_context: FoodPhotoContext | None = None
) -> tuple[str, str, object | None]:
    if verification_type == 2:
        return "accepted", "사진 제출을 확인했습니다. 활동 시간·섭취량은 본인 기록이며 AI 검증이 아닙니다.", None
    if config.DEMO_MODE and not food_vision_is_configured():
        return (
            "accepted",
            "데모: 사진 제출만 확인했습니다. 채소 포함 여부·섭취량은 자동 판정하지 않았으며 본인 기록입니다.",
            None,
        )
    if config.FOOD_VISION_PROVIDER != "local_kfood":
        raise HTTPException(
            status_code=503, detail="사진 검토 서비스가 연결되지 않았습니다. 완료로 처리하지 않았습니다."
        )
    try:
        provider = get_food_vision_provider()
        if provider.provider_kind != "local_kfood_cv":
            raise FoodVisionError("The local Korean-food CV provider is required")
        result = await provider.analyze(photo, "image/jpeg", "challenge.jpg")
        result = await _supplement_review(result, photo, photo_context)
        if result.provider_kind not in {"local_kfood_cv", "local_kfood_openai_vlm"}:
            raise FoodVisionError("The image-review result is not from the local provider")
    except FoodVisionRuntimeError as exc:
        # Do not expose DLL paths, image contents, credentials or account details.
        logger.error("challenge_photo_runtime_unavailable reason=%s", exc.reason_code)
        raise _runtime_unavailable(exc.reason_code) from exc
    except FoodVisionError as exc:
        raise HTTPException(
            status_code=502, detail="사진 검토에 실패했습니다. 완료되지 않았으니 다시 시도해 주세요."
        ) from exc
    internal_metrics = {
        "event": "challenge_photo_ratio_analysis",
        "provider": result.provider_kind,
        "model_version": result.model_version,
        "food_coverage_percent": result.food_coverage_percent,
        "food_threshold_percent": config.FOOD_COVERAGE_PASS_THRESHOLD * 100,
        "vegetable_ratio_percent": result.vegetable_ratio_percent,
        "vegetable_threshold_percent": config.VEGETABLE_RATIO_PASS_THRESHOLD * 100,
        "reliable": result.reliable,
        "uncertainty_reasons": result.uncertainty_reasons,
        "decision_status": result.decision_status,
        "photo_context": photo_context.as_dict() if photo_context else None,
    }
    logger.info("%s", json.dumps(internal_metrics, ensure_ascii=False, separators=(",", ":")))

    messages = {
        "valid": ("needs_confirmation", "사진이 인증 기준을 충족했어요. 최종 확인 후 기록됩니다."),
        "invalid_photo_content": (
            "rejected", "식사 사진인지 확인하지 못했어요. 조리된 음식이 잘 보이는 사진을 제출해 주세요."
        ),
        "invalid_vegetable_content": (
            "rejected", "사진에서 채소를 확인하지 못했어요. 채소가 포함된 식사 전체를 촬영해 주세요."
        ),
        "invalid_food_ratio": (
            "rejected",
            "음식이 충분히 보이지 않아요. 식사 전체가 크게 보이도록 다시 촬영해 주세요.",
        ),
        "invalid_vegetable_ratio": (
            "rejected",
            "채소 포함 기준을 확인하지 못했어요. 채소가 잘 보이도록 다시 촬영해 주세요.",
        ),
        "uncertain": (
            "needs_review",
            "사진을 정확히 확인하기 어려워요. 밝은 곳에서 음식이 가리지 않도록 다시 촬영해 주세요.",
        ),
    }
    review_status, notice = messages.get(result.decision_status or "uncertain", messages["uncertain"])
    unavailable_reason = next(
        (reason for reason in result.uncertainty_reasons if reason in _VLM_UNAVAILABLE_NOTICES), None
    )
    if unavailable_reason:
        notice = f"{notice} {_VLM_UNAVAILABLE_NOTICES[unavailable_reason]}"
    return review_status, notice, result


async def _supplement_review(result, photo, photo_context: FoodPhotoContext | None = None):
    if config.OPENAI_VLM_FALLBACK_ENABLED:
        from app.vision.openai_vlm import supplement_with_vlm

        return await supplement_with_vlm(result, photo, photo_context)
    from app.vision.openai_vlm import needs_vlm

    if needs_vlm(result, photo_context):
        return replace(
            result,
            reliable=False if photo_context and photo_context.needs_supplement else result.reliable,
            decision_status="uncertain" if photo_context and photo_context.needs_supplement else result.decision_status,
            uncertainty_reasons=[*result.uncertainty_reasons, "vlm_disabled"],
        )
    return result


def _runtime_unavailable(reason_code: str) -> HTTPException:
    notices = {
        "runtime_security_blocked": "서버의 보안 설정이 사진 분석 프로그램 실행을 차단하고 있어요. 사진 문제가 아니며, 서버 실행 환경을 복구해야 합니다. 기록은 완료되지 않았어요.",
        "runtime_dependency_missing": "서버에 사진 분석 프로그램이 준비되지 않았어요. 서버 실행 환경을 확인해야 합니다. 기록은 완료되지 않았어요.",
    }
    return HTTPException(
        status_code=503,
        detail={
            "error_code": "PHOTO_REVIEW_UNAVAILABLE",
            "message": notices.get(
                reason_code,
                "서버의 사진 분석 프로그램을 실행하지 못했어요. 서버 실행 환경을 확인해야 합니다. 기록은 완료되지 않았어요.",
            ),
            "retryable": False,
        },
    )


async def _accepted_submission(user_id, selected_id, proof_date):
    existing = await ChallengeVerification.get_or_none(
        user_id=user_id, user_challenge_id=selected_id, verification_date=proof_date
    )
    log = await ChallengeLog.get_or_none(user_id=user_id, user_challenge_id=selected_id, log_date=proof_date)
    if existing and log and log.is_completed and existing.review_status == "accepted":
        return {
            "challenge_completed": True,
            "review_status": "accepted",
            "already_recorded": True,
            "verification_id": existing.id,
            "notice": "이미 저장된 인증입니다. 보상을 추가 지급하지 않습니다.",
        }
    return None


async def verify_photo(
    service, user, selected_id, proof_date, file, actual_value, confirmed=False, *, photo_context: FoodPhotoContext | None = None
):
    metadata = await _context(service, user, selected_id, proof_date)
    target = metadata["goal"]["target_minutes"] or metadata["goal"]["target_count"]
    if not math.isfinite(actual_value) or actual_value < target:
        raise HTTPException(status_code=422, detail=f"실제 실천량을 입력해 주세요. 완료 목표는 {target}입니다.")
    photo = await sanitized_photo(file)
    if metadata["verification_type"] != 1:
        photo_context = None
    digest = sha256_digest(photo)
    if photo_context is not None:
        # Final confirmation must match the reviewed image AND the same answers.
        answers = json.dumps(photo_context.as_dict(), sort_keys=True, separators=(",", ":")).encode()
        digest = sha256_digest(photo + b"\x00food-photo-context-v1\x00" + answers)
    prior_draft = await ChallengeVerification.get_or_none(
        user_id=user.id,
        user_challenge_id=selected_id,
        verification_date=proof_date,
        evidence_digest=digest,
        review_status="needs_confirmation",
    )
    try:
        existing = await _accepted_submission(user.id, selected_id, proof_date)
        if existing is not None:
            return existing
        review_status, notice, result = await _review(photo, metadata["verification_type"], photo_context)
    finally:
        del photo
    if review_status == "needs_confirmation" and confirmed and prior_draft is not None:
        review_status = "accepted"
        notice = "최종 확인이 완료되어 채소 식사 인증을 기록했어요."
    completed = review_status == "accepted"
    async with in_transaction():
        # The external review can take time. Honor eligibility or
        # cycle changes before recording its result, then preserve a concurrent
        # successful submission without changing its evidence or quantity.
        await _context(service, user, selected_id, proof_date, for_update=True)
        existing = await _accepted_submission(user.id, selected_id, proof_date)
        if existing is not None:
            return existing
        verification = await service.repo.upsert_verification(
            user_challenge_id=selected_id,
            user_id=user.id,
            verification_date=proof_date,
            values={
                "verification_type": "photo",
                "evidence_digest": digest,
                "evidence_ref": (
                    f"v3:{result.provider_kind}:{result.model_version}:{result.decision_status}"
                    if result is not None
                    else "v3:server-photo"
                ),
                "review_status": review_status,
            },
        )
        await service.repo.record_verification_event(verification)
        if completed:
            await service.repo.upsert_log(
                user_challenge_id=selected_id,
                user_id=user.id,
                log_date=proof_date,
                values={
                    "is_completed": True,
                    "value": actual_value,
                    "source": "photo_v3",
                    "note": f"evidence-v3 type{metadata['verification_type']}; quantity self-reported",
                },
            )
    return {
        "verification_id": verification.id,
        "challenge_completed": completed,
        "review_status": review_status,
        "already_recorded": False,
        "notice": notice,
    }
