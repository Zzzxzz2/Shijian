import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request

load_dotenv()  # Load .env file for os.getenv() in config/mail/analytics modules
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from config import DATABASE_URL
from database import engine, init_db

from services.mock.engine import registry
from services.mock.recorder import shutdown_all as _shutdown_recorders
from services.scheduler import init_scheduler, shutdown_scheduler

logger = logging.getLogger(__name__)


def _cors_origins() -> list[str]:
    """Return the explicit browser origins permitted to send credentials."""
    origins = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ALLOW_ORIGINS", "http://localhost:5173,http://localhost:8000"
        ).split(",")
        if origin.strip()
    ]
    if "*" in origins:
        raise RuntimeError(
            "CORS_ALLOW_ORIGINS cannot contain '*' when credentials are enabled"
        )
    return origins


CORS_ALLOW_ORIGINS = _cors_origins()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    await init_scheduler(DATABASE_URL)
    yield
    await shutdown_scheduler()
    await registry.shutdown_all()
    await _shutdown_recorders()  # safety net: drain orphan recorders
    await engine.dispose()
    logger.info("All mock resources shut down")


app = FastAPI(title="\u8bd5\u5251 V2", lifespan=lifespan)


# ── Global exception handlers ─────────────────────────────────────────────
@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: Exception):
    logger.error("Unhandled error: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请查看日志"},
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error("Unexpected error: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Register routers ──────────────────────────────────────────────────────
from routers.admin import router as admin_router  # noqa: E402
from routers.analytics import router as analytics_router  # noqa: E402
from routers.user import router as user_router  # noqa: E402
from routers.ai_planner import router as ai_planner_router  # noqa: E402
from routers.members import router as members_router  # noqa: E402
from routers.api_keys import router as api_keys_router  # noqa: E402
from routers.auth import router as auth_router  # noqa: E402
from routers.docs import router as docs_router  # noqa: E402
from routers.mock import router as mock_router  # noqa: E402
from routers.projects import router as projects_router  # noqa: E402
from routers.quick_test import router as quick_test_router  # noqa: E402
from routers.schema_driver import router as schema_driver_router  # noqa: E402
from routers.schedules import router as schedules_router  # noqa: E402
from routers.security import router as security_router  # noqa: E402
from routers.suites import router as suites_router  # noqa: E402
from routers.screenshots import router as screenshots_router  # noqa: E402
from routers.test_cases import router as test_cases_router  # noqa: E402
from routers.test_runs import router as test_runs_router, run_lookup_router  # noqa: E402
from routers.token_stats import router as token_stats_router  # noqa: E402
from routers.ws import router as ws_router  # noqa: E402

app.include_router(auth_router)
app.include_router(quick_test_router)
app.include_router(projects_router)
app.include_router(test_cases_router)
app.include_router(test_runs_router)
app.include_router(run_lookup_router)
app.include_router(api_keys_router)
app.include_router(docs_router)
app.include_router(admin_router)
app.include_router(ai_planner_router)
app.include_router(mock_router)
app.include_router(token_stats_router)
app.include_router(schema_driver_router)
app.include_router(ws_router)
app.include_router(screenshots_router)
app.include_router(security_router)
app.include_router(schedules_router)
app.include_router(analytics_router)
app.include_router(user_router)
app.include_router(suites_router)
app.include_router(members_router)

# ── Static files (frontend SPA, must be last — fallback for unmatched routes) ──
FRONTEND_DIR = str(Path(__file__).resolve().parent.parent / "frontend")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
