"""测试组：权限/认证（MOCK-301 ~ MOCK-304）。

验剑策略：
  MOCK-301: 未认证用户访问 Mock API → 401
  MOCK-302: 非项目成员操作 Mock → 403
  MOCK-303: viewer 角色不可编辑/删除 Mock → 403
  MOCK-304: 不同项目 Mock 数据隔离
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import MockRecord
from services.mock.engine import MockEngine

pytestmark = pytest.mark.asyncio


# ── MOCK-301 ──────────────────────────────────────────────────────────────────


async def test_mock_301_unauthorized_returns_401(
    async_client: AsyncClient,
    test_project,
):
    """验剑策略：MOCK-301 — 未认证用户访问 Mock API → 401

    操作：不带 JWT token 调用任意 Mock 管理 API
    预期：返回 401 Unauthorized
    """
    pid = test_project.id

    endpoints = [
        ("GET", f"/api/projects/{pid}/mocks/config"),
        ("PATCH", f"/api/projects/{pid}/mocks/config"),
        ("GET", f"/api/projects/{pid}/mocks"),
        ("POST", f"/api/projects/{pid}/mocks/start-recording"),
        ("POST", f"/api/projects/{pid}/mocks/stop-recording"),
    ]

    for method, url in endpoints:
        resp = await async_client.request(method, url)
        assert resp.status_code == 401, (
            f"{method} {url} 无认证应返回 401，实际 {resp.status_code}: {resp.text}"
        )


# ── MOCK-302 ──────────────────────────────────────────────────────────────────


async def test_mock_302_non_owner_access_returns_403(
    async_client: AsyncClient,
    test_project,
    auth2_headers: dict[str, str],
):
    """验剑策略：MOCK-302 — 非项目成员操作 Mock

    操作：用户 B（test_user2）操作项目 A（test_user）的 Mock
    预期：返回 403（非项目成员）
    """
    pid = test_project.id

    endpoints = [
        ("GET", f"/api/projects/{pid}/mocks/config"),
        ("GET", f"/api/projects/{pid}/mocks"),
        ("POST", f"/api/projects/{pid}/mocks/start-recording"),
        ("POST", f"/api/projects/{pid}/mocks/stop-recording"),
    ]

    for method, url in endpoints:
        resp = await async_client.request(method, url, headers=auth2_headers)
        # 现在返回 403（非项目成员）
        assert resp.status_code == 403, (
            f"{method} {url} 非 owner 应返回 403，实际 {resp.status_code}: {resp.text}"
        )


# ── MOCK-303 ──────────────────────────────────────────────────────────────────


async def test_mock_303_editor_can_edit(
    async_client: AsyncClient,
    test_project,
    recorded_get: MockRecord,
    auth_headers: dict[str, str],
):
    """验剑策略：MOCK-303 — 编辑/删除权限

    注意：试剑 V2 使用 ProjectMembers 角色系统（owner/editor/viewer）。
    owner/editor 可以编辑/删除 mock 记录，viewer 不可。
    此测试验证「owner 可以编辑/删除」的正常路径。
    """
    pid = test_project.id
    record_id = recorded_get.id

    # 1) PATCH (owner → 允许)
    resp = await async_client.patch(
        f"/api/projects/{pid}/mocks/{record_id}",
        json={"response_status": 202},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # 2) DELETE
    resp = await async_client.delete(
        f"/api/projects/{pid}/mocks/{record_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 204

    # 3) Toggle（需要先有新记录）
    resp = await async_client.post(
        f"/api/projects/{pid}/mocks/99999/toggle",
        headers=auth_headers,
    )
    assert resp.status_code == 404  # 不存在，但至少说明已认证


# ── MOCK-304 ──────────────────────────────────────────────────────────────────


async def test_mock_304_project_isolation(
    async_client: AsyncClient,
    test_project,
    test_project2,
    auth_headers: dict[str, str],
    auth2_headers: dict[str, str],
    mock_engine: MockEngine,
    db_session: AsyncSession,
):
    """验剑策略：MOCK-304 — 不同项目 Mock 数据隔离

    前置：项目 A（test_user）和项目 B（test_user2）各有录制数据
    操作：项目 A 的用户查看 Mock 列表
    预期：只看到项目 A 的记录，看不到项目 B 的
    """
    pid_a = test_project.id
    pid_b = test_project2.id

    # 1) 在项目 A 录制 3 条
    for i in range(3):
        await mock_engine.record_request(
            method="GET", path=f"/api/proj-a/{i}", query_string="",
            request_headers={}, request_body=None,
            response_status=200, response_headers={}, response_body=b"a",
        )
    await mock_engine._recorder.flush()

    # 2) 在项目 B 录制 2 条（使用 test_project2 的 engine）
    engine_b = MockEngine(pid_b)
    await engine_b.initialize()
    for i in range(2):
        await engine_b.record_request(
            method="GET", path=f"/api/proj-b/{i}", query_string="",
            request_headers={}, request_body=None,
            response_status=200, response_headers={}, response_body=b"b",
        )
    await engine_b._recorder.flush()

    # 3) 项目 A 的 user 查看项目 A 的列表 → 应看到 3 条
    resp_a = await async_client.get(
        f"/api/projects/{pid_a}/mocks",
        headers=auth_headers,
    )
    assert resp_a.status_code == 200
    data_a = resp_a.json()
    assert data_a["total"] == 3, f"项目 A 应有 3 条记录，实际 {data_a['total']}"

    # 4) 项目 A 的 user 查看项目 B → 应 403（非项目成员）
    resp_b = await async_client.get(
        f"/api/projects/{pid_b}/mocks",
        headers=auth_headers,
    )
    assert resp_b.status_code == 403, (
        "项目 A 的 user 访问项目 B 应 403，"
        f"实际 {resp_b.status_code}: {resp_b.text}"
    )
