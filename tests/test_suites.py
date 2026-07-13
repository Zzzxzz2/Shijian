"""测试组：测试集管理 — 22 个场景覆盖（验剑策略）。

策略文件：`.omo/tests/test-plan-test-suites.md`
覆盖维度：
  正常路径  9 个（SUITE-001 ~ SUITE-009）
  边界值    7 个（SUITE-101 ~ SUITE-107）
  异常场景  7 个（SUITE-201 ~ SUITE-207）
  权限隔离  3 个（SUITE-301 ~ SUITE-303）
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import create_access_token, hash_password
from models import Project, ProjectMembers, TestCase, TestRun, TestRunCases, TestSuite, TestSuiteCases, User

pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════════════
#  Fixtures — 角色用户 + 项目 + 测试用例
# ═══════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def suite_owner(db_session) -> User:
    """Owner 用户：项目的拥有者（Project.user_id 指向此用户）。"""
    await db_session.execute(sa_delete(User).where(User.username == "suite_owner"))
    await db_session.commit()
    user = User(username="suite_owner", password_hash=hash_password("pass123"), role="user")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def suite_editor(db_session) -> User:
    """Editor 用户：项目的成员（ProjectMembers role=editor）。"""
    await db_session.execute(sa_delete(User).where(User.username == "suite_editor"))
    await db_session.commit()
    user = User(username="suite_editor", password_hash=hash_password("pass123"), role="user")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def suite_viewer(db_session) -> User:
    """Viewer 用户：项目的成员（ProjectMembers role=viewer）。"""
    await db_session.execute(sa_delete(User).where(User.username == "suite_viewer"))
    await db_session.commit()
    user = User(username="suite_viewer", password_hash=hash_password("pass123"), role="user")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def suite_stranger(db_session) -> User:
    """Stranger 用户：普通用户，与测试项目无关。"""
    await db_session.execute(sa_delete(User).where(User.username == "suite_stranger"))
    await db_session.commit()
    user = User(username="suite_stranger", password_hash=hash_password("pass123"), role="user")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def suite_project(db_session, suite_owner: User, suite_editor: User, suite_viewer: User) -> Project:
    """由 suite_owner 拥有的项目。"""
    proj = Project(
        name="Suite Test Project",
        description="Project for suite management tests",
        user_id=suite_owner.id,
    )
    db_session.add(proj)
    await db_session.commit()
    await db_session.refresh(proj)

    # 创建成员关系
    await db_session.execute(
        sa_delete(ProjectMembers).where(
            ProjectMembers.project_id == proj.id,
            ProjectMembers.user_id == suite_owner.id,
        )
    )
    db_session.add(ProjectMembers(project_id=proj.id, user_id=suite_owner.id, role="owner"))
    db_session.add(ProjectMembers(project_id=proj.id, user_id=suite_editor.id, role="editor"))
    db_session.add(ProjectMembers(project_id=proj.id, user_id=suite_viewer.id, role="viewer"))
    await db_session.commit()

    return proj


@pytest_asyncio.fixture
async def suite_cases(db_session, suite_project: Project) -> list[TestCase]:
    """属于 suite_project 的 3 条测试用例。"""
    cases = []
    for i in range(1, 4):
        tc = TestCase(
            project_id=suite_project.id,
            name=f"Suite Case {i}",
            test_type="api",
            content={"method": "GET", "url": f"/api/test/{i}"},
            source="manual",
        )
        db_session.add(tc)
        cases.append(tc)
    await db_session.commit()
    for tc in cases:
        await db_session.refresh(tc)
    return cases


# ── Tokens & Headers ────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def owner_token(suite_owner: User) -> str:
    return create_access_token({"sub": str(suite_owner.id)}, user=suite_owner)


@pytest_asyncio.fixture
async def owner_headers(owner_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {owner_token}"}


@pytest_asyncio.fixture
async def editor_token(suite_editor: User) -> str:
    return create_access_token({"sub": str(suite_editor.id)}, user=suite_editor)


@pytest_asyncio.fixture
async def editor_headers(editor_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {editor_token}"}


@pytest_asyncio.fixture
async def viewer_token(suite_viewer: User) -> str:
    return create_access_token({"sub": str(suite_viewer.id)}, user=suite_viewer)


@pytest_asyncio.fixture
async def viewer_headers(viewer_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {viewer_token}"}


@pytest_asyncio.fixture
async def stranger_token(suite_stranger: User) -> str:
    return create_access_token({"sub": str(suite_stranger.id)}, user=suite_stranger)


@pytest_asyncio.fixture
async def stranger_headers(stranger_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {stranger_token}"}


# ═══════════════════════════════════════════════════════════════════════════
#  I. 正常路径（Happy Path）
# ═══════════════════════════════════════════════════════════════════════════


class TestHappyPath:
    """SUITE-001 ~ SUITE-009：正常路径 9 个场景。"""

    async def test_suite_001_viewer_list_suites(
        self,
        async_client: AsyncClient,
        viewer_headers: dict,
        suite_project: Project,
        suite_cases: list[TestCase],
        db_session: AsyncSession,
    ):
        """SUITE-001：Viewer 获取测试集列表 — GET /api/projects/{pid}/suites → 200。"""
        # 先创建一条 suite 确保列表非空
        suite = TestSuite(project_id=suite_project.id, name="List Test Suite")
        db_session.add(suite)
        await db_session.commit()

        resp = await async_client.get(
            f"/api/projects/{suite_project.id}/suites",
            headers=viewer_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        item = data[0]
        assert "id" in item
        assert "name" in item
        assert "description" in item
        assert "case_count" in item
        assert isinstance(item["case_count"], int)
        assert "created_at" in item

    async def test_suite_002_viewer_get_detail(
        self,
        async_client: AsyncClient,
        viewer_headers: dict,
        suite_project: Project,
        suite_cases: list[TestCase],
        db_session: AsyncSession,
    ):
        """SUITE-002：Viewer 获取测试集详情 — GET /api/projects/{pid}/suites/{sid} → 200。"""
        suite = TestSuite(project_id=suite_project.id, name="Detail Test Suite")
        db_session.add(suite)
        await db_session.flush()

        # 添加 2 条用例
        db_session.add(TestSuiteCases(suite_id=suite.id, case_id=suite_cases[0].id, sort_order=1))
        db_session.add(TestSuiteCases(suite_id=suite.id, case_id=suite_cases[1].id, sort_order=0))
        await db_session.commit()

        resp = await async_client.get(
            f"/api/projects/{suite_project.id}/suites/{suite.id}",
            headers=viewer_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == suite.id
        assert data["name"] == "Detail Test Suite"
        assert "cases" in data
        assert len(data["cases"]) == 2

    async def test_suite_003_editor_create_with_cases(
        self,
        async_client: AsyncClient,
        editor_headers: dict,
        suite_project: Project,
        suite_cases: list[TestCase],
    ):
        """SUITE-003：Editor 创建测试集（含用例）— POST /api/projects/{pid}/suites → 201，case_count=3。"""
        case_ids = [c.id for c in suite_cases]
        resp = await async_client.post(
            f"/api/projects/{suite_project.id}/suites",
            headers=editor_headers,
            json={"name": "Suite With Cases", "description": "has 3 cases", "case_ids": case_ids},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Suite With Cases"
        assert data["case_count"] == 3
        assert data["description"] == "has 3 cases"

    async def test_suite_004_editor_create_empty(
        self,
        async_client: AsyncClient,
        editor_headers: dict,
        suite_project: Project,
    ):
        """SUITE-004：Editor 创建空测试集 — POST /api/projects/{pid}/suites → 201，case_count=0。"""
        resp = await async_client.post(
            f"/api/projects/{suite_project.id}/suites",
            headers=editor_headers,
            json={"name": "Empty Suite", "case_ids": []},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Empty Suite"
        assert data["case_count"] == 0

    async def test_suite_005_editor_update_name(
        self,
        async_client: AsyncClient,
        editor_headers: dict,
        suite_project: Project,
        suite_cases: list[TestCase],
        db_session: AsyncSession,
    ):
        """SUITE-005：Editor 更新测试集名称和描述 — PUT /api/projects/{pid}/suites/{sid} → 200。"""
        suite = TestSuite(project_id=suite_project.id, name="Old Name")
        db_session.add(suite)
        await db_session.commit()

        resp = await async_client.put(
            f"/api/projects/{suite_project.id}/suites/{suite.id}",
            headers=editor_headers,
            json={"name": "New Name", "description": "Updated desc"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Name"
        assert data["description"] == "Updated desc"

    async def test_suite_006_editor_replace_cases(
        self,
        async_client: AsyncClient,
        editor_headers: dict,
        suite_project: Project,
        suite_cases: list[TestCase],
        db_session: AsyncSession,
    ):
        """SUITE-006：Editor 全量替换测试集用例 — PUT 后旧用例移除，case_count=2。"""
        suite = TestSuite(project_id=suite_project.id, name="Replace Cases")
        db_session.add(suite)
        await db_session.flush()

        # 原有 3 条用例
        for idx, c in enumerate(suite_cases):
            db_session.add(TestSuiteCases(suite_id=suite.id, case_id=c.id, sort_order=idx))
        await db_session.commit()

        # 全量替换为前 2 条
        new_ids = [suite_cases[0].id, suite_cases[1].id]
        resp = await async_client.put(
            f"/api/projects/{suite_project.id}/suites/{suite.id}",
            headers=editor_headers,
            json={"case_ids": new_ids},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["case_count"] == 2

    async def test_suite_007_editor_delete_suite(
        self,
        async_client: AsyncClient,
        editor_headers: dict,
        suite_project: Project,
        db_session: AsyncSession,
    ):
        """SUITE-007：Editor 删除测试集 — DELETE → 204，再次 GET 返回 404。"""
        suite = TestSuite(project_id=suite_project.id, name="To Delete")
        db_session.add(suite)
        await db_session.commit()

        resp = await async_client.delete(
            f"/api/projects/{suite_project.id}/suites/{suite.id}",
            headers=editor_headers,
        )
        assert resp.status_code == 204

        # 再次 GET 返回 404
        resp2 = await async_client.get(
            f"/api/projects/{suite_project.id}/suites/{suite.id}",
            headers=editor_headers,
        )
        assert resp2.status_code == 404

    async def test_suite_008_one_click_run(
        self,
        async_client: AsyncClient,
        editor_headers: dict,
        suite_project: Project,
        suite_cases: list[TestCase],
        db_session: AsyncSession,
    ):
        """SUITE-008：一键执行测试集 — POST /{sid}/run → 200，返回 run_id，TestRun 已创建。"""
        suite = TestSuite(project_id=suite_project.id, name="Run Suite")
        db_session.add(suite)
        await db_session.flush()
        for idx, c in enumerate(suite_cases):
            db_session.add(TestSuiteCases(suite_id=suite.id, case_id=c.id, sort_order=idx))
        await db_session.commit()

        resp = await async_client.post(
            f"/api/projects/{suite_project.id}/suites/{suite.id}/run",
            headers=editor_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        run_id = data["run_id"]

        # 验证 TestRun
        run = await db_session.get(TestRun, run_id)
        assert run is not None
        assert run.project_id == suite_project.id
        assert run.status == "pending"

        # 验证 TestRunCases 包含 3 条记录
        count = (
            await db_session.execute(
                select(TestRunCases).where(TestRunCases.run_id == run_id)
            )
        ).scalars().all()
        assert len(count) == 3

    async def test_suite_009_execute_run_completes(
        self,
        async_client: AsyncClient,
        editor_headers: dict,
        suite_project: Project,
        suite_cases: list[TestCase],
        db_session: AsyncSession,
    ):
        """SUITE-009：测试集执行后 execute_run 正常启动 — 等待后台任务完成，status 不再 pending。"""
        import asyncio

        suite = TestSuite(project_id=suite_project.id, name="Execute Suite")
        db_session.add(suite)
        await db_session.flush()
        for idx, c in enumerate(suite_cases):
            db_session.add(TestSuiteCases(suite_id=suite.id, case_id=c.id, sort_order=idx))
        await db_session.commit()

        resp = await async_client.post(
            f"/api/projects/{suite_project.id}/suites/{suite.id}/run",
            headers=editor_headers,
        )
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]

        # 等待后台 execute_run 完成（asyncio 任务共享事件循环）
        for _ in range(20):
            await asyncio.sleep(0.5)
            run = await db_session.get(TestRun, run_id)
            if run and run.status != "pending":
                break

        await db_session.refresh(run)
        # execute_run 应当改变 status（即使执行失败也是 "done"/"error"，而非 pending）
        assert run.status != "pending", "execute_run 未能在超时内完成"


# ═══════════════════════════════════════════════════════════════════════════
#  II. 边界值
# ═══════════════════════════════════════════════════════════════════════════


class TestBoundary:
    """SUITE-101 ~ SUITE-107：边界值 7 个场景。"""

    async def test_suite_101_empty_name(
        self,
        async_client: AsyncClient,
        editor_headers: dict,
        suite_project: Project,
    ):
        """SUITE-101：空名称创建测试集 → 422 校验错误。"""
        resp = await async_client.post(
            f"/api/projects/{suite_project.id}/suites",
            headers=editor_headers,
            json={"name": ""},
        )
        assert resp.status_code == 422

    async def test_suite_102_name_too_long(
        self,
        async_client: AsyncClient,
        editor_headers: dict,
        suite_project: Project,
    ):
        """SUITE-102：名称超长（201 字符）→ 422。"""
        resp = await async_client.post(
            f"/api/projects/{suite_project.id}/suites",
            headers=editor_headers,
            json={"name": "a" * 201},
        )
        assert resp.status_code == 422

    async def test_suite_103_large_case_set(
        self,
        async_client: AsyncClient,
        editor_headers: dict,
        suite_project: Project,
        db_session: AsyncSession,
    ):
        """SUITE-103：大量用例（50+）的测试集 → 201，case_count=50。"""
        # 创建 50 条测试用例
        case_ids = []
        for i in range(50):
            tc = TestCase(
                project_id=suite_project.id,
                name=f"Bulk Case {i}",
                test_type="api",
                content={"method": "GET", "url": f"/api/bulk/{i}"},
            )
            db_session.add(tc)
        await db_session.commit()

        # 重新查询获取 id
        all_cases = (
            await db_session.execute(
                select(TestCase).where(TestCase.project_id == suite_project.id)
                .order_by(TestCase.id.desc())
                .limit(50)
            )
        ).scalars().all()
        case_ids = [c.id for c in reversed(all_cases)]

        resp = await async_client.post(
            f"/api/projects/{suite_project.id}/suites",
            headers=editor_headers,
            json={"name": "Bulk Suite", "case_ids": case_ids},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["case_count"] == 50

    async def test_suite_104_empty_suite_run(
        self,
        async_client: AsyncClient,
        editor_headers: dict,
        suite_project: Project,
        db_session: AsyncSession,
    ):
        """SUITE-104：空测试集一键执行 → 400 'Suite is empty'。"""
        suite = TestSuite(project_id=suite_project.id, name="Empty Suite")
        db_session.add(suite)
        await db_session.commit()

        resp = await async_client.post(
            f"/api/projects/{suite_project.id}/suites/{suite.id}/run",
            headers=editor_headers,
        )
        assert resp.status_code == 400
        data = resp.json()
        assert "empty" in data.get("detail", "").lower()

    async def test_suite_105_nonexistent_suite(
        self,
        async_client: AsyncClient,
        editor_headers: dict,
        suite_project: Project,
    ):
        """SUITE-105：不存在的 suite → 404。"""
        # GET
        resp = await async_client.get(
            f"/api/projects/{suite_project.id}/suites/99999",
            headers=editor_headers,
        )
        assert resp.status_code == 404

        # PUT
        resp = await async_client.put(
            f"/api/projects/{suite_project.id}/suites/99999",
            headers=editor_headers,
            json={"name": "noop"},
        )
        assert resp.status_code == 404

        # DELETE
        resp = await async_client.delete(
            f"/api/projects/{suite_project.id}/suites/99999",
            headers=editor_headers,
        )
        assert resp.status_code == 404

    async def test_suite_106_cross_project_access(
        self,
        async_client: AsyncClient,
        viewer_headers: dict,
        suite_project: Project,
        db_session: AsyncSession,
        suite_editor: User,
    ):
        """SUITE-106：跨项目访问 suite → 404（suite 不属于该项目）。"""
        # 另一个项目
        other_proj = Project(name="Other Project", user_id=suite_editor.id)
        db_session.add(other_proj)
        await db_session.commit()
        await db_session.refresh(other_proj)
        db_session.add(ProjectMembers(project_id=other_proj.id, user_id=suite_editor.id, role="owner"))
        await db_session.commit()

        # suite 属于 other_proj
        suite = TestSuite(project_id=other_proj.id, name="Other Suite")
        db_session.add(suite)
        await db_session.commit()

        # 用 suite_project 的 viewer 访问 other_project 的 suite（viewer 不能访问 other_proj → 403 先于 404）
        # 改用 editor 访问，但指向错误的 project_id
        # suite_project 的 viewer/editor 能访问 suite_project，但 suite 实际属于 other_proj
        # 需要 suite_project 的成员访问 suite_project 下不存在的 suite_id → 实际场景是 cross-project
        # 更准确的测试：用 suite_project 的 editor 访问 other_proj 的 suite
        editor_token_2 = create_access_token(
            {"sub": str(suite_editor.id)}, user=suite_editor
        )
        editor2_headers = {"Authorization": f"Bearer {editor_token_2}"}

        # 对 suite_project 的成员来说，在 suite_project 下访问 suite 99999（不存在的）→ 404
        resp = await async_client.get(
            f"/api/projects/{suite_project.id}/suites/{suite.id}",
            headers=editor2_headers,
        )
        # suite.id = N, suite_project.id = M, suite.project_id (=M_other) != M
        # 后端判断：if not suite or suite.project_id != pid → 404
        assert resp.status_code == 404

    async def test_suite_107_duplicate_case_ids(
        self,
        async_client: AsyncClient,
        editor_headers: dict,
        suite_project: Project,
        suite_cases: list[TestCase],
    ):
        """SUITE-107：重复 case_id 创建 → 201，case_count=3（无 UniqueConstraint，允许重复）。"""
        case_ids = [suite_cases[0].id, suite_cases[0].id, suite_cases[1].id]
        resp = await async_client.post(
            f"/api/projects/{suite_project.id}/suites",
            headers=editor_headers,
            json={"name": "Dup Suite", "case_ids": case_ids},
        )
        assert resp.status_code == 201
        data = resp.json()
        # 注意：策略说明允许重复，后端返回的 case_count 是 len(case_ids) = 3
        assert data["case_count"] == 3


# ═══════════════════════════════════════════════════════════════════════════
#  III. 异常场景
# ═══════════════════════════════════════════════════════════════════════════


class TestExceptions:
    """SUITE-201 ~ SUITE-207：异常场景 7 个。"""

    async def test_suite_201_unauth_access(
        self,
        async_client: AsyncClient,
        suite_project: Project,
    ):
        """SUITE-201：未认证访问 → 401。"""
        endpoints = [
            ("GET", f"/api/projects/{suite_project.id}/suites"),
            ("POST", f"/api/projects/{suite_project.id}/suites"),
        ]
        for method, path in endpoints:
            resp = await async_client.request(method, path)
            assert resp.status_code == 401, f"{method} {path} expected 401, got {resp.status_code}"

    async def test_suite_202_viewer_write_403(
        self,
        async_client: AsyncClient,
        viewer_headers: dict,
        suite_project: Project,
    ):
        """SUITE-202：Viewer 写操作 → 403 '权限不足'。"""
        endpoints = [
            ("POST", f"/api/projects/{suite_project.id}/suites", {"name": "nope", "case_ids": []}),
            ("PUT", f"/api/projects/{suite_project.id}/suites/1", {"name": "nope"}),
            ("DELETE", f"/api/projects/{suite_project.id}/suites/1"),
        ]
        for method, path, *body in endpoints:
            kwargs = {"headers": viewer_headers}
            if body:
                kwargs["json"] = body[0]
            resp = await async_client.request(method, path, **kwargs)
            assert resp.status_code == 403, f"{method} {path} expected 403, got {resp.status_code}"

    async def test_suite_203_non_member_403(
        self,
        async_client: AsyncClient,
        stranger_headers: dict,
        suite_project: Project,
    ):
        """SUITE-203：非项目成员访问 → 403 '你不是该项目的成员'。"""
        resp = await async_client.get(
            f"/api/projects/{suite_project.id}/suites",
            headers=stranger_headers,
        )
        assert resp.status_code == 403

    async def test_suite_204_nonexistent_project(
        self,
        async_client: AsyncClient,
        viewer_headers: dict,
    ):
        """SUITE-204：不存在项目 → 404。"""
        resp = await async_client.get(
            "/api/projects/99999/suites",
            headers=viewer_headers,
        )
        assert resp.status_code == 404

    async def test_suite_205_delete_nonexistent_suite(
        self,
        async_client: AsyncClient,
        editor_headers: dict,
        suite_project: Project,
    ):
        """SUITE-205：删除不存在的 suite → 404。"""
        resp = await async_client.delete(
            f"/api/projects/{suite_project.id}/suites/99999",
            headers=editor_headers,
        )
        assert resp.status_code == 404

    async def test_suite_206_update_nonexistent_suite(
        self,
        async_client: AsyncClient,
        editor_headers: dict,
        suite_project: Project,
    ):
        """SUITE-206：更新不存在的 suite → 404。"""
        resp = await async_client.put(
            f"/api/projects/{suite_project.id}/suites/99999",
            headers=editor_headers,
            json={"name": "noop"},
        )
        assert resp.status_code == 404

    async def test_suite_207_run_deleted_suite(
        self,
        async_client: AsyncClient,
        editor_headers: dict,
        suite_project: Project,
        db_session: AsyncSession,
    ):
        """SUITE-207：重复执行已删除测试集 → 404。"""
        suite = TestSuite(project_id=suite_project.id, name="Gone Suite")
        db_session.add(suite)
        await db_session.commit()
        sid = suite.id

        # 删除
        await async_client.delete(
            f"/api/projects/{suite_project.id}/suites/{sid}",
            headers=editor_headers,
        )

        # 再次运行 → 404
        resp = await async_client.post(
            f"/api/projects/{suite_project.id}/suites/{sid}/run",
            headers=editor_headers,
        )
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
#  IV. 权限/认证
# ═══════════════════════════════════════════════════════════════════════════


class TestAuth:
    """SUITE-301 ~ SUITE-303：权限隔离 3 个场景。"""

    async def test_suite_301_viewer_readonly_editor_rw(
        self,
        async_client: AsyncClient,
        viewer_headers: dict,
        editor_headers: dict,
        suite_project: Project,
        suite_cases: list[TestCase],
    ):
        """SUITE-301：Viewer 只读，Editor 可写。"""
        # Viewer 读：列表 → 200
        r1 = await async_client.get(
            f"/api/projects/{suite_project.id}/suites",
            headers=viewer_headers,
        )
        assert r1.status_code == 200

        # Viewer 写：创建 → 403
        r2 = await async_client.post(
            f"/api/projects/{suite_project.id}/suites",
            headers=viewer_headers,
            json={"name": "viewer try", "case_ids": []},
        )
        assert r2.status_code == 403

        # Editor 写：创建 → 201
        r3 = await async_client.post(
            f"/api/projects/{suite_project.id}/suites",
            headers=editor_headers,
            json={"name": "editor create", "case_ids": [suite_cases[0].id]},
        )
        assert r3.status_code == 201

    async def test_suite_302_admin_bypass(
        self,
        async_client: AsyncClient,
        admin_headers: dict,
        suite_project: Project,
        suite_cases: list[TestCase],
        db_session: AsyncSession,
    ):
        """SUITE-302：Admin bypass — admin 对任意项目 CRUD + 执行无限制。"""
        # Create
        r1 = await async_client.post(
            f"/api/projects/{suite_project.id}/suites",
            headers=admin_headers,
            json={"name": "Admin Suite", "case_ids": [suite_cases[0].id]},
        )
        assert r1.status_code == 201
        sid = r1.json()["id"]

        # Read
        r2 = await async_client.get(
            f"/api/projects/{suite_project.id}/suites",
            headers=admin_headers,
        )
        assert r2.status_code == 200

        # Detail
        r3 = await async_client.get(
            f"/api/projects/{suite_project.id}/suites/{sid}",
            headers=admin_headers,
        )
        assert r3.status_code == 200

        # Update
        r4 = await async_client.put(
            f"/api/projects/{suite_project.id}/suites/{sid}",
            headers=admin_headers,
            json={"name": "Admin Updated"},
        )
        assert r4.status_code == 200

        # Run
        r5 = await async_client.post(
            f"/api/projects/{suite_project.id}/suites/{sid}/run",
            headers=admin_headers,
        )
        assert r5.status_code == 200

        # Delete
        r6 = await async_client.delete(
            f"/api/projects/{suite_project.id}/suites/{sid}",
            headers=admin_headers,
        )
        assert r6.status_code == 204

    async def test_suite_303_owner_full_access(
        self,
        async_client: AsyncClient,
        owner_headers: dict,
        suite_project: Project,
        suite_cases: list[TestCase],
        db_session: AsyncSession,
    ):
        """SUITE-303：Owner 完整权限 — owner 执行全部 CRUD + 一键执行。"""
        # Create
        r1 = await async_client.post(
            f"/api/projects/{suite_project.id}/suites",
            headers=owner_headers,
            json={"name": "Owner Suite", "case_ids": [suite_cases[0].id]},
        )
        assert r1.status_code == 201
        sid = r1.json()["id"]

        # Read
        r2 = await async_client.get(
            f"/api/projects/{suite_project.id}/suites",
            headers=owner_headers,
        )
        assert r2.status_code == 200

        # Detail
        r3 = await async_client.get(
            f"/api/projects/{suite_project.id}/suites/{sid}",
            headers=owner_headers,
        )
        assert r3.status_code == 200

        # Update
        r4 = await async_client.put(
            f"/api/projects/{suite_project.id}/suites/{sid}",
            headers=owner_headers,
            json={"name": "Owner Updated"},
        )
        assert r4.status_code == 200

        # Run
        r5 = await async_client.post(
            f"/api/projects/{suite_project.id}/suites/{sid}/run",
            headers=owner_headers,
        )
        assert r5.status_code == 200

        # Delete
        r6 = await async_client.delete(
            f"/api/projects/{suite_project.id}/suites/{sid}",
            headers=owner_headers,
        )
        assert r6.status_code == 204
