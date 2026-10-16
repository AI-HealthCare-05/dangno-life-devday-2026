"""One daily receipt per domain and one completion bonus across challenge UIs."""

from tortoise.transactions import in_transaction

from app.models.challenge_v2 import ChallengeV2Assignment, ChallengeV2Day
from app.models.game import RewardTransaction
from app.models.health import Challenge
from app.repositories.game_repository import GameRepository
from app.services.challenge_catalog import metadata_for

MESSAGES = {
    "diet": "당근밭에 비료를 주었습니다",
    "activity": "당근밭의 잡초를 뽑았습니다",
    "routine": "당근밭에 물을 주었습니다",
}


def receipt_key(user_id, reward_date, domain=None):
    return (
        f"challenge-daily:{user_id}:{reward_date}"
        if domain is None
        else f"challenge-domain:{user_id}:{reward_date}:{domain}"
    )


async def v2_receipt_key(user_id, day_id, source):
    day = await ChallengeV2Day.get(id=day_id)
    if source.startswith("v2-day:"):
        return receipt_key(user_id, day.assigned_date)
    slot = int(source.rsplit(":", 1)[1])
    item = await ChallengeV2Assignment.filter(day_id=day_id, slot=slot).order_by("revision").first()
    domain = item.goal["domain"] if item else f"slot-{slot}"
    return receipt_key(user_id, day.assigned_date, domain)


async def credit_daily_bonus(user, reward_date, using_db=None):
    game = GameRepository()
    key = receipt_key(user.id, reward_date)
    # Existing 55-carrot legacy claims remain intact; do not pay a second bonus.
    legacy = await RewardTransaction.get_or_none(
        idempotency_key=f"daily-reward:{user.id}:{reward_date}", using_db=using_db
    )
    return await game.credit(
        user.id, 0 if legacy else 50, "daily_challenge_reward", str(reward_date), key, using_db=using_db
    )


async def award_v3_completion(user, selected, reward_date, repo):
    challenge = await Challenge.get(id=selected.challenge_id)
    metadata = metadata_for(challenge.code)
    if not metadata:
        return None
    domain = "routine" if metadata["domain"] == "hydration" else challenge.category
    # Import locally: forest migration also uses the shared receipt-key helpers.
    from app.repositories.forest_repository import ForestRepository

    async with in_transaction() as connection:
        await ForestRepository().avatar(user)
        transaction, granted = await GameRepository().credit(
            user.id,
            10,
            "challenge_completion",
            f"{selected.id}:{reward_date}",
            receipt_key(user.id, reward_date, domain),
            using_db=connection,
        )
        items = await repo.list_user_challenges(selected.cycle_id, user.id)
        completed = await repo.completed_challenge_ids_for_date(selected.cycle_id, user.id, reward_date)
        bonus = 0
        if items and len(completed) == len(items):
            bonus_transaction, bonus_granted = await credit_daily_bonus(user, reward_date, using_db=connection)
            bonus = bonus_transaction.amount if bonus_granted else 0
            await repo.claim_daily_reward(user.id, reward_date, 50)
        wallet = await GameRepository().wallet(user.id)
        earned = transaction.amount if granted else 0
        return {
            "carrot_balance": wallet.carrot_balance,
            "earned_carrots": earned,
            "daily_bonus": bonus,
            "notice": (
                f"{MESSAGES[domain]}. 당근 {earned}개를 획득했습니다!"
                if earned
                else "오늘 이 챌린지 보상은 이미 받았습니다."
            )
            + (" 모든 챌린지를 완료해 당근 50개를 추가로 획득했습니다!" if bonus else ""),
        }
