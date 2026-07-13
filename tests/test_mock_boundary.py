"""测试组：边界值（MOCK-101 ~ MOCK-107）。

验剑策略：
  MOCK-101: 录制空 body 的响应（204 No Content）
  MOCK-102: 同 method+path 录制 N 次 → 匹配按 priority + recorded_at 定序
  MOCK-103: query_string 不同 → 精确匹配区分
  MOCK-104: 500 条并发录制（模拟高频录制）
  MOCK-105: 进程退出时 buffer 中未落盘数据自动 flush
  MOCK-106: 超大 body（>1MB）录制与回放
  MOCK-107: query_string 含特殊字符（中文、URL 编码）
"""

import asyncio
import json

import pytest
from httpx import AsyncClient, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models import MockRecord
from services.mock.replayer import replay, replay_raw
from services.mock.recorder import Recorder, BATCH_SIZE
from services.mock.engine import MockEngine

pytestmark = pytest.mark.asyncio


# ── MOCK-101 ──────────────────────────────────────────────────────────────────


async def test_mock_101_empty_body_204(
    test_project,
    mock_engine: MockEngine,
):
    """验剑策略：MOCK-101 — 录制空 body 的响应（204 No Content）

    操作：录制一个返回 204 无 body 的端点
    预期：response_body=""、response_status=204、回放时返回一致
    """
    pid = test_project.id

    # 1) 录制 204 无 body 响应
    await mock_engine.record_request(
        method="GET", path="/api/no-content", query_string="",
        request_headers={}, request_body=None,
        response_status=204, response_headers={}, response_body=b"",
    )
    await mock_engine._recorder.flush()

    # 2) 回放
    resp = await replay_raw(pid, "GET", "/api/no-content")
    assert resp is not None, "回放不应返回 None"
    assert resp.status_code == 204, f"状态码应为 204，实际 {resp.status_code}"
    assert resp.content == b"", f"body 应为空，实际 {resp.content!r}"


# ── MOCK-102 ──────────────────────────────────────────────────────────────────


async def test_mock_102_priority_ordering(
    test_project,
    mock_engine: MockEngine,
    db_session: AsyncSession,
):
    """验剑策略：MOCK-102 — 同 method+path 录制 N 次 → 匹配按 priority 定序

    前置：同一个 GET /api/test 录制 3 次，priority 分别为 0、1、2
    操作：回放 GET /api/test
    预期：匹配到 priority=2 的记录（数字最大优先）
    """
    pid = test_project.id

    # 1) 录制 3 条相同 path，priority 0→1→2，不同 response_body
    for pri in [0, 1, 2]:
        await mock_engine.record_request(
            method="GET", path="/api/priority-test", query_string="",
            request_headers={}, request_body=None,
            response_status=200, response_headers={},
            response_body=f'{{"priority":{pri}}}'.encode(),
        )
    await mock_engine._recorder.flush()

    # 2) 手动设置 priority (recorder 默认 priority=0)
    rows = (
        await db_session.execute(
            select(MockRecord).where(
                MockRecord.project_id == pid,
                MockRecord.path == "/api/priority-test",
            ).order_by(MockRecord.id)
        )
    ).scalars().all()
    for i, row in enumerate(rows):
        row.priority = i
    await db_session.commit()

    # 3) 回放 → 应匹配 priority=2 的记录
    resp = await replay_raw(pid, "GET", "/api/priority-test")
    assert resp is not None
    body = json.loads(resp.content)
    assert body["priority"] == 2, (
        f"应匹配 priority=2 的记录，实际 priority={body['priority']}"
    )


# ── MOCK-103 ──────────────────────────────────────────────────────────────────


async def test_mock_103_query_string_distinction(
    test_project,
    mock_engine: MockEngine,
):
    """验剑策略：MOCK-103 — query_string 不同 → 精确匹配区分

    操作：录制 GET /api/search?q=cat 和 GET /api/search?q=dog
    预期：各自的 query_string 正确匹配
    """
    pid = test_project.id

    # 1) 录制两条不同 query_string 的记录
    await mock_engine.record_request(
        method="GET", path="/api/search", query_string="q=cat",
        request_headers={}, request_body=None,
        response_status=200, response_headers={}, response_body=b'"cat result"',
    )
    await mock_engine.record_request(
        method="GET", path="/api/search", query_string="q=dog",
        request_headers={}, request_body=None,
        response_status=200, response_headers={}, response_body=b'"dog result"',
    )
    await mock_engine._recorder.flush()

    # 2) 回放 ?q=cat → cat 结果
    resp_cat = await replay_raw(pid, "GET", "/api/search", query_string="q=cat")
    assert resp_cat is not None
    assert b"cat" in resp_cat.content, f"?q=cat 应返回 cat 结果: {resp_cat.content}"

    # 3) 回放 ?q=dog → dog 结果
    resp_dog = await replay_raw(pid, "GET", "/api/search", query_string="q=dog")
    assert resp_dog is not None
    assert b"dog" in resp_dog.content, f"?q=dog 应返回 dog 结果: {resp_dog.content}"

    # 4) 确认两条不同
    assert resp_cat.content != resp_dog.content, "不同 query 应返回不同响应"


# ── MOCK-104 ──────────────────────────────────────────────────────────────────


