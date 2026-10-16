from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.apis.responses import envelope
from app.dependencies.security import get_request_user
from app.dtos.forest import (
    ForestAvatarUpdateRequest,
    ForestObjectCreateRequest,
    ForestSpaceCreateRequest,
    ForestWalletActionRequest,
)
from app.models.users import User
from app.services.forest import ForestService
from app.services.forest_wallet import ForestWalletService

forest_router = APIRouter(prefix="/forest", tags=["Carrot Forest Lite"])


@forest_router.post("/wallet/actions")
async def forest_wallet_action(request: ForestWalletActionRequest, user: Annotated[User, Depends(get_request_user)]):
    return envelope(await ForestWalletService().perform(user, request))


@forest_router.get("/catalog")
async def forest_catalog(_: Annotated[User, Depends(get_request_user)]) -> dict[str, object]:
    return envelope(ForestService().catalog())


@forest_router.post("/spaces", status_code=status.HTTP_201_CREATED)
async def create_forest_space(
    request: ForestSpaceCreateRequest,
    user: Annotated[User, Depends(get_request_user)],
) -> dict[str, object]:
    return envelope(await ForestService().create_space(user, request))


@forest_router.get("/spaces/{group_id}")
async def forest_home(group_id: int, user: Annotated[User, Depends(get_request_user)]) -> dict[str, object]:
    return envelope(await ForestService().home(user, group_id))


@forest_router.patch("/avatar")
async def update_forest_avatar(
    request: ForestAvatarUpdateRequest,
    user: Annotated[User, Depends(get_request_user)],
) -> dict[str, object]:
    return envelope(await ForestService().update_avatar(user, request))


@forest_router.post("/spaces/{group_id}/rewards/group-daily")
async def claim_group_daily_reward(
    group_id: int,
    user: Annotated[User, Depends(get_request_user)],
) -> dict[str, object]:
    return envelope(await ForestService().claim_group_reward(user, group_id))


@forest_router.post("/spaces/{group_id}/objects", status_code=status.HTTP_201_CREATED)
async def place_forest_object(
    group_id: int,
    request: ForestObjectCreateRequest,
    user: Annotated[User, Depends(get_request_user)],
) -> dict[str, object]:
    return envelope(await ForestService().place_object(user, group_id, request))


@forest_router.delete("/spaces/{group_id}/objects/{object_id}")
async def remove_forest_object(
    group_id: int,
    object_id: int,
    user: Annotated[User, Depends(get_request_user)],
) -> dict[str, object]:
    return envelope(await ForestService().remove_object(user, group_id, object_id))
