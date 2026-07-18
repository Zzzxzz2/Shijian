"""验剑策略：即时执行（Quick Test）— WebSocket 层（QT-002~004, 103~105, 201~206, 302~303）

WS 测试通过 TestClient portal 在应用事件循环中运行 broadcast 协程，
避免跨事件循环操作 WebSocket。
"""

import asyncio
import time as _time

import pytest
from fastapi.testclient import TestClient

from auth import create_access_token
from routers.ws import qt_broadcast
from services.task_manager import _tasks


# ═══════════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _token(sub: str = "1") -> str:
    from conftest import WS_TEST_TOKEN

    return WS_TEST_TOKEN


def _start_task_qt(sync_client: TestClient, task_id: str, messages: list[dict],
                   delay_per_msg: float = 0.01,
                   delay_before: float = 0.1):
    """Register a task in ``_tasks`` and start a background thread that
    broadcasts *messages* via ``qt_broadcast``.

    *delay_before* gives the WS client time to connect before the first
    broadcast, preventing a race where messages are sent before the
    client is listening.

    Uses the ``TestClient`` portal so broadcasts and WebSocket sends run
    on the same event loop as the application.
    """
    _tasks[task_id] = {
        "task_id": task_id,
        "status": "running",
        "result": None,
        "error": None,
    }

    async def _run():
        try:
            if delay_before:
                await asyncio.sleep(delay_before)
            for msg in messages:
                await qt_broadcast(task_id, msg)
                if delay_per_msg:
                    await asyncio.sleep(delay_per_msg)
            _tasks[task_id]["status"] = "done"
            _tasks[task_id]["result"] = {"passed": 0, "failed": 0, "total": 0}
        except Exception as exc:
            _tasks[task_id]["status"] = "failed"
            _tasks[task_id]["error"] = str(exc)

    assert sync_client.portal is not None
    return sync_client.portal.start_task_soon(_run)


def _receive_all(ws) -> list[dict]:
    """Receive all WS messages until ``done`` is received."""
    msgs = []
    while True:
        msg = ws.receive_json()
        msgs.append(msg)
        if msg["type"] == "done":
            break
    return msgs


# ═══════════════════════════════════════════════════════════════════════════
#  一、正常路径 — WebSocket 消息流
# ═══════════════════════════════════════════════════════════════════════════


