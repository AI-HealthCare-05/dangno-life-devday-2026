from __future__ import annotations

import hashlib
from datetime import date

from fastapi import HTTPException, status
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.dtos.forest import ForestAvatarUpdateRequest, ForestObjectCreateRequest, ForestSpaceCreateRequest
from app.models.forest import ForestAvatar, ForestInventory, ForestReward, ForestSpace
from app.models.users import User
from app.repositories.forest_repository import ForestRepository
from app.repositories.game_repository import GameRepository
from app.repositories.health_repository import HealthRepository

DAILY_QUEST_COUNT = 3
WELCOME_CARROTS = 100
GROUP_REWARD_CARROTS = 50

HAIR_CATALOG = {
    "midnight_short": "밤색 숏헤어",
    "silver_bob": "은빛 보브",
    "carrot_bob": "당근빛 단발",
}
OUTFIT_CATALOG = {
    "orange_hoodie": "오렌지 후드",
    "garden_overall": "정원 멜빵",
    "green_knit": "초록 니트",
}
ACCESSORY_CATALOG = {
    "none": {"name": "착용 안 함", "default": True},
    "sprout_beret": {"name": "새싹 베레모", "default": False},
    "flower_pin": {"name": "꽃 머리핀", "default": False},
    "carrot_bag": {"name": "당근 가방", "default": False},
    "blue_watering_can": {"name": "파란 물뿌리개", "default": False},
}
OBJECT_CATALOG = {
    "sunflower": {"name": "해바라기", "cost": 20},
    "bench": {"name": "나무 벤치", "cost": 35},
    "mushroom": {"name": "버섯 장식", "cost": 15},
    "rabbit": {"name": "토끼 친구", "cost": 50},
}
REWARD_ITEMS = tuple(code for code, item in ACCESSORY_CATALOG.items() if not item["default"])


