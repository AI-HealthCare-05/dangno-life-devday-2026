from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Response, status
from redis.exceptions import RedisError
from tortoise import connections
from tortoise.exceptions import DBConnectionError, OperationalError

from app.core import config
from app.core.redis import redis_client

health_router = APIRouter(tags=["Health"])
_DEPENDENCY_ERRORS = (RedisError, OperationalError, DBConnectionError)


async def dependency_status() -> tuple[bool, bool]:
    """Return database and Redis availability without leaking dependency errors."""
    database_ok = True
    redis_ok = True

    if not config.DEMO_MODE:
        try:
            await redis_client.ping()
        except _DEPENDENCY_ERRORS:
            redis_ok = False

    try:
        await connections.get("default").execute_query("SELECT 1")
    except _DEPENDENCY_ERRORS:
        database_ok = False

    return database_ok, redis_ok


@health_router.get("/health")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@health_router.get("/api/health")
@health_router.get("/api/v1/health")
async def health(response: Response) -> dict[str, str]:
    database_ok, redis_ok = await dependency_status()
    healthy = database_ok and redis_ok
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ok" if healthy else "degraded",
        "database": "ok" if database_ok else "unavailable",
        "redis": "embedded-demo" if config.DEMO_MODE else ("ok" if redis_ok else "unavailable"),
    }


@health_router.get("/api/v1/ready")
async def ready(response: Response) -> dict[str, object]:
    database_ok, redis_ok = await dependency_status()
    if not (database_ok and redis_ok):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "not_ready",
            "dependencies": {
                "database": "ready" if database_ok else "unavailable",
                "redis": "embedded-demo" if config.DEMO_MODE else ("ready" if redis_ok else "unavailable"),
            },
        }

    from app.prediction.contracts import ACTIVE_MODEL, CURRENT_SCREENING_MODEL
    from app.vision.food_vision import food_vision_is_configured

    future_artifact_available = config.PREDICTION_PROVIDER != "artifact" or Path(config.MODEL_URI).is_file()
    current_artifact_path = (
        config.ML_SHARED8_MODEL_URI
        if config.CURRENT_SCREENING_RUNTIME == "shared8-waist"
        else config.CURRENT_SCREENING_MODEL_URI
    )
    current_artifact_available = bool(current_artifact_path) and Path(current_artifact_path).is_file()
    food_vision_ready = config.FOOD_VISION_PROVIDER != "local_kfood" or food_vision_is_configured()
    food_vision_vlm_fallback_ready = not config.OPENAI_VLM_FALLBACK_ENABLED or bool(config.OPENAI_API_KEY.strip())
    operational_ready = (
        (not ACTIVE_MODEL.operational_model_activated or future_artifact_available)
        and (not CURRENT_SCREENING_MODEL.operational_model_activated or current_artifact_available)
        and food_vision_ready
        and food_vision_vlm_fallback_ready
    )
    if not operational_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if operational_ready else "not_ready",
        "dependencies": {
            "database": "ready",
            "redis": "embedded-demo" if config.DEMO_MODE else "ready",
            "prediction_provider": config.PREDICTION_PROVIDER,
            "future_artifact_path_available": future_artifact_available,
            "current_artifact_path_available": current_artifact_available,
            "food_vision_ready": food_vision_ready,
            "food_vision_vlm_fallback_enabled": config.OPENAI_VLM_FALLBACK_ENABLED,
            "food_vision_vlm_fallback_ready": food_vision_vlm_fallback_ready,
            "demo_artifact_inference_enabled": config.DEMO_ARTIFACT_INFERENCE_ENABLED,
            "worker_preload_required_for_release": not (config.DEMO_MODE and config.DEMO_ARTIFACT_INFERENCE_ENABLED),
        },
        "active_model": {
            "model_key": ACTIVE_MODEL.model_key,
            "version": ACTIVE_MODEL.version,
            "promotion_status": ACTIVE_MODEL.promotion_status,
        },
        "current_screening_model": {
            "model_key": CURRENT_SCREENING_MODEL.model_key,
            "version": CURRENT_SCREENING_MODEL.version,
            "runtime": config.CURRENT_SCREENING_RUNTIME,
            "promotion_status": CURRENT_SCREENING_MODEL.promotion_status,
            "operational_model_activated": CURRENT_SCREENING_MODEL.operational_model_activated,
        },
    }
