from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile

from app.apis.responses import envelope
from app.dependencies.security import get_request_user
from app.dtos.challenge_v2 import V2Preferences, V2Replacement, V2Review, V2SessionInput
from app.models.users import User
from app.services import challenge_v2 as service
from app.services import challenge_v2_evidence as evidence

challenge_v2_router = APIRouter(
    prefix="/challenge-v2",
    tags=["Challenge V2 pilot (deprecated)"],
    deprecated=True,
)


async def active_user(user: Annotated[User, Depends(get_request_user)]):
    if not user.is_active:
        raise HTTPException(403, "비활성 계정입니다.")
    return user


CurrentUser = Annotated[User, Depends(active_user)]


@challenge_v2_router.get("/capabilities")
async def capabilities():
    return envelope(
        {
            "enabled": service.enabled(),
            "policy_version": "2.1",
            "notice": "파일럿 목표입니다. 임상 효과나 운영 승인을 의미하지 않습니다.",
        }
    )


@challenge_v2_router.put("/preferences")
async def preferences(request: V2Preferences, user: CurrentUser):
    return envelope(await service.enroll(user, request))


@challenge_v2_router.get("/today")
async def today(user: CurrentUser):
    return envelope(await service.today(user))


@challenge_v2_router.post("/today")
async def assign_today(user: CurrentUser):
    return envelope(await service.today(user, create=True))


@challenge_v2_router.get("/history/{day_date}")
async def history(day_date: date, user: CurrentUser):
    return envelope(await service.history(user, day_date))


@challenge_v2_router.put("/assignments/{assignment_id}/sessions/{index}")
async def session(assignment_id: int, index: int, request: V2SessionInput, user: CurrentUser):
    return envelope(await service.record_session(user, assignment_id, index, request))


@challenge_v2_router.get("/assignments/{assignment_id}/alternatives")
async def alternatives(assignment_id: int, user: CurrentUser):
    service.require_enabled()
    await service.safety(user.id)
    return envelope({"items": await service.replacement_options(user, assignment_id)})


@challenge_v2_router.patch("/assignments/{assignment_id}/replacement")
async def replacement(assignment_id: int, request: V2Replacement, user: CurrentUser):
    return envelope(await service.replace(user, assignment_id, request))


@challenge_v2_router.put("/assignments/{assignment_id}/evidence/{index}")
async def upload(assignment_id: int, index: int, user: CurrentUser, photo: Annotated[UploadFile, File()]):
    service.require_enabled()
    await service.safety(user.id)
    await service.owned_assignment(user.id, assignment_id)
    raw = await photo.read(evidence.MAX_BYTES + 1)
    await photo.close()
    if len(raw) > evidence.MAX_BYTES:
        raise HTTPException(413, "사진은 10MB 이하로 올려 주세요.")
    return envelope(
        await evidence.upload(user, assignment_id, index, raw, photo.filename or "", photo.content_type or "")
    )


@challenge_v2_router.get("/evidence/{evidence_id}")
async def photo(evidence_id: int, user: CurrentUser):
    return Response(
        await evidence.read_photo(user, evidence_id),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@challenge_v2_router.get("/reviews")
async def queue(user: CurrentUser):
    return envelope({"items": await evidence.review_queue(user)})


@challenge_v2_router.post("/evidence/{evidence_id}/review")
async def review(evidence_id: int, request: V2Review, user: CurrentUser):
    return envelope(await evidence.review_photo(user, evidence_id, request))