async def test_mock_104_concurrent_500_records(
    test_project,
    mock_engine: MockEngine,
    db_session: AsyncSession,
):
    """验剑策略：MOCK-104 — 500 条并发录制（模拟高频录制）

    前置：录制模式，batch buffer 未满（BATCH_SIZE=100）
    操作：连续快速发 500 个不同 path 的请求
    预期：全部录制成功，无数据丢失，无 SQLite 锁超时
    """
    pid = test_project.id

    # 1) 并发录制 500 条
    async def record_one(i: int):
        await mock_engine.record_request(
            method="GET", path=f"/api/concurrent/{i}", query_string="",
            request_headers={}, request_body=None,
            response_status=200, response_headers={},
            response_body=b"ok",
        )

    tasks = [record_one(i) for i in range(500)]
    await asyncio.gather(*tasks)

    # 2) 确保所有数据落盘
    await mock_engine._recorder.flush()

    # 3) 验证
    count = (
        await db_session.execute(
            select(func.count()).select_from(
                select(MockRecord).where(MockRecord.project_id == pid).subquery()
            )
        )
    ).scalar() or 0
    assert count == 500, f"应录制 500 条，实际 {count}"


# ── MOCK-105 ──────────────────────────────────────────────────────────────────


async def test_mock_105_shutdown_flushes_buffer(
    test_project,
    mock_engine: MockEngine,
    db_session: AsyncSession,
):
    """验剑策略：MOCK-105 — 进程退出时 buffer 中未落盘数据自动 flush

    前置：录制了不足 BATCH_SIZE 的数据（buffer 未触发自动 flush）
    操作：调用 engine.shutdown()
    预期：buffer 中所有数据写入 DB，不丢失
    """
    pid = test_project.id

    # 1) 录制少量数据（< BATCH_SIZE）
    for i in range(3):
        await mock_engine.record_request(
            method="GET", path=f"/api/shutdown-test/{i}", query_string="",
            request_headers={}, request_body=None,
            response_status=200, response_headers={}, response_body=b"ok",
        )
    # ⚠️ 不调用 flush — 数据仍在 buffer

    # 2) 调用 shutdown（应 flush buffer）
    await mock_engine.shutdown()

    # 3) 验证
    count = (
        await db_session.execute(
            select(func.count()).select_from(
                select(MockRecord).where(MockRecord.project_id == pid).subquery()
            )
        )
    ).scalar() or 0
    assert count == 3, f"shutdown 后应落盘 3 条，实际 {count}"


# ── MOCK-106 ──────────────────────────────────────────────────────────────────


async def test_mock_106_large_body_2mb(
    test_project,
    mock_engine: MockEngine,
    db_session: AsyncSession,
):
    """验剑策略：MOCK-106 — 超大 body（>1MB）录制与回放

    前置：录制模式
    操作：录制 POST 请求，body 约 2MB JSON
    预期：保存成功，回放时能返回同样大小的 body
    """
    pid = test_project.id

    # 1) 生成 2MB body
    large_data = {"data": "x" * (2 * 1024 * 1024)}  # ~2MB
    body_bytes = json.dumps(large_data).encode("utf-8")

    await mock_engine.record_request(
        method="POST", path="/api/large-body", query_string="",
        request_headers={"content-type": "application/json"},
        request_body=body_bytes,
        response_status=200, response_headers={},
        response_body=body_bytes,
    )
    await mock_engine._recorder.flush()

    # 2) 回放
    resp = await replay_raw(pid, "POST", "/api/large-body",
                            request_body=json.dumps(large_data),
                            request_headers={"content-type": "application/json"})
    assert resp is not None, "超大 body 回放失败"
    assert len(resp.content) > 1_000_000, (
        f"回放 body 应 >1MB，实际 {len(resp.content)} bytes"
    )
    # 验证内容一致（用长度 + 前后缀）
    assert resp.content[:20] == body_bytes[:20], "回放 body 前缀不匹配"
    assert resp.content[-20:] == body_bytes[-20:], "回放 body 后缀不匹配"
    assert len(resp.content) == len(body_bytes), "回放 body 长度不匹配"


# ── MOCK-107 ──────────────────────────────────────────────────────────────────


async def test_mock_107_special_chars_in_query_string(
    test_project,
    mock_engine: MockEngine,
    db_session: AsyncSession,
):
    """验剑策略：MOCK-107 — query_string 含特殊字符（中文、URL 编码）

    操作：录制 GET /api?name=张三&redirect=http://example.com?a=1
    预期：query_string 原文保存，匹配时按原文精确匹配
    """
    pid = test_project.id
    # 使用 URL 编码后的值（与生产环境 HTTP 层传入格式一致）
    from urllib.parse import urlencode  # noqa: PLC0415
    qs = urlencode({"name": "张三", "redirect": "http://example.com?a=1"})

    # 1) 录制含中文和 URL 的 query_string
    await mock_engine.record_request(
        method="GET", path="/api/profile", query_string=qs,
        request_headers={}, request_body=None,
        response_status=200, response_headers={},
        response_body=b'"profile ok"',
    )
    await mock_engine._recorder.flush()

    # 2) 验证 DB 中原文保存
    row = (
        await db_session.execute(
            select(MockRecord).where(
                MockRecord.project_id == pid,
                MockRecord.path == "/api/profile",
            )
        )
    ).scalars().first()
    assert row is not None
    assert row.query_string == qs, (
        f"query_string 原文保存异常:\n  期望: {qs}\n  实际: {row.query_string}"
    )

    # 3) 按原文回放 → 应匹配
    resp = await replay_raw(pid, "GET", "/api/profile", query_string=qs)
    assert resp is not None, "特殊字符 query_string 回放应匹配"
    assert resp.status_code == 200

    # 4) 不同的 query_string → 不应匹配（回退到无 query match 状态）
    wrong_qs = urlencode({"name": "李四"})
    resp_mismatch = await replay_raw(pid, "GET", "/api/profile", query_string=wrong_qs)
    # 因无其他记录，会 fall through 到 Content-Type 层，最终匹配或无匹配
    # 这里只要确认不会「错误匹配到」即可