class TestWSMessageFlow:
    """验剑策略：QT-002 ~ QT-004 — WS 消息序列与状态。"""

    def test_qt_002_ws_full_sequence(self, sync_client: TestClient):
        """验剑策略：QT-002 — WS 收到完整消息序列。

        预期按序收到：
          status → case_start × N → case_done × N → done
        """
        _start_task_qt(sync_client, "qt_002", [
            {"type": "status", "data": "正在分析需求..."},
            {"type": "status", "data": "生成了 2 条用例"},
            {"type": "case_start", "data": {"name": "用例1", "index": 0, "total": 2, "test_type": "api"}},
            {"type": "case_done", "data": {"index": 0, "name": "用例1", "status": "pass", "duration_ms": 10, "detail": {}}},
            {"type": "case_start", "data": {"name": "用例2", "index": 1, "total": 2, "test_type": "api"}},
            {"type": "case_done", "data": {"index": 1, "name": "用例2", "status": "pass", "duration_ms": 20, "detail": {}}},
            {"type": "done", "data": {"passed": 2, "failed": 0, "total": 2}},
        ])

        token = _token()
        with sync_client.websocket_connect(f"/ws/quick-test/qt_002?token={token}") as ws:
            msg1 = ws.receive_json()
            assert msg1["type"] == "status"
            assert "分析" in msg1.get("data", "")

            msg2 = ws.receive_json()
            assert msg2["type"] == "status"
            assert "2 条" in msg2.get("data", "")

            msg3 = ws.receive_json()
            assert msg3["type"] == "case_start"
            assert msg3["data"]["index"] == 0

            msg4 = ws.receive_json()
            assert msg4["type"] == "case_done"
            assert msg4["data"]["index"] == 0
            assert msg4["data"]["status"] == "pass"

            msg5 = ws.receive_json()
            assert msg5["type"] == "case_start"
            assert msg5["data"]["index"] == 1

            msg6 = ws.receive_json()
            assert msg6["type"] == "case_done"
            assert msg6["data"]["index"] == 1
            assert msg6["data"]["status"] == "pass"

            msg7 = ws.receive_json()
            assert msg7["type"] == "done"
            assert msg7["data"]["passed"] == 2
            assert msg7["data"]["failed"] == 0
            assert msg7["data"]["total"] == 2

    def test_qt_003_all_pass(self, sync_client: TestClient):
        """验剑策略：QT-003 — 全部用例通过 → done 中 passed=total。"""
        _start_task_qt(sync_client, "qt_003", [
            {"type": "status", "data": "生成了 3 条用例"},
            {"type": "case_start", "data": {"name": "t1", "index": 0, "total": 3, "test_type": "api"}},
            {"type": "case_done", "data": {"index": 0, "name": "t1", "status": "pass", "duration_ms": 5, "detail": {"assertions": [{"passed": True}]}}},
            {"type": "case_start", "data": {"name": "t2", "index": 1, "total": 3, "test_type": "api"}},
            {"type": "case_done", "data": {"index": 1, "name": "t2", "status": "pass", "duration_ms": 5, "detail": {"assertions": [{"passed": True}]}}},
            {"type": "case_start", "data": {"name": "t3", "index": 2, "total": 3, "test_type": "api"}},
            {"type": "case_done", "data": {"index": 2, "name": "t3", "status": "pass", "duration_ms": 5, "detail": {"assertions": [{"passed": True}]}}},
            {"type": "done", "data": {"passed": 3, "failed": 0, "total": 3}},
        ])

        total_passed = 0
        total_cases = 0
        with sync_client.websocket_connect(f"/ws/quick-test/qt_003?token={_token()}") as ws:
            while True:
                msg = ws.receive_json()
                if msg["type"] == "case_done" and msg["data"]["status"] == "pass":
                    total_passed += 1
                if msg["type"] == "case_start":
                    total_cases += 1
                if msg["type"] == "done":
                    assert msg["data"]["passed"] == total_passed
                    assert msg["data"]["passed"] == msg["data"]["total"]
                    assert msg["data"]["failed"] == 0
                    assert total_cases == msg["data"]["total"]
                    break

    def test_qt_004_some_fail(self, sync_client: TestClient):
        """验剑策略：QT-004 — 部分用例失败 → done.failed > 0。

        失败用例 case_done.status="fail"，detail.assertions 含断言详情。
        """
        _start_task_qt(sync_client, "qt_004", [
            {"type": "status", "data": "生成了 2 条用例"},
            {"type": "case_start", "data": {"name": "ok", "index": 0, "total": 2, "test_type": "api"}},
            {"type": "case_done", "data": {"index": 0, "name": "ok", "status": "pass", "duration_ms": 5, "detail": {"assertions": [{"passed": True}]}}},
            {"type": "case_start", "data": {"name": "fail", "index": 1, "total": 2, "test_type": "api"}},
            {"type": "case_done", "data": {"index": 1, "name": "fail", "status": "fail", "duration_ms": 5, "detail": {"assertions": [{"passed": False, "rule": {"type": "status_code", "target": "status_code", "operator": "eq", "expected": 200}, "actual": 500, "error": None}]}}},
            {"type": "done", "data": {"passed": 1, "failed": 1, "total": 2}},
        ])

        with sync_client.websocket_connect(f"/ws/quick-test/qt_004?token={_token()}") as ws:
            case_statuses = []
            while True:
                msg = ws.receive_json()
                if msg["type"] == "case_done":
                    case_statuses.append(msg["data"]["status"])
                    if msg["data"]["status"] == "fail":
                        detail = msg["data"].get("detail", {})
                        assertions = detail.get("assertions", [])
                        assert len(assertions) > 0, "失败用例应有断言详情"
                        failed_assertions = [a for a in assertions if not a.get("passed", True)]
                        assert len(failed_assertions) > 0, f"失败用例应有失败的断言: {assertions}"
                    if msg["data"]["index"] == 1:
                        assert msg["data"]["status"] == "fail"
                if msg["type"] == "done":
                    assert msg["data"]["passed"] == 1
                    assert msg["data"]["failed"] == 1
                    assert msg["data"]["total"] == 2
                    break


# ═══════════════════════════════════════════════════════════════════════════
#  二、边界值
# ═══════════════════════════════════════════════════════════════════════════


