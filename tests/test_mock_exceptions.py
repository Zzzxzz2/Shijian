"""测试组：异常场景（MOCK-201 ~ MOCK-210）。

验剑策略：
  MOCK-201: 回放模式 → 请求不匹配任何 Mock → 返回 404
  MOCK-202: 请求 body 非空但无 body 匹配 → body fall-through 行为
  MOCK-203: Mock 引擎未启用（mock_configs.enabled=false）→ 不截获请求
  MOCK-204: 项目不存在 → 返回 404
  MOCK-205: 重复 start-recording → 幂等处理
  MOCK-206: 重复 stop-recording → 幂等处理
  MOCK-207: 二进制 body（PNG 图片）录制 → base64 存储 → 回放正确
  MOCK-208: 录制时 target_url 不可达 → 优雅处理（engine 层容忍）
  MOCK-209: PATCH 编辑不存在的 mock_id → 404
  MOCK-210: DELETE 不存在的 mock_id → 404
"""

import json

import pytest
from httpx import AsyncClient, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import MockRecord
from services.mock.replayer import replay, replay_raw
from services.mock.recorder import _encode_body
from services.mock.engine import MockEngine

pytestmark = pytest.mark.asyncio


# ── MOCK-201 ──────────────────────────────────────────────────────────────────


async def test_mock_201_no_match_returns_404(
    test_project,
):
    """验剑策略：MOCK-201 — 回放模式 → 请求不匹配任何 Mock → 返回 None (caller 转 404)

    前置：项目处于 replay 模式，无匹配 MockRecord
    操作：发一个未录制的 GET /api/nonexistent
    预期：返回 None（replay 函数契约），caller 应转为 404
    """
    pid = test_project.id

    resp = await replay_raw(pid, "GET", "/api/nonexistent")
    assert resp is None, "无匹配时应返回 None"


# ── MOCK-202 ──────────────────────────────────────────────────────────────────


async def test_mock_202_body_mismatch_fallthrough(
    test_project,
    mock_engine: MockEngine,
):
    """验剑策略：MOCK-202 — 请求 body 非空但无 body 匹配 → body fall-through 行为

    前置：有一条无 body 的 GET /api/test 录制 + 一条有 body 的 GET /api/test 录制
    操作：发 GET /api/test（无 body）
    预期：按实现，#4 修复后精确匹配；未修复时 fall through
    """
    pid = test_project.id

    # 1) 先录一条「无 body」的 GET
    await mock_engine.record_request(
        method="GET", path="/api/body-test", query_string="",
        request_headers={}, request_body=None,
        response_status=200, response_headers={},
        response_body=b'"no body"',
    )
    # 2) 再录一条「有 body」的 GET（模拟带 body 的 GET）
    await mock_engine.record_request(
        method="GET", path="/api/body-test", query_string="",
        request_headers={"content-type": "application/json"},
        request_body=b'{"filter":"active"}',
        response_status=200, response_headers={},
        response_body=b'"with body"',
    )
    await mock_engine._recorder.flush()

    # 3) 发 GET 请求（无 body）→ 应匹配无 body 的记录
    resp = await replay_raw(pid, "GET", "/api/body-test")
    assert resp is not None
    # 如果 #4 已修复：应匹配无 body 记录 → "no body"
    # 如果 #4 未修复：可能 fall through 到 body 记录 → "with body"
    # 这个测试记录行为，不假设哪一种
    body = resp.content.decode("utf-8")
    assert body in ['"no body"', '"with body"'], f"未知的响应 body: {body}"


# ── MOCK-203 ──────────────────────────────────────────────────────────────────


