"""试剑 V2 — E2E Playwright 测试基础设施。

E2E 测试直接操作真实浏览器 + 真实后端，覆盖 4 条核心流程。
后端需提前运行在 localhost:8000（可用 webServer 或手动启动）。
"""

import os
import sys
import uuid
import logging
from datetime import datetime
from pathlib import Path

import pytest

_BACKEND_DIR = str(Path(__file__).resolve().parent.parent.parent / "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8000")
SPA_BASE = BASE_URL + "/app.html"  # SPA 壳在 app.html，不是 index.html
logger = logging.getLogger(__name__)


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: E2E test (requires running backend + browser)")
    config.addinivalue_line("markers", "requires_backend: skip if backend is not reachable")
    config.addinivalue_line("markers", "requires_playwright: skip if Playwright is not installed")


# ── Backend availability check ─────────────────────────────────────────────


def _check_backend() -> bool:
    try:
        import httpx
        r = httpx.get(f"{BASE_URL}/docs", timeout=5)
        return r.status_code < 500
    except Exception:
        return False


def pytest_collection_modifyitems(config, items):
    """Auto-skip tests that require backend if backend is not running."""
    backend_ok = _check_backend()
    for item in items:
        if item.get_closest_marker("requires_backend") and not backend_ok:
            item.add_marker(pytest.mark.skip(reason="Backend is not running (try: uvicorn backend.main:app --reload --port 8000)"))


# ── Session-scoped fixtures ────────────────────────────────────────────────


@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture(scope="session")
def sync_playwright():
    """Playwright sync API instance (session-scoped).

    Skip the entire test if playwright is not installed.
    """
    try:
        from playwright.sync_api import sync_playwright as _sync_pw
    except ImportError:
        pytest.skip("Playwright is not installed (pip install playwright)")
    with _sync_pw() as pw:
        yield pw


@pytest.fixture(scope="module")
def browser(sync_playwright):
    """Chromium browser instance (module-scoped)."""
    browser = sync_playwright.chromium.launch(headless=False)
    yield browser
    browser.close()


@pytest.fixture
def page(browser):
    """New browser context + page for each test."""
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        locale="zh-CN",
    )
    page = context.new_page()
    page.set_default_timeout(15000)
    yield page
    context.close()


@pytest.fixture
def api_client(base_url):
    """Sync HTTP client for API calls without browser."""
    import httpx
    return httpx.Client(base_url=base_url, timeout=15)


# ── Test data helpers ──────────────────────────────────────────────────────


SESSION_USER = {"username": "e2e-session-user", "password": "TestPass123!"}


@pytest.fixture(scope="session")
def session_user(api_client_session) -> dict:
    """Register ONE user for the entire test session.

    The backend rate limiter allows only 3 registrations/day globally,
    2 per-IP/day, and 1 per 10 min.  We register exactly once at session
    start and reuse this user for all tests.
    """
    register_user(api_client_session, SESSION_USER)
    return {**SESSION_USER}


@pytest.fixture(scope="session")
def auth_token(session_user, api_client_session) -> str | None:
    """Get a fresh JWT token for the session user."""
    return login_and_get_token(api_client_session, session_user)


@pytest.fixture(scope="session")
def api_client_session(base_url):
    """Session-scoped HTTP client (for session_setup / helper calls)."""
    import httpx
    with httpx.Client(base_url=base_url, timeout=15) as client:
        yield client


@pytest.fixture
def test_user(session_user) -> dict:
    """Reuse the session user for every test (avoids rate limiter)."""
    return session_user


@pytest.fixture(autouse=True)
def cleanup_before():
    """Before each test: no-op cleanup.

    All tests share one session user, so no per-test cleanup needed.
    Rate limiter prevents creating new users anyway.
    """
    pass


@pytest.fixture
def screenshots_dir(request) -> Path:
    """Directory to save failure/debug screenshots.

    Created per test module under tests/e2e/screenshots/.
    """
    module_name = Path(request.module.__file__).stem
    dir_path = Path(__file__).parent / "screenshots" / module_name
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


# ── Helper functions ───────────────────────────────────────────────────────


def register_user(api_client, user: dict) -> str | None:
    """Register a test user via API. Returns JWT token or None on failure.

    NOTE: register returns a JWT token directly (TokenResponse).
    """
    import httpx
    try:
        resp = api_client.post(
            "/api/auth/register",
            json={"username": user["username"], "password": user["password"]},
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            return data.get("access_token")
        logger.warning("register_user failed (%d): %s", resp.status_code, resp.text)
        return None
    except httpx.HTTPError as exc:
        logger.warning("register_user HTTP error: %s", exc)
        return None


def login_and_get_token(api_client, user: dict) -> str | None:
    """Login via JSON POST and return the JWT token.

    Endpoint: POST /api/auth/login  with JSON body {"username": ..., "password": ...}
    Returns:  {"access_token": "...", "token_type": "bearer", "user": {...}}
    """
    resp = api_client.post(
        "/api/auth/login",
        json={"username": user["username"], "password": user["password"]},
    )
    if resp.status_code == 200:
        return resp.json().get("access_token")
    logger.warning("login failed (%d): %s", resp.status_code, resp.text)
    return None


def create_project(api_client, token: str, name: str, description: str = "") -> int | None:
    """Create a project via API. Returns project ID or None."""
    resp = api_client.post(
        "/api/projects",
        json={"name": name, "description": description},
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code in (200, 201):
        return resp.json().get("id")
    logger.warning("create_project failed (%d): %s", resp.status_code, resp.text)
    return None
