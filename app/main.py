from pathlib import Path

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.apis.v1 import v1_routers
from app.core import config
from app.core.db.databases import initialize_tortoise
from app.health import health_router
from app.lifecycle import lifespan
from app.middleware.challenge_upload_limit import ChallengeUploadLimit
from app.services.mobile_downloads import mobile_download_payload

app = FastAPI(
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
initialize_tortoise(app)
app.add_middleware(ChallengeUploadLimit)

app.include_router(v1_routers)
app.include_router(health_router)

_SENSITIVE_REPORT_PATH_PREFIXES = ("/api/v1/reports", "/api/v1/weekly-reports")


@app.middleware("http")
async def _no_store_for_sensitive_reports(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(_SENSITIVE_REPORT_PATH_PREFIXES):
        response.headers["Cache-Control"] = "private, no-store"
    return response


FRONTEND_DIR = Path(__file__).resolve().parents[1] / "src" / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


_APP_ENTRY_QUERY_KEYS = frozenset(
    {"intro", "auth", "preview", "resume", "workspace", "invite_token", "account", "returnTo"}
)
_RETRO_INTRO_URL = "/static/intro-retro.html?v=20260917-server-entry-v1"


@app.get("/mobile-downloads", include_in_schema=False)
async def mobile_download_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "mobile-downloads.html", headers={"Cache-Control": "no-store"})


@app.get("/api/mobile-downloads", include_in_schema=False)
async def mobile_download_links() -> dict:
    return mobile_download_payload(config.MOBILE_IOS_DOWNLOAD_URL, config.MOBILE_ANDROID_DOWNLOAD_URL)


@app.get("/", include_in_schema=False)
async def home(request: Request) -> Response:
    """Show the retro introduction before the customer interface.

    Authentication, invitation, preview, and signed-in resume links keep serving the
    application directly.  A server redirect is intentional here: some embedded or
    privacy-restricted browsers disable ``window.location.replace``, which made the
    previous client-only entry guard unreliable.
    """
    if not _APP_ENTRY_QUERY_KEYS.intersection(request.query_params):
        response = RedirectResponse(_RETRO_INTRO_URL, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        return response

    response = FileResponse(FRONTEND_DIR / "index.html")
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@app.get("/forest", include_in_schema=False)
async def carrot_forest() -> FileResponse:
    response = FileResponse(FRONTEND_DIR / "forest.html")
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@app.get("/favicon.ico", include_in_schema=False)
async def site_favicon() -> FileResponse:
    """Serve the compact brand mark from the conventional browser icon path."""
    response = FileResponse(FRONTEND_DIR / "favicon.ico", media_type="image/x-icon")
    response.headers["Cache-Control"] = "public, max-age=604800"
    return response


@app.get("/service", include_in_schema=False)
async def suin_service() -> FileResponse:
    """Compatibility entry for the current customer UI and its session restore."""
    response = FileResponse(FRONTEND_DIR / "index.html")
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@app.get("/manifest.webmanifest", include_in_schema=False)
async def forest_manifest() -> FileResponse:
    response = FileResponse(
        FRONTEND_DIR / "forest.webmanifest",
        media_type="application/manifest+json",
    )
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/forest-sw.js", include_in_schema=False)
async def forest_service_worker() -> FileResponse:
    response = FileResponse(FRONTEND_DIR / "forest-sw.js", media_type="text/javascript")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Service-Worker-Allowed"] = "/forest"
    return response
