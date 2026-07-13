"""测试组：正常路径 — 管理 API（MOCK-007 ~ MOCK-011）。

验剑策略：
  MOCK-007: Mock 列表分页 + 筛选
  MOCK-008: Mock 详情查询
  MOCK-009: PATCH 编辑响应 → source 标记 manual
  MOCK-010: DELETE 删除 Mock 记录
  MOCK-011: Toggle 启用/禁用 Mock 记录
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import MockRecord

pytestmark = pytest.mark.asyncio


# ── MOCK-007 ──────────────────────────────────────────────────────────────────


async def test_mock_007_list_pagination_and_filter(
    async_client: AsyncClient,
    test_project,
    auth_headers: dict[str, str],
    mock_engine,
    db_session: AsyncSession,
):
    """验剑策略：MOCK-007 — Mock 列表分页 + 筛选

    前置：项目有 15 条 MockRecord
    操作：GET /api/projects/{pid}/mocks?method=GET&limit=10&offset=0
    预期：返回 total、items 数组、分页信息正确
    """
    pid = test_project.id

    # 1) 创建 15 条记录：10 条 GET + 5 条 POST
    for i in range(10):
        await mock_engine.record_request(
            method="GET", path=f"/api/items/{i}", query_string="",
            request_headers={}, request_body=None,
            response_status=200, response_headers={}, response_body=b"ok",
        )
    for i in range(5):
        await mock_engine.record_request(
            method="POST", path="/api/items", query_string="",
            request_headers={"content-type": "application/json"},
            request_body=b'{"name":"test"}',
            response_status=201, response_headers={}, response_body=b'{"id":1}',
        )
    await mock_engine._recorder.flush()

    # 2) 筛选 GET + limit=5 + offset=0
    resp = await async_client.get(
        f"/api/projects/{pid}/mocks",
        params={"method": "GET", "limit": 5, "offset": 0},
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"列表查询失败: {resp.text}"
    data = resp.json()
    assert data["total"] == 10, f"GET 总数应为 10，实际 {data['total']}"
    assert len(data["items"]) == 5, f"limit=5 应返回 5 条，实际 {len(data['items'])}"
    for item in data["items"]:
        assert item["method"] == "GET", f"筛选 method=GET，出现 {item['method']}"

    # 3) 第二页
    resp2 = await async_client.get(
        f"/api/projects/{pid}/mocks",
        params={"method": "GET", "limit": 5, "offset": 5},
        headers=auth_headers,
    )
    assert resp2.status_code == 200
    assert len(resp2.json()["items"]) == 5, "第二页应返回剩余 5 条"

    # 4) 筛选 POST
    resp3 = await async_client.get(
        f"/api/projects/{pid}/mocks",
        params={"method": "POST"},
        headers=auth_headers,
    )
    assert resp3.status_code == 200
    assert resp3.json()["total"] == 5, f"POST 总数应为 5，实际 {resp3.json()['total']}"


# ── MOCK-008 ──────────────────────────────────────────────────────────────────


async def test_mock_008_get_detail(
    async_client: AsyncClient,
    test_project,
    auth_headers: dict[str, str],
    recorded_get: MockRecord,
):
    """验剑策略：MOCK-008 — Mock 详情查询

    操作：GET /api/projects/{pid}/mocks/{id}
    预期：返回完整 MockRecord 字段
    """
    pid = test_project.id
    record_id = recorded_get.id

    resp = await async_client.get(
        f"/api/projects/{pid}/mocks/{record_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"详情查询失败: {resp.text}"
    data = resp.json()
    assert data["id"] == record_id
    assert data["method"] == "GET"
    assert data["path"] == "/api/test"
    assert data["response_status"] == 200
    assert data["response_body"] is not None
    assert "recorded_at" in data
    assert "hit_count" in data


# ── MOCK-009 ──────────────────────────────────────────────────────────────────


async def test_mock_009_patch_edits_response_and_marks_manual(
    async_client: AsyncClient,
    test_project,
    auth_headers: dict[str, str],
    recorded_get: MockRecord,
    mock_engine,
):
    """验剑策略：MOCK-009 — PATCH 编辑响应 → source 标记 manual

    操作：PATCH /api/projects/{pid}/mocks/{id} body {"response_status": 201, ...}
    预期：source="manual"，下次回放返回 201 + 新 body
    """
    pid = test_project.id
    record_id = recorded_get.id

    # 1) PATCH 编辑
    new_body = '{"msg":"edited"}'
    resp = await async_client.patch(
        f"/api/projects/{pid}/mocks/{record_id}",
        json={"response_status": 201, "response_body": new_body},
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"PATCH 失败: {resp.text}"
    updated = resp.json()
    assert updated["source"] == "manual", f"source 应为 manual，实际 {updated['source']}"
    assert updated["response_status"] == 201

    # 2) 回放确认新响应
    from services.mock.replayer import replay_raw
    replay_resp = await replay_raw(pid, "GET", "/api/test")
    assert replay_resp is not None
    assert replay_resp.status_code == 201, f"回放状态码应为 201，实际 {replay_resp.status_code}"
    assert replay_resp.content == new_body.encode(), (
        f"回放 body 应为 {new_body}，实际 {replay_resp.content}"
    )


# ── MOCK-010 ──────────────────────────────────────────────────────────────────


async def test_mock_010_delete_removes_record(
    async_client: AsyncClient,
    test_project,
    auth_headers: dict[str, str],
    recorded_get: MockRecord,
    mock_engine,
    db_session: AsyncSession,
):
    """验剑策略：MOCK-010 — DELETE 删除 Mock 记录

    操作：DELETE /api/projects/{pid}/mocks/{id}
    预期：记录从 DB 删除，回放不再匹配
    """
    pid = test_project.id
    record_id = recorded_get.id

    # 1) 回放确认存在
    from services.mock.replayer import replay_raw
    assert await replay_raw(pid, "GET", "/api/test") is not None, "删除前应可回放"

    # 2) 删除
    resp = await async_client.delete(
        f"/api/projects/{pid}/mocks/{record_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 204, f"DELETE 失败: {resp.text}"

    # 3) 确认已删除
    assert await replay_raw(pid, "GET", "/api/test") is None, "删除后回放应返回 None"
    get_resp = await async_client.get(
        f"/api/projects/{pid}/mocks/{record_id}",
        headers=auth_headers,
    )
    assert get_resp.status_code == 404, "删除后查询应 404"


# ── MOCK-011 ──────────────────────────────────────────────────────────────────


async def test_mock_011_toggle_enables_disables(
    async_client: AsyncClient,
    test_project,
    auth_headers: dict[str, str],
    recorded_get: MockRecord,
    mock_engine,
):
    """验剑策略：MOCK-011 — Toggle 启用/禁用 Mock 记录

    操作：POST /api/projects/{pid}/mocks/{id}/toggle
    预期：enabled 字段翻转，禁用的记录不参与匹配
    """
    pid = test_project.id
    record_id = recorded_get.id
    from services.mock.replayer import replay_raw

    # 1) Toggle → 禁用 (enabled: True → False)
    resp = await async_client.post(
        f"/api/projects/{pid}/mocks/{record_id}/toggle",
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Toggle 失败: {resp.text}"
    assert resp.json()["enabled"] is False, "Toggle 后 enabled 应为 False"

    # 2) 禁用后回放应不匹配
    assert await replay_raw(pid, "GET", "/api/test") is None, (
        "禁用后回放应返回 None"
    )

    # 3) 再 Toggle → 启用
    resp2 = await async_client.post(
        f"/api/projects/{pid}/mocks/{record_id}/toggle",
        headers=auth_headers,
    )
    assert resp2.status_code == 200
    assert resp2.json()["enabled"] is True, "再次 Toggle 后 enabled 应为 True"

    # 4) 启用后回放恢复
    assert await replay_raw(pid, "GET", "/api/test") is not None, (
        "启用后回放应正常"
    )