class TestBoundaryWS:
    """验剑策略：QT-103 ~ QT-105 — 边界条件。"""

    def test_qt_103_zero_cases(self, sync_client: TestClient):
        """验剑策略：QT-103 — AI 生成 0 条用例 → done{total=0}。"""
        _start_task_qt(sync_client, "qt_103", [
            {"type": "status", "data": "生成了 0 条用例"},
            {"type": "done", "data": {"passed": 0, "failed": 0, "total": 0}},
        ])

        with sync_client.websocket_connect(f"/ws/quick-test/qt_103?token={_token()}") as ws:
            msg1 = ws.receive_json()
            assert msg1["type"] == "status"
            assert "0 条" in msg1.get("data", "")

            msg2 = ws.receive_json()
            assert msg2["type"] == "done"
            assert msg2["data"]["total"] == 0
            assert msg2["data"]["passed"] == 0
            assert msg2["data"]["failed"] == 0

    def test_qt_104_single_case(self, sync_client: TestClient):
        """验剑策略：QT-104 — AI 仅生成 1 条用例 → case_start/case_done 各 1。"""
        _start_task_qt(sync_client, "qt_104", [
            {"type": "status", "data": "生成了 1 条用例"},
            {"type": "case_start", "data": {"name": "single", "index": 0, "total": 1, "test_type": "api"}},
            {"type": "case_done", "data": {"index": 0, "name": "single", "status": "pass", "duration_ms": 5, "detail": {}}},
            {"type": "done", "data": {"passed": 1, "failed": 0, "total": 1}},
        ])

        with sync_client.websocket_connect(f"/ws/quick-test/qt_104?token={_token()}") as ws:
            msgs = _receive_all(ws)
        start_count = sum(1 for m in msgs if m["type"] == "case_start")
        done_count = sum(1 for m in msgs if m["type"] == "case_done")
        assert start_count == 1, f"应有 1 条 case_start: {msgs}"
        assert done_count == 1, f"应有 1 条 case_done: {msgs}"
        start_msgs = [m for m in msgs if m["type"] == "case_start"]
        assert start_msgs[0]["data"]["index"] == 0
        assert start_msgs[0]["data"]["total"] == 1

    def test_qt_105_thirty_cases(self, sync_client: TestClient):
        """验剑策略：QT-105 — AI 生成 30 条用例 → 全部执行，WS 流完整。"""
        msgs = []
        for i in range(30):
            msgs.append({"type": "case_start", "data": {"name": f"c{i}", "index": i, "total": 30, "test_type": "api"}})
            msgs.append({"type": "case_done", "data": {"index": i, "name": f"c{i}", "status": "pass", "duration_ms": 1, "detail": {}}})
        msgs.append({"type": "done", "data": {"passed": 30, "failed": 0, "total": 30}})

        _start_task_qt(sync_client, "qt_105", msgs, delay_per_msg=0.001)

        start_time = _time.monotonic()
        received = 0
        with sync_client.websocket_connect(f"/ws/quick-test/qt_105?token={_token()}") as ws:
            while True:
                msg = ws.receive_json()
                if msg["type"] == "done":
                    assert msg["data"]["passed"] == 30
                    assert msg["data"]["total"] == 30
                    break
                received += 1
        elapsed = _time.monotonic() - start_time
        assert received >= 60, f"应收到至少 60 条消息，实际 {received}"
        assert elapsed < 30, f"30 条用例应在 30 秒内完成，实际 {elapsed:.1f}s"


# ═══════════════════════════════════════════════════════════════════════════
#  三、异常场景
# ═══════════════════════════════════════════════════════════════════════════


