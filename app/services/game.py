from fastapi import HTTPException, status
from tortoise.transactions import in_transaction

from app.dtos.game import AvatarEquipRequest
from app.models.game import InventoryItem, UserInventory
from app.models.users import User
from app.repositories.game_repository import GameRepository
from app.services.forest_wallet import ForestWalletService

CATALOG = (
    {
        "code": "sprout_hat",
        "name": "새싹 모자",
        "category": "hat",
        "price_carrots": 0,
        "asset_ref": "avatar/sprout-hat",
    },
    {
        "code": "round_glasses",
        "name": "동그란 안경",
        "category": "accessory",
        "price_carrots": 40,
        "asset_ref": "avatar/round-glasses",
    },
    {"code": "blue_cap", "name": "새벽 베레모", "category": "hat", "price_carrots": 60, "asset_ref": "avatar/blue-cap"},
)


class GameService:
    def __init__(self):
        self.repo = GameRepository()

    async def ensure_catalog(self):
        for item in CATALOG:
            await InventoryItem.update_or_create(defaults=item, code=item["code"])

    async def wallet(self, user: User):
        return await ForestWalletService().snapshot(user)

    async def catalog(self):
        await self.ensure_catalog()
        return {"items": [self.item_payload(item) for item in await self.repo.items()]}

    async def inventory(self, user: User):
        await self.ensure_catalog()
        rows = await self.repo.inventory(user.id)
        item_map = {item.id: item for item in await self.repo.items()}
        return {
            "items": [
                {**self.item_payload(item_map[row.item_id]), "quantity": row.quantity, "acquired_at": row.acquired_at}
                for row in rows
                if row.item_id in item_map
            ]
        }

    async def purchase(self, user: User, item_id: int):
        await self.ensure_catalog()
        item = await InventoryItem.get_or_none(id=item_id, is_active=True)
        if item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="아이템을 찾을 수 없습니다.")
        async with in_transaction():
            owned = await UserInventory.get_or_none(user_id=user.id, item_id=item.id)
            if owned is not None:
                return {"item_id": item.id, "already_owned": True}
            wallet = await self.repo.wallet(user.id)
            if wallet.carrot_balance < item.price_carrots:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="당근이 부족합니다.")
            await self.repo.credit(
                user.id, -item.price_carrots, "inventory_purchase", str(item.id), f"purchase:{user.id}:{item.id}"
            )
            await UserInventory.create(user_id=user.id, item_id=item.id, quantity=1)
        return {
            "item_id": item.id,
            "already_owned": False,
            "carrot_balance": (await self.repo.wallet(user.id)).carrot_balance,
        }

    async def avatar(self, user: User):
        avatar = await self.repo.avatar(user.id)
        return {
            "equipped_item_ids": avatar.equipped_item_ids,
            "version": avatar.version,
            "updated_at": avatar.updated_at,
        }

    async def equip(self, user: User, request: AvatarEquipRequest):
        unique_ids = list(dict.fromkeys(request.item_ids))
        owned = await UserInventory.filter(user_id=user.id, item_id__in=unique_ids).values_list("item_id", flat=True)
        if set(owned) != set(unique_ids):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="보유한 아이템만 장착할 수 있습니다.")
        items = await InventoryItem.filter(id__in=unique_ids)
        categories = [item.category for item in items]
        if len(categories) != len(set(categories)):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="같은 종류의 아이템은 하나만 장착할 수 있습니다.",
            )
        avatar = await self.repo.avatar(user.id)
        avatar.equipped_item_ids = unique_ids
        avatar.version += 1
        await avatar.save(update_fields=["equipped_item_ids", "version", "updated_at"])
        return await self.avatar(user)

    @staticmethod
    def item_payload(item: InventoryItem):
        return {
            "item_id": item.id,
            "code": item.code,
            "name": item.name,
            "category": item.category,
            "price_carrots": item.price_carrots,
            "asset_ref": item.asset_ref,
        }
