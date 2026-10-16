from __future__ import annotations

import secrets
from datetime import date
from typing import Any

from tortoise.transactions import in_transaction

from app.models.challenge_v2 import ChallengeV2Reward
from app.models.engagement import SharedChallengeGroup, SharedChallengeMember
from app.models.forest import ForestAvatar, ForestInventory, ForestObject, ForestReward, ForestSpace
from app.models.health import ChallengeLog
from app.models.users import User
from app.repositories.game_repository import GameRepository
from app.services.challenge_wallet import v2_receipt_key

WELCOME_CARROTS = 100

# Placeholder shown for accounts that have not set an account name yet. Never derived
# from the email address -- an avatar display name must not leak account contact info.
GENERIC_DISPLAY_NAME = "숲지기"

# Mirrors the adjective/noun pool the forest world's demo mode generates nicknames from
# (src/frontend/forest-game.js), so a brand-new avatar's display name looks the same
# whether it came from a real account or the local demo.
NICKNAME_ADJECTIVES = ("씩씩한", "다정한", "반짝이는", "꾸준한", "포근한", "용감한", "싱그러운", "재빠른")
NICKNAME_NOUNS = ("당근", "새싹", "토끼", "숲지기", "햇살")


class ForestRepository:
    async def active_member(self, group_id: int, user_id: int) -> SharedChallengeMember | None:
        return await SharedChallengeMember.get_or_none(group_id=group_id, user_id=user_id, status="active")

    async def group(self, group_id: int) -> SharedChallengeGroup | None:
        return await SharedChallengeGroup.get_or_none(id=group_id, status="active")

    async def members(self, group_id: int) -> list[SharedChallengeMember]:
        return await SharedChallengeMember.filter(group_id=group_id, status="active").order_by("id")

    async def users(self, user_ids: list[int]) -> dict[int, User]:
        return {item.id: item for item in await User.filter(id__in=user_ids)}

    async def space(self, group_id: int) -> ForestSpace | None:
        return await ForestSpace.get_or_none(group_id=group_id)

    async def create_space(self, **values: Any) -> ForestSpace:
        return await ForestSpace.create(**values)

    async def _unique_nickname(self) -> str:
        existing = set(await ForestAvatar.all().values_list("display_name", flat=True))
        candidates = [f"{adjective} {noun}" for adjective in NICKNAME_ADJECTIVES for noun in NICKNAME_NOUNS]
        available = [name for name in candidates if name not in existing]
        picked = secrets.choice(available or candidates)
        if picked in existing:
            # Every combination in the pool is already taken (very unlikely) — disambiguate
            # instead of silently colliding with another account's nickname.
            picked = f"{picked}{secrets.randbelow(90) + 10}"
        return picked

    async def nickname_taken(self, display_name: str, exclude_user_id: int) -> bool:
        return await ForestAvatar.filter(display_name=display_name).exclude(user_id=exclude_user_id).exists()

    def _resolved_display_name(self, user: User) -> str:
        # The forest avatar's display name is a derived view of the account name, not an
        # independently editable nickname -- it must always read back either the user's
        # current name or this generic placeholder, never a stale value, a legacy
        # request-supplied nickname, or anything derived from the account's email.
        return user.name if user.name else GENERIC_DISPLAY_NAME

    async def sync_existing_avatar_name(self, user: User) -> None:
        # Keep the forest avatar's display name in step with the account name shown
        # elsewhere in the app whenever the user renames themselves via PATCH
        # /api/v1/users/me. Deliberately uses get_or_none rather than the get_or_create
        # pattern `avatar()` uses: a user who has never opened the forest feature must
        # not have an avatar (and the welcome-carrot grant that comes with creating one)
        # created as a side effect of an unrelated profile edit. Only this user's own
        # avatar is ever touched, and only display_name changes -- cosmetics and
        # carrot_balance are left exactly as they were.
        avatar = await ForestAvatar.get_or_none(user_id=user.id)
        if avatar is None:
            return
        resolved_name = self._resolved_display_name(user)
        if avatar.display_name == resolved_name:
            return
        avatar.display_name = resolved_name
        await avatar.save(update_fields=["display_name", "updated_at"])

    async def avatar(self, user: User) -> ForestAvatar:
        async with in_transaction() as connection:
            return await self._account_avatar(user, connection)

    async def _account_avatar(self, user: User, connection) -> ForestAvatar:
        resolved_name = self._resolved_display_name(user)
        avatar, created = await ForestAvatar.get_or_create(
            user_id=user.id,
            defaults={"display_name": resolved_name, "carrot_balance": WELCOME_CARROTS},
            using_db=connection,
        )
        if not created and avatar.display_name != resolved_name:
            # Self-heal any avatar row that has drifted from the account name -- e.g. one
            # created back when avatars had independently chosen nicknames, or a legacy
            # email-derived name. The account name (or the generic placeholder above) is
            # always the source of truth now.
            avatar.display_name = resolved_name
            await avatar.save(using_db=connection, update_fields=["display_name", "updated_at"])
        # Wallet (UserWallet) is the single source of truth for the carrot balance shown
        # across the app now. Migrate/grant the balance this row already held (100 for a
        # brand-new avatar, or whatever an existing avatar had accumulated before this
        # switchover) into the wallet exactly once — `credit()` is idempotent on this key,
        # so every call after the first is a no-op.
        game = GameRepository()
        welcome, _ = await game.credit(
            user.id,
            avatar.carrot_balance,
            "forest_welcome_bonus",
            str(user.id),
            f"forest-welcome:{user.id}",
            using_db=connection,
        )
        # Before wallet unification V2 wrote only to ForestAvatar. Rewards older
        # than the welcome migration were already included in that snapshot;
        # replay only later receipts, once each, without trusting browser balances.
        _, migrate = await game.credit(
            user.id, 0, "forest_wallet_migration", str(user.id), f"forest-wallet-unified:{user.id}", using_db=connection
        )
        if migrate:
            old_rewards = (
                await ChallengeV2Reward.filter(user_id=user.id).using_db(connection).order_by("created_at", "id")
            )
            for reward in old_rewards:
                if reward.created_at > welcome.created_at:
                    await game.credit(
                        user.id,
                        reward.carrot_amount,
                        "challenge_v2_reward",
                        reward.source_key,
                        f"challenge-v2:{reward.source_key}",
                        using_db=connection,
                    )
                # A zero receipt reserves today's shared key for amounts already
                # included in the avatar snapshot or replayed above.
                await game.credit(
                    user.id,
                    0,
                    "challenge_reward_migration",
                    reward.source_key,
                    await v2_receipt_key(user.id, reward.day_id, reward.source_key),
                    using_db=connection,
                )
        return avatar

    async def avatars(self, users: list[User]) -> dict[int, ForestAvatar]:
        result: dict[int, ForestAvatar] = {}
        for user in users:
            result[user.id] = await self.avatar(user)
        return result

    async def inventory(self, user_id: int) -> list[ForestInventory]:
        return await ForestInventory.filter(user_id=user_id).order_by("acquired_at", "id")

    async def has_item(self, user_id: int, item_code: str) -> bool:
        return await ForestInventory.filter(user_id=user_id, item_code=item_code).exists()

    async def add_item(self, user_id: int, item_code: str, acquired_source: str) -> None:
        await ForestInventory.get_or_create(
            user_id=user_id,
            item_code=item_code,
            defaults={"acquired_source": acquired_source},
        )

    async def objects(self, forest_space_id: int) -> list[ForestObject]:
        return await ForestObject.filter(forest_space_id=forest_space_id).order_by("id")

    async def create_object(self, **values: Any) -> ForestObject:
        return await ForestObject.create(**values)

    async def object(self, forest_space_id: int, object_id: int) -> ForestObject | None:
        return await ForestObject.get_or_none(id=object_id, forest_space_id=forest_space_id)

    async def completed_today(self, user_id: int, today: date) -> int:
        return await ChallengeLog.filter(user_id=user_id, log_date=today, is_completed=True).count()

    async def reward(self, source_key: str) -> ForestReward | None:
        return await ForestReward.get_or_none(source_key=source_key)

    async def create_reward(self, **values: Any) -> ForestReward:
        return await ForestReward.create(**values)