class ForestService:
    def __init__(self) -> None:
        self.repo = ForestRepository()
        self.game_repo = GameRepository()
        self.health_repo = HealthRepository()

    async def _group_and_member(self, user: User, group_id: int):
        group = await self.repo.group(group_id)
        member = await self.repo.active_member(group_id, user.id)
        if group is None or member is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="참여 중인 공동 챌린지를 찾을 수 없습니다."
            )
        return group, member

    async def _space_for_user(self, user: User, group_id: int) -> ForestSpace:
        await self._group_and_member(user, group_id)
        space = await self.repo.space(group_id)
        if space is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="당근의 숲이 아직 열리지 않았습니다. 먼저 숲을 시작해 주세요.",
            )
        return space

    def catalog(self) -> dict[str, object]:
        return {
            "hair": [{"code": code, "name": name} for code, name in HAIR_CATALOG.items()],
            "outfits": [{"code": code, "name": name} for code, name in OUTFIT_CATALOG.items()],
            "accessories": [
                {"code": code, "name": item["name"], "default": item["default"]}
                for code, item in ACCESSORY_CATALOG.items()
            ],
            "objects": [{"code": code, **item} for code, item in OBJECT_CATALOG.items()],
            "policy": "무료 활동 보상만 제공하며 결제·아이템 거래·확률형 유료 상품은 포함하지 않습니다.",
        }

    async def create_space(self, user: User, request: ForestSpaceCreateRequest) -> dict[str, object]:
        group, _ = await self._group_and_member(user, request.group_id)
        space = await self.repo.space(group.id)
        if space is None:
            space = await self.repo.create_space(
                group_id=group.id,
                name=request.name,
                created_by_user_id=user.id,
            )
        await self.repo.avatar(user)
        return await self.home(user, group.id)

    async def _progress(self, group_id: int) -> tuple[list[dict[str, object]], int, int]:
        members = await self.repo.members(group_id)
        users = await self.repo.users([member.user_id for member in members])
        avatars = await self.repo.avatars(list(users.values()))
        rows: list[dict[str, object]] = []
        total = 0
        target_total = 0
        today = date.today()
        for member in members:
            # A member's real daily target is however many challenges THEY selected for
            # their own cycle, not a flat 3 — the challenge-selection flow only requires
            # "1 or more" (see ChallengeService.create_cycle), so assuming everyone has
            # exactly 3 made the group goal permanently unreachable for anyone who didn't.
            cycle = await self.health_repo.cycle_for_date(member.user_id, today)
            selected_count = len(await self.health_repo.list_user_challenges(cycle.id, member.user_id)) if cycle else 0
            member_target = selected_count or DAILY_QUEST_COUNT
            completed = min(member_target, await self.repo.completed_today(member.user_id, today))
            total += completed
            target_total += member_target
            person = users[member.user_id]
            avatar = avatars[member.user_id]
            wallet = await self.game_repo.wallet(member.user_id)
            rows.append(
                {
                    "user_id": member.user_id,
                    "display_name": avatar.display_name or person.name or "구성원",
                    "today_completed": completed,
                    "today_target": member_target,
                    "avatar": self._avatar_payload(avatar, wallet.carrot_balance),
                }
            )
        return rows, total, target_total

    def _avatar_payload(self, avatar: ForestAvatar, carrot_balance: int) -> dict[str, object]:
        return {
            "display_name": avatar.display_name,
            "hair_code": avatar.hair_code,
            "outfit_code": avatar.outfit_code,
            "accessory_code": avatar.accessory_code,
            "carrot_balance": carrot_balance,
        }

    async def home(self, user: User, group_id: int) -> dict[str, object]:
        space = await self._space_for_user(user, group_id)
        avatar = await self.repo.avatar(user)
        wallet = await self.game_repo.wallet(user.id)
        members, completed, target = await self._progress(group_id)
        inventory = await self.repo.inventory(user.id)
        objects = await self.repo.objects(space.id)
        reward_key = f"group-daily:{group_id}:{date.today().isoformat()}:{user.id}"
        return {
            "forest_space_id": space.id,
            "group_id": group_id,
            "name": space.name,
            "today": {
                "completed": completed,
                "target": target,
                "group_reward_ready": target > 0 and completed >= target,
                "group_reward_claimed": await self.repo.reward(reward_key) is not None,
            },
            "me": self._avatar_payload(avatar, wallet.carrot_balance),
            "members": members,
            "inventory": [item.item_code for item in inventory],
            "objects": [
                {
                    "object_id": item.id,
                    "object_code": item.object_code,
                    "position_x": item.position_x,
                    "position_y": item.position_y,
                }
                for item in objects
            ],
            "sharing_scope": ["challenge_status", "avatar", "forest_objects"],
            "privacy_notice": "챌린지 완료 여부와 아바타·숲 장식만 공유합니다. 건강정보와 예측 결과는 공유하지 않습니다.",
        }

    async def update_avatar(self, user: User, request: ForestAvatarUpdateRequest) -> dict[str, object]:
        if request.hair_code not in HAIR_CATALOG or request.outfit_code not in OUTFIT_CATALOG:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="선택할 수 없는 아바타 항목입니다."
            )
        accessory = ACCESSORY_CATALOG.get(request.accessory_code)
        if accessory is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="선택할 수 없는 액세서리입니다."
            )
        if not accessory["default"] and not await self.repo.has_item(user.id, request.accessory_code):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="아직 획득하지 않은 액세서리입니다.")
        # `request.display_name` is a deprecated field (see ForestAvatarUpdateRequest).
        # Named accounts use the main profile as the source of truth; only legacy
        # nameless accounts may promote this field into their account name so older
        # clients keep working without reintroducing independently editable nicknames.
        avatar = await self.repo.avatar(user)
        update_fields = ["hair_code", "outfit_code", "accessory_code", "updated_at"]
        display_name_value = request.__dict__.get("display_name")
        legacy_display_name = display_name_value.strip() if display_name_value else None
        if user.name is None and legacy_display_name:
            user.name = legacy_display_name
            await user.save(update_fields=["name", "updated_at"])
            avatar.display_name = legacy_display_name
            update_fields.insert(0, "display_name")
        avatar.hair_code = request.hair_code
        avatar.outfit_code = request.outfit_code
        avatar.accessory_code = request.accessory_code
        await avatar.save(update_fields=update_fields)
        wallet = await self.game_repo.wallet(user.id)
        return self._avatar_payload(avatar, wallet.carrot_balance)

    async def claim_group_reward(self, user: User, group_id: int) -> dict[str, object]:
        space = await self._space_for_user(user, group_id)
        _, completed, target = await self._progress(group_id)
        if target == 0 or completed < target:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="모든 구성원이 오늘 3개를 완료하면 보상 상자가 열립니다."
            )
        source_key = f"group-daily:{group_id}:{date.today().isoformat()}:{user.id}"
        if await self.repo.reward(source_key) is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="오늘의 그룹 보상을 이미 받았습니다.")
        owned = {item.item_code for item in await self.repo.inventory(user.id)}
        available = [code for code in REWARD_ITEMS if code not in owned]
        seed = int(hashlib.sha256(source_key.encode()).hexdigest()[:8], 16)
        item_code = available[seed % len(available)] if available else None
        await self.repo.avatar(user)
        try:
            async with in_transaction() as connection:
                await ForestReward.create(
                    user_id=user.id,
                    forest_space_id=space.id,
                    source_key=source_key,
                    reward_date=date.today(),
                    carrot_amount=GROUP_REWARD_CARROTS,
                    item_code=item_code,
                    using_db=connection,
                )
                transaction, _ = await self.game_repo.credit(
                    user.id,
                    GROUP_REWARD_CARROTS,
                    "group_daily_reward",
                    source_key,
                    source_key,
                    using_db=connection,
                )
                if item_code:
                    await ForestInventory.get_or_create(
                        user_id=user.id,
                        item_code=item_code,
                        defaults={"acquired_source": "group_daily_reward"},
                        using_db=connection,
                    )
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="오늘의 그룹 보상을 이미 받았습니다."
            ) from exc
        return {
            "carrot_amount": GROUP_REWARD_CARROTS,
            "item_code": item_code,
            "item_name": ACCESSORY_CATALOG[item_code]["name"] if item_code else None,
            "carrot_balance": transaction.balance_after,
            "notice": "활동 완료에 따른 무료 보상입니다. 결제 또는 현금성 가치가 없습니다.",
        }

    async def place_object(self, user: User, group_id: int, request: ForestObjectCreateRequest) -> dict[str, object]:
        space = await self._space_for_user(user, group_id)
        catalog_item = OBJECT_CATALOG[request.object_code]
        await self.repo.avatar(user)
        wallet = await self.game_repo.wallet(user.id)
        if wallet.carrot_balance < catalog_item["cost"]:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="당근이 부족합니다.")
        # Placement and debit must roll back together if another purchase spent
        # the remaining carrots while this request was waiting for the wallet lock.
        async with in_transaction() as connection:
            item = await self.repo.create_object(
                forest_space_id=space.id,
                placed_by_user_id=user.id,
                **request.model_dump(),
            )
            transaction, _ = await self.game_repo.credit(
                user.id,
                -catalog_item["cost"],
                "forest_object_purchase",
                str(item.id),
                f"forest-object-purchase:{item.id}",
                using_db=connection,
            )
        return {
            "object_id": item.id,
            "object_code": item.object_code,
            "position_x": item.position_x,
            "position_y": item.position_y,
            "carrot_balance": transaction.balance_after,
        }

    async def remove_object(self, user: User, group_id: int, object_id: int) -> dict[str, object]:
        space = await self._space_for_user(user, group_id)
        item = await self.repo.object(space.id, object_id)
        if item is None:
            return {"object_id": object_id, "removed": False, "already_removed": True, "carrot_refund": 0}
        if item.placed_by_user_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="본인이 배치한 오브젝트만 회수할 수 있습니다."
            )
        await item.delete()
        return {"object_id": object_id, "removed": True, "already_removed": False, "carrot_refund": 0}
