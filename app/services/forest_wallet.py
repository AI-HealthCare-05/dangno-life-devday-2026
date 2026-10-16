"""Authenticated forest actions share the account wallet and durable receipts."""

from datetime import datetime
from zoneinfo import ZoneInfo

from tortoise.transactions import in_transaction

from app.dtos.forest import ForestWalletActionRequest
from app.models.game import RewardTransaction
from app.models.users import User
from app.repositories.forest_repository import ForestRepository
from app.repositories.game_repository import GameRepository

KST = ZoneInfo("Asia/Seoul")
ACTION_AMOUNTS = {"water": 10, "fish": 5, "rabbit_catch": 1, "pet_feed": -1}


def forest_day():
    return datetime.now(KST).date().isoformat()


class ForestWalletService:
    async def snapshot(self, user: User):
        async with in_transaction():
            return await self._snapshot(user)

    async def _snapshot(self, user: User):
        await ForestRepository().avatar(user)
        wallet = await GameRepository().wallet(user.id)
        latest = await RewardTransaction.filter(user_id=user.id).select_for_update().order_by("-id").first()
        today = forest_day()
        daily_actions = {}
        for action in ("water", "fish"):
            daily_actions[action] = bool(
                await RewardTransaction.filter(
                    user_id=user.id, idempotency_key=f"forest-action:{user.id}:{action}:{today}"
                )
                .select_for_update()
                .first()
            )
        return {
            "user_id": user.id,
            "wallet_revision": latest.id if latest else 0,
            "carrot_balance": wallet.carrot_balance,
            "updated_at": wallet.updated_at.isoformat(),
            "wallet_updated_at": wallet.updated_at.isoformat(),
            "date": today,
            "daily_actions": daily_actions,
        }

    async def perform(self, user: User, request: ForestWalletActionRequest):
        action = request.action
        today = forest_day()
        reference = today if action in ("water", "fish") else str(request.request_id)
        async with in_transaction() as connection:
            await ForestRepository().avatar(user)
            transaction, granted = await GameRepository().credit(
                user.id,
                ACTION_AMOUNTS[action],
                f"forest_{action}",
                reference,
                f"forest-action:{user.id}:{action}:{reference}",
                using_db=connection,
            )
        # A retry returns the CURRENT balance, never an older receipt's balance_after.
        return {
            **await self.snapshot(user),
            "action": action,
            "amount": transaction.amount if granted else 0,
            "applied": granted,
        }
