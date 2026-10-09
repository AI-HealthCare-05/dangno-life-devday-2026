from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI

from app.core import config
from app.core.redis import close_redis, redis_client


async def preload_embedded_demo_models() -> None:
    """Load and verify both approved artifacts before accepting demo traffic."""
    from app.prediction.providers import load_standard_model
    from src.ml.inference.diabetes_current_screening import load_current_screening_model

    await asyncio.gather(
        asyncio.to_thread(load_standard_model),
        asyncio.to_thread(
            load_current_screening_model,
            manifest_path=Path(config.CURRENT_SCREENING_MANIFEST_URI),
            model_path=config.CURRENT_SCREENING_MODEL_URI,
        ),
    )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Own application startup resources and collect them during shutdown."""
    if not config.DEMO_MODE:
        await redis_client.ping()
    if config.DEMO_MODE and config.DEMO_ARTIFACT_INFERENCE_ENABLED:
        await preload_embedded_demo_models()

    from app.services.challenge_v2_retention import retention_loop

    retention = asyncio.create_task(retention_loop())
    try:
        yield
    finally:
        retention.cancel()
        with suppress(asyncio.CancelledError):
            await retention
        if not config.DEMO_MODE:
            await close_redis()
