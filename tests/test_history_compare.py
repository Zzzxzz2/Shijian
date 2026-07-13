"""测试组：执行历史对比 — 19 个场景覆盖（验剑策略）。

策略文件：``.omo/tests/test-plan-history-compare.md``
覆盖维度：
  正常路径  7 个（HIST-001 ~ HIST-007）
  边界值   6 个（HIST-101 ~ HIST-106）
  异常场景  4 个（HIST-201 ~ HIST-204）
  权限隔离  2 个（HIST-301 ~ HIST-302）
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import create_access_token, hash_password
from models import Project, ProjectMembers, TestCase, TestRun, TestRunCases, TestResult, User

pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════════════
#  URL helpers
# ═══════════════════════════════════════════════════════════════════════════


def _results_url(pid: int, run_id: int) -> str:
    return f"/api/projects/{pid}/runs/{run_id}/results"


def _standalone_results_url(run_id: int) -> str:
    return f"/api/runs/{run_id}/results"


def _diff_url(run_id: int) -> str:
    return f"/api/runs/{run_id}/diff"


# ═══════════════════════════════════════════════════════════════════════════
#  Fixtures — Role Users
# ═══════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def hist_owner(db_session) -> User:
    await db_session.execute(sa_delete(User).where(User.username == "hist_owner"))
    await db_session.commit()
    u = User(username="hist_owner", password_hash=hash_password("pass123"), role="user")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def hist_viewer(db_session) -> User:
    await db_session.execute(sa_delete(User).where(User.username == "hist_viewer"))
    await db_session.commit()
    u = User(username="hist_viewer", password_hash=hash_password("pass123"), role="user")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def hist_stranger(db_session) -> User:
    await db_session.execute(sa_delete(User).where(User.username == "hist_stranger"))
    await db_session.commit()
    u = User(username="hist_stranger", password_hash=hash_password("pass123"), role="user")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def hist_owner_token(hist_owner: User) -> str:
    return create_access_token({"sub": str(hist_owner.id)})


@pytest_asyncio.fixture
async def hist_viewer_token(hist_viewer: User) -> str:
    return create_access_token({"sub": str(hist_viewer.id)})


@pytest_asyncio.fixture
async def hist_stranger_token(hist_stranger: User) -> str:
    return create_access_token({"sub": str(hist_stranger.id)})


@pytest_asyncio.fixture
async def hist_owner_headers(hist_owner_token: str) -> dict:
    return {"Authorization": f"Bearer {hist_owner_token}"}


@pytest_asyncio.fixture
async def hist_viewer_headers(hist_viewer_token: str) -> dict:
    return {"Authorization": f"Bearer {hist_viewer_token}"}


@pytest_asyncio.fixture
async def hist_stranger_headers(hist_stranger_token: str) -> dict:
    return {"Authorization": f"Bearer {hist_stranger_token}"}


# ═══════════════════════════════════════════════════════════════════════════
#  Fixtures — Project + Cases + Member
# ═══════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def hist_project(db_session, hist_owner: User) -> Project:
    proj = Project(name="History Compare Project", user_id=hist_owner.id)
    db_session.add(proj)
    await db_session.commit()
    await db_session.refresh(proj)
    return proj


@pytest_asyncio.fixture
async def hist_cases(db_session, hist_project: Project) -> dict[str, TestCase]:
    """Return 5 named cases keyed by scenario role."""
    names = ["C1", "C2", "C3", "C4", "C5"]
    cases: dict[str, TestCase] = {}
    for n in names:
        c = TestCase(
            project_id=hist_project.id,
            name=n,
            test_type="api",
            content={"method": "GET", "url": f"/api/{n}"},
        )
        db_session.add(c)
        # need flush to get id before commit
        await db_session.flush()
        cases[n] = c
    await db_session.commit()
    return cases


@pytest_asyncio.fixture
async def hist_member(db_session, hist_project: Project, hist_viewer: User) -> None:
    """Grant viewer role to hist_viewer on hist_project."""
    await db_session.execute(
        sa_delete(ProjectMembers).where(
            ProjectMembers.project_id == hist_project.id,
            ProjectMembers.user_id == hist_viewer.id,
        )
    )
    await db_session.commit()
    db_session.add(ProjectMembers(project_id=hist_project.id, user_id=hist_viewer.id, role="viewer"))
    await db_session.commit()


@pytest_asyncio.fixture
async def hist_admin(db_session) -> User:
    await db_session.execute(sa_delete(User).where(User.username == "hist_admin"))
    await db_session.commit()
    u = User(username="hist_admin", password_hash=hash_password("admin123"), role="admin")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def hist_admin_token(hist_admin: User) -> str:
    return create_access_token({"sub": str(hist_admin.id)}, user=hist_admin)


@pytest_asyncio.fixture
async def hist_admin_headers(hist_admin_token: str) -> dict:
    return {"Authorization": f"Bearer {hist_admin_token}"}


# ═══════════════════════════════════════════════════════════════════════════
#  Helper
# ═══════════════════════════════════════════════════════════════════════════


async def _create_run(db: AsyncSession, pid: int, status: str = "done") -> TestRun:
    run = TestRun(project_id=pid, status=status)
    db.add(run)
    await db.flush()
    return run


async def _add_result(db: AsyncSession, run_id: int, case_id: int, status: str) -> None:
    db.add(TestRunCases(run_id=run_id, case_id=case_id))
    db.add(TestResult(run_id=run_id, case_id=case_id, status=status))
    await db.flush()


async def _setup_two_runs(db: AsyncSession, pid: int, cases: dict[str, TestCase]) -> tuple[int, int]:
    """Create run1 + run2 with classic regression/fixed/unchanged/new pattern.

    ┌───────────┬───────┬───────┐
    │ case      │ run1  │ run2  │
    ├───────────┼───────┼───────┤
    │ C1        │ pass  │ fail  │ ← regression
    │ C2        │ fail  │ pass  │ ← fixed
    │ C3        │ pass  │ pass  │ ← unchanged
    │ C4        │ —     │ pass  │ ← new
    │ C5        │ fail  │ fail  │ ← unchanged (fail)
    └───────────┴───────┴───────┘
    """
    r1 = await _create_run(db, pid)
    await _add_result(db, r1.id, cases["C1"].id, "pass")
    await _add_result(db, r1.id, cases["C2"].id, "fail")
    await _add_result(db, r1.id, cases["C3"].id, "pass")
    await _add_result(db, r1.id, cases["C5"].id, "fail")

    r2 = await _create_run(db, pid)
    await _add_result(db, r2.id, cases["C1"].id, "fail")
    await _add_result(db, r2.id, cases["C2"].id, "pass")
    await _add_result(db, r2.id, cases["C3"].id, "pass")
    await _add_result(db, r2.id, cases["C4"].id, "pass")
    await _add_result(db, r2.id, cases["C5"].id, "fail")

    await db.commit()
    return r1.id, r2.id


# ═══════════════════════════════════════════════════════════════════════════
#  I. 正常路径
# ═══════════════════════════════════════════════════════════════════════════


class TestHappyPath:
    """HIST-001 ~ HIST-007：正常路径 7 个场景。"""

    async def test_hist_001_results_with_history(
        self,
        async_client: AsyncClient,
        hist_owner_headers: dict,
        hist_project: Project,
        hist_cases: dict[str, TestCase],
        db_session: AsyncSession,
    ):
        """HIST-001：有历史 run → 每条结果含 prev_status + change。"""
        _, r2_id = await _setup_two_runs(db_session, hist_project.id, hist_cases)

        resp = await async_client.get(
            _results_url(hist_project.id, r2_id), headers=hist_owner_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 5

        for item in data:
            assert "prev_status" in item
            assert "change" in item
            assert item["change"] in ("regression", "fixed", "unchanged", "new")

    async def test_hist_002_regression(
        self,
        async_client: AsyncClient,
        hist_owner_headers: dict,
        hist_project: Project,
        hist_cases: dict[str, TestCase],
        db_session: AsyncSession,
    ):
        """HIST-002：regression 标记（pass → fail）。"""
        _, r2_id = await _setup_two_runs(db_session, hist_project.id, hist_cases)
        resp = await async_client.get(
            _results_url(hist_project.id, r2_id), headers=hist_owner_headers
        )
        data = resp.json()
        c1_result = next(r for r in data if r["case_id"] == hist_cases["C1"].id)
        assert c1_result["change"] == "regression"
        assert c1_result["prev_status"] == "pass"
        assert c1_result["status"] == "fail"

    async def test_hist_003_fixed(
        self,
        async_client: AsyncClient,
        hist_owner_headers: dict,
        hist_project: Project,
        hist_cases: dict[str, TestCase],
        db_session: AsyncSession,
    ):
        """HIST-003：fixed 标记（fail → pass）。"""
        _, r2_id = await _setup_two_runs(db_session, hist_project.id, hist_cases)
        resp = await async_client.get(
            _results_url(hist_project.id, r2_id), headers=hist_owner_headers
        )
        data = resp.json()
        c2_result = next(r for r in data if r["case_id"] == hist_cases["C2"].id)
        assert c2_result["change"] == "fixed"
        assert c2_result["prev_status"] == "fail"
        assert c2_result["status"] == "pass"

    async def test_hist_004_unchanged(
        self,
        async_client: AsyncClient,
        hist_owner_headers: dict,
        hist_project: Project,
        hist_cases: dict[str, TestCase],
        db_session: AsyncSession,
    ):
        """HIST-004：unchanged 标记（状态相同）。"""
        _, r2_id = await _setup_two_runs(db_session, hist_project.id, hist_cases)
        resp = await async_client.get(
            _results_url(hist_project.id, r2_id), headers=hist_owner_headers
        )
        data = resp.json()
        c3_result = next(r for r in data if r["case_id"] == hist_cases["C3"].id)
        assert c3_result["change"] == "unchanged"
        assert c3_result["prev_status"] == "pass"
        assert c3_result["status"] == "pass"

    async def test_hist_005_new_case(
        self,
        async_client: AsyncClient,
        hist_owner_headers: dict,
        hist_project: Project,
        hist_cases: dict[str, TestCase],
        db_session: AsyncSession,
    ):
        """HIST-005：新用例首次出现 → change='new'。"""
        _, r2_id = await _setup_two_runs(db_session, hist_project.id, hist_cases)
        resp = await async_client.get(
            _results_url(hist_project.id, r2_id), headers=hist_owner_headers
        )
        data = resp.json()
        c4_result = next(r for r in data if r["case_id"] == hist_cases["C4"].id)
        assert c4_result["change"] == "new"
        assert c4_result["prev_status"] is None

    async def test_hist_006_first_run(
        self,
        async_client: AsyncClient,
        hist_owner_headers: dict,
        hist_project: Project,
        hist_cases: dict[str, TestCase],
        db_session: AsyncSession,
    ):
        """HIST-006：首次执行（无历史 run）→ 全部 change='new'。"""
        r1 = await _create_run(db_session, hist_project.id)
        for c in hist_cases.values():
            await _add_result(db_session, r1.id, c.id, "pass")
        await db_session.commit()

        resp = await async_client.get(
            _results_url(hist_project.id, r1.id), headers=hist_owner_headers
        )
        data = resp.json()
        assert len(data) == 5
        for item in data:
            assert item["change"] == "new"
            assert item["prev_status"] is None

    async def test_hist_007_diff_endpoint(
        self,
        async_client: AsyncClient,
        hist_owner_headers: dict,
        hist_project: Project,
        hist_cases: dict[str, TestCase],
        db_session: AsyncSession,
    ):
        """HIST-007：diff 端点返回对比摘要。"""
        _, r2_id = await _setup_two_runs(db_session, hist_project.id, hist_cases)

        resp = await async_client.get(_diff_url(r2_id), headers=hist_owner_headers)
        assert resp.status_code == 200
        body = resp.json()

        assert "diff" in body
        assert isinstance(body["diff"], list)
        assert "summary" in body
        assert "new_failures" in body["summary"]
        assert "new_passes" in body["summary"]
        assert "unchanged" in body["summary"]

        # In our setup: C1 regression=new_failure, C2 fixed=new_pass, C3 unchanged, C4 new_case, C5 unchanged
        assert body["summary"]["new_failures"] == 1
        assert body["summary"]["new_passes"] == 1
        assert body["summary"]["unchanged"] == 2  # C3 + C5
        # C4 is "new_case", not counted in summary
        assert len(body["diff"]) == 5


# ═══════════════════════════════════════════════════════════════════════════
#  II. 边界值
# ═══════════════════════════════════════════════════════════════════════════


class TestBoundary:
    """HIST-101 ~ HIST-106：边界值 6 个场景。"""

    async def test_hist_101_multiple_history(
        self,
        async_client: AsyncClient,
        hist_owner_headers: dict,
        hist_project: Project,
        hist_cases: dict[str, TestCase],
        db_session: AsyncSession,
    ):
        """HIST-101：多个历史 run → 只取最近一个对比。

        run1 (done) → run2 (done) → run3 (current)
        run3 应只与 run2 对比，不跟 run1 对比。
        """
        c1 = hist_cases["C1"]
        c2 = hist_cases["C2"]

        r1 = await _create_run(db_session, hist_project.id)
        await _add_result(db_session, r1.id, c1.id, "pass")
        await _add_result(db_session, r1.id, c2.id, "fail")

        r2 = await _create_run(db_session, hist_project.id)
        await _add_result(db_session, r2.id, c1.id, "fail")
        await _add_result(db_session, r2.id, c2.id, "pass")

        r3 = await _create_run(db_session, hist_project.id)
        await _add_result(db_session, r3.id, c1.id, "pass")
        await _add_result(db_session, r3.id, c2.id, "fail")
        await db_session.commit()

        resp = await async_client.get(
            _results_url(hist_project.id, r3.id), headers=hist_owner_headers
        )
        data = resp.json()

        # r3 vs r2: C1 pass←fail → fixed; C2 fail←pass → regression
        c1_r = next(r for r in data if r["case_id"] == c1.id)
        c2_r = next(r for r in data if r["case_id"] == c2.id)
        assert c1_r["change"] == "fixed", "C1 should compare with r2 (fixed), not r1"
        assert c1_r["prev_status"] == "fail"
        assert c2_r["change"] == "regression", "C2 should compare with r2 (regression), not r1"

    async def test_hist_102_history_extra_cases(
        self,
        async_client: AsyncClient,
        hist_owner_headers: dict,
        hist_project: Project,
        hist_cases: dict[str, TestCase],
        db_session: AsyncSession,
    ):
        """HIST-102：历史 run 有当前 run 没有的 case → 不影响。"""
        c1 = hist_cases["C1"]
        c2 = hist_cases["C2"]

        r1 = await _create_run(db_session, hist_project.id)
        await _add_result(db_session, r1.id, c1.id, "pass")
        await _add_result(db_session, r1.id, c2.id, "fail")  # extra case in history

        r2 = await _create_run(db_session, hist_project.id)
        await _add_result(db_session, r2.id, c1.id, "fail")
        await db_session.commit()

        resp = await async_client.get(
            _results_url(hist_project.id, r2.id), headers=hist_owner_headers
        )
        data = resp.json()
        assert len(data) == 1  # only C1 in current run
        assert data[0]["case_id"] == c1.id
        assert data[0]["change"] == "regression"
        assert data[0]["prev_status"] == "pass"

    async def test_hist_103_current_new_cases(
        self,
        async_client: AsyncClient,
        hist_owner_headers: dict,
        hist_project: Project,
        hist_cases: dict[str, TestCase],
        db_session: AsyncSession,
    ):
        """HIST-103：当前 run 含有历史没有的 case → change='new'。"""
        c1 = hist_cases["C1"]
        c2 = hist_cases["C2"]

        r1 = await _create_run(db_session, hist_project.id)
        await _add_result(db_session, r1.id, c1.id, "pass")

        r2 = await _create_run(db_session, hist_project.id)
        await _add_result(db_session, r2.id, c1.id, "pass")
        await _add_result(db_session, r2.id, c2.id, "pass")
        await db_session.commit()

        resp = await async_client.get(
            _results_url(hist_project.id, r2.id), headers=hist_owner_headers
        )
        data = resp.json()
        assert len(data) == 2

        c1_r = next(r for r in data if r["case_id"] == c1.id)
        assert c1_r["change"] == "unchanged"
        assert c1_r["prev_status"] == "pass"

        c2_r = next(r for r in data if r["case_id"] == c2.id)
        assert c2_r["change"] == "new"
        assert c2_r["prev_status"] is None

    async def test_hist_104_all_pass(
        self,
        async_client: AsyncClient,
        hist_owner_headers: dict,
        hist_project: Project,
        hist_cases: dict[str, TestCase],
        db_session: AsyncSession,
    ):
        """HIST-104：全部 pass → 全部 unchanged。"""
        r1 = await _create_run(db_session, hist_project.id)
        r2 = await _create_run(db_session, hist_project.id)
        for c in hist_cases.values():
            await _add_result(db_session, r1.id, c.id, "pass")
            await _add_result(db_session, r2.id, c.id, "pass")
        await db_session.commit()

        resp = await async_client.get(
            _results_url(hist_project.id, r2.id), headers=hist_owner_headers
        )
        data = resp.json()
        assert len(data) == 5
        for item in data:
            assert item["change"] == "unchanged"

    async def test_hist_105_all_fail(
        self,
        async_client: AsyncClient,
        hist_owner_headers: dict,
        hist_project: Project,
        hist_cases: dict[str, TestCase],
        db_session: AsyncSession,
    ):
        """HIST-105：全部 fail → 全部 unchanged。"""
        r1 = await _create_run(db_session, hist_project.id)
        r2 = await _create_run(db_session, hist_project.id)
        for c in hist_cases.values():
            await _add_result(db_session, r1.id, c.id, "fail")
            await _add_result(db_session, r2.id, c.id, "fail")
        await db_session.commit()

        resp = await async_client.get(
            _results_url(hist_project.id, r2.id), headers=hist_owner_headers
        )
        data = resp.json()
        assert len(data) == 5
        for item in data:
            assert item["change"] == "unchanged"

    async def test_hist_106_only_current_run(
        self,
        async_client: AsyncClient,
        hist_owner_headers: dict,
        hist_project: Project,
        hist_cases: dict[str, TestCase],
        db_session: AsyncSession,
    ):
        """HIST-106：只有当前 run 没有历史 run → 全部 change='new'。"""
        r1 = await _create_run(db_session, hist_project.id)
        for c in hist_cases.values():
            await _add_result(db_session, r1.id, c.id, "pass")
        await db_session.commit()

        resp = await async_client.get(
            _results_url(hist_project.id, r1.id), headers=hist_owner_headers
        )
        data = resp.json()
        assert len(data) == 5
        for item in data:
            assert item["change"] == "new"
            assert item["prev_status"] is None


# ═══════════════════════════════════════════════════════════════════════════
#  III. 异常场景
# ═══════════════════════════════════════════════════════════════════════════


class TestExceptions:
    """HIST-201 ~ HIST-204：异常场景 4 个。"""

    async def test_hist_201_unauth(
        self,
        async_client: AsyncClient,
        hist_project: Project,
        hist_cases: dict[str, TestCase],
        db_session: AsyncSession,
    ):
        """HIST-201：未认证访问 → 空列表（非 401）。"""
        _, r2_id = await _setup_two_runs(db_session, hist_project.id, hist_cases)
        # 无 headers
        resp = await async_client.get(_standalone_results_url(r2_id))
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_hist_202_non_member(
        self,
        async_client: AsyncClient,
        hist_stranger_headers: dict,
        hist_project: Project,
        hist_cases: dict[str, TestCase],
        db_session: AsyncSession,
    ):
        """HIST-202：非成员 → 403。"""
        _, r2_id = await _setup_two_runs(db_session, hist_project.id, hist_cases)
        resp = await async_client.get(
            _results_url(hist_project.id, r2_id), headers=hist_stranger_headers
        )
        assert resp.status_code == 403

    async def test_hist_203_nonexistent_run(
        self,
        async_client: AsyncClient,
        hist_owner_headers: dict,
        hist_project: Project,
        db_session: AsyncSession,
    ):
        """HIST-203：不存在 run → scoped endpoint 返回 404。"""
        resp = await async_client.get(
            _results_url(hist_project.id, 99999), headers=hist_owner_headers
        )
        # 当前实现：require_project_access 先通过（项目存在），然后查 run 返回 404
        assert resp.status_code == 404

    async def test_hist_204_nonexistent_project(
        self,
        async_client: AsyncClient,
        hist_owner_headers: dict,
        db_session: AsyncSession,
    ):
        """HIST-204：不存在项目 → 404。"""
        resp = await async_client.get(
            _results_url(99999, 1), headers=hist_owner_headers
        )
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
#  IV. 权限/认证
# ═══════════════════════════════════════════════════════════════════════════


class TestAuth:
    """HIST-301 ~ HIST-302：权限 2 个场景。"""

    async def test_hist_301_viewer_can_view(
        self,
        async_client: AsyncClient,
        hist_viewer_headers: dict,
        hist_project: Project,
        hist_cases: dict[str, TestCase],
        db_session: AsyncSession,
        hist_member,
    ):
        """HIST-301：Viewer 可查看历史对比。"""
        _, r2_id = await _setup_two_runs(db_session, hist_project.id, hist_cases)

        resp = await async_client.get(
            _results_url(hist_project.id, r2_id), headers=hist_viewer_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 5
        for item in data:
            assert "prev_status" in item
            assert "change" in item

    async def test_hist_302_admin_bypass(
        self,
        async_client: AsyncClient,
        hist_admin_headers: dict,
        hist_project: Project,
        hist_cases: dict[str, TestCase],
        db_session: AsyncSession,
    ):
        """HIST-302：Admin 可查看任意项目的 run results。"""
        _, r2_id = await _setup_two_runs(db_session, hist_project.id, hist_cases)

        resp = await async_client.get(
            _results_url(hist_project.id, r2_id), headers=hist_admin_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 5
        for item in data:
            assert "prev_status" in item
            assert "change" in item
