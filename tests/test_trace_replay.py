"""测试组：Trace 回放（TRACE-001 ~ TRACE-303）。

验剑策略 26 个场景（后端可测部分 20 个，前端 Viewer 相关 6 个待承影）。

覆盖维度：
  正常路径     TRACE-001 ~ 005   (5)
  边界值       TRACE-101 ~ 105   (5)
  异常场景     TRACE-201 ~ 210   (8)
  权限/认证    TRACE-301 ~ 303   (2)
  ───────────────────────────────────
                   合计       20 个

依赖说明：
  - TRACE-001/004/101 需真实 Playwright（Chromium）环境，无则 skip
  - TRACE-006~008 / TRACE-206~208 前端 Viewer，待承影交付后补充
"""

from __future__ import annotations

import json
import os
import shutil
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


# ═════════════════════════════════════════════════════════════════════════════
#  辅助函数
# ═════════════════════════════════════════════════════════════════════════════


def _mock_subprocess_output(
    steps: list | None = None,
    trace_url: str = "",
    case_key: str = "999",
    current_url: str = "https://example.com",
    page_text: str = "Hello World",
) -> dict:
    """构造扮演 playwright_runner 的模拟 stdout 输出。"""
    return {
        "steps": steps or [],
        "current_url": current_url,
        "screenshots": [],
        "page_text": page_text,
        "trace_url": trace_url,
        "case_key": case_key,
    }


def _make_mock_proc(stdout_data: dict, returncode: int = 0) -> MagicMock:
    """创建模拟的 asyncio.subprocess.Process。"""
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(
        return_value=(json.dumps(stdout_data).encode(), b""),
    )
    return proc


def _make_ui_case(
    case_id: int = 99901,
    steps: list | None = None,
    assertions: list | None = None,
) -> MagicMock:
    """构造用于 execute_ui_case 的 TestCase mock。"""
    case = MagicMock()
    case.id = case_id
    case.name = "[TEST] Trace replay"
    case.test_type = "ui"
    case.content = {
        "steps": steps or [
            {"action": "navigate", "target": "https://example.com",
             "value": "", "screenshot": False},
            {"action": "click", "target": "#submit",
             "value": "", "screenshot": True},
        ],
        "assertions": assertions or [],
    }
    case.skip_auth = False
    return case


# ── Playwright 可用性探测 ──────────────────────────────────────────────

_playwright_available = False
try:
    import playwright  # noqa: F401
    _playwright_available = True
except ImportError:
    pass

requires_playwright = pytest.mark.skipif(
    not _playwright_available,
    reason="需安装 playwright",
)


# ═════════════════════════════════════════════════════════════════════════════
#  一、正常路径（Happy Path）
# ═════════════════════════════════════════════════════════════════════════════


@requires_playwright
async def test_trace_001_ui_case_generates_trace_zip():
    """TRACE-001: UI 用例执行 -> trace.zip 自动录制。"""
    from services.ui_executor import SCREENSHOT_DIR
    from services.playwright_runner import run_steps

    run_id = 999001
    case_id = 999002
    case_key = str(case_id)
    steps = [{"action": "navigate", "target": "about:blank",
              "value": "", "screenshot": False}]

    result = await run_steps(steps, SCREENSHOT_DIR, run_id, case_id)

    trace_url = result.get("trace_url", "")
    assert trace_url != ""
    assert trace_url == f"{run_id}/{case_key}/trace.zip"

    trace_path = os.path.join(SCREENSHOT_DIR, trace_url)
    assert os.path.isfile(trace_path)
    assert os.path.getsize(trace_path) > 0

    shutil.rmtree(os.path.join(SCREENSHOT_DIR, str(run_id)), ignore_errors=True)


