"""Real local CV + HTTP proof flow, using only samples and an in-memory DB."""

import asyncio
import os
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


async def main():
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env.local-mobile")
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["OPENAI_VLM_FALLBACK_ENABLED"] = "false"
    from httpx import ASGITransport, AsyncClient
    from tortoise import Tortoise

    from app.core import config
    from app.core.db.databases import TORTOISE_APP_MODELS
    from app.main import app
    from app.models.health import ChallengeLog, ChallengeVerification
    from app.vision.food_vision import food_vision_is_configured

    assert not config.OPENAI_VLM_FALLBACK_ENABLED and not config.OPENAI_API_KEY
    assert config.FOOD_VISION_PROVIDER == "local_kfood" and food_vision_is_configured()
    helpers = runpy.run_path(str(ROOT / "tests/test_challenge_v3_api.py"))
    await Tortoise.init(db_url="sqlite://:memory:", modules={"models": TORTOISE_APP_MODELS}, timezone="Asia/Seoul")
    await Tortoise.generate_schemas()
    try:
        user, headers = await helpers["eligible_user"]("cv-smoke@example.test")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            api = SimpleNamespace(user=user, headers=headers, client=client)
            cycle = await helpers["start_cycle"](api, rotation=1)
            item = helpers["find_item"](cycle, "fiber_diet")

            async def submit(name, confirmed=False):
                response = await helpers["submit_photo"](
                    api, item, content=(ROOT / "src/frontend/assets/demo" / name).read_bytes(), confirmed=confirmed
                )
                assert response.status_code == 201, response.text
                return response.json()["data"]

            for name in ("vegetable-meal-low-veg.png", "irrelevant-desk.png"):
                result = await submit(name)
                assert result["review_status"] == "rejected" and result["challenge_completed"] is False
                assert await ChallengeLog.all().count() == 0
                print("PASS rejected", name)
            draft = await submit("vegetable-meal-1.png")
            assert draft["review_status"] == "needs_confirmation" and draft["challenge_completed"] is False
            assert await ChallengeLog.all().count() == 0
            accepted = await submit("vegetable-meal-1.png", confirmed=True)
            assert accepted["review_status"] == "accepted" and accepted["challenge_completed"] is True
            assert await ChallengeLog.filter(is_completed=True).count() == 1
            proof = await ChallengeVerification.get(user_challenge_id=item["user_challenge_id"])
            assert proof.evidence_ref.startswith("v3:local_kfood_cv:")
            duplicate = await submit("vegetable-meal-1.png", confirmed=True)
            assert duplicate["already_recorded"] is True
            assert await ChallengeLog.all().count() == 1
            print("PASS actual local CV: confirmation, completion, duplicate protection")
    finally:
        await Tortoise.close_connections()


if __name__ == "__main__":
    asyncio.run(main())
