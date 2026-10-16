"""Loopback-only browser fixture. Synthetic user, in-memory DB, no model/API calls."""

import re
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from tortoise import Tortoise

from app.apis.v1.game_routers import game_router
from app.apis.v1.health_routers import health_router
from app.dependencies.security import get_request_user
from app.dtos.health import ConsentCreateRequest, EligibilityCreateRequest
from app.models.users import Gender, User
from app.services.health import HealthService
from tests.db_utils import init_sqlite_test_db

ROOT = Path(__file__).resolve().parents[2]


@asynccontextmanager
async def lifespan(app):
    await init_sqlite_test_db()
    user = await User.create(
        email="browser-reward@example.invalid",
        hashed_password="not-a-login",
        name="보상 검증 계정",
        birthday=date(2000, 1, 1),
        gender=Gender.FEMALE,
    )
    await HealthService().create_consent(user, ConsentCreateRequest(is_agreed=True))
    await HealthService().check_eligibility(user, EligibilityCreateRequest())
    app.dependency_overrides[get_request_user] = lambda: user
    app.state.user_id = user.id
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        await Tortoise.close_connections()


app = FastAPI(lifespan=lifespan)
app.include_router(health_router, prefix="/api/v1")
app.include_router(game_router, prefix="/api/v1")
app.mount("/static", StaticFiles(directory=ROOT / "src/frontend"), name="static")


@app.get("/fixture")
async def fixture():
    return {"user_id": app.state.user_id}


@app.get("/", response_class=HTMLResponse)
async def page():
    html = (ROOT / "src/frontend/index.html").read_text(encoding="utf-8")
    # Keep real input markup and production styles; replace unrelated application
    # controllers with an isolated driver. The reward widget itself is unchanged.
    html = re.sub(r"<script\b[^>]*>[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
    return html.replace("</body>", '<script src="/static/health-input-rewards.js"></script></body>')