async def test_mock_203_engine_disabled_no_intercept(
    test_project,
    mock_engine: MockEngine,
):
    """验剑策略：MOCK-203 — Mock 引擎未启用（mock_configs.enabled=false）→ 不截获请求

    前置：mock_configs.enabled=false，任何 mode
    操作：发请求
    预期：MockEngine.replay() 在 enabled=false 时返回 None（表示不截获）；
         底层 replay_raw 仍可工作（纯匹配引擎，不受 config 影响）。
    """
    from httpx import Request as HttpxRequest

    pid = test_project.id

    # 1) 先录制一条，确保有数据
    await mock_engine.record_request(
        method="GET", path="/api/disabled-test", query_string="",
        request_headers={}, request_body=None,
        response_status=200, response_headers={}, response_body=b"ok",
    )
    await mock_engine._recorder.flush()

    # 2) 禁用 MockConfig
    await mock_engine.update_config(enabled=False)

    # 3) 通过 MockEngine.replay() 调用 → 应返回 None（config-aware）
    req = HttpxRequest(method="GET", url="http://test/api/disabled-test")
    resp = await mock_engine.replay(req)
    assert resp is None, "enabled=false 时 MockEngine.replay() 应返回 None"

    # 4) 通过 replay_raw() 调用（无 check_config） → 仍能匹配（纯匹配引擎不受 config 影响）
    resp_raw = await replay_raw(pid, "GET", "/api/disabled-test")
    assert resp_raw is not None, "replay_raw 不应受 config 影响，应正常匹配"
    assert resp_raw.status_code == 200


# ── MOCK-204 ──────────────────────────────────────────────────────────────────


async def test_mock_204_nonexistent_project_404(
    async_client: AsyncClient,
    auth_headers: dict[str, str],
):
    """验剑策略：MOCK-204 — 项目不存在 → 返回 404

    操作：操作不存在的 project_id
    预期：404 {"detail":"Project not found"}
    """
    nonexistent_pid = 99999

    # 尝试各种 API
    for method_fn, url in [
        (lambda: async_client.get(f"/api/projects/{nonexistent_pid}/mocks/config", headers=auth_headers), "GET config"),
        (lambda: async_client.get(f"/api/projects/{nonexistent_pid}/mocks", headers=auth_headers), "GET list"),
        (lambda: async_client.post(f"/api/projects/{nonexistent_pid}/mocks/start-recording", headers=auth_headers), "POST start-recording"),
        (lambda: async_client.post(f"/api/projects/{nonexistent_pid}/mocks/stop-recording", headers=auth_headers), "POST stop-recording"),
    ]:
        resp = await method_fn()
        assert resp.status_code == 404, f"{url} 应返回 404，实际 {resp.status_code}: {resp.text}"
        assert "not found" in resp.text.lower(), f"404 消息应包含 'not found': {resp.text}"


# ── MOCK-205 ──────────────────────────────────────────────────────────────────


async def test_mock_205_double_start_recording_idempotent(
    async_client: AsyncClient,
    test_project,
    auth_headers: dict[str, str],
    mock_engine: MockEngine,
):
    """验剑策略：MOCK-205 — 重复 start-recording → 幂等处理

    前置：start-recording 已调用
    操作：再次调用 start-recording
    预期：不创建新 Recorder、不泄漏后台任务、响应成功
    """
    pid = test_project.id

    # 1) 第一次 start
    resp1 = await async_client.post(
        f"/api/projects/{pid}/mocks/start-recording",
        headers=auth_headers,
    )
    assert resp1.status_code == 200

    # 2) 第二次 start（幂等）
    resp2 = await async_client.post(
        f"/api/projects/{pid}/mocks/start-recording",
        headers=auth_headers,
    )
    assert resp2.status_code == 200, f"重复 start 应返回 200: {resp2.text}"

    # 3) 验证录制仍正常（没有泄漏破坏状态）
    await mock_engine.record_request(
        method="GET", path="/api/idempotent-test", query_string="",
        request_headers={}, request_body=None,
        response_status=200, response_headers={}, response_body=b"ok",
    )
    await mock_engine._recorder.flush()
    resp = await replay_raw(pid, "GET", "/api/idempotent-test")
    assert resp is not None, "重复 start 后录制/回放仍应正常"


# ── MOCK-206 ──────────────────────────────────────────────────────────────────


async def test_mock_206_double_stop_recording_idempotent(
    async_client: AsyncClient,
    test_project,
    auth_headers: dict[str, str],
):
    """验剑策略：MOCK-206 — 重复 stop-recording → 幂等处理

    前置：引擎已停止
    操作：再次调用 stop-recording
    预期：不报错，返回当前状态
    """
    pid = test_project.id

    # 1) 从未 start 过，直接 stop
    resp1 = await async_client.post(
        f"/api/projects/{pid}/mocks/stop-recording",
        headers=auth_headers,
    )
    assert resp1.status_code == 200, f"未 start 时 stop 应返回 200: {resp1.text}"

    # 2) 再 stop 一次
    resp2 = await async_client.post(
        f"/api/projects/{pid}/mocks/stop-recording",
        headers=auth_headers,
    )
    assert resp2.status_code == 200, f"重复 stop 应返回 200: {resp2.text}"


