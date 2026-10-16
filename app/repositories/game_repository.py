from fastapi import HTTPException
from tortoise.transactions import in_transaction

from app.models.game import InventoryItem, RewardTransaction, UserAvatar, UserInventory, UserWallet


class GameRepository:
    async def wallet(self, user_id: int) -> UserWallet:
        await UserWallet.get_or_create(user_id=user_id)
        return await UserWallet.filter(user_id=user_id).select_for_update().get()

    async def credit(
        self,
        user_id: int,
        amount: int,
        source_type: str,
        source_ref: str,
        key: str,
        using_db=None,
    ):
        # Every balance update and its receipt commit together. Lock the wallet BEFORE
        # checking the key so simultaneous retries cannot both grant the same reward.
        if using_db is None:
            async with in_transaction() as connection:
                return await self.credit(user_id, amount, source_type, source_ref, key, using_db=connection)
        await UserWallet.get_or_create(user_id=user_id, using_db=using_db)
        wallet = await UserWallet.filter(user_id=user_id).using_db(using_db).select_for_update().get()
        existing = await RewardTransaction.filter(idempotency_key=key).using_db(using_db).select_for_update().first()
        if existing is not None:
            return existing, False
        if wallet.carrot_balance + amount < 0:
            raise HTTPException(409, "당근이 부족합니다.")
        wallet.carrot_balance += amount
        await wallet.save(using_db=using_db, update_fields=["carrot_balance", "updated_at"])
        transaction = await RewardTransaction.create(
            user_id=user_id,
            transaction_type="earn" if amount >= 0 else "spend",
            amount=amount,
            balance_after=wallet.carrot_balance,
            source_type=source_type,
            source_ref=source_ref,
            idempotency_key=key,
            using_db=using_db,
        )
        return transaction, True

    async def items(self) -> list[InventoryItem]:
        return await InventoryItem.filter(is_active=True).order_by("price_carrots", "id")

    async def inventory(self, user_id: int) -> list[UserInventory]:
        return await UserInventory.filter(user_id=user_id).order_by("item_id")

    async def avatar(self, user_id: int) -> UserAvatar:
        avatar, _ = await UserAvatar.get_or_create(user_id=user_id)
        return avatar
