"""测试组：定时执行 — 34 个场景覆盖（验剑策略）。

策略文件：`.omo/tests/test-plan-scheduled-execution.md`
覆盖维度：
  正常路径 13 个（SCHED-001 ~ SCHED-013）
  边界值    7 个（SCHED-101 ~ SCHED-107）
  异常场景  6 个（SCHED-201 ~ SCHED-206）
  权限隔离  3 个（SCHED-301 ~ SCHED-303）
  生命周期  5 个（SCHED-401 ~ SCHED-405）

核心策略：
  - APScheduler job 注册/移除通过 scheduler.get_job() 直接断言
  - 自动触发路径通过直接调用 _execute_schedule(sid) 验证
  - 不依赖真实 cron 等待
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import create_access_token, hash_password
from models import Project, ProjectMembers, Schedule, TestCase, TestRun, TestRunCases, TestSuite, TestSuiteCases, User
from services.scheduler import add_job, remove_job, scheduler as global_scheduler, _execute_schedule

pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════════════
#  Fixtures — 角色用户 + 项目 + 测试用例 + 测试集
# ═══════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def sched_owner(db_session) -> User:
    await db_session.execute(sa_delete(User).where(User.username == "sched_owner"))
    await db_session.commit()
    user = User(username="sched_owner", password_hash=hash_password("pass123"), role="user")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def sched_editor(db_session) -> User:
    await db_session.execute(sa_delete(User).where(User.username == "sched_editor"))
    await db_session.commit()
    user = User(username="sched_editor", password_hash=hash_password("pass123"), role="user")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def sched_viewer(db_session) -> User:
    await db_session.execute(sa_delete(User).where(User.username == "sched_viewer"))
    await db_session.commit()
    user = User(username="sched_viewer", password_hash=hash_password("pass123"), role="user")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def sched_stranger(db_session) -> User:
    await db_session.execute(sa_delete(User).where(User.username == "sched_stranger"))
    await db_session.commit()
    user = User(username="sched_stranger", password_hash=hash_password("pass123"), role="user")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def sched_project(
    db_session, sched_owner: User, sched_editor: User, sched_viewer: User
) -> Project:
    proj = Project(name="Sched Test Project", user_id=sched_owner.id)
    db_session.add(proj)
    await db_session.commit()
    await db_session.refresh(proj)

    db_session.add(ProjectMembers(project_id=proj.id, user_id=sched_owner.id, role="owner"))
    db_session.add(ProjectMembers(project_id=proj.id, user_id=sched_editor.id, role="editor"))
    db_session.add(ProjectMembers(project_id=proj.id, user_id=sched_viewer.id, role="viewer"))
    await db_session.commit()
    return proj


@pytest_asyncio.fixture
async def sched_cases(db_session, sched_project: Project) -> list[TestCase]:
    cases = []
    for i in range(1, 5):
        tc = TestCase(
            project_id=sched_project.id,
            name=f"Sched Case {i}",
            test_type="api",
            content={"method": "GET", "url": f"/api/sched/{i}"},
        )
        db_session.add(tc)
        cases.append(tc)
    await db_session.commit()
    for tc in cases:
        await db_session.refresh(tc)
    return cases


@pytest_asyncio.fixture
async def sched_suite(db_session, sched_project: Project, sched_cases: list[TestCase]) -> TestSuite:
    """含 3 条用例的测试集。"""
    suite = TestSuite(project_id=sched_project.id, name="Sched Suite")
    db_session.add(suite)
    await db_session.flush()
    for idx, c in enumerate(sched_cases[:3]):
        db_session.add(TestSuiteCases(suite_id=suite.id, case_id=c.id, sort_order=idx))
    await db_session.commit()
    await db_session.refresh(suite)
    return suite


# ── Tokens & Headers ────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def owner_token(sched_owner: User) -> str:
    return create_access_token({"sub": str(sched_owner.id)}, user=sched_owner)


@pytest_asyncio.fixture
async def owner_headers(owner_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {owner_token}"}


@pytest_asyncio.fixture
async def editor_token(sched_editor: User) -> str:
    return create_access_token({"sub": str(sched_editor.id)}, user=sched_editor)


@pytest_asyncio.fixture
async def editor_headers(editor_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {editor_token}"}


@pytest_asyncio.fixture
async def viewer_token(sched_viewer: User) -> str:
    return create_access_token({"sub": str(sched_viewer.id)}, user=sched_viewer)


@pytest_asyncio.fixture
async def viewer_headers(viewer_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {viewer_token}"}


@pytest_asyncio.fixture
async def stranger_token(sched_stranger: User) -> str:
    return create_access_token({"sub": str(sched_stranger.id)}, user=sched_stranger)


@pytest_asyncio.fixture
async def stranger_headers(stranger_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {stranger_token}"}


# ═══════════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════════


def job_id(sid: int) -> str:
    return f"schedule_{sid}"


def assert_job_exists(sid: int, exists: bool = True):
    """断言 APScheduler job 存在/不存在。"""
    job = global_scheduler.get_job(job_id(sid))
    if exists:
        assert job is not None, f"Expected job {job_id(sid)} to exist"
    else:
        assert job is None, f"Expected job {job_id(sid)} to NOT exist"


# ═══════════════════════════════════════════════════════════════════════════
#  I. 正常路径（Happy Path）
# ═══════════════════════════════════════════════════════════════════════════


class TestHappyPath:
    """SCHED-001 ~ SCHED-013：正常路径 13 个场景。"""

    async def test_sched_001_viewer_list(
        self, async_client: AsyncClient, viewer_headers: dict, sched_project: Project, db_session: AsyncSession
    ):
        """SCHED-001：Viewer 获取定时任务列表 — GET → 200，返回 id/cron_expr/enabled/suite_id 等字段。"""
        s = Schedule(project_id=sched_project.id, cron_expr="0 2 * * *")
        db_session.add(s)
        await db_session.commit()

        resp = await async_client.get(
            f"/api/projects/{sched_project.id}/schedules", headers=viewer_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        item = data[0]
        assert "id" in item
        assert "cron_expr" in item
        assert "enabled" in item
        assert "suite_id" in item
        assert "case_ids" in item
        assert "last_run_at" in item
        assert "created_at" in item

    async def test_sched_002_create_with_suite(
        self, async_client: AsyncClient, editor_headers: dict, sched_project: Project, sched_suite: TestSuite
    ):
        """SCHED-002：Editor 创建定时任务（关联测试集）— POST → 201，enabled=true，APScheduler job 注册。"""
        resp = await async_client.post(
            f"/api/projects/{sched_project.id}/schedules",
            headers=editor_headers,
            json={"suite_id": sched_suite.id, "cron_expr": "0 2 * * *"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["enabled"] is True
        assert data["suite_id"] == sched_suite.id
        assert data["cron_expr"] == "0 2 * * *"

        # APScheduler job 已注册
        assert_job_exists(data["id"], exists=True)

    async def test_sched_003_create_with_cases(
        self, async_client: AsyncClient, editor_headers: dict, sched_project: Project, sched_cases: list[TestCase]
    ):
        """SCHED-003：Editor 创建定时任务（直接指定用例）— POST → 201，case_ids 匹配。"""
        case_ids = [c.id for c in sched_cases[:3]]
        resp = await async_client.post(
            f"/api/projects/{sched_project.id}/schedules",
            headers=editor_headers,
            json={"case_ids": case_ids, "cron_expr": "30 9 * * 1-5"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["case_ids"] == case_ids
        assert_job_exists(data["id"], exists=True)

    async def test_sched_004_create_disabled(
        self, async_client: AsyncClient, editor_headers: dict, sched_project: Project
    ):
        """SCHED-004：Editor 创建禁用定时任务 — POST → 201，enabled=false，APScheduler job 不注册。"""
        resp = await async_client.post(
            f"/api/projects/{sched_project.id}/schedules",
            headers=editor_headers,
            json={"cron_expr": "0 2 * * *", "enabled": False},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["enabled"] is False
        assert_job_exists(data["id"], exists=False)

    async def test_sched_005_update_cron(
        self, async_client: AsyncClient, editor_headers: dict, sched_project: Project, db_session: AsyncSession
    ):
        """SCHED-005：Editor 更新定时任务（修改 cron 表达式）— PUT → 200，cron_expr 更新，job 重新注册。"""
        s = Schedule(project_id=sched_project.id, cron_expr="0 2 * * *", enabled=True)
        db_session.add(s)
        await db_session.commit()
        await db_session.refresh(s)

        # 手动注册 APScheduler job（直接 DB 创建绕过 API endpoint）
        add_job(s.id, s.cron_expr)
        assert_job_exists(s.id, exists=True)

        resp = await async_client.put(
            f"/api/projects/{sched_project.id}/schedules/{s.id}",
            headers=editor_headers,
            json={"cron_expr": "0 3 * * *"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["cron_expr"] == "0 3 * * *"

        # job 仍然存在（重新注册）
        assert_job_exists(s.id, exists=True)

    async def test_sched_006_disable_to_enable(
        self, async_client: AsyncClient, editor_headers: dict, sched_project: Project, db_session: AsyncSession
    ):
        """SCHED-006：Editor 更新（禁用 → 启用）— PUT → 200，APScheduler job 注册。"""
        s = Schedule(project_id=sched_project.id, cron_expr="0 2 * * *", enabled=False)
        db_session.add(s)
        await db_session.commit()

        # 确认 job 不存在
        assert_job_exists(s.id, exists=False)

        resp = await async_client.put(
            f"/api/projects/{sched_project.id}/schedules/{s.id}",
            headers=editor_headers,
            json={"enabled": True},
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True
        assert_job_exists(s.id, exists=True)

    async def test_sched_007_enable_to_disable(
        self, async_client: AsyncClient, editor_headers: dict, sched_project: Project, db_session: AsyncSession
    ):
        """SCHED-007：Editor 更新（启用 → 禁用）— PUT → 200，APScheduler job 移除。"""
        s = Schedule(project_id=sched_project.id, cron_expr="0 2 * * *", enabled=True)
        db_session.add(s)
        await db_session.commit()

        # 手动注册 APScheduler job（直接 DB 创建绕过 API endpoint）
        add_job(s.id, s.cron_expr)
        assert_job_exists(s.id, exists=True)

        resp = await async_client.put(
            f"/api/projects/{sched_project.id}/schedules/{s.id}",
            headers=editor_headers,
            json={"enabled": False},
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False
        assert_job_exists(s.id, exists=False)

    async def test_sched_008_delete(
        self, async_client: AsyncClient, editor_headers: dict, sched_project: Project, db_session: AsyncSession
    ):
        """SCHED-008：Editor 删除定时任务 — DELETE → 204，APScheduler job 移除，GET → 404。"""
        s = Schedule(project_id=sched_project.id, cron_expr="0 2 * * *", enabled=True)
        db_session.add(s)
        await db_session.commit()

        # 手动注册 APScheduler job（直接 DB 创建绕过 API endpoint）
        add_job(s.id, s.cron_expr)
        assert_job_exists(s.id, exists=True)

        resp = await async_client.delete(
            f"/api/projects/{sched_project.id}/schedules/{s.id}",
            headers=editor_headers,
        )
        assert resp.status_code == 204
        assert_job_exists(s.id, exists=False)

        # GET → 404
        resp2 = await async_client.delete(
            f"/api/projects/{sched_project.id}/schedules/{s.id}",
            headers=editor_headers,
        )
        assert resp2.status_code == 404

    async def test_sched_009_trigger_with_suite(
        self,
        async_client: AsyncClient,
        editor_headers: dict,
        sched_project: Project,
        sched_suite: TestSuite,
        db_session: AsyncSession,
    ):
        """SCHED-009：手动触发（关联测试集）— POST /trigger → 200，返回 run_id，TestRun source='scheduled'。"""
        s = Schedule(project_id=sched_project.id, suite_id=sched_suite.id, cron_expr="0 2 * * *")
        db_session.add(s)
        await db_session.commit()

        resp = await async_client.post(
            f"/api/projects/{sched_project.id}/schedules/{s.id}/trigger",
            headers=editor_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        run_id = data["run_id"]

        run = await db_session.get(TestRun, run_id)
        assert run is not None
        assert run.source == "scheduled"

    async def test_sched_010_trigger_with_cases(
        self,
        async_client: AsyncClient,
        editor_headers: dict,
        sched_project: Project,
        sched_cases: list[TestCase],
        db_session: AsyncSession,
    ):
        """SCHED-010：手动触发（指定用例列表）— POST /trigger → 200，TestRunCases 包含所有指定用例。"""
        case_ids = [c.id for c in sched_cases[:2]]
        s = Schedule(project_id=sched_project.id, case_ids=case_ids, cron_expr="0 2 * * *")
        db_session.add(s)
        await db_session.commit()

        resp = await async_client.post(
            f"/api/projects/{sched_project.id}/schedules/{s.id}/trigger",
            headers=editor_headers,
        )
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]

        rows = (
            await db_session.execute(
                select(TestRunCases).where(TestRunCases.run_id == run_id)
            )
        ).scalars().all()
        assert len(rows) == 2

    async def test_sched_011_trigger_executes(
        self,
        async_client: AsyncClient,
        editor_headers: dict,
        sched_project: Project,
        sched_cases: list[TestCase],
        db_session: AsyncSession,
    ):
        """SCHED-011：手动触发后 execute_run 正常启动 — 等待后台完成，status 不再 pending。"""
        import asyncio

        case_ids = [sched_cases[0].id]
        s = Schedule(project_id=sched_project.id, case_ids=case_ids, cron_expr="0 2 * * *")
        db_session.add(s)
        await db_session.commit()

        resp = await async_client.post(
            f"/api/projects/{sched_project.id}/schedules/{s.id}/trigger",
            headers=editor_headers,
        )
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]

        for _ in range(20):
            await asyncio.sleep(0.5)
            run = await db_session.get(TestRun, run_id)
            if run and run.status != "pending":
                break

        await db_session.refresh(run)
        assert run.status != "pending", "execute_run 未能在超时内完成"

    async def test_sched_012_restore_enabled(
        self, db_session: AsyncSession, sched_project: Project
    ):
        """SCHED-012：服务启动时 enabled schedule 自动注册 — init_scheduler → _restore_schedules。"""
        from services.scheduler import _restore_schedules

        s = Schedule(project_id=sched_project.id, cron_expr="0 2 * * *", enabled=True)
        db_session.add(s)
        await db_session.commit()

        # 确保无残留 job
        remove_job(s.id)

        # 模拟启动恢复
        await _restore_schedules()
        assert_job_exists(s.id, exists=True)

    async def test_sched_013_restore_disabled(
        self, db_session: AsyncSession, sched_project: Project
    ):
        """SCHED-013：服务启动时 disabled schedule 不注册 — _restore_schedules 跳过。"""
        from services.scheduler import _restore_schedules

        s = Schedule(project_id=sched_project.id, cron_expr="0 2 * * *", enabled=False)
        db_session.add(s)
        await db_session.commit()

        await _restore_schedules()
        assert_job_exists(s.id, exists=False)


# ═══════════════════════════════════════════════════════════════════════════
#  II. 边界值
# ═══════════════════════════════════════════════════════════════════════════


class TestBoundary:
    """SCHED-101 ~ SCHED-107：边界值 7 个场景。"""

    async def test_sched_101_invalid_cron(
        self, async_client: AsyncClient, editor_headers: dict, sched_project: Project
    ):
        """SCHED-101：无效 cron 表达式 → 400 'Invalid cron expression'。"""
        resp = await async_client.post(
            f"/api/projects/{sched_project.id}/schedules",
            headers=editor_headers,
            json={"cron_expr": "invalid"},
        )
        assert resp.status_code == 400
        assert "Invalid cron" in resp.json().get("detail", "")

    async def test_sched_102_no_suite_no_cases(
        self,
        async_client: AsyncClient,
        editor_headers: dict,
        sched_project: Project,
        db_session: AsyncSession,
    ):
        """SCHED-102：suite_id 和 case_ids 都为空 → 201 创建成功，但 trigger → 400 'No cases to run'。"""
        resp = await async_client.post(
            f"/api/projects/{sched_project.id}/schedules",
            headers=editor_headers,
            json={"cron_expr": "0 2 * * *"},
        )
        assert resp.status_code == 201
        sid = resp.json()["id"]

        # 手动触发 → 400
        resp2 = await async_client.post(
            f"/api/projects/{sched_project.id}/schedules/{sid}/trigger",
            headers=editor_headers,
        )
        assert resp2.status_code == 400
        assert "No cases to run" in resp2.json().get("detail", "")

    async def test_sched_103_empty_suite(
        self,
        async_client: AsyncClient,
        editor_headers: dict,
        sched_project: Project,
        db_session: AsyncSession,
    ):
        """SCHED-103：suite_id 关联空测试集 → trigger → 400 'No cases to run'。"""
        empty_suite = TestSuite(project_id=sched_project.id, name="Empty Suite")
        db_session.add(empty_suite)
        await db_session.commit()

        s = Schedule(project_id=sched_project.id, suite_id=empty_suite.id, cron_expr="0 2 * * *")
        db_session.add(s)
        await db_session.commit()

        resp = await async_client.post(
            f"/api/projects/{sched_project.id}/schedules/{s.id}/trigger",
            headers=editor_headers,
        )
        assert resp.status_code == 400
        assert "No cases to run" in resp.json().get("detail", "")

    async def test_sched_104_large_case_set(
        self,
        async_client: AsyncClient,
        editor_headers: dict,
        sched_project: Project,
        db_session: AsyncSession,
    ):
        """SCHED-104：大量用例（50+）的定时任务 → 201，手动触发正常创建 TestRun。"""
        case_ids = []
        for i in range(50):
            tc = TestCase(
                project_id=sched_project.id,
                name=f"Sched Bulk {i}",
                test_type="api",
                content={"method": "GET", "url": f"/api/sched/bulk/{i}"},
            )
            db_session.add(tc)
        await db_session.commit()

        all_cases = (
            await db_session.execute(
                select(TestCase).where(TestCase.project_id == sched_project.id)
                .order_by(TestCase.id.desc()).limit(50)
            )
        ).scalars().all()
        case_ids = [c.id for c in reversed(all_cases)]

        resp = await async_client.post(
            f"/api/projects/{sched_project.id}/schedules",
            headers=editor_headers,
            json={"case_ids": case_ids, "cron_expr": "0 2 * * *"},
        )
        assert resp.status_code == 201
        sid = resp.json()["id"]

        r2 = await async_client.post(
            f"/api/projects/{sched_project.id}/schedules/{sid}/trigger",
            headers=editor_headers,
        )
        assert r2.status_code == 200
        run_id = r2.json()["run_id"]
        rows = (await db_session.execute(
            select(TestRunCases).where(TestRunCases.run_id == run_id)
        )).scalars().all()
        assert len(rows) == 50

    async def test_sched_105_nonexistent(
        self, async_client: AsyncClient, editor_headers: dict, sched_project: Project
    ):
        """SCHED-105：不存在的 schedule → 404。"""
        # GET
        resp = await async_client.get(
            f"/api/projects/{sched_project.id}/schedules/99999", headers=editor_headers
        )
        assert resp.status_code == 404

        # PUT
        resp = await async_client.put(
            f"/api/projects/{sched_project.id}/schedules/99999",
            headers=editor_headers, json={"cron_expr": "0 2 * * *"},
        )
        assert resp.status_code == 404

        # DELETE
        resp = await async_client.delete(
            f"/api/projects/{sched_project.id}/schedules/99999", headers=editor_headers
        )
        assert resp.status_code == 404

        # TRIGGER
        resp = await async_client.post(
            f"/api/projects/{sched_project.id}/schedules/99999/trigger", headers=editor_headers
        )
        assert resp.status_code == 404

    async def test_sched_106_cross_project(
        self,
        async_client: AsyncClient,
        sched_project: Project,
        sched_editor: User,
        sched_stranger: User,
        db_session: AsyncSession,
    ):
        """SCHED-106：跨项目访问 schedule → 404。"""
        other_proj = Project(name="Other Sched Proj", user_id=sched_editor.id)
        db_session.add(other_proj)
        await db_session.commit()
        await db_session.refresh(other_proj)

        s = Schedule(project_id=other_proj.id, cron_expr="0 2 * * *")
        db_session.add(s)
        await db_session.commit()

        stranger_token = create_access_token({"sub": str(sched_stranger.id)}, user=sched_stranger)
        stranger_headers = {"Authorization": f"Bearer {stranger_token}"}

        # 非成员访问 sched_project → 403
        resp = await async_client.get(
            f"/api/projects/{sched_project.id}/schedules",
            headers=stranger_headers,
        )
        assert resp.status_code == 403

        # editor 是 sched_project 的成员，但 s 属于 other_proj
        # 在 sched_project 端点上操作 other_proj 的 schedule → 404 (project_id mismatch)
        ed_headers = {"Authorization": f"Bearer {create_access_token({'sub': str(sched_editor.id)}, user=sched_editor)}"}
        resp2 = await async_client.put(
            f"/api/projects/{sched_project.id}/schedules/{s.id}",
            headers=ed_headers, json={"cron_expr": "0 3 * * *"},
        )
        assert resp2.status_code == 404

    async def test_sched_107_cron_every_minute(
        self, async_client: AsyncClient, editor_headers: dict, sched_project: Project
    ):
        """SCHED-107：cron 表达式 '* * * * *' → 201 创建成功。"""
        resp = await async_client.post(
            f"/api/projects/{sched_project.id}/schedules",
            headers=editor_headers,
            json={"cron_expr": "* * * * *"},
        )
        assert resp.status_code == 201
        assert_job_exists(resp.json()["id"], exists=True)


# ═══════════════════════════════════════════════════════════════════════════
#  III. 异常场景
# ═══════════════════════════════════════════════════════════════════════════


class TestExceptions:
    """SCHED-201 ~ SCHED-206：异常场景 6 个。"""

    async def test_sched_201_unauth(
        self, async_client: AsyncClient, sched_project: Project
    ):
        """SCHED-201：未认证访问 → 401。"""
        endpoints = [
            ("GET", f"/api/projects/{sched_project.id}/schedules"),
            ("POST", f"/api/projects/{sched_project.id}/schedules"),
        ]
        for method, path in endpoints:
            resp = await async_client.request(method, path)
            assert resp.status_code == 401

    async def test_sched_202_viewer_write(
        self, async_client: AsyncClient, viewer_headers: dict, sched_project: Project
    ):
        """SCHED-202：Viewer 写操作 → 403。"""
        endpoints = [
            ("POST", f"/api/projects/{sched_project.id}/schedules", {"cron_expr": "0 2 * * *"}),
            ("PUT", f"/api/projects/{sched_project.id}/schedules/1", {"cron_expr": "0 2 * * *"}),
            ("DELETE", f"/api/projects/{sched_project.id}/schedules/1"),
            ("POST", f"/api/projects/{sched_project.id}/schedules/1/trigger"),
        ]
        for method, path, *body in endpoints:
            kwargs = {"headers": viewer_headers}
            if body:
                kwargs["json"] = body[0]
            resp = await async_client.request(method, path, **kwargs)
            assert resp.status_code == 403, f"{method} {path} expected 403"

    async def test_sched_203_non_member(
        self, async_client: AsyncClient, stranger_headers: dict, sched_project: Project
    ):
        """SCHED-203：非项目成员访问 → 403。"""
        resp = await async_client.get(
            f"/api/projects/{sched_project.id}/schedules", headers=stranger_headers
        )
        assert resp.status_code == 403

    async def test_sched_204_nonexistent_project(
        self, async_client: AsyncClient, viewer_headers: dict
    ):
        """SCHED-204：不存在项目 → 404。"""
        resp = await async_client.get(
            "/api/projects/99999/schedules", headers=viewer_headers
        )
        assert resp.status_code == 404

    async def test_sched_205_trigger_deleted(
        self,
        async_client: AsyncClient,
        editor_headers: dict,
        sched_project: Project,
        db_session: AsyncSession,
    ):
        """SCHED-205：手动触发已删除 schedule → 404。"""
        s = Schedule(project_id=sched_project.id, cron_expr="0 2 * * *")
        db_session.add(s)
        await db_session.commit()
        sid = s.id

        # 删除
        await async_client.delete(
            f"/api/projects/{sched_project.id}/schedules/{sid}", headers=editor_headers
        )

        # 触发 → 404
        resp = await async_client.post(
            f"/api/projects/{sched_project.id}/schedules/{sid}/trigger",
            headers=editor_headers,
        )
        assert resp.status_code == 404

    async def test_sched_206_trigger_disabled(
        self,
        async_client: AsyncClient,
        editor_headers: dict,
        sched_project: Project,
        sched_cases: list[TestCase],
        db_session: AsyncSession,
    ):
        """SCHED-206：手动触发时 APScheduler job 不存在 → 不影响手动触发（200）。"""
        s = Schedule(
            project_id=sched_project.id,
            enabled=False,
            case_ids=[sched_cases[0].id],
            cron_expr="0 2 * * *",
        )
        db_session.add(s)
        await db_session.commit()

        # 确认无 APScheduler job
        assert_job_exists(s.id, exists=False)

        # 手动触发仍然成功
        resp = await async_client.post(
            f"/api/projects/{sched_project.id}/schedules/{s.id}/trigger",
            headers=editor_headers,
        )
        assert resp.status_code == 200
        assert "run_id" in resp.json()


# ═══════════════════════════════════════════════════════════════════════════
#  IV. 权限/认证
# ═══════════════════════════════════════════════════════════════════════════


class TestAuth:
    """SCHED-301 ~ SCHED-303：权限隔离 3 个场景。"""

    async def test_sched_301_viewer_readonly(
        self, async_client: AsyncClient, viewer_headers: dict, editor_headers: dict, sched_project: Project
    ):
        """SCHED-301：Viewer 只读 / Editor 可写 — viewer 列表 ✅，写 403；editor 写 ✅。"""
        # Viewer 读
        r1 = await async_client.get(
            f"/api/projects/{sched_project.id}/schedules", headers=viewer_headers
        )
        assert r1.status_code == 200

        # Viewer 写 → 403
        r2 = await async_client.post(
            f"/api/projects/{sched_project.id}/schedules",
            headers=viewer_headers, json={"cron_expr": "0 2 * * *"},
        )
        assert r2.status_code == 403

        # Editor 写 → 201
        r3 = await async_client.post(
            f"/api/projects/{sched_project.id}/schedules",
            headers=editor_headers, json={"cron_expr": "0 2 * * *"},
        )
        assert r3.status_code == 201

    async def test_sched_302_admin_bypass(
        self,
        async_client: AsyncClient,
        admin_headers: dict,
        sched_project: Project,
        sched_cases: list[TestCase],
        db_session: AsyncSession,
    ):
        """SCHED-302：Admin bypass — admin 对任意项目 schedules 全操作。"""
        # Create
        r1 = await async_client.post(
            f"/api/projects/{sched_project.id}/schedules",
            headers=admin_headers,
            json={"cron_expr": "0 2 * * *", "case_ids": [sched_cases[0].id]},
        )
        assert r1.status_code == 201
        sid = r1.json()["id"]

        # Read
        r2 = await async_client.get(
            f"/api/projects/{sched_project.id}/schedules", headers=admin_headers
        )
        assert r2.status_code == 200

        # Update
        r3 = await async_client.put(
            f"/api/projects/{sched_project.id}/schedules/{sid}",
            headers=admin_headers, json={"cron_expr": "0 3 * * *"},
        )
        assert r3.status_code == 200

        # Trigger
        r4 = await async_client.post(
            f"/api/projects/{sched_project.id}/schedules/{sid}/trigger",
            headers=admin_headers,
        )
        assert r4.status_code == 200

        # Delete
        r5 = await async_client.delete(
            f"/api/projects/{sched_project.id}/schedules/{sid}",
            headers=admin_headers,
        )
        assert r5.status_code == 204

    async def test_sched_303_owner_full_access(
        self,
        async_client: AsyncClient,
        owner_headers: dict,
        sched_project: Project,
        sched_cases: list[TestCase],
    ):
        """SCHED-303：Owner 完整控制 — owner 执行全部 CRUD + 手动触发。"""
        # Create
        r1 = await async_client.post(
            f"/api/projects/{sched_project.id}/schedules",
            headers=owner_headers,
            json={"cron_expr": "0 2 * * *", "case_ids": [sched_cases[0].id]},
        )
        assert r1.status_code == 201
        sid = r1.json()["id"]

        # Read
        r2 = await async_client.get(
            f"/api/projects/{sched_project.id}/schedules", headers=owner_headers
        )
        assert r2.status_code == 200

        # Update
        r3 = await async_client.put(
            f"/api/projects/{sched_project.id}/schedules/{sid}",
            headers=owner_headers, json={"enabled": False},
        )
        assert r3.status_code == 200

        # Trigger
        r4 = await async_client.post(
            f"/api/projects/{sched_project.id}/schedules/{sid}/trigger",
            headers=owner_headers,
        )
        assert r4.status_code == 200

        # Delete
        r5 = await async_client.delete(
            f"/api/projects/{sched_project.id}/schedules/{sid}",
            headers=owner_headers,
        )
        assert r5.status_code == 204


# ═══════════════════════════════════════════════════════════════════════════
#  V. 生命周期（直接调用 _execute_schedule 验证）
# ═══════════════════════════════════════════════════════════════════════════


class TestLifecycle:
    """SCHED-401 ~ SCHED-405：生命周期 5 个场景 — 直接测试 APScheduler 回调路径。"""

    async def test_sched_401_init_shutdown(self):
        """SCHED-401：init_scheduler 正常启动和关闭。"""
        import asyncio as _asyncio
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from services.scheduler import init_scheduler

        # 使用临时调度器，不干扰全局 scheduler
        import services.scheduler as sched_mod
        orig = sched_mod.scheduler

        ts = AsyncIOScheduler()
        sched_mod.scheduler = ts
        try:
            await init_scheduler("sqlite://")
            assert ts.running
            ts.shutdown(wait=False)
            # AsyncIOScheduler.shutdown 通过 @run_in_event_loop 延迟执行，
            # 需要让出事件循环以处理关闭回调
            await _asyncio.sleep(0)
            assert not ts.running
        finally:
            sched_mod.scheduler = orig

    async def test_sched_402_execute_schedule_creates_run(
        self,
        db_session: AsyncSession,
        sched_project: Project,
        sched_cases: list[TestCase],
    ):
        """SCHED-402：定时触发自动创建 TestRun — _execute_schedule 创建 TestRun source='scheduled'。"""
        s = Schedule(
            project_id=sched_project.id,
            case_ids=[sched_cases[0].id],
            cron_expr="0 2 * * *",
        )
        db_session.add(s)
        await db_session.commit()
        await db_session.refresh(s)

        await _execute_schedule(s.id)

        # TestRun 创建
        rows = (await db_session.execute(
            select(TestRun).where(TestRun.project_id == sched_project.id)
        )).scalars().all()
        assert len(rows) >= 1
        run = rows[-1]
        assert run.source == "scheduled"

    async def test_sched_403_execute_disabled_skips(
        self,
        db_session: AsyncSession,
        sched_project: Project,
        sched_cases: list[TestCase],
    ):
        """SCHED-403：定时触发时 schedule 已被禁用 → 跳过执行，不创建 TestRun。"""
        s = Schedule(
            project_id=sched_project.id,
            enabled=False,
            case_ids=[sched_cases[0].id],
            cron_expr="0 2 * * *",
        )
        db_session.add(s)
        await db_session.commit()
        await db_session.refresh(s)

        await _execute_schedule(s.id)

        rows = (await db_session.execute(
            select(TestRun).where(TestRun.project_id == sched_project.id)
        )).scalars().all()
        assert len(rows) == 0  # 没有创建 TestRun

    async def test_sched_404_execute_deleted_skips(
        self,
        db_session: AsyncSession,
        sched_project: Project,
    ):
        """SCHED-404：定时触发时 schedule 已被删除 → 跳过执行。"""
        s = Schedule(
            project_id=sched_project.id,
            case_ids=[1],
            cron_expr="0 2 * * *",
        )
        db_session.add(s)
        await db_session.commit()
        await db_session.refresh(s)
        sid = s.id

        await db_session.delete(s)
        await db_session.commit()

        await _execute_schedule(sid)  # 不应崩溃

        rows = (await db_session.execute(
            select(TestRun).where(TestRun.project_id == sched_project.id)
        )).scalars().all()
        assert len(rows) == 0

    async def test_sched_405_execute_no_cases_skips(
        self,
        db_session: AsyncSession,
        sched_project: Project,
    ):
        """SCHED-405：定时触发无可用用例 → 仅日志不创建 TestRun。"""
        # 空 case_ids + 无 suite_id
        s = Schedule(
            project_id=sched_project.id,
            cron_expr="0 2 * * *",
        )
        db_session.add(s)
        await db_session.commit()
        await db_session.refresh(s)

        await _execute_schedule(s.id)

        rows = (await db_session.execute(
            select(TestRun).where(TestRun.project_id == sched_project.id)
        )).scalars().all()
        assert len(rows) == 0