class TestExceptionWS:
    """验剑策略：QT-201 ~ QT-206 — 异常场景与 failover。"""

    def test_qt_201_ai_failover_trace(self, sync_client: TestClient):
        """验剑策略：QT-201 — AI 全挂 → failover 链全部失败 → Mock 兜底。

        done 消息中 failover_trace 非空。
        """
        _start_task_qt(sync_client, "qt_201", [
            {"type": "status", "data": "正在分析需求..."},
            {"type": "done", "data": {
                "passed": 3, "failed": 0, "total": 3,
                "failover_trace": [
                    "ClaudeProvider: 401 invalid API key",
                    "OpenAICompatibleProvider: timeout after 30s",
                ],
            }},
        ])

        with sync_client.websocket_connect(f"/ws/quick-test/qt_201?token={_token()}") as ws:
            msgs = _receive_all(ws)
        done_msg = [m for m in msgs if m["type"] == "done"][0]
        failover_trace = done_msg["data"].get("failover_trace")
        assert failover_trace is not None, "全挂后 done 应带 failover_trace"
        assert len(failover_trace) == 2
        assert "ClaudeProvider" in failover_trace[0]

    def test_qt_202_mock_fails_graceful(self, sync_client: TestClient):
        """验剑策略：QT-202 — Mock 也挂 → 优雅兜底（push error + done）。"""
        _start_task_qt(sync_client, "qt_202", [
            {"type": "status", "data": "正在分析需求..."},
            {"type": "error", "data": "AI 生成失败：all providers failed"},
            {"type": "done", "data": {"passed": 0, "failed": 0, "total": 0}},
        ])

        with sync_client.websocket_connect(f"/ws/quick-test/qt_202?token={_token()}") as ws:
            msgs = _receive_all(ws)
        error_msgs = [m for m in msgs if m["type"] == "error"]
        assert len(error_msgs) >= 1, f"Mock 失败应推送 error 消息: {msgs}"
        done_msg = [m for m in msgs if m["type"] == "done"][0]
        assert done_msg["data"]["total"] == 0

    def test_qt_203_timeout(self, sync_client: TestClient):
        """验剑策略：QT-203 — 超时 → error + done。

        模拟：后台协程先 push error 再 push done。
        """
        _start_task_qt(sync_client, "qt_203", [
            {"type": "error", "data": "任务超时"},
            {"type": "done", "data": {"passed": 0, "failed": 0, "total": 0}},
        ])

        with sync_client.websocket_connect(f"/ws/quick-test/qt_203?token={_token()}") as ws:
            msg1 = ws.receive_json()
            assert msg1["type"] == "error"
            msg2 = ws.receive_json()
            assert msg2["type"] == "done"

    def test_qt_204_client_disconnect(self, sync_client: TestClient):
        """验剑策略：QT-204 — 客户端断连 → 后台继续执行，不抛异常。

        验证：后台协程在 WS 断开后仍然完成（通过 flag + _tasks 状态检测）。
        """
        backend_done = {"flag": False}

        async def _tracked():
            await qt_broadcast("qt_204", {"type": "status", "data": "running"})
            await asyncio.sleep(0.3)
            backend_done["flag"] = True
            await qt_broadcast("qt_204", {"type": "done", "data": {"passed": 0, "failed": 0, "total": 0}})
            _tasks["qt_204"]["status"] = "done"
            _tasks["qt_204"]["result"] = {"passed": 0, "failed": 0, "total": 0}

        _tasks["qt_204"] = {"task_id": "qt_204", "status": "running", "result": None, "error": None}
        assert sync_client.portal is not None
        task = sync_client.portal.start_task_soon(_tracked)

        # Connect, receive status, disconnect immediately
        with sync_client.websocket_connect(f"/ws/quick-test/qt_204?token={_token()}") as ws:
            ws.receive_json()  # status: running
        # Disconnected — wait for backend
        task.result(timeout=3)
        assert backend_done["flag"], "后台应在客户端断开后继续执行"
        assert _tasks.get("qt_204", {}).get("status") == "done"

    def test_qt_205_ws_after_task_done(self, sync_client: TestClient):
        """验剑策略：QT-205 — WS 在任务完成后连接。

        已知问题：当前 WS 接受连接但可能无消息推送。
        验证 WS 连接不拒绝（不 500）。
        """
        async def _quick():
            await qt_broadcast("qt_205", {"type": "status", "data": "fast"})
            await asyncio.sleep(0.05)
            await qt_broadcast("qt_205", {"type": "done", "data": {"passed": 1, "failed": 0, "total": 1}})
            _tasks["qt_205"]["status"] = "done"
            _tasks["qt_205"]["result"] = {"passed": 1, "failed": 0, "total": 1}

        _tasks["qt_205"] = {"task_id": "qt_205", "status": "running", "result": None, "error": None}
        assert sync_client.portal is not None
        sync_client.portal.start_task_soon(_quick).result(timeout=2)

        # Connect after task is done
        with sync_client.websocket_connect(f"/ws/quick-test/qt_205?token={_token()}") as ws:
            pass  # Must not raise

    def test_qt_206_nonexistent_task(self, sync_client: TestClient):
        """验剑策略：QT-206 — WS 连接不存在的 task_id → 4001 拒绝。"""
        with pytest.raises(Exception):
            with sync_client.websocket_connect(f"/ws/quick-test/qt_nonexistent?token={_token()}") as ws:
                ws.receive_json()


# ═══════════════════════════════════════════════════════════════════════════
#  四、权限/认证 — WS 层
# ═══════════════════════════════════════════════════════════════════════════


class TestAuthWS:
    """验剑策略：QT-302 ~ QT-303 — WS 认证。"""

    def test_qt_302_no_token(self, sync_client: TestClient):
        """验剑策略：QT-302 — WS 无 token → 4001。"""
        async def _dummy():
            _tasks["qt_302"]["status"] = "done"

        _tasks["qt_302"] = {"task_id": "qt_302", "status": "running", "result": None, "error": None}
        assert sync_client.portal is not None
        sync_client.portal.start_task_soon(_dummy).result(timeout=1)

        with pytest.raises(Exception):
            with sync_client.websocket_connect("/ws/quick-test/qt_302") as ws:
                ws.receive_json()

    def test_qt_303_invalid_token(self, sync_client: TestClient):
        """验剑策略：QT-303 — WS 无效 token → 4001。"""
        async def _dummy():
            _tasks["qt_303"]["status"] = "done"

        _tasks["qt_303"] = {"task_id": "qt_303", "status": "running", "result": None, "error": None}
        assert sync_client.portal is not None
        sync_client.portal.start_task_soon(_dummy).result(timeout=1)

        with pytest.raises(Exception):
            with sync_client.websocket_connect("/ws/quick-test/qt_303?token=invalid_jwt") as ws:
                ws.receive_json()
