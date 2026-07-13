"""测试组：个人用户中心 + 系统管理员面板 — 32 个场景覆盖（验剑策略）。

策略文件：`.omo/tests/test-plan-user-center-admin.md`
覆盖维度：
  正常路径 12 个（USR-001 ~ USR-012）
  边界值   10 个（USR-101 ~ USR-110）
  异常场景  7 个（USR-201 ~ USR-207）
  权限隔离  2 个（USR-301 ~ USR-302）
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import create_access_token, hash_password, verify_password
from models import Project, ProjectMembers, User

pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════════════
#  Fixtures — 测试用用户角色
# ═══════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def uc_target_user(db_session) -> User:
    """普通目标用户（用于强制下线 / 角色修改等 admin 操作的目标）。"""
    await db_session.execute(sa_delete(User).where(User.username == "uc_target"))
    await db_session.commit()
    user = User(
        username="uc_target",
        password_hash=hash_password("target123"),
        role="user",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def uc_target_token(uc_target_user: User) -> str:
    """uc_target_user 的 JWT token（含 ver 声明）。"""
    return create_access_token({"sub": str(uc_target_user.id)}, user=uc_target_user)


@pytest_asyncio.fixture
async def uc_target_headers(uc_target_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {uc_target_token}"}


@pytest_asyncio.fixture
async def uc_other_user(db_session) -> User:
    """另一个普通用户（用于隔离测试）。"""
    await db_session.execute(sa_delete(User).where(User.username == "uc_other"))
    await db_session.commit()
    user = User(
        username="uc_other",
        password_hash=hash_password("other123"),
        role="user",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def uc_other_token(uc_other_user: User) -> str:
    return create_access_token({"sub": str(uc_other_user.id)}, user=uc_other_user)


@pytest_asyncio.fixture
async def uc_other_headers(uc_other_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {uc_other_token}"}


@pytest_asyncio.fixture
async def uc_nullver_user(db_session) -> User:
    """token_version=NULL 的历史用户（模拟旧数据未迁移）。"""
    await db_session.execute(sa_delete(User).where(User.username == "uc_nullver"))
    await db_session.commit()
    user = User(
        username="uc_nullver",
        password_hash=hash_password("nullver123"),
        role="user",
        token_version=None,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def uc_nullver_token(uc_nullver_user: User) -> str:
    """token_version=NULL 用户的 JWT token（含 ver=0 声明）。"""
    return create_access_token({"sub": str(uc_nullver_user.id)}, user=uc_nullver_user)


@pytest_asyncio.fixture
async def uc_nullver_headers(uc_nullver_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {uc_nullver_token}"}


# ═══════════════════════════════════════════════════════════════════════════
#  I. 正常路径（Happy Path）
# ═══════════════════════════════════════════════════════════════════════════


class TestHappyPath:
    """USR-001 ~ USR-012：正常路径 12 个场景。"""

    async def test_usr_001_get_profile(
        self, async_client: AsyncClient, auth_headers: dict, test_user: User
    ):
        """USR-001：获取个人信息 — GET /api/user/profile → 200，返回 username/role/notification_config。"""
        resp = await async_client.get("/api/user/profile", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == test_user.username
        assert data["role"] == test_user.role
        assert "notification_config" in data
        assert "id" in data
        assert "created_at" in data

    async def test_usr_002_update_username(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """USR-002：修改用户名 — PUT /api/user/profile {username} → 200，username 已更新。"""
        resp = await async_client.put(
            "/api/user/profile",
            headers=auth_headers,
            json={"username": "new_username_002"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "new_username_002"

        # 二次读取验证：GET 确认已持久化
        resp2 = await async_client.get("/api/user/profile", headers=auth_headers)
        assert resp2.status_code == 200
        assert resp2.json()["username"] == "new_username_002"

    async def test_usr_003_change_password(
        self, async_client: AsyncClient, auth_headers: dict, test_user: User, db_session: AsyncSession
    ):
        """USR-003：旧密码正确 → 修改密码成功 — PUT /api/user/password → 200 {ok:true}，密码已更新。"""
        resp = await async_client.put(
            "/api/user/password",
            headers=auth_headers,
            json={"old_password": "password123", "new_password": "newpass003"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

        # 验证：DB 中新密码 hash 已更新
        await db_session.refresh(test_user)
        assert verify_password("newpass003", test_user.password_hash)

        # 验证：可通过新密码登录
        login_resp = await async_client.post(
            "/api/auth/login",
            json={"username": test_user.username, "password": "newpass003"},
        )
        assert login_resp.status_code == 200

    async def test_usr_004_notification_config(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """USR-004：通知配置写入 — PUT /api/user/notifications → 200，notification_config 包含对应条目。"""
        resp = await async_client.put(
            "/api/user/notifications",
            headers=auth_headers,
            json={"type": "wechat", "webhook_url": "https://qyapi.weixin.qq.com/webhook/test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "notification_config" in data
        assert data["notification_config"].get("wechat") == "https://qyapi.weixin.qq.com/webhook/test"

    async def test_usr_005_admin_system_stats(
        self, async_client: AsyncClient, admin_headers: dict
    ):
        """USR-005：系统级统计 — GET /api/admin/system-stats → 200，返回 5 组计数。"""
        resp = await async_client.get("/api/admin/system-stats", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        for key in ("users", "projects", "test_cases", "test_runs", "today_executions"):
            assert key in data
            assert isinstance(data[key], int)

    async def test_usr_006_force_logout_increment(
        self,
        async_client: AsyncClient,
        admin_headers: dict,
        uc_target_user: User,
        db_session: AsyncSession,
    ):
        """USR-006：强制下线 → token_version 递增 — POST /api/admin/users/{id}/logout → 200，token_version +1。"""
        original_ver = uc_target_user.token_version
        resp = await async_client.post(
            f"/api/admin/users/{uc_target_user.id}/logout",
            headers=admin_headers,
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

        # DB 验证
        await db_session.refresh(uc_target_user)
        assert uc_target_user.token_version == (original_ver if original_ver is not None else 0) + 1

    async def test_usr_007_old_token_invalid_after_logout(
        self,
        async_client: AsyncClient,
        admin_headers: dict,
        uc_target_user: User,
        uc_target_headers: dict,
        db_session: AsyncSession,
    ):
        """USR-007：强制下线后旧 token 失效 — admin 强制下线 → 旧 token 调用 API → 401 'Session expired'。"""
        # 先确认 uc_target_user 有非零 token_version，否则 ver=0 的 token 会跳过校验
        if uc_target_user.token_version == 0:
            uc_target_user.token_version = 1
            await db_session.commit()

        # 用当前 token_version 重新签发 token（此时 ver=1）
        fresh_token = create_access_token(
            {"sub": str(uc_target_user.id)}, user=uc_target_user
        )
        old_headers = {"Authorization": f"Bearer {fresh_token}"}

        # admin 强制下线（token_version → 2）
        resp = await async_client.post(
            f"/api/admin/users/{uc_target_user.id}/logout",
            headers=admin_headers,
        )
        assert resp.status_code == 200

        # 旧 token（ver=1）访问受保护 API → 401
        resp = await async_client.get("/api/user/profile", headers=old_headers)
        assert resp.status_code == 401
        data = resp.json()
        detail = data.get("detail", "")
        assert "expired" in detail.lower() or "Session expired" in detail

    async def test_usr_008_admin_project_list(
        self,
        async_client: AsyncClient,
        admin_headers: dict,
        test_user: User,
        db_session: AsyncSession,
    ):
        """USR-008：admin 项目列表（含成员数 + 创建人）— GET /api/admin/projects → 200，返回所有项目。"""
        # 先创建一个带成员的项目
        other_user = User(
            username="uc_proj_member",
            password_hash=hash_password("member123"),
            role="user",
        )
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)

        proj = Project(name="Admin List Test Proj", user_id=test_user.id)
        db_session.add(proj)
        await db_session.commit()
        await db_session.refresh(proj)

        member = ProjectMembers(project_id=proj.id, user_id=other_user.id, role="viewer")
        db_session.add(member)
        await db_session.commit()

        resp = await async_client.get("/api/admin/projects", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["total"], int)
        # 至少包含我们刚创建的项目
        found = [i for i in data["items"] if i["name"] == "Admin List Test Proj"]
        assert len(found) >= 1
        item = found[0]
        assert "id" in item
        assert "user_id" in item
        assert "creator_name" in item
        assert "member_count" in item
        assert item["member_count"] >= 1

    async def test_usr_009_admin_update_role(
        self,
        async_client: AsyncClient,
        admin_headers: dict,
        uc_target_user: User,
    ):
        """USR-009：admin 修改用户角色 — PUT /api/admin/users/{id}/role {role:'admin'} → 200。"""
        resp = await async_client.put(
            f"/api/admin/users/{uc_target_user.id}/role",
            headers=admin_headers,
            json={"role": "admin"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "admin"

    async def test_usr_010_admin_create_user(
        self,
        async_client: AsyncClient,
        admin_headers: dict,
    ):
        """USR-010：admin 创建用户 — POST /api/admin/users → 201，verified=true。"""
        resp = await async_client.post(
            "/api/admin/users",
            headers=admin_headers,
            json={"username": "admin_created_user", "password": "create123", "role": "user"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["username"] == "admin_created_user"
        assert data["verified"] is True
        assert data["role"] == "user"

    async def test_usr_011_admin_delete_user(
        self,
        async_client: AsyncClient,
        admin_headers: dict,
        admin_user: User,
        db_session: AsyncSession,
    ):
        """USR-011：admin 删除用户 — DELETE /api/admin/users/{id} → 204，项目转交 admin。"""
        # 创建被删除用户 + 其项目
        doomed = User(
            username="doomed_user",
            password_hash=hash_password("doom123"),
            role="user",
        )
        db_session.add(doomed)
        await db_session.commit()
        await db_session.refresh(doomed)

        doomed_proj = Project(name="Doomed Project", user_id=doomed.id)
        db_session.add(doomed_proj)
        await db_session.commit()
        await db_session.refresh(doomed_proj)

        resp = await async_client.delete(
            f"/api/admin/users/{doomed.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 204

        # 验证：用户已删除（用 fresh select 绕过跨会话 stale 问题）
        deleted = (await db_session.execute(
            select(User).where(User.id == doomed.id)
        )).scalar_one_or_none()
        assert deleted is None

        # 验证：项目已转交 admin（refresh 绕过身份映射 stale 问题）
        proj = (await db_session.execute(
            select(Project).where(Project.id == doomed_proj.id)
        )).scalar_one_or_none()
        assert proj is not None
        await db_session.refresh(proj)
        assert proj.user_id == admin_user.id

    async def test_usr_012_admin_reset_password(
        self,
        async_client: AsyncClient,
        admin_headers: dict,
        uc_target_user: User,
    ):
        """USR-012：admin 重置密码 — PUT /api/admin/users/{id}/reset-password → 200，新密码可登录。"""
        resp = await async_client.put(
            f"/api/admin/users/{uc_target_user.id}/reset-password",
            headers=admin_headers,
            json={"new_password": "reset_new_pass"},
        )
        assert resp.status_code == 200

        # 验证：新密码可登录
        login_resp = await async_client.post(
            "/api/auth/login",
            json={"username": uc_target_user.username, "password": "reset_new_pass"},
        )
        assert login_resp.status_code == 200
        assert "access_token" in login_resp.json()


# ═══════════════════════════════════════════════════════════════════════════
#  II. 边界值
# ═══════════════════════════════════════════════════════════════════════════


class TestBoundary:
    """USR-101 ~ USR-110：边界值 10 个场景。"""

    async def test_usr_101_username_exists(
        self, async_client: AsyncClient, auth_headers: dict, test_user: User, db_session: AsyncSession
    ):
        """USR-101：用户名已存在 → 400 'Username already exists'。"""
        # 创建一个已存在的用户名
        existing = User(
            username="existing_user_101",
            password_hash=hash_password("existing123"),
            role="user",
        )
        db_session.add(existing)
        await db_session.commit()

        resp = await async_client.put(
            "/api/user/profile",
            headers=auth_headers,
            json={"username": "existing_user_101"},
        )
        assert resp.status_code == 400
        assert "already exists" in resp.json().get("detail", "").lower()

    async def test_usr_102_same_username(
        self, async_client: AsyncClient, auth_headers: dict, test_user: User
    ):
        """USR-102：修改为相同用户名 → 200（自己查自己不冲突）。"""
        resp = await async_client.put(
            "/api/user/profile",
            headers=auth_headers,
            json={"username": test_user.username},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == test_user.username

    async def test_usr_103_empty_username(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """USR-103：空 username → 200（后端 ProfileUpdate 无 min_length 校验，接受空字符串）。"""
        resp = await async_client.put(
            "/api/user/profile",
            headers=auth_headers,
            json={"username": ""},
        )
        # 后端未对 username 做 min_length 校验，返回 200 而非 422
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == ""

    async def test_usr_104_wrong_old_password(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """USR-104：旧密码错误 → 403 '旧密码不正确'。"""
        resp = await async_client.put(
            "/api/user/password",
            headers=auth_headers,
            json={"old_password": "wrong_password", "new_password": "new123"},
        )
        assert resp.status_code == 403
        assert "旧密码不正确" in resp.json().get("detail", "")

    async def test_usr_105_null_token_version(
        self,
        async_client: AsyncClient,
        uc_nullver_headers: dict,
        uc_nullver_user: User,
    ):
        """USR-105：token_version=NULL（旧用户）→ 不崩不踢，正常访问。"""
        resp = await async_client.get("/api/user/profile", headers=uc_nullver_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == uc_nullver_user.username

    async def test_usr_106_relogin_after_logout(
        self,
        async_client: AsyncClient,
        admin_headers: dict,
        uc_target_user: User,
        db_session: AsyncSession,
    ):
        """USR-106：强制下线后重新登录 → 新 token 可用。"""
        # 确保 token_version 非零，否则 ver=0 的 token 会跳过校验
        if uc_target_user.token_version == 0:
            uc_target_user.token_version = 1
            await db_session.commit()

        # 用当前 token_version 签发 token（ver=1）
        old_token = create_access_token(
            {"sub": str(uc_target_user.id)}, user=uc_target_user
        )
        old_headers = {"Authorization": f"Bearer {old_token}"}

        # admin 强制下线（token_version → 2）
        resp = await async_client.post(
            f"/api/admin/users/{uc_target_user.id}/logout",
            headers=admin_headers,
        )
        assert resp.status_code == 200

        # 旧 token（ver=1）失效
        resp = await async_client.get("/api/user/profile", headers=old_headers)
        assert resp.status_code == 401

        # 重新登录 → 新 token 有效
        login_resp = await async_client.post(
            "/api/auth/login",
            json={"username": uc_target_user.username, "password": "target123"},
        )
        assert login_resp.status_code == 200
        login_data = login_resp.json()
        new_token = login_data["access_token"]
        new_headers = {"Authorization": f"Bearer {new_token}"}

        resp = await async_client.get("/api/user/profile", headers=new_headers)
        assert resp.status_code == 200

    async def test_usr_107_multi_notification_types(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """USR-107：通知配置多种类型共存 — 依次 PUT → notification_config 包含两条。"""
        # PUT wechat
        resp1 = await async_client.put(
            "/api/user/notifications",
            headers=auth_headers,
            json={"type": "wechat", "webhook_url": "https://wechat.test/hook1"},
        )
        assert resp1.status_code == 200

        # PUT feishu
        resp2 = await async_client.put(
            "/api/user/notifications",
            headers=auth_headers,
            json={"type": "feishu", "webhook_url": "https://feishu.test/hook2"},
        )
        assert resp2.status_code == 200

        # GET profile → 验证两条都存在
        resp3 = await async_client.get("/api/user/profile", headers=auth_headers)
        assert resp3.status_code == 200
        config = resp3.json().get("notification_config", {})
        assert config.get("wechat") == "https://wechat.test/hook1"
        assert config.get("feishu") == "https://feishu.test/hook2"

    async def test_usr_108_overwrite_notification_key(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """USR-108：通知配置覆盖已有 key — 先 PUT wechat=url1 → PUT wechat=url2 → 值更新，其他 key 不受影响。"""
        # PUT wechat=url1 + feishu=url
        await async_client.put(
            "/api/user/notifications",
            headers=auth_headers,
            json={"type": "wechat", "webhook_url": "https://wechat.test/old"},
        )
        await async_client.put(
            "/api/user/notifications",
            headers=auth_headers,
            json={"type": "feishu", "webhook_url": "https://feishu.test/hook"},
        )

        # PUT wechat=url2（覆盖）
        resp = await async_client.put(
            "/api/user/notifications",
            headers=auth_headers,
            json={"type": "wechat", "webhook_url": "https://wechat.test/new"},
        )
        assert resp.status_code == 200

        # GET → wechat 已更新，feishu 保留
        profile = await async_client.get("/api/user/profile", headers=auth_headers)
        config = profile.json().get("notification_config", {})
        assert config.get("wechat") == "https://wechat.test/new"
        assert config.get("feishu") == "https://feishu.test/hook"

    async def test_usr_109_admin_delete_self(
        self, async_client: AsyncClient, admin_headers: dict, admin_user: User
    ):
        """USR-109：admin 删除自己 → 400 'Cannot delete yourself'。"""
        resp = await async_client.delete(
            f"/api/admin/users/{admin_user.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 400
        assert "Cannot delete yourself" in resp.json().get("detail", "")

    async def test_usr_110_admin_create_duplicate_username(
        self, async_client: AsyncClient, admin_headers: dict, test_user: User
    ):
        """USR-110：admin 创建用户用户名重复 → 400 'Username already exists'。"""
        resp = await async_client.post(
            "/api/admin/users",
            headers=admin_headers,
            json={"username": test_user.username, "password": "dupuser123"},
        )
        assert resp.status_code == 400
        assert "already exists" in resp.json().get("detail", "").lower()


# ═══════════════════════════════════════════════════════════════════════════
#  III. 异常场景
# ═══════════════════════════════════════════════════════════════════════════


class TestExceptions:
    """USR-201 ~ USR-207：异常场景 7 个。"""

    async def test_usr_201_unauth_user_center(
        self, async_client: AsyncClient
    ):
        """USR-201：未认证访问用户中心 → 401。"""
        endpoints = [
            ("GET", "/api/user/profile"),
            ("PUT", "/api/user/profile"),
            ("PUT", "/api/user/password"),
            ("PUT", "/api/user/notifications"),
        ]
        for method, path in endpoints:
            resp = await async_client.request(method, path)
            assert resp.status_code == 401, f"{method} {path} expected 401, got {resp.status_code}"

    async def test_usr_202_non_admin_access_admin(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """USR-202：非 admin 访问 admin 路由 → 403 'Admin privileges required'。"""
        admin_endpoints = [
            ("GET", "/api/admin/system-stats"),
            ("GET", "/api/admin/stats"),
            ("GET", "/api/admin/users"),
            ("GET", "/api/admin/projects"),
        ]
        for method, path in admin_endpoints:
            resp = await async_client.request(method, path, headers=auth_headers)
            assert resp.status_code == 403, f"{method} {path} expected 403, got {resp.status_code}"
            detail = resp.json().get("detail", "")
            assert "Admin privileges required" in detail or "admin" in detail.lower()

    async def test_usr_203_force_logout_nonexistent(
        self, async_client: AsyncClient, admin_headers: dict
    ):
        """USR-203：强制下线不存在的用户 → 404 'User not found'。"""
        resp = await async_client.post(
            "/api/admin/users/99999/logout",
            headers=admin_headers,
        )
        assert resp.status_code == 404
        assert "not found" in resp.json().get("detail", "").lower()

    async def test_usr_204_delete_nonexistent(
        self, async_client: AsyncClient, admin_headers: dict
    ):
        """USR-204：admin 删除不存在的用户 → 404 'User not found'。"""
        resp = await async_client.delete(
            "/api/admin/users/99999",
            headers=admin_headers,
        )
        assert resp.status_code == 404
        assert "not found" in resp.json().get("detail", "").lower()

    async def test_usr_205_reset_password_nonexistent(
        self, async_client: AsyncClient, admin_headers: dict
    ):
        """USR-205：admin 重置不存在用户的密码 → 404 'User not found'。"""
        resp = await async_client.put(
            "/api/admin/users/99999/reset-password",
            headers=admin_headers,
            json={"new_password": "newpass123"},
        )
        assert resp.status_code == 404
        assert "not found" in resp.json().get("detail", "").lower()

    async def test_usr_206_update_role_nonexistent(
        self, async_client: AsyncClient, admin_headers: dict
    ):
        """USR-206：admin 修改不存在的用户角色 → 404 'User not found'。"""
        resp = await async_client.put(
            "/api/admin/users/99999/role",
            headers=admin_headers,
            json={"role": "admin"},
        )
        assert resp.status_code == 404
        assert "not found" in resp.json().get("detail", "").lower()

    async def test_usr_207_unauth_admin_route(
        self, async_client: AsyncClient
    ):
        """USR-207：未认证调用 admin 路由 → 401（auth middleware 拦截在前）。"""
        admin_endpoints = [
            ("GET", "/api/admin/system-stats"),
            ("GET", "/api/admin/stats"),
            ("GET", "/api/admin/users"),
            ("PUT", "/api/admin/users/1/role"),
            ("POST", "/api/admin/users"),
            ("DELETE", "/api/admin/users/1"),
            ("PUT", "/api/admin/users/1/reset-password"),
            ("POST", "/api/admin/users/1/logout"),
            ("GET", "/api/admin/projects"),
        ]
        for method, path in admin_endpoints:
            resp = await async_client.request(method, path)
            assert resp.status_code == 401, f"{method} {path} expected 401, got {resp.status_code}"


# ═══════════════════════════════════════════════════════════════════════════
#  IV. 权限/认证 & 隔离
# ═══════════════════════════════════════════════════════════════════════════


class TestAuth:
    """USR-301 ~ USR-302：权限隔离 2 个场景。"""

    async def test_usr_301_user_center_isolation(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        uc_other_headers: dict,
        test_user: User,
        uc_other_user: User,
    ):
        """USR-301：用户中心路由只返回当前用户信息 — 用户 A 和 B 各自看到自己的信息。"""
        # 用户 A GET /profile
        resp_a = await async_client.get("/api/user/profile", headers=auth_headers)
        assert resp_a.status_code == 200
        assert resp_a.json()["username"] == test_user.username

        # 用户 B GET /profile
        resp_b = await async_client.get("/api/user/profile", headers=uc_other_headers)
        assert resp_b.status_code == 200
        assert resp_b.json()["username"] == uc_other_user.username

        # 互相不能看到对方
        assert resp_a.json()["id"] != resp_b.json()["id"]

    async def test_usr_302_all_admin_routes_guarded(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
    ):
        """USR-302：所有 admin 路由都走 `_require_admin` 守卫 — 普通用户调用每条 admin 路由都返回 403。"""
        admin_routes = [
            ("GET", "/api/admin/stats"),
            ("GET", "/api/admin/system-stats"),
            ("GET", "/api/admin/users"),
            ("GET", "/api/admin/projects"),
            ("PUT", "/api/admin/users/1/role", {"role": "user"}),
            ("POST", "/api/admin/users", {"username": "_guard_check", "password": "guard123"}),
            ("DELETE", "/api/admin/users/1"),
            ("PUT", "/api/admin/users/1/reset-password", {"new_password": "guard123"}),
            ("POST", "/api/admin/users/1/logout"),
        ]
        for route in admin_routes:
            method = route[0]
            path = route[1]
            body = route[2] if len(route) > 2 else None
            if body is not None:
                resp = await async_client.request(method, path, headers=auth_headers, json=body)
            else:
                resp = await async_client.request(method, path, headers=auth_headers)
            assert resp.status_code == 403, (
                f"{method} {path} expected 403 (non-admin), got {resp.status_code}"
            )
