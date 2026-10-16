from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ForestSpaceCreateRequest(BaseModel):
    group_id: int = Field(gt=0)
    name: str = Field(default="당근의 숲", min_length=2, max_length=40)


class ForestAvatarUpdateRequest(BaseModel):
    # Older clients may still send this field; only the main profile can rename a user.
    display_name: str | None = Field(default=None, min_length=1, max_length=20, deprecated=True)
    hair_code: str = Field(min_length=1, max_length=40)
    outfit_code: str = Field(min_length=1, max_length=40)
    accessory_code: str = Field(min_length=1, max_length=40)


class ForestObjectCreateRequest(BaseModel):
    object_code: Literal["sunflower", "bench", "mushroom", "rabbit"]
    position_x: int = Field(ge=0, le=100)
    position_y: int = Field(ge=0, le=100)


class ForestWalletActionRequest(BaseModel):
    # Amounts and daily reward keys are always determined by the server.
    model_config = {"extra": "forbid"}
    action: Literal["water", "fish", "rabbit_catch", "pet_feed"]
    request_id: UUID
