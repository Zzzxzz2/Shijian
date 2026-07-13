"""测试组：正常路径 — 回放流程（MOCK-004 ~ MOCK-006）。

验剑策略：
  MOCK-004: 回放模式 → 精确 method+path 匹配 → 返回录制的响应
  MOCK-005: 同 method+path 不同 request_body → 回放各自正确的响应
  MOCK-006: 回放命中记录后 hit_count 自增
"""

import pytest
from httpx import AsyncClient, Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models import MockRecord
from services.mock.replayer import replay, replay_raw
from services.mock.engine import MockEngine


@pytest.mark.asyncio
class TestReplayFlow:
    """回放流程 — MOCK-004 ~ MOCK-006"""

    # ── MOCK-004 ──────────────────────────────────────────────────────────────

    async def test_mock_004_replay_exact_method_path_match(
        self,
        test_project,
        db_session: AsyncSession,
        mock_engine: MockEngine,
    ):
        """验剑策略：MOCK-004 — 回放模式 → 精确 method+path 匹配 → 返回录制的响应

        前置：已录制 GET /api/test，项目切换到 replay 模式
        操作：发 GET /api/test
        预期：返回 MockRecord 中保存的 response_status + response_body + response_headers
        """
        pid = test_project.id
        expected_body = b'{"result":"from_replay"}'

        # 1) 录制
        await mock_engine.record_request(
            method="GET", path="/api/test", query_string="",
            request_headers={}, request_body=None,
            response_status=200, response_headers={"x-mock": "true"},
            response_body=expected_body,
        )
        await mock_engine._recorder.flush()

        # 2) 回放
        req = Request(method="GET", url="http://test/api/test")
        resp = await replay(pid, req)

        assert resp is not None, "回放应返回响应，而不是 None"
        assert resp.status_code == 200, f"response_status 期望 200，实际 {resp.status_code}"
        assert resp.content == expected_body, (
            f"response_body 不匹配:\n  期望: {expected_body}\n  实际: {resp.content}"
        )
        assert resp.headers.get("x-mock") == "true", "response_headers 丢失 x-mock"

    # ── MOCK-005 ──────────────────────────────────────────────────────────────

    async def test_mock_005_different_body_different_response(
        self,
        test_project,
        mock_engine: MockEngine,
        db_session: AsyncSession,
    ):
        """验剑策略：MOCK-005 — 同 method+path 不同 request_body → 回放各自正确的响应

        前置：录制两条记录：(POST /api/login body A) 和 (POST /api/login body B)
        操作：发 POST body A → 得到 A 的响应；发 POST body B → 得到 B 的响应
        预期：两条响应不同，各自对应录制时的真实响应
        """
        pid = test_project.id

        # 1) 录制两条 body 不同的 POST 记录
        await mock_engine.record_request(
            method="POST", path="/api/login", query_string="",
            request_headers={"content-type": "application/json"},
            request_body=b'{"user":"admin","pass":"admin123"}',
            response_status=200, response_headers={},
            response_body=b'{"role":"admin"}',
        )
        await mock_engine.record_request(
            method="POST", path="/api/login", query_string="",
            request_headers={"content-type": "application/json"},
            request_body=b'{"user":"guest","pass":"guest123"}',
            response_status=200, response_headers={},
            response_body=b'{"role":"guest"}',
        )
        await mock_engine._recorder.flush()

        # 2) 回放 body A → 期望 admin 响应
        resp_a = await replay_raw(
            pid, "POST", "/api/login",
            request_body='{"user":"admin","pass":"admin123"}',
            request_headers={"content-type": "application/json"},
        )
        assert resp_a is not None, "Body A 回放失败"
        assert resp_a.content == b'{"role":"admin"}', (
            f"Body A 期望 admin 响应，实际: {resp_a.content}"
        )

        # 3) 回放 body B → 期望 guest 响应
        resp_b = await replay_raw(
            pid, "POST", "/api/login",
            request_body='{"user":"guest","pass":"guest123"}',
            request_headers={"content-type": "application/json"},
        )
        assert resp_b is not None, "Body B 回放失败"
        assert resp_b.content == b'{"role":"guest"}', (
            f"Body B 期望 guest 响应，实际: {resp_b.content}"
        )

        # 4) 确认两条响应不同
        assert resp_a.content != resp_b.content, "不同 body 应返回不同响应"

    # ── MOCK-006 ──────────────────────────────────────────────────────────────

    async def test_mock_006_hit_count_increments(
        self,
        test_project,
        mock_engine: MockEngine,
        db_session: AsyncSession,
    ):
        """验剑策略：MOCK-006 — 回放命中记录后 hit_count 自增

        前置：1 条活跃 MockRecord
        操作：回放 3 次
        预期：hit_count 逐次从 0→1→2→3
        """
        pid = test_project.id

        # 1) 录制一条 GET 记录
        await mock_engine.record_request(
            method="GET", path="/api/hit-test", query_string="",
            request_headers={}, request_body=None,
            response_status=200, response_headers={}, response_body=b"hit me",
        )
        await mock_engine._recorder.flush()

        # 查回 record_id
        row = (
            await db_session.execute(
                select(MockRecord).where(
                    MockRecord.project_id == pid,
                    MockRecord.path == "/api/hit-test",
                )
            )
        ).scalars().first()
        record_id = row.id
        assert row.hit_count == 0, "初始 hit_count 应为 0"

        # 2) 回放 3 次
        for expected_hits in [1, 2, 3]:
            resp = await replay_raw(pid, "GET", "/api/hit-test")
            assert resp is not None, f"第 {expected_hits} 次回放返回 None"
            # 从 DB 刷新
            await db_session.refresh(row)
            assert row.hit_count == expected_hits, (
                f"第 {expected_hits} 次回放后 hit_count 应为 {expected_hits}，"
                f"实际 {row.hit_count}"
            )