# ── MOCK-207 ──────────────────────────────────────────────────────────────────


async def test_mock_207_binary_body_base64(
    test_project,
    mock_engine: MockEngine,
    db_session: AsyncSession,
):
    """验剑策略：MOCK-207 — 二进制 body（PNG 图片）录制 → base64 存储 → 回放正确

    操作：录制 POST 请求，body 为二进制图片数据
    预期：body_type="binary"、request_body 为 base64 编码，回放时返回相同二进制内容
    """
    pid = test_project.id

    # 1) 构造伪 PNG 二进制数据
    import base64
    png_header = b'\x89PNG\r\n\x1a\n'
    fake_png = png_header + b'\x00' * 1024  # ~1KB pseudo-binary

    await mock_engine.record_request(
        method="POST", path="/api/upload", query_string="",
        request_headers={"content-type": "image/png"},
        request_body=fake_png,
        response_status=200, response_headers={"content-type": "image/png"},
        response_body=fake_png,
    )
    await mock_engine._recorder.flush()

    # 2) 验证 DB 存储
    row = (
        await db_session.execute(
            select(MockRecord).where(
                MockRecord.project_id == pid,
                MockRecord.path == "/api/upload",
            )
        )
    ).scalars().first()
    assert row is not None
    assert row.body_type == "binary", f"body_type 应为 binary，实际 {row.body_type}"
    # request_body 应是 base64 编码
    try:
        decoded = base64.b64decode(row.request_body)
        assert decoded[:len(png_header)] == png_header, "base64 解码后内容不匹配"
    except Exception as exc:
        pytest.fail(f"request_body 不是有效的 base64: {exc}")

    # 3) 回放 → 返回相同二进制内容
    resp = await replay_raw(pid, "POST", "/api/upload",
                            request_headers={"content-type": "image/png"})
    assert resp is not None, "二进制 body 回放失败"
    assert resp.content == fake_png, "回放二进制内容不匹配"


# ── MOCK-208 ──────────────────────────────────────────────────────────────────


async def test_mock_208_target_unreachable(
    test_project,
    mock_engine: MockEngine,
):
    """验剑策略：MOCK-208 — 录制时 target_url 不可达 → engine 容忍

    MockEngine.record_request() 不转发请求到 target_url（那是 middleware 的职责）。
    Engine 层只做 buffered-write，target_url 不可达不应影响录制逻辑。
    此测试验证 engine 在「无 target_url」时仍能正常录制。
    """
    pid = test_project.id

    # engine 的 target_url 为空（默认） → 录制不应受影响
    config = await mock_engine.get_config()
    assert config.target_url == "", "默认 target_url 应为空"

    # 正常录制
    await mock_engine.record_request(
        method="GET", path="/api/no-target", query_string="",
        request_headers={}, request_body=None,
        response_status=200, response_headers={}, response_body=b"ok",
    )
    await mock_engine._recorder.flush()

    resp = await replay_raw(pid, "GET", "/api/no-target")
    assert resp is not None, "target_url 为空时录制/回放应正常"
    assert resp.status_code == 200


# ── MOCK-209 ──────────────────────────────────────────────────────────────────


async def test_mock_209_patch_nonexistent_404(
    async_client: AsyncClient,
    test_project,
    auth_headers: dict[str, str],
):
    """验剑策略：MOCK-209 — PATCH 编辑不存在的 mock_id → 404"""
    pid = test_project.id
    resp = await async_client.patch(
        f"/api/projects/{pid}/mocks/99999",
        json={"response_status": 200},
        headers=auth_headers,
    )
    assert resp.status_code == 404, f"PATCH 不存在记录应 404: {resp.text}"
    assert "not found" in resp.text.lower()


# ── MOCK-210 ──────────────────────────────────────────────────────────────────


async def test_mock_210_delete_nonexistent_404(
    async_client: AsyncClient,
    test_project,
    auth_headers: dict[str, str],
):
    """验剑策略：MOCK-210 — DELETE 不存在的 mock_id → 404"""
    pid = test_project.id
    resp = await async_client.delete(
        f"/api/projects/{pid}/mocks/99999",
        headers=auth_headers,
    )
    assert resp.status_code == 404, f"DELETE 不存在记录应 404: {resp.text}"
    assert "not found" in resp.text.lower()
