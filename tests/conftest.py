"""试剑 V3 Mock 引擎 — 测试基础设施。

数据库隔离策略：
  1. 设置 DATABASE_URL → shijian_test.db（独立测试库）
  2. 会话开始时：init_db() 创建所有表
  3. 每个测试用例：独立的 test_user / test_project / async_client
  4. 会话结束后：删除 shijian_test.db（含 WAL/SHM 文件）

验剑策略覆盖 30 个场景（MOCK-001 ~ MOCK-304）。
"""

import os
import sys
import tempfile
from pathlib import Path

# ── 必须在任何 backend 模块导入前设置 DATABASE_URL ──────────────────────
_TEST_DB = Path(tempfile.gettempdir()) / f"shijian_test_{os.getpid()}.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB.as_posix()}"

# 将 backend 目录加入 Python 路径，确保 from backend.xxx 或直接 import 可用
_BACKEND_DIR = str(Path(__file__).resolve().parent.parent / "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# 在 conftest 顶层延迟导入 backend 模块（此时 DATABASE_URL 已生效）
# ---------------------------------------------------------------------------
from database import async_session, engine, init_db
from auth import create_access_token, hash_password
from models import Base, MockConfig, MockRecord, Project, User
from main import app
from services.mock.engine import registry, MockEngine

if "sqlite" not in os.environ.get("DATABASE_URL", ""):
    pytest.exit("Mock 引擎测试仅支持 SQLite 数据库")





# ═══════════════════════════════════════════════════════════════════════════
#  会话级：pytest hooks（同步 hooks 避免 async autouse fixture 兼容问题）
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="session")
def event_loop():
    """pytest-asyncio 要求：session 级别的事件循环。"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def pytest_sessionstart():
    """所有测试开始前：初始化测试数据库。"""
    for path in (_TEST_DB, Path(f"{_TEST_DB}-shm"), Path(f"{_TEST_DB}-wal")):
        path.unlink(missing_ok=True)
    asyncio.run(init_db())


def pytest_sessionfinish():
    """所有测试结束后：清理数据库。"""
    async def _cleanup():
        await registry.shutdown_all()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()
        for path in (_TEST_DB, Path(f"{_TEST_DB}-shm"), Path(f"{_TEST_DB}-wal")):
            path.unlink(missing_ok=True)
    asyncio.run(_cleanup())


# ═══════════════════════════════════════════════════════════════════════════
#  函数级：测试客户端
# ═══════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """FastAPI 异步测试客户端。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def db_session():
    """直接 DB session，用于数据准备 / 验证查询。"""
    async with async_session() as session:
        yield session