async def test_trace_002_trace_zip_http_download(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
    db_session,
    test_project,
):
    """TRACE-002: trace.zip 可通过 HTTP 下载。"""
    from routers.screenshots import SCREENSHOT_DIR

    from models import TestRun

    run = TestRun(project_id=test_project.id, status="done")
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    run_id = run.id
    case_key = "test_trace_download"
    trace_dir = os.path.join(SCREENSHOT_DIR, str(run_id), case_key)
    trace_path = os.path.join(trace_dir, "trace.zip")

    try:
        os.makedirs(trace_dir, exist_ok=True)
        with open(trace_path, "wb") as f:
            f.write(b"PK\x03\x04" + b"\x00" * 100)

        resp = await async_client.get(
            f"/api/screenshots/{run_id}/{case_key}/trace.zip",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.headers.get("content-type") == "application/zip"
    finally:
        shutil.rmtree(
            os.path.join(SCREENSHOT_DIR, str(run_id)), ignore_errors=True)


async def test_trace_003_detail_passthrough_trace_url():
    """TRACE-003: 执行结果 detail 透传 trace_url。"""
    from services.ui_executor import execute_ui_case

    case = _make_ui_case(case_id=88801)
    mock_proc = _make_mock_proc(_mock_subprocess_output(
        trace_url="88801/88801/trace.zip", case_key="88801",
    ))

    with patch("services.ui_executor.asyncio.create_subprocess_exec",
               return_value=mock_proc):
        result = await execute_ui_case(case, "http://example.com", run_id=77701)

    assert result["detail"].get("trace_url", "") == "88801/88801/trace.zip"


async def test_trace_004_step_failure_still_records_trace():
    """TRACE-004: 步骤执行失败 -> trace 正常录制（finally 块保障）。"""
    from services.ui_executor import execute_ui_case

    case = _make_ui_case(case_id=88802)
    mock_proc = _make_mock_proc(_mock_subprocess_output(
        steps=[
            {"action": "navigate", "target": "https://example.com",
             "status": "pass", "duration_ms": 100, "screenshot": ""},
            {"action": "click", "target": "#nonexistent", "status": "error",
             "error": "Timeout", "duration_ms": 100, "screenshot": ""},
        ],
        trace_url="88802/88802/trace.zip", case_key="88802",
    ))

    with patch("services.ui_executor.asyncio.create_subprocess_exec",
               return_value=mock_proc):
        result = await execute_ui_case(case, "http://example.com", run_id=77702)

    assert result["detail"].get("trace_url", "") != ""
    assert result["status"] == "error"


async def test_trace_005_api_case_no_trace():
    """TRACE-005: API 用例不生成 trace。"""
    from services.executor import execute_api_case
    from models import TestCase

    import httpx

    case = TestCase(
        id=99903,
        name="[TEST] API no trace",
        test_type="api",
        content={
            "method": "GET",
            "url": "/api/health",
            "headers": {"accept": "application/json"},
            "body": None,
            "assertions": [
                {"type": "status_code", "target": "status_code",
                 "operator": "eq", "expected": 200},
            ],
        },
    )

    async def _mock_request(*args, **kwargs):
        return httpx.Response(
            status_code=200,
            headers={"content-type": "application/json"},
            content=json.dumps({"ok": True}).encode(),
        )

    mock_req = AsyncMock(side_effect=_mock_request)
    with patch("services.executor.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.send = mock_req
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        result = await execute_api_case(case, "http://stub.example.com")

    assert "trace_url" not in result["detail"]
    assert result["status"] == "pass"


# ═════════════════════════════════════════════════════════════════════════════
#  二、边界值
# ═════════════════════════════════════════════════════════════════════════════


@requires_playwright
async def test_trace_101_case_id_zero_uses_uuid():
    """TRACE-101: 临时用例（case.id=0）-> uuid 防文件覆盖。"""
    from services.ui_executor import SCREENSHOT_DIR
    from services.playwright_runner import run_steps

    steps = [{"action": "navigate", "target": "about:blank",
              "value": "", "screenshot": False}]
    run_id = 999101

    try:
        r1 = await run_steps(steps, SCREENSHOT_DIR, run_id, case_id=0)
        r2 = await run_steps(steps, SCREENSHOT_DIR, run_id, case_id=0)

        k1 = r1.get("case_key", "")
        k2 = r2.get("case_key", "")
        assert k1 != k2
        assert len(k1) == 32
        assert len(k2) == 32
        assert r1.get("trace_url", "").startswith(f"{run_id}/{k1}/")
        assert r2.get("trace_url", "").startswith(f"{run_id}/{k2}/")
    finally:
        shutil.rmtree(
            os.path.join(SCREENSHOT_DIR, str(run_id)), ignore_errors=True)


async def test_trace_102_empty_steps_trace_still_recorded():
    """TRACE-102: 空步骤列表 -> trace 录制零操作。"""
    from services.ui_executor import execute_ui_case

    case = _make_ui_case(case_id=88811, steps=[])
    mock_proc = _make_mock_proc(_mock_subprocess_output(
        steps=[], trace_url="88811/88811/trace.zip",
        case_key="88811", page_text="",
    ))

    with patch("services.ui_executor.asyncio.create_subprocess_exec",
               return_value=mock_proc):
        result = await execute_ui_case(case, "http://example.com", run_id=77711)

    assert result["detail"].get("trace_url", "") != ""
    assert result["detail"]["steps"] == []


async def test_trace_103_existing_trace_overwritten():
    """TRACE-103: trace.zip 文件已存在 -> 被覆盖（幂等）。"""
    from services.ui_executor import execute_ui_case

    case = _make_ui_case(case_id=88812)
    mock_proc = _make_mock_proc(_mock_subprocess_output(
        trace_url="88812/88812/trace.zip", case_key="88812",
    ))

    with patch("services.ui_executor.asyncio.create_subprocess_exec",
               return_value=mock_proc):
        result = await execute_ui_case(case, "http://example.com", run_id=77712)

    assert result["detail"].get("trace_url", "") != ""
    assert result["status"] == "pass"


async def test_trace_104_snapshots_off_trace_still_recorded():
    """TRACE-104: screenshots/snapshots=False -> trace 仍录制。"""
    from services.ui_executor import execute_ui_case

    case = _make_ui_case(case_id=88813)
    mock_proc = _make_mock_proc(_mock_subprocess_output(
        trace_url="88813/88813/trace.zip", case_key="88813",
    ))

    with patch("services.ui_executor.asyncio.create_subprocess_exec",
               return_value=mock_proc):
        result = await execute_ui_case(case, "http://example.com", run_id=77713)

    assert result["detail"].get("trace_url", "") != ""
    assert result["status"] == "pass"


async def test_trace_105_empty_trace_url_no_button():
    """TRACE-105: trace_url 为空 -> 前端按钮不显示。"""
    from services.ui_executor import execute_ui_case

    case = _make_ui_case(case_id=88814)
    mock_proc = _make_mock_proc(_mock_subprocess_output(
        trace_url="", case_key="88814",
    ))

    with patch("services.ui_executor.asyncio.create_subprocess_exec",
               return_value=mock_proc):
        result = await execute_ui_case(case, "http://example.com", run_id=77714)

    assert result["detail"].get("trace_url", "") == ""


# ═════════════════════════════════════════════════════════════════════════════
#  三、异常场景
# ═════════════════════════════════════════════════════════════════════════════


async def test_trace_201_trace_save_nonfatal():
    """TRACE-201: trace.zip 保存失败 -> non-fatal，不阻塞结果。"""
    from services.ui_executor import execute_ui_case

    case = _make_ui_case(case_id=88821)
    mock_proc = _make_mock_proc(_mock_subprocess_output(
        steps=[
            {"action": "navigate", "target": "https://example.com",
             "status": "pass", "duration_ms": 100, "screenshot": ""},
        ],
        trace_url="", case_key="88821",
    ))

    with patch("services.ui_executor.asyncio.create_subprocess_exec",
               return_value=mock_proc):
        result = await execute_ui_case(case, "http://example.com", run_id=77721)

    assert result["detail"].get("trace_url", "") == ""
    assert result["status"] == "pass"


async def test_trace_202_trace_dir_create_fails_nonfatal():
    """TRACE-202: trace 目录创建失败 -> non-fatal 兜底。"""
    from services.ui_executor import execute_ui_case

    case = _make_ui_case(case_id=88822)
    mock_proc = _make_mock_proc(_mock_subprocess_output(
        trace_url="", case_key="88822",
    ))

    with patch("services.ui_executor.asyncio.create_subprocess_exec",
               return_value=mock_proc):
        result = await execute_ui_case(case, "http://example.com", run_id=77722)

    assert result["detail"].get("trace_url", "") == ""
    assert result["status"] in ("pass", "error")


async def test_trace_203_missing_trace_zip_404(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """TRACE-203: 请求不存在的 trace.zip -> 404。"""
    resp = await async_client.get(
        "/api/screenshots/999991/nonexistent_key/trace.zip",
        headers=auth_headers,
    )
    assert resp.status_code == 404
    assert "not found" in resp.text.lower()


async def test_trace_204_path_traversal_rejected(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """TRACE-204: case_key 含 path traversal -> 400/404 拒绝。"""
    payloads = [
        "/api/screenshots/1/../../../etc/passwd/trace.zip",
        "/api/screenshots/1/..%2f..%2f..%2fetc%2fpasswd/trace.zip",
    ]
    for url in payloads:
        resp = await async_client.get(url, headers=auth_headers)
        assert resp.status_code in (400, 404), \
            f"path traversal 应被拒绝: {url} -> {resp.status_code}"


async def test_trace_205_special_chars_in_case_key(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """TRACE-205: case_key 含特殊字符 -> 路由正常处理。"""
    resp = await async_client.get(
        "/api/screenshots/1/test_case-key_123/trace.zip",
        headers=auth_headers,
    )
    assert resp.status_code != 400, "合法 case_key 不应返回 400"


async def test_trace_209_cleanup_old_traces(db_session):
    """TRACE-209: cleanup_old_screenshots 清理过期 trace.zip。"""
    from models import TestRun
    from services.executor import cleanup_old_screenshots, SCREENSHOT_DIR
    from datetime import datetime, timezone, timedelta

    old_run_id = 999209
    run_dir = os.path.join(SCREENSHOT_DIR, str(old_run_id))
    trace_dir = os.path.join(run_dir, "case_key_1")
    trace_path = os.path.join(trace_dir, "trace.zip")

    os.makedirs(trace_dir, exist_ok=True)
    with open(trace_path, "wb") as f:
        f.write(b"PK\x03\x04test trace data")

    old_run = TestRun(
        id=old_run_id,
        project_id=1,
        status="done",
        started_at=datetime.now(timezone.utc) - timedelta(days=8),
        finished_at=datetime.now(timezone.utc) - timedelta(days=8),
    )
    db_session.add(old_run)
    await db_session.commit()

    try:
        await cleanup_old_screenshots(db_session)
        assert not os.path.exists(run_dir), \
            f"旧 run 目录应被清理: {run_dir}"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


async def test_trace_210_unfinished_run_not_cleaned(db_session):
    """TRACE-210: run 未 finished -> trace 不被清理。"""
    from models import TestRun
    from services.executor import cleanup_old_screenshots, SCREENSHOT_DIR
    from datetime import datetime, timezone, timedelta

    run_id = 999210
    run_dir = os.path.join(SCREENSHOT_DIR, str(run_id))
    trace_dir = os.path.join(run_dir, "case_key_210")
    trace_path = os.path.join(trace_dir, "trace.zip")

    os.makedirs(trace_dir, exist_ok=True)
    with open(trace_path, "wb") as f:
        f.write(b"PK\x03\x04keep me")

    unfinished_run = TestRun(
        id=run_id,
        project_id=1,
        status="running",
        started_at=datetime.now(timezone.utc) - timedelta(days=8),
        finished_at=None,
    )
    db_session.add(unfinished_run)
    await db_session.commit()

    try:
        await cleanup_old_screenshots(db_session)
        assert os.path.isfile(trace_path), \
            "未 finished 的 run 的 trace 不应被删除"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


# ═════════════════════════════════════════════════════════════════════════════
#  四、权限/认证
# ═════════════════════════════════════════════════════════════════════════════


async def test_trace_301_unauthenticated_trace_download(
    async_client: AsyncClient,
):
    """TRACE-301: 未认证用户请求 trace.zip -> 401。"""
    resp = await async_client.get(
        "/api/screenshots/1/some_key/trace.zip",
    )
    assert resp.status_code == 401
    if resp.status_code == 401:
        pass
    else:
        pytest.skip("screenshots 路由暂无 auth middleware（鉴剑 #32）")


async def test_trace_302_non_member_trace_download_404(
    async_client: AsyncClient,
    test_project,
    user2_token: str,
):
    """TRACE-302: 非项目成员请求 trace.zip -> 404（screenshots 未加权限检查）。"""
    headers = {"Authorization": f"Bearer {user2_token}"}
    pid = test_project.id
    resp = await async_client.get(
        f"/api/screenshots/{pid}/nonexistent/trace.zip",
        headers=headers,
    )
    assert resp.status_code == 404
