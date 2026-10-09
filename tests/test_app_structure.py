from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI

from app.core import config
from app.lifecycle import lifespan
from app.main import app
from app.services import challenge_v2_retention


def test_health_routes_remain_registered_after_module_split() -> None:
    paths = set(app.openapi()["paths"])

    assert {"/health", "/api/health", "/api/v1/health", "/api/v1/ready"} <= paths


def test_challenge_v2_routes_are_marked_deprecated_in_openapi() -> None:
    schema = app.openapi()
    challenge_v2_operations = [
        operation
        for path, methods in schema["paths"].items()
        if path.startswith("/api/v1/challenge-v2/")
        for operation in methods.values()
    ]

    assert challenge_v2_operations
    assert all(operation["deprecated"] is True for operation in challenge_v2_operations)


@pytest.mark.asyncio
async def test_lifespan_cancels_and_collects_retention_task(monkeypatch: pytest.MonkeyPatch) -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def fake_retention_loop() -> None:
        started.set()
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    monkeypatch.setattr(config, "DEMO_MODE", True)
    monkeypatch.setattr(config, "DEMO_ARTIFACT_INFERENCE_ENABLED", False)
    monkeypatch.setattr(challenge_v2_retention, "retention_loop", fake_retention_loop)

    async with lifespan(FastAPI()):
        await asyncio.wait_for(started.wait(), timeout=1)

    assert cancelled.is_set()