# ═══════════════════════════════════════════════════════════════════════════
#  函数级：测试用户 & JWT Token
# ═══════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def test_user(db_session) -> User:
    """第一个测试用户（通过模型创建，绕过注册频率限制）。"""
    # 先清除同名的遗留数据
    from sqlalchemy import delete as sa_delete
    await db_session.execute(sa_delete(User).where(User.username == "test_mock_user"))
    await db_session.commit()

    user = User(
        username="test_mock_user",
        password_hash=hash_password("password123"),
        role="user",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_user2(db_session) -> User:
    """第二个测试用户（用于权限/隔离测试）。"""
    from sqlalchemy import delete as sa_delete
    await db_session.execute(sa_delete(User).where(User.username == "test_mock_user2"))
    await db_session.commit()

    user = User(
        username="test_mock_user2",
        password_hash=hash_password("password123"),
        role="user",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def user_token(test_user: User) -> str:
    """test_user 的 JWT token."""
    return create_access_token({"sub": str(test_user.id)})


@pytest_asyncio.fixture
async def user2_token(test_user2: User) -> str:
    """test_user2 的 JWT token."""
    return create_access_token({"sub": str(test_user2.id)})


@pytest_asyncio.fixture
async def auth_headers(user_token: str) -> dict[str, str]:
    """test_user 认证头。"""
    return {"Authorization": f"Bearer {user_token}"}


@pytest_asyncio.fixture
async def auth2_headers(user2_token: str) -> dict[str, str]:
    """test_user2 认证头。"""
    return {"Authorization": f"Bearer {user2_token}"}


@pytest_asyncio.fixture
async def admin_user(db_session) -> User:
    """Admin 用户（User.role='admin'）。"""
    from sqlalchemy import delete as sa_delete
    await db_session.execute(sa_delete(User).where(User.username == "test_admin"))
    await db_session.commit()
    user = User(
        username="test_admin",
        password_hash=hash_password("admin123"),
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_token(admin_user: User) -> str:
    """Admin 用户的 JWT token（含 ver 声明）。"""
    return create_access_token({"sub": str(admin_user.id)}, user=admin_user)


@pytest_asyncio.fixture
async def admin_headers(admin_token: str) -> dict[str, str]:
    """Admin 认证头。"""
    return {"Authorization": f"Bearer {admin_token}"}


# ═══════════════════════════════════════════════════════════════════════════
#  函数级：测试项目
# ═══════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def test_project(db_session, test_user: User) -> Project:
    """test_user 拥有的项目。"""
    project = Project(
        name="Mock Engine Test Project",
        description="Project for mock engine automated tests",
        user_id=test_user.id,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


@pytest_asyncio.fixture
async def test_project2(db_session, test_user2: User) -> Project:
    """test_user2 拥有的第二个项目（权限隔离用）。"""
    project = Project(
        name="Mock Engine Test Project 2",
        description="Second project for isolation tests",
        user_id=test_user2.id,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


# ═══════════════════════════════════════════════════════════════════════════
#  函数级：Mock 引擎实例 & MockRecord 工厂
# ═══════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def mock_engine(test_project: Project) -> MockEngine:
    """为 test_project 初始化的 MockEngine。"""
    engine_inst = registry.get_or_create(test_project.id)
    await engine_inst.initialize()
    return engine_inst


@pytest_asyncio.fixture
async def recorded_get(mock_engine: MockEngine, db_session, test_project) -> MockRecord:
    """辅助 fixture：录制一条 GET /api/test 记录到 test_project。"""
    from sqlalchemy import select as sa_select
    await mock_engine.record_request(
        method="GET",
        path="/api/test",
        query_string="q=1",
        request_headers={"accept": "application/json"},
        request_body=None,
        response_status=200,
        response_headers={"content-type": "application/json"},
        response_body=b'{"result":"ok"}',
    )
    await mock_engine._recorder.flush()
    result = await db_session.execute(
        sa_select(MockRecord).where(MockRecord.project_id == test_project.id)
    )
    return result.scalars().first()


@pytest_asyncio.fixture
async def recorded_post(mock_engine: MockEngine, db_session, test_project) -> MockRecord:
    """辅助 fixture：录制一条 POST /api/login 记录（含 body）。"""
    from sqlalchemy import select as sa_select
    await mock_engine.record_request(
        method="POST",
        path="/api/login",
        query_string="",
        request_headers={"content-type": "application/json"},
        request_body=b'{"user":"test","pass":"123"}',
        response_status=200,
        response_headers={"content-type": "application/json"},
        response_body=b'{"token":"jwt123"}',
    )
    await mock_engine._recorder.flush()
    result = await db_session.execute(
        sa_select(MockRecord).where(MockRecord.project_id == test_project.id)
    )
    return result.scalars().first()


@pytest_asyncio.fixture
async def recorded_post(mock_engine: MockEngine, db_session) -> MockRecord:
    """辅助 fixture：录制一条 POST /api/login 记录（含 body）。"""
    await mock_engine.record_request(
        method="POST",
        path="/api/login",
        query_string="",
        request_headers={"content-type": "application/json"},
        request_body=b'{"user":"test","pass":"123"}',
        response_status=200,
        response_headers={"content-type": "application/json"},
        response_body=b'{"token":"jwt123"}',
    )
    await mock_engine._recorder.flush()
    result = await db_session.execute(
        MockRecord.__table__.select().where(MockRecord.project_id == test_project.id)
    )
    return result.scalars().first()


# ═══════════════════════════════════════════════════════════════════════════
#  多厂商 LLM 测试 — 辅助函数 & Fixtures
# ═══════════════════════════════════════════════════════════════════════════

import json as _json
from typing import Callable

import httpx as _httpx
from openai import OpenAI as _OpenAI

from services.ai_provider.base import BaseAIProvider, GeneratePlanResult, TokenUsage
from services.ai_provider.mock import MockProvider
from services.ai_provider.failover import FailoverProvider
from services.ai_provider.openai_compat import OpenAICompatibleProvider
from services.ai_provider.claude import ClaudeProvider
from services.ai_provider.gemini import GeminiProvider
from services.ai_provider.ollama import OllamaProvider
from services.crypto import encrypt as _encrypt


# ── Mock HTTP Transport 辅助 ─────────────────────────────────────────────


def _make_chat_completion_json(
    cases: list[dict] | None = None,
    prompt_tokens: int = 10,
    completion_tokens: int = 20,
) -> str:
    """Generate a realistic OpenAI chat completion JSON response body."""
    if cases is None:
        cases = [
            {
                "name": "正常登录",
                "test_type": "api",
                "content": {
                    "method": "POST",
                    "url": "/api/auth/login",
                    "body": {"username": "test", "password": "test"},
                    "assertions": [
                        {"type": "status_code", "target": "status_code", "operator": "eq", "expected": 200},
                    ],
                },
            },
        ]
    body = {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "mock-model",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": _json.dumps({"cases": cases}),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }
    return _json.dumps(body)


def _make_mock_handler(
    cases: list[dict] | None = None,
    status_code: int = 200,
    delay: float = 0,
) -> Callable[[_httpx.Request], _httpx.Response]:
    """Create an ``httpx.MockTransport`` handler for OpenAI chat completions.

    The handler matches any POST to ``*/chat/completions`` and returns a
    proper OpenAI-format JSON response.
    """
    response_body = _make_chat_completion_json(cases=cases)

    def handler(request: _httpx.Request) -> _httpx.Response:
        import time
        if delay:
            time.sleep(delay)
        return _httpx.Response(
            status_code=status_code,
            headers={"Content-Type": "application/json"},
            content=response_body.encode(),
            request=request,
        )

    return handler


def build_mocked_client(
    handler: Callable[[_httpx.Request], _httpx.Response],
) -> _OpenAI:
    """Build an ``OpenAI`` client that uses ``httpx.MockTransport``.

    All HTTP calls go through *handler* instead of the real API.
    """
    transport = _httpx.MockTransport(handler)
    http_client = _httpx.Client(transport=transport)
    return _OpenAI(api_key="sk-mock", http_client=http_client)


# ── Provider Factory Fixtures ────────────────────────────────────────────


@pytest_asyncio.fixture
async def test_project_with_ai_config(
    db_session,
    test_user: "User",
    request,
) -> "Project":
    """Create a project with a custom ``ai_config``.

    Override ``ai_config`` via ``request.param``::

        @pytest.mark.parametrize("test_project_with_ai_config", [
            {"provider": "failover", "failover_chain": ["claude", "deepseek"]},
        ], indirect=True)
    """
    from models import Project as _Project
    ai_config = getattr(request, "param", {})
    project = _Project(
        name="AI-LLM Test Project",
        description="Project for multi-LLM provider tests",
        user_id=test_user.id,
        ai_config=ai_config,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


@pytest_asyncio.fixture
async def test_api_keys(db_session, test_user: "User") -> list:
    """Create one ApiKey row per known provider.

    Each key is a dummy value encrypted with the dev key.
    Returns ``list[ApiKey]``.
    """
    from models import ApiKey as _ApiKey
    keys: list[_ApiKey] = []
    for prov, base_url in [
        ("deepseek", "https://api.deepseek.com/v1"),
        ("openai", "https://api.openai.com/v1"),
        ("claude", "https://api.anthropic.com/v1"),
        ("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/"),
    ]:
        key = _ApiKey(
            user_id=test_user.id,
            provider=prov,
            api_key_encrypted=_encrypt(f"sk-mock-{prov}"),
            api_key_masked=f"sk-...{prov[:3]}",
            base_url=base_url,
            model="",
        )
        db_session.add(key)
        keys.append(key)
    await db_session.commit()
    for k in keys:
        await db_session.refresh(k)
    return keys


@pytest_asyncio.fixture
async def test_api_key_deepseek_only(db_session, test_user: "User") -> list:
    """Create a single DeepSeek ApiKey row (for failover tests)."""
    from models import ApiKey as _ApiKey
    key = _ApiKey(
        user_id=test_user.id,
        provider="deepseek",
        api_key_encrypted=_encrypt("sk-mock-deepseek"),
        api_key_masked="sk-...deepseek",
        base_url="https://api.deepseek.com/v1",
    )
    db_session.add(key)
    await db_session.commit()
    await db_session.refresh(key)
    return [key]


# ── Mock Provider Fixtures ───────────────────────────────────────────────


@pytest.fixture
def mock_chat_handler() -> Callable[[_httpx.Request], _httpx.Response]:
    """Default mock handler that returns a valid 200 response with sample cases.

    Override with ``_make_mock_handler(cases=..., status_code=..., delay=...)``.
    """
    return _make_mock_handler()


@pytest.fixture
def mocked_openai_provider(mock_chat_handler) -> OpenAICompatibleProvider:
    """An ``OpenAICompatibleProvider`` with mocked HTTP transport."""
    provider = OpenAICompatibleProvider(
        api_key="sk-mock",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
    )
    provider.client = build_mocked_client(mock_chat_handler)
    return provider


@pytest.fixture
def mocked_claude_provider(mock_chat_handler) -> ClaudeProvider:
    """A ``ClaudeProvider`` with mocked HTTP transport."""
    provider = ClaudeProvider(api_key="sk-mock")
    provider.client = build_mocked_client(mock_chat_handler)
    return provider


@pytest.fixture
def mocked_gemini_provider(mock_chat_handler) -> GeminiProvider:
    """A ``GeminiProvider`` with mocked HTTP transport."""
    provider = GeminiProvider(api_key="sk-mock")
    provider.client = build_mocked_client(mock_chat_handler)
    return provider


@pytest.fixture
def mocked_ollama_provider(mock_chat_handler) -> OllamaProvider:
    """An ``OllamaProvider`` with mocked HTTP transport."""
    provider = OllamaProvider()
    provider.client = build_mocked_client(mock_chat_handler)
    return provider


# ═══════════════════════════════════════════════════════════════════════════
#  Quick Test — Sync TestClient for WebSocket testing
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="session")
def sync_client():
    """Synchronous FastAPI TestClient — required for WebSocket tests.

    Use this instead of ``async_client`` when you need to connect to
    ``/ws/quick-test/{task_id}?token=...`` via ``websocket_connect()``.
    """
    from fastapi.testclient import TestClient
    from main import app

    async def _ensure_ws_user():
        from sqlalchemy import select

        async with async_session() as session:
            user = (
                await session.execute(
                    select(User).where(User.username == "_ws_test_user")
                )
            ).scalar_one_or_none()
            if user is None:
                user = User(
                    username="_ws_test_user",
                    password_hash=hash_password("ws-test-only"),
                    role="user",
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
            return create_access_token({"sub": str(user.id)}, user=user)

    global WS_TEST_TOKEN
    WS_TEST_TOKEN = asyncio.run(_ensure_ws_user())
    with TestClient(app) as c:
        yield c


# ═══════════════════════════════════════════════════════════════════════════
#  Quick Test — Helpers
# ═══════════════════════════════════════════════════════════════════════════


def make_qt_task_coro(
    task_id: str,
    messages: list[dict],
    delay_before: float = 0.0,
    delay_per_msg: float = 0.01,
) -> callable:
    """Build a controlled async coroutine that pushes WS messages.

    Use in WS tests that need to verify message ordering without
    going through the full AI + executor pipeline::

        coro = make_qt_task_coro("qt_test", [
            {"type": "status", "data": "..."},
            {"type": "done", "data": {"passed": 1, "failed": 0, "total": 1}},
        ])
        create_task(coro, task_id="qt_test")
    """
    import asyncio as _asyncio
    from routers.ws import qt_broadcast

    async def _qt_coro():
        if delay_before:
            await _asyncio.sleep(delay_before)
        for msg in messages:
            await qt_broadcast(task_id, msg)
            if delay_per_msg:
                await _asyncio.sleep(delay_per_msg)
        return {"passed": 0, "failed": 0, "total": 0}
    return _qt_coro


# ═══════════════════════════════════════════════════════════════════════════
#  引用传递 — 确保 conftest 顶层导入了所有测试所需的模块
# ═══════════════════════════════════════════════════════════════════════════

__all__ = [
    # helpers
    "_make_chat_completion_json",
    "_make_mock_handler",
    "build_mocked_client",
    "make_qt_task_coro",
    # fixtures
    "test_project_with_ai_config",
    "test_api_keys",
    "test_api_key_deepseek_only",
    "mock_chat_handler",
    "mocked_openai_provider",
    "mocked_claude_provider",
    "mocked_gemini_provider",
    "mocked_ollama_provider",
    "sync_client",
]
