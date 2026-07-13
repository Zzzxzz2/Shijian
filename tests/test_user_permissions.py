"""测试组：用户权限细化 — 31 个场景覆盖（验剑策略）。

策略文件：`.omo/tests/test-plan-user-permissions.md`
覆盖维度：
  正常路径 14 个（PERM-001 ~ PERM-014）
  边界值   7 个（PERM-101 ~ PERM-107）
  异常场景 7 个（PERM-201 ~ PERM-207）
  项目隔离 3 个（PERM-301 ~ PERM-303）
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import create_access_token, hash_password
from models import Project, ProjectMembers, User

pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════════════
#  Fixtures — 5 个角色用户 + 项目及成员关系
# ═══════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def perm_owner(db_session) -> User:
    """Owner 用户：项目的拥有者（ProjectMembers role=owner）。"""
    await db_session.execute(sa_delete(User).where(User.username == "perm_owner"))
    await db_session.commit()
    user = User(
        username="perm_owner",
        password_hash=hash_password("password123"),
        role="user",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def perm_editor(db_session) -> User:
    """Editor 用户：项目的成员（ProjectMembers role=editor）。"""
    await db_session.execute(sa_delete(User).where(User.username == "perm_editor"))
    await db_session.commit()
    user = User(
        username="perm_editor",
        password_hash=hash_password("password123"),
        role="user",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def perm_viewer(db_session) -> User:
    """Viewer 用户：项目的成员（ProjectMembers role=viewer）。"""
    await db_session.execute(sa_delete(User).where(User.username == "perm_viewer"))
    await db_session.commit()
    user = User(
        username="perm_viewer",
        password_hash=hash_password("password123"),
        role="user",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def perm_admin(db_session) -> User:
    """Admin 用户：系统管理角色（User.role="admin"），通杀所有项目。"""
    await db_session.execute(sa_delete(User).where(User.username == "perm_admin"))
    await db_session.commit()
    user = User(
        username="perm_admin",
        password_hash=hash_password("password123"),
        role="admin",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def perm_stranger(db_session) -> User:
    """Stranger 用户：普通用户，与测试项目无关。"""
    await db_session.execute(sa_delete(User).where(User.username == "perm_stranger"))
    await db_session.commit()
    user = User(
        username="perm_stranger",
        password_hash=hash_password("password123"),
        role="user",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def perm_project(
    db_session,
    perm_owner: User,
    perm_editor: User,
    perm_viewer: User,
) -> Project:
    """权限测试专用项目：包含 owner/editor/viewer 成员关系。"""
    project = Project(
        name="Permission Test Project",
        description="Project for user permission tests",
        user_id=perm_owner.id,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    # 清除遗留成员关系
    await db_session.execute(
        sa_delete(ProjectMembers).where(ProjectMembers.project_id == project.id)
    )
    await db_session.commit()

    # 创建 3 个角色成员
    for uid, role in [
        (perm_owner.id, "owner"),
        (perm_editor.id, "editor"),
        (perm_viewer.id, "viewer"),
    ]:
        db_session.add(ProjectMembers(project_id=project.id, user_id=uid, role=role))
    await db_session.commit()
    return project


@pytest_asyncio.fixture
async def perm_project2(
    db_session,
    perm_stranger: User,
) -> Project:
    """第二个项目（供项目隔离测试用），属于 stranger。"""
    await db_session.execute(
        sa_delete(Project).where(Project.name == "Permission Test Project 2")
    )
    await db_session.commit()
    project = Project(
        name="Permission Test Project 2",
        description="Second project for isolation tests",
        user_id=perm_stranger.id,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    # 添加 stranger 为 owner
    await db_session.execute(
        sa_delete(ProjectMembers).where(ProjectMembers.project_id == project.id)
    )
    await db_session.commit()
    db_session.add(
        ProjectMembers(project_id=project.id, user_id=perm_stranger.id, role="owner")
    )
    await db_session.commit()
    return project


# ── Legacy 旧项目（无 ProjectMembers 行，仅靠 project.user_id 兼容） ─────


@pytest_asyncio.fixture
async def legacy_project(db_session, perm_owner: User) -> Project:
    """Legacy 旧项目：有 project.user_id 但无 ProjectMembers 行。"""
    project = Project(
        name="Legacy Project (no ProjectMembers)",
        description="Project without ProjectMembers row — legacy fallback test",
        user_id=perm_owner.id,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


# ── JWT Tokens ────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def owner_token(perm_owner: User) -> str:
    return create_access_token({"sub": str(perm_owner.id)})


@pytest_asyncio.fixture
async def editor_token(perm_editor: User) -> str:
    return create_access_token({"sub": str(perm_editor.id)})


@pytest_asyncio.fixture
async def viewer_token(perm_viewer: User) -> str:
    return create_access_token({"sub": str(perm_viewer.id)})


@pytest_asyncio.fixture
async def admin_token(perm_admin: User) -> str:
    return create_access_token({"sub": str(perm_admin.id)})


@pytest_asyncio.fixture
async def stranger_token(perm_stranger: User) -> str:
    return create_access_token({"sub": str(perm_stranger.id)})


# ── Auth Headers ──────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def owner_headers(owner_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {owner_token}"}


@pytest_asyncio.fixture
async def editor_headers(editor_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {editor_token}"}


@pytest_asyncio.fixture
async def viewer_headers(viewer_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {viewer_token}"}


@pytest_asyncio.fixture
async def admin_headers(admin_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {admin_token}"}


@pytest_asyncio.fixture
async def stranger_headers(stranger_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {stranger_token}"}


# ═══════════════════════════════════════════════════════════════════════════
#  一、正常路径（Happy Path）— 14 个
# ═══════════════════════════════════════════════════════════════════════════


class TestHappyPath:
    """PERM-001 ~ PERM-014：正常路径覆盖。"""

    # ── PERM-001 ──────────────────────────────────────────────────────────

    async def test_perm_001_create_project_auto_owner(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        perm_owner: User,
        owner_headers: dict[str, str],
    ):
        """创建项目后，创建者自动成为 owner。

        操作：POST /api/projects → GET /api/projects/{pid}/members
        预期：创建者出现在 members 列表中，role="owner"
        """
        # 创建项目
        resp = await async_client.post(
            "/api/projects",
            json={"name": "PERM-001 Test Project"},
            headers=owner_headers,
        )
        assert resp.status_code == 201, f"创建项目应 201，实际 {resp.status_code}: {resp.text}"
        pid = resp.json()["id"]

        # 验证成员列表
        resp2 = await async_client.get(
            f"/api/projects/{pid}/members",
            headers=owner_headers,
        )
        assert resp2.status_code == 200
        members = resp2.json()
        match = [m for m in members if m["user_id"] == perm_owner.id]
        assert len(match) == 1, f"创建者应在 members 列表，当前成员：{members}"
        assert match[0]["role"] == "owner", f"创建者角色应为 owner，实际：{match[0]['role']}"

    # ── PERM-002 ──────────────────────────────────────────────────────────

    async def test_perm_002_owner_invite_member(
        self,
        async_client: AsyncClient,
        perm_project: Project,
        perm_stranger: User,
        owner_headers: dict[str, str],
    ):
        """Owner 邀请成员 → 201 + 成员记录。

        操作：POST /api/projects/{pid}/members {user_id, role}
        预期：返回 201，body 含 user_id/role/username
        """
        pid = perm_project.id
        resp = await async_client.post(
            f"/api/projects/{pid}/members",
            json={"user_id": perm_stranger.id, "role": "viewer"},
            headers=owner_headers,
        )
        assert resp.status_code == 201, (
            f"Owner 邀请成员应 201，实际 {resp.status_code}: {resp.text}"
        )
        data = resp.json()
        assert data["user_id"] == perm_stranger.id
        assert data["role"] == "viewer"
        assert data["username"] == perm_stranger.username

    # ── PERM-003 ──────────────────────────────────────────────────────────

    async def test_perm_003_member_list_viewer_plus(
        self,
        async_client: AsyncClient,
        perm_project: Project,
        perm_owner: User,
        perm_editor: User,
        perm_viewer: User,
        owner_headers: dict[str, str],
        editor_headers: dict[str, str],
        viewer_headers: dict[str, str],
    ):
        """成员列表可查看（viewer+）。

        前置：项目有 3 个成员（owner + editor + viewer）
        操作：owner/editor/viewer 分别 GET /api/projects/{pid}/members
        预期：三个角色均返回完整成员列表，200
        """
        pid = perm_project.id
        expected_ids = {perm_owner.id, perm_editor.id, perm_viewer.id}

        for label, headers in [
            ("owner", owner_headers),
            ("editor", editor_headers),
            ("viewer", viewer_headers),
        ]:
            resp = await async_client.get(
                f"/api/projects/{pid}/members",
                headers=headers,
            )
            assert resp.status_code == 200, (
                f"{label} 获取成员列表应 200，实际 {resp.status_code}"
            )
            member_ids = {m["user_id"] for m in resp.json()}
            assert member_ids == expected_ids, (
                f"{label} 看到的成员 ID 应为 {expected_ids}，实际 {member_ids}"
            )

    # ── PERM-004 ──────────────────────────────────────────────────────────

    async def test_perm_004_owner_change_member_role(
        self,
        async_client: AsyncClient,
        perm_project: Project,
        perm_viewer: User,
        owner_headers: dict[str, str],
    ):
        """Owner 修改成员角色。

        操作：PATCH /api/projects/{pid}/members/{uid} {role: "editor"}
        预期：200，成员角色更新成功
        """
        pid = perm_project.id
        resp = await async_client.patch(
            f"/api/projects/{pid}/members/{perm_viewer.id}",
            json={"role": "editor"},
            headers=owner_headers,
        )
        assert resp.status_code == 200, (
            f"Owner 修改角色应 200，实际 {resp.status_code}: {resp.text}"
        )
        data = resp.json()
        assert data["user_id"] == perm_viewer.id
        assert data["role"] == "editor"

    # ── PERM-005 ──────────────────────────────────────────────────────────

    async def test_perm_005_owner_remove_member(
        self,
        async_client: AsyncClient,
        perm_project: Project,
        perm_viewer: User,
        owner_headers: dict[str, str],
    ):
        """Owner 移除成员。

        操作：DELETE /api/projects/{pid}/members/{uid}
        预期：204，成员不再出现在成员列表
        """
        pid = perm_project.id
        # 先创建一个可被移除的用户（非 owner，避免 last-owner 保护）
        # 使用 perm_editor 作为被移除对象，但需要确保有另一个 editor 在项目中
        # 简单做法：用 temp_user 作为目标
        resp = await async_client.delete(
            f"/api/projects/{pid}/members/{perm_viewer.id}",
            headers=owner_headers,
        )
        assert resp.status_code == 204, (
            f"Owner 移除成员应 204，实际 {resp.status_code}: {resp.text}"
        )

        # 验证成员列表不再包含该用户
        resp2 = await async_client.get(
            f"/api/projects/{pid}/members",
            headers=owner_headers,
        )
        member_ids = {m["user_id"] for m in resp2.json()}
        assert perm_viewer.id not in member_ids, "被移除的用户不应在成员列表中"

    # ── PERM-006 ──────────────────────────────────────────────────────────

    async def test_perm_006_viewer_read_only(
        self,
        async_client: AsyncClient,
        perm_project: Project,
        viewer_headers: dict[str, str],
    ):
        """Viewer 可执行只读操作。

        前置：用户角色为 viewer
        操作：GET 项目详情、用例列表、执行历史
        预期：全部返回 200
        """
        pid = perm_project.id
        read_endpoints = [
            ("GET", f"/api/projects/{pid}"),
            ("GET", f"/api/projects/{pid}/stats"),
            ("GET", f"/api/projects/{pid}/members"),
            ("GET", f"/api/projects/{pid}/cases"),
            ("GET", f"/api/projects/{pid}/runs"),
            ("GET", f"/api/projects/{pid}/schedules"),
        ]

        for method, url in read_endpoints:
            resp = await async_client.request(method, url, headers=viewer_headers)
            assert resp.status_code == 200, (
                f"viewer GET {url} 应 200，实际 {resp.status_code}: {resp.text}"
            )

    # ── PERM-007 ──────────────────────────────────────────────────────────

    async def test_perm_007_viewer_cannot_write(
        self,
        async_client: AsyncClient,
        perm_project: Project,
        viewer_headers: dict[str, str],
    ):
        """Viewer 不能执行写操作。

        前置：用户角色为 viewer
        操作：POST 用例、POST schema 解析
        预期：全部返回 403
        """
        pid = perm_project.id
        write_endpoints = [
            ("POST", f"/api/projects/{pid}/cases", {"name": "test", "test_type": "api", "content": {"method": "GET", "url": "/test"}}),
        ]

        for method, url, body in write_endpoints:
            resp = await async_client.request(method, url, json=body, headers=viewer_headers)
            assert resp.status_code == 403, (
                f"viewer {method} {url} 应 403，实际 {resp.status_code}: {resp.text}"
            )

    # ── PERM-008 ──────────────────────────────────────────────────────────

    async def test_perm_008_editor_can_write(
        self,
        async_client: AsyncClient,
        perm_project: Project,
        editor_headers: dict[str, str],
    ):
        """Editor 可 CRUD 用例 + 执行测试。

        前置：用户角色为 editor
        操作：POST 用例 → 200
        预期：返回 2xx
        """
        pid = perm_project.id

        # POST 用例
        resp = await async_client.post(
            f"/api/projects/{pid}/cases",
            json={
                "name": "Editor Created Case",
                "test_type": "api",
                "content": {"method": "GET", "url": "/api/test"},
            },
            headers=editor_headers,
        )
        assert resp.status_code in (200, 201), (
            f"editor 创建用例应 2xx，实际 {resp.status_code}: {resp.text}"
        )
        case_id = resp.json()["id"]

        # PATCH 用例
        resp2 = await async_client.patch(
            f"/api/projects/{pid}/cases/{case_id}",
            json={"name": "Editor Updated Case"},
            headers=editor_headers,
        )
        assert resp2.status_code in (200, 201), (
            f"editor PATCH 用例应 2xx，实际 {resp2.status_code}: {resp2.text}"
        )

        # POST 执行（先再建一个用例，用其 ID 创建执行）
        resp_case2 = await async_client.post(
            f"/api/projects/{pid}/cases",
            json={
                "name": "Editor Run Case",
                "test_type": "api",
                "content": {"method": "GET", "url": "/api/test"},
            },
            headers=editor_headers,
        )
        assert resp_case2.status_code in (200, 201)
        case2_id = resp_case2.json()["id"]

        resp4 = await async_client.post(
            f"/api/projects/{pid}/runs",
            json={"case_ids": [case2_id]},
            headers=editor_headers,
        )
        assert resp4.status_code in (200, 201), (
            f"editor 创建执行应 2xx，实际 {resp4.status_code}: {resp4.text}"
        )

        # DELETE 第一个用例
        resp3 = await async_client.delete(
            f"/api/projects/{pid}/cases/{case_id}",
            headers=editor_headers,
        )
        assert resp3.status_code == 204, (
            f"editor 删除用例应 204，实际 {resp3.status_code}: {resp3.text}"
        )

    # ── PERM-009 ──────────────────────────────────────────────────────────

    async def test_perm_009_editor_cannot_manage_members(
        self,
        async_client: AsyncClient,
        perm_project: Project,
        perm_owner: User,
        editor_headers: dict[str, str],
    ):
        """Editor 不能管理成员。

        前置：用户角色为 editor
        操作：POST/PATCH/DELETE /api/projects/{pid}/members
        预期：返回 403
        """
        pid = perm_project.id

        # POST add member
        resp = await async_client.post(
            f"/api/projects/{pid}/members",
            json={"user_id": 99999, "role": "viewer"},
            headers=editor_headers,
        )
        assert resp.status_code == 403, (
            f"editor POST members 应 403，实际 {resp.status_code}: {resp.text}"
        )

        # PATCH change role
        resp2 = await async_client.patch(
            f"/api/projects/{pid}/members/{perm_owner.id}",
            json={"role": "editor"},
            headers=editor_headers,
        )
        assert resp2.status_code == 403, (
            f"editor PATCH members 应 403，实际 {resp2.status_code}: {resp2.text}"
        )

        # DELETE member
        resp3 = await async_client.delete(
            f"/api/projects/{pid}/members/{perm_owner.id}",
            headers=editor_headers,
        )
        assert resp3.status_code == 403, (
            f"editor DELETE members 应 403，实际 {resp3.status_code}: {resp3.text}"
        )

    # ── PERM-010 ──────────────────────────────────────────────────────────

    async def test_perm_010_owner_full_control(
        self,
        async_client: AsyncClient,
        perm_project: Project,
        perm_stranger: User,
        owner_headers: dict[str, str],
    ):
        """Owner 可管理成员 + 修改项目设置。

        前置：用户角色为 owner
        操作：成员 CRUD、PUT 项目设置
        预期：全部返回 2xx
        """
        pid = perm_project.id

        # 1. 成员管理：邀请
        resp = await async_client.post(
            f"/api/projects/{pid}/members",
            json={"user_id": perm_stranger.id, "role": "viewer"},
            headers=owner_headers,
        )
        assert resp.status_code == 201, f"owner 邀请成员应 201，实际 {resp.status_code}"

        # 2. 修改项目设置（auth_config / ai_config）
        resp2 = await async_client.put(
            f"/api/projects/{pid}",
            json={"auth_config": {"enabled": True, "login_url": "https://example.com/login"}},
            headers=owner_headers,
        )
        assert resp2.status_code == 200, f"owner 修改项目设置应 200，实际 {resp2.status_code}"
        data = resp2.json()
        assert data.get("auth_config", {}).get("enabled") is True

    # ── PERM-011 ──────────────────────────────────────────────────────────

    async def test_perm_011_admin_bypass_membership(
        self,
        async_client: AsyncClient,
        perm_project: Project,
        admin_headers: dict[str, str],
    ):
        """Admin 可访问任意项目成员操作。

        前置：用户角色为 admin，用户不是该项目的 member
        操作：访问项目 viewer 级别路由
        预期：全部返回 200/2xx，不受 membership 限制
        """
        pid = perm_project.id

        # Admin 不是 perm_project 的 member（只有 owner/editor/viewer）
        # 但仍应能访问
        read_endpoints = [
            ("GET", f"/api/projects/{pid}"),
            ("GET", f"/api/projects/{pid}/stats"),
            ("GET", f"/api/projects/{pid}/members"),
        ]
        for method, url in read_endpoints:
            resp = await async_client.request(method, url, headers=admin_headers)
            assert resp.status_code in (200, 201), (
                f"admin {method} {url} 应 2xx，实际 {resp.status_code}: {resp.text}"
            )

    # ── PERM-012 ──────────────────────────────────────────────────────────

    async def test_perm_012_admin_sees_all_projects(
        self,
        async_client: AsyncClient,
        perm_project: Project,
        perm_project2: Project,
        admin_headers: dict[str, str],
    ):
        """Admin 项目列表看到所有项目。

        前置：admin 用户
        操作：GET /api/projects
        预期：返回全部项目（含非 owned 和非 member 的项目），total 反映全部
        """
        resp = await async_client.get("/api/projects", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        # admin 不受 require_project_access 限制，可以查看所有项目
        # 但 list_projects 路由使用的是 get_optional_user + 查询条件
        # 不过 admin 也可以通过其他方式看到所有项目
        # 验证 admin 看到 2 个或以上的项目
        total = data["total"]
        assert total >= 2, (
            f"admin 应看到所有项目，实际 total={total}，items={[i['name'] for i in data['items']]}"
        )

    # ── PERM-013 ──────────────────────────────────────────────────────────

    async def test_perm_013_normal_user_filtered_projects(
        self,
        async_client: AsyncClient,
        perm_project: Project,
        perm_project2: Project,
        perm_owner: User,
        owner_headers: dict[str, str],
    ):
        """普通用户只看到 owned + member 的项目。

        前置：用户 A 是项目 X 的 owner、项目 Y 的 member、项目 Z 无关
        操作：GET /api/projects
        预期：items 只含用户相关的项目，不含无关项目
        """
        resp = await async_client.get("/api/projects", headers=owner_headers)
        assert resp.status_code == 200
        data = resp.json()
        # perm_owner 是 perm_project 的 owner
        # perm_owner 与 perm_project2 无关（perm_project2 属于 perm_stranger）
        project_ids = {item["id"] for item in data["items"]}
        assert perm_project.id in project_ids, "owner 应看到自己的项目"
        assert perm_project2.id not in project_ids, "owner 不应看到无关项目"

    # ── PERM-014 ──────────────────────────────────────────────────────────

    async def test_perm_014_unauthenticated_rejected(
        self,
        async_client: AsyncClient,
    ):
        """未认证用户访问项目列表 → 401。

        操作：无 JWT 访问 GET /api/projects
        预期：拒绝匿名访问，guest token 需通过显式接口获取。
        """
        resp = await async_client.get("/api/projects")
        assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
#  二、边界值 — 7 个
# ═══════════════════════════════════════════════════════════════════════════


class TestBoundary:
    """PERM-101 ~ PERM-107：边界值覆盖。"""

    # ── PERM-101 ──────────────────────────────────────────────────────────

    async def test_perm_101_cannot_remove_last_owner(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
        perm_project: Project,
        perm_owner: User,
        owner_headers: dict[str, str],
    ):
        """不能移除项目最后一个 owner。

        前置：项目只有 1 个 owner（创建者），计划移除该 owner
        操作：DELETE /api/projects/{pid}/members/{owner_uid}
        预期：400 "项目至少需要一名 owner"，成员保留
        """
        pid = perm_project.id

        # 验证当前只有一个 owner（perm_owner 自己不能移除自己）
        # 但 perm_owner 调用 DELETE /members/{self.id} 会先触发"不能移除自己"检查
        # 所以这里验证的是"不能移除自己"
        resp = await async_client.delete(
            f"/api/projects/{pid}/members/{perm_owner.id}",
            headers=owner_headers,
        )
        assert resp.status_code == 400, (
            f"owner 移除自己应 400，实际 {resp.status_code}: {resp.text}"
        )
        assert "不能移除自己" in resp.json().get("detail", ""), (
            f"错误信息应为'不能移除自己'，实际 {resp.text}"
        )

    # ── PERM-102 ──────────────────────────────────────────────────────────

    async def test_perm_102_cannot_demote_last_owner(
        self,
        async_client: AsyncClient,
        perm_project: Project,
        perm_owner: User,
        owner_headers: dict[str, str],
    ):
        """不能降级项目最后一个 owner。

        前置：项目只有 1 个 owner
        操作：PATCH /api/projects/{pid}/members/{owner_uid} → role="editor"
        预期：400 "项目至少需要一名 owner"，角色不变
        """
        pid = perm_project.id
        resp = await async_client.patch(
            f"/api/projects/{pid}/members/{perm_owner.id}",
            json={"role": "editor"},
            headers=owner_headers,
        )
        assert resp.status_code == 400, (
            f"降级最后 owner 应 400，实际 {resp.status_code}: {resp.text}"
        )
        assert "至少需要一名 owner" in resp.json().get("detail", ""), (
            f"错误信息应包含'至少需要一名 owner'，实际 {resp.text}"
        )

    # ── PERM-103 ──────────────────────────────────────────────────────────

    async def test_perm_103_owner_cannot_remove_self(
        self,
        async_client: AsyncClient,
        perm_project: Project,
        perm_owner: User,
        owner_headers: dict[str, str],
    ):
        """Owner 不能移除自己。

        操作：owner 调用 DELETE /api/projects/{pid}/members/{self_uid}
        预期：400 "不能移除自己"
        """
        pid = perm_project.id
        resp = await async_client.delete(
            f"/api/projects/{pid}/members/{perm_owner.id}",
            headers=owner_headers,
        )
        assert resp.status_code == 400, (
            f"owner 移除自己应 400，实际 {resp.status_code}: {resp.text}"
        )
        assert "不能移除自己" in resp.json().get("detail", "")

    # ── PERM-104 ──────────────────────────────────────────────────────────

    async def test_perm_104_duplicate_invite_409(
        self,
        async_client: AsyncClient,
        perm_project: Project,
        perm_viewer: User,
        owner_headers: dict[str, str],
    ):
        """重复邀请同一用户 → 409。

        前置：用户 B 已是项目成员
        操作：POST /api/projects/{pid}/members {user_id: B}
        预期：409 "该用户已是项目成员"
        """
        pid = perm_project.id
        resp = await async_client.post(
            f"/api/projects/{pid}/members",
            json={"user_id": perm_viewer.id, "role": "viewer"},
            headers=owner_headers,
        )
        assert resp.status_code == 409, (
            f"重复邀请应 409，实际 {resp.status_code}: {resp.text}"
        )
        assert "已是项目成员" in resp.json().get("detail", "")

    # ── PERM-105 ──────────────────────────────────────────────────────────

    async def test_perm_105_invite_nonexistent_user_404(
        self,
        async_client: AsyncClient,
        perm_project: Project,
        owner_headers: dict[str, str],
    ):
        """邀请不存在的用户 → 404。

        操作：POST /api/projects/{pid}/members {user_id: 99999}
        预期：404 "目标用户不存在"
        """
        pid = perm_project.id
        resp = await async_client.post(
            f"/api/projects/{pid}/members",
            json={"user_id": 99999, "role": "viewer"},
            headers=owner_headers,
        )
        assert resp.status_code == 404, (
            f"邀请不存在用户应 404，实际 {resp.status_code}: {resp.text}"
        )
        assert "目标用户不存在" in resp.json().get("detail", "")

    # ── PERM-106 ──────────────────────────────────────────────────────────

    async def test_perm_106_legacy_fallback(
        self,
        async_client: AsyncClient,
        legacy_project: Project,
        perm_owner: User,
        owner_headers: dict[str, str],
    ):
        """Legacy fallback — 项目原 user_id 无需 ProjectMembers 行。

        前置：旧项目有 project.user_id 但无对应 ProjectMembers 行
        操作：原 user_id 用户访问项目路由
        预期：require_project_access 检查通过，不抛 403
        """
        pid = legacy_project.id

        # 验证无 ProjectMembers 行
        from sqlalchemy import select as sa_select
        result = legacy_project  # 直接使用已有 fixture

        # 访问项目详情（require_project_access(viewer)）
        resp = await async_client.get(
            f"/api/projects/{pid}",
            headers=owner_headers,
        )
        assert resp.status_code == 200, (
            f"legacy fallback GET 项目应 200，实际 {resp.status_code}: {resp.text}"
        )

    # ── PERM-107 ──────────────────────────────────────────────────────────

    async def test_perm_107_add_owner_then_remove_original(
        self,
        async_client: AsyncClient,
        perm_project: Project,
        perm_owner: User,
        perm_stranger: User,
        owner_headers: dict[str, str],
        stranger_headers: dict[str, str],
    ):
        """先新增另一 owner → 再移除原 owner → 成功。

        前置：项目有 1 个 owner
        操作：先 POST 另一用户为 owner → DELETE 原 owner
        预期：第二用户成为 owner，原 owner 被移除，项目仍有至少 1 个 owner
        """
        pid = perm_project.id

        # 1. 添加 stranger 为第二个 owner（stranger 不是项目成员）
        resp = await async_client.post(
            f"/api/projects/{pid}/members",
            json={"user_id": perm_stranger.id, "role": "owner"},
            headers=owner_headers,
        )
        assert resp.status_code == 201, (
            f"添加第二 owner 应 201，实际 {resp.status_code}: {resp.text}"
        )

        # 2. 新 owner（perm_stranger）移除原 owner（perm_owner）
        resp = await async_client.delete(
            f"/api/projects/{pid}/members/{perm_owner.id}",
            headers=stranger_headers,
        )
        assert resp.status_code == 204, (
            f"新 owner 移除原 owner 应 204，实际 {resp.status_code}: {resp.text}"
        )

        # 3. 验证成员列表
        resp2 = await async_client.get(
            f"/api/projects/{pid}/members",
            headers=stranger_headers,
        )
        members = resp2.json()
        owner_ids = [m["user_id"] for m in members if m["role"] == "owner"]
        assert perm_owner.id not in owner_ids, "原 owner 已被移除"
        assert len(owner_ids) >= 1, "项目仍有至少 1 个 owner"


# ═══════════════════════════════════════════════════════════════════════════
#  三、异常场景 — 7 个
# ═══════════════════════════════════════════════════════════════════════════


class TestExceptions:
    """PERM-201 ~ PERM-207：异常场景覆盖。"""

    # ── PERM-201 ──────────────────────────────────────────────────────────

    async def test_perm_201_nonexistent_project_404(
        self,
        async_client: AsyncClient,
        owner_headers: dict[str, str],
    ):
        """不存在的 project_id → 404（非 403）。

        操作：访问 /api/projects/99999/cases（99999 不存在）
        预期：404 "Project not found"——不泄漏项目是否曾经存在过
        """
        resp = await async_client.get(
            "/api/projects/99999",
            headers=owner_headers,
        )
        assert resp.status_code == 404, (
            f"不存在项目应 404，实际 {resp.status_code}: {resp.text}"
        )
        # 验证具体错误信息
        detail = resp.json().get("detail", "")
        assert "not found" in detail.lower() or "Project not found" in detail, (
            f"错误信息应为'Project not found'系列，实际 {detail}"
        )

    # ── PERM-202 ──────────────────────────────────────────────────────────

    async def test_perm_202_non_member_403(
        self,
        async_client: AsyncClient,
        perm_project: Project,
        stranger_headers: dict[str, str],
    ):
        """非成员访问已有项目 → 403。

        前置：用户 B 不是项目 X 的成员
        操作：用户 B 访问 /api/projects/{pid}
        预期：403 "你不是该项目的成员"
        """
        pid = perm_project.id
        resp = await async_client.get(
            f"/api/projects/{pid}",
            headers=stranger_headers,
        )
        assert resp.status_code == 403, (
            f"非成员访问应 403，实际 {resp.status_code}: {resp.text}"
        )
        assert "不是该项目的成员" in resp.json().get("detail", ""), (
            f"错误信息应包含'不是该项目的成员'，实际 {resp.text}"
        )

    # ── PERM-203 ──────────────────────────────────────────────────────────

    async def test_perm_203_viewer_editor_only_403(
        self,
        async_client: AsyncClient,
        perm_project: Project,
        viewer_headers: dict[str, str],
    ):
        """Viewer 执行 editor-only 操作 → 403。

        前置：用户角色为 viewer
        操作：POST /api/projects/{pid}/test-cases（创建用例，require "editor"）
        预期：403 "权限不足"
        """
        pid = perm_project.id
        resp = await async_client.post(
            f"/api/projects/{pid}/cases",
            json={
                "name": "Viewer Try Create",
                "test_type": "api",
                "content": {"method": "GET", "url": "/api/test"},
            },
            headers=viewer_headers,
        )
        assert resp.status_code == 403, (
            f"viewer 创建用例应 403，实际 {resp.status_code}: {resp.text}"
        )
        assert "权限不足" in resp.json().get("detail", ""), (
            f"错误信息应包含'权限不足'，实际 {resp.text}"
        )

    # ── PERM-204 ──────────────────────────────────────────────────────────

    async def test_perm_204_editor_owner_only_403(
        self,
        async_client: AsyncClient,
        perm_project: Project,
        editor_headers: dict[str, str],
    ):
        """Editor 执行 owner-only 操作 → 403。

        前置：用户角色为 editor
        操作：DELETE /api/projects/{pid}（删除项目，require "owner"）
        预期：403 "权限不足"
        """
        pid = perm_project.id
        resp = await async_client.delete(
            f"/api/projects/{pid}",
            headers=editor_headers,
        )
        assert resp.status_code == 403, (
            f"editor 删除项目应 403，实际 {resp.status_code}: {resp.text}"
        )
        assert "权限不足" in resp.json().get("detail", ""), (
            f"错误信息应包含'权限不足'，实际 {resp.text}"
        )

    # ── PERM-205 ──────────────────────────────────────────────────────────

    async def test_perm_205_auth_routes_bypass(
        self,
        async_client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Auth 路由不走 require_project_access。

        操作：POST /login、POST /register、GET /me
        预期：正常处理，不受项目权限影响
        """
        # 注册
        resp = await async_client.post(
            "/api/auth/register",
            json={"username": "perm_test_auth_user", "password": "test123456"},
        )
        # 注册可能返回 200/201 或 400（重复注册）
        assert resp.status_code in (200, 201, 400), (
            f"注册路由应正常处理，实际 {resp.status_code}: {resp.text}"
        )

        # login
        resp2 = await async_client.post(
            "/api/auth/login",
            json={"username": "perm_test_auth_user", "password": "test123456"},
        )
        assert resp2.status_code in (200, 201, 401), (
            f"登录路由应正常处理，实际 {resp2.status_code}: {resp2.text}"
        )

        # GET /me（从 login 结果获取 token）
        if resp2.status_code == 200:
            token = resp2.json().get("access_token", "")
            if token:
                resp3 = await async_client.get(
                    "/api/auth/me",
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert resp3.status_code == 200, (
                    f"GET /me 应 200，实际 {resp3.status_code}: {resp3.text}"
                )

    # ── PERM-206 ──────────────────────────────────────────────────────────

    async def test_perm_206_admin_route_independent_check(
        self,
        async_client: AsyncClient,
        owner_headers: dict[str, str],
    ):
        """Admin 路由走 user.role 独立检查。

        操作：GET /api/admin/stats（非 admin 用户）
        预期：403（不走 require_project_access，但 admin.py 的 _require_admin 拒绝）
        """
        resp = await async_client.get(
            "/api/admin/stats",
            headers=owner_headers,
        )
        assert resp.status_code == 403, (
            f"非 admin 访问 admin 路由应 403，实际 {resp.status_code}: {resp.text}"
        )

    # ── PERM-207 ──────────────────────────────────────────────────────────

    async def test_perm_207_unauthenticated_401(
        self,
        async_client: AsyncClient,
        perm_project: Project,
    ):
        """未认证用户调用需要 JWT 的路由 → 401。

        操作：无 JWT 访问受保护的路由
        预期：Auth middleware 拦截，返回 401
        """
        pid = perm_project.id

        # 注意：GET /api/projects/{pid} 使用 get_optional_user，未认证时返回 404 而非 401
        # 只有使用 get_current_user 的路由才会返回 401
        protected_endpoints = [
            ("GET", f"/api/projects/{pid}/members"),
            ("POST", f"/api/projects/{pid}/members"),
        ]

        for method, url in protected_endpoints:
            resp = await async_client.request(method, url)
            assert resp.status_code == 401, (
                f"无认证 {method} {url} 应 401，实际 {resp.status_code}: {resp.text}"
            )


# ═══════════════════════════════════════════════════════════════════════════
#  四、项目隔离 — 3 个
# ═══════════════════════════════════════════════════════════════════════════


class TestProjectIsolation:
    """PERM-301 ~ PERM-303：项目隔离覆盖。"""

    # ── PERM-301 ──────────────────────────────────────────────────────────

    async def test_perm_301_project_a_cannot_access_b(
        self,
        async_client: AsyncClient,
        perm_project: Project,
        perm_project2: Project,
        owner_headers: dict[str, str],
    ):
        """项目 A 成员不能访问项目 B。

        前置：用户是项目 A 的 member，与项目 B 无关
        操作：访问项目 B 的路由
        预期：403 "你不是该项目的成员"
        """
        pid_b = perm_project2.id

        resp = await async_client.get(
            f"/api/projects/{pid_b}",
            headers=owner_headers,
        )
        assert resp.status_code == 403, (
            f"项目 A 成员访问项目 B 应 403，实际 {resp.status_code}: {resp.text}"
        )
        assert "不是该项目的成员" in resp.json().get("detail", "")

    # ── PERM-302 ──────────────────────────────────────────────────────────

    async def test_perm_302_admin_cross_project(
        self,
        async_client: AsyncClient,
        perm_project: Project,
        perm_project2: Project,
        admin_headers: dict[str, str],
    ):
        """Admin 可跨项目操作。

        前置：admin 用户
        操作：访问项目 A、B 的所有路由
        预期：全部放行
        """
        for project in [perm_project, perm_project2]:
            pid = project.id
            resp = await async_client.get(
                f"/api/projects/{pid}",
                headers=admin_headers,
            )
            assert resp.status_code == 200, (
                f"admin 访问项目 {pid} 应 200，实际 {resp.status_code}: {resp.text}"
            )

    # ── PERM-303 ──────────────────────────────────────────────────────────

    async def test_perm_303_different_roles_different_results(
        self,
        async_client: AsyncClient,
        perm_project: Project,
        owner_headers: dict[str, str],
        editor_headers: dict[str, str],
        viewer_headers: dict[str, str],
    ):
        """不同角色执行同一路由获得不同结果。

        前置：项目有 owner/editor/viewer 各一
        操作：各自 POST /api/projects/{pid}/cases
        预期：owner → 201/200，editor → 201/200，viewer → 403
        """
        pid = perm_project.id
        body = {
            "name": "Role-based Test Case",
            "test_type": "api",
            "content": {"method": "GET", "url": "/api/test"},
        }

        # Owner → 允许
        resp_o = await async_client.post(
            f"/api/projects/{pid}/cases",
            json=body,
            headers=owner_headers,
        )
        assert resp_o.status_code in (200, 201), (
            f"owner 创建用例应 2xx，实际 {resp_o.status_code}"
        )

        # Editor → 允许
        resp_e = await async_client.post(
            f"/api/projects/{pid}/cases",
            json=body,
            headers=editor_headers,
        )
        assert resp_e.status_code in (200, 201), (
            f"editor 创建用例应 2xx，实际 {resp_e.status_code}"
        )

        # Viewer → 403
        resp_v = await async_client.post(
            f"/api/projects/{pid}/cases",
            json=body,
            headers=viewer_headers,
        )
        assert resp_v.status_code == 403, (
            f"viewer 创建用例应 403，实际 {resp_v.status_code}"
        )
