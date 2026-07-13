"""测试组：正常路径 — 录制流程（MOCK-001 ~ MOCK-003）。

验剑策略：
  MOCK-001: 开启录制 → 发 GET 请求 → 请求/响应被保存
  MOCK-002: 录制 POST 请求 → JSON body 完整保存
  MOCK-003: 关闭录制 → 不再录制新请求
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import MockRecord
from services.mock.engine import MockEngine


@pytest.mark.asyncio
class TestRecordingFlow:
    """录制流程 — MOCK-001 ~ MOCK-003"""

    async def _count_records(self, db: AsyncSession, project_id: int) -> int:
        result = await db.execute(
            select(MockRecord).where(MockRecord.project_id == project_id)
        )
        return len(result.scalars().all())

    # ── MOCK-001 ──────────────────────────────────────────────────────────────

    async def test_mock_001_record_get_request(
        self,
        async_client: AsyncClient,
        test_project,
        auth_headers: dict[str, str],
        mock_engine: MockEngine,
        db_session: AsyncSession,
    ):
        """验剑策略：MOCK-001 — 开启录制 → 发 GET 请求 → 请求/响应被保存

        前置：创建 project
        操作：POST /api/projects/{pid}/mocks/start-recording → 录制一条 GET 请求
        预期：mock_records 表写入 1 条记录，method=GET、path=/api/test
        """
        pid = test_project.id

        # 1) 开启录制
        resp = await async_client.post(
            f"/api/projects/{pid}/mocks/start-recording",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"start-recording 失败: {resp.text}"
        assert resp.json()["status"] == "recording"

        # 2) 录制一条 GET 请求
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

        # 3) 验证 DB 中有一条记录
        records = (
            await db_session.execute(
                select(MockRecord).where(MockRecord.project_id == pid)
            )
        ).scalars().all()
        assert len(records) == 1, f"预期 1 条记录，实际 {len(records)}"

        record = records[0]
        assert record.method == "GET", f"method 期望 GET，实际 {record.method}"
        assert record.path == "/api/test", f"path 期望 /api/test，实际 {record.path}"
        assert record.query_string == "q=1", f"query_string 期望 q=1，实际 {record.query_string}"
        assert record.response_status == 200
        assert record.source == "auto"

    # ── MOCK-002 ──────────────────────────────────────────────────────────────

    async def test_mock_002_record_post_with_json_body(
        self,
        async_client: AsyncClient,
        test_project,
        auth_headers: dict[str, str],
        mock_engine: MockEngine,
        db_session: AsyncSession,
    ):
        """验剑策略：MOCK-002 — 录制 POST 请求 → JSON body 完整保存

        操作：发 POST /api/login，body {"user":"test","pass":"123"}
        预期：request_body 保存 JSON 文本，body_type="text"（因 bytes→utf-8 可解码）
        """
        pid = test_project.id
        request_json = b'{"user":"test","pass":"123"}'

        # 1) 开启录制
        await async_client.post(
            f"/api/projects/{pid}/mocks/start-recording",
            headers=auth_headers,
        )

        # 2) 录制 POST 请求
        await mock_engine.record_request(
            method="POST",
            path="/api/login",
            query_string="",
            request_headers={"content-type": "application/json"},
            request_body=request_json,
            response_status=200,
            response_headers={"content-type": "application/json"},
            response_body=b'{"token":"jwt123"}',
        )
        await mock_engine._recorder.flush()

        # 3) 验证
        records = (
            await db_session.execute(
                select(MockRecord).where(MockRecord.project_id == pid)
            )
        ).scalars().all()
        assert len(records) == 1

        record = records[0]
        assert record.method == "POST"
        assert record.path == "/api/login"
        assert record.request_body == '{"user":"test","pass":"123"}', (
            f"request_body 保存异常:\n 期望: {request_json.decode()}\n 实际: {record.request_body}"
        )
        assert record.body_type == "text", f"body_type 期望 text，实际 {record.body_type}"
        assert record.response_body == '{"token":"jwt123"}', (
            f"response_body 保存异常: {record.response_body}"
        )

    # ── MOCK-003 ──────────────────────────────────────────────────────────────

    async def test_mock_003_stop_recording_stops_new_requests(
        self,
        async_client: AsyncClient,
        test_project,
        auth_headers: dict[str, str],
        mock_engine: MockEngine,
        db_session: AsyncSession,
    ):
        """验剑策略：MOCK-003 — 关闭录制 → 不再录制新请求

        前置：录制模式运行中
        操作：POST /api/projects/{pid}/mocks/stop-recording → 再发请求
        预期：stop-recording API 正常工作、config.enabled=False、
              且 stop 返回前 buffer 中数据已 flush。
              新请求不被录制是中间件层的保障（此处验证 API 层行为）。
        """
        pid = test_project.id

        # 1) 开启录制并录制一条
        resp = await async_client.post(
            f"/api/projects/{pid}/mocks/start-recording",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"start-recording 失败: {resp.text}"
        assert resp.json()["status"] == "recording"

        await mock_engine.record_request(
            method="GET", path="/api/before-stop", query_string="",
            request_headers={}, request_body=None,
            response_status=200, response_headers={}, response_body=b"ok",
        )
        await mock_engine._recorder.flush()
        count_before = await self._count_records(db_session, pid)
        assert count_before == 1, "录制后应有 1 条记录"

        # 2) 关闭录制 → 验证 API 响应
        resp = await async_client.post(
            f"/api/projects/{pid}/mocks/stop-recording",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"stop-recording 失败: {resp.text}"
        assert resp.json()["status"] == "stopped"

        # 3) 验证 config.enabled=False
        config = await mock_engine.get_config()
        assert config is not None
        assert config.enabled is False, "stop-recording 后 config.enabled 应变为 False"

        # 4) 验证 stop-recording 已 flush buffer（之前的记录未丢失）
        count_after = await self._count_records(db_session, pid)
        assert count_after == 1, (
            f"stop-recording 应 flush 已有数据，不应丢失: 停止前 {count_before}，停止后 {count_after}"
        )

        # 5) 验证 replay 通过 MockEngine 调用时返回 None（config-aware）
        from httpx import Request as HttpxRequest
        req = HttpxRequest(method="GET", url="http://test/api/before-stop")
        replay_resp = await mock_engine.replay(req)
        assert replay_resp is None, (
            "stop-recording 后 MockEngine.replay() 应返回 None（config.enabled=False）"
        )
