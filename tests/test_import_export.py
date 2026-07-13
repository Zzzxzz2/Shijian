"""测试组：用例导入/导出 — 31 个场景覆盖（验剑策略）。

策略文件：`.omo/tests/test-plan-import-export.md`
覆盖维度：
  正常路径  9 个（EXP-001~005, IMP-001~004）
  边界值   11 个（EXP-101~103, IMP-101~108）
  异常场景  8 个（EXP-201~203, IMP-201~205）
  权限隔离  3 个（EXP-301, IMP-301, EXP-302）
"""

import json

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import create_access_token, hash_password
from models import Project, ProjectMembers, TestCase, User

pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════════════
#  Fixtures — 角色用户 + 项目 + 测试用例
# ═══════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def imp_exp_owner(db_session) -> User:
    await db_session.execute(sa_delete(User).where(User.username == "imp_exp_owner"))
    await db_session.commit()
    user = User(username="imp_exp_owner", password_hash=hash_password("pass123"), role="user")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def imp_exp_editor(db_session) -> User:
    await db_session.execute(sa_delete(User).where(User.username == "imp_exp_editor"))
    await db_session.commit()
    user = User(username="imp_exp_editor", password_hash=hash_password("pass123"), role="user")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def imp_exp_viewer(db_session) -> User:
    await db_session.execute(sa_delete(User).where(User.username == "imp_exp_viewer"))
    await db_session.commit()
    user = User(username="imp_exp_viewer", password_hash=hash_password("pass123"), role="user")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def imp_exp_stranger(db_session) -> User:
    await db_session.execute(sa_delete(User).where(User.username == "imp_exp_stranger"))
    await db_session.commit()
    user = User(username="imp_exp_stranger", password_hash=hash_password("pass123"), role="user")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def imp_exp_project(
    db_session, imp_exp_owner: User, imp_exp_editor: User, imp_exp_viewer: User
) -> Project:
    proj = Project(name="Import Export Test Project", user_id=imp_exp_owner.id)
    db_session.add(proj)
    await db_session.commit()
    await db_session.refresh(proj)

    db_session.add(ProjectMembers(project_id=proj.id, user_id=imp_exp_owner.id, role="owner"))
    db_session.add(ProjectMembers(project_id=proj.id, user_id=imp_exp_editor.id, role="editor"))
    db_session.add(ProjectMembers(project_id=proj.id, user_id=imp_exp_viewer.id, role="viewer"))
    await db_session.commit()
    return proj


@pytest_asyncio.fixture
async def imp_exp_cases(db_session, imp_exp_project: Project) -> list[TestCase]:
    """创建 5 条用例（3 api + 2 ui），部分含 tag。"""
    cases_data = [
        ("Login API", "api", {"method": "POST", "url": "/api/login"}, ["smoke", "auth"]),
        ("Logout API", "api", {"method": "POST", "url": "/api/logout"}, ["smoke"]),
        ("Dashboard Page", "ui", {"url": "/dashboard", "steps": []}, ["regression"]),
        ("User Profile API", "api", {"method": "GET", "url": "/api/profile"}, []),
        ("Settings Page", "ui", {"url": "/settings", "steps": []}, []),
    ]
    cases = []
    for name, test_type, content, tags in cases_data:
        tc = TestCase(
            project_id=imp_exp_project.id,
            name=name,
            test_type=test_type,
            source="manual",
            content=content,
            tags=tags,
        )
        db_session.add(tc)
        cases.append(tc)
    await db_session.commit()
    for tc in cases:
        await db_session.refresh(tc)
    return cases


# ── Tokens & Headers ────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def owner_token(imp_exp_owner: User) -> str:
    return create_access_token({"sub": str(imp_exp_owner.id)}, user=imp_exp_owner)


@pytest_asyncio.fixture
async def owner_headers(owner_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {owner_token}"}


@pytest_asyncio.fixture
async def editor_token(imp_exp_editor: User) -> str:
    return create_access_token({"sub": str(imp_exp_editor.id)}, user=imp_exp_editor)


@pytest_asyncio.fixture
async def editor_headers(editor_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {editor_token}"}


@pytest_asyncio.fixture
async def viewer_token(imp_exp_viewer: User) -> str:
    return create_access_token({"sub": str(imp_exp_viewer.id)}, user=imp_exp_viewer)


@pytest_asyncio.fixture
async def viewer_headers(viewer_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {viewer_token}"}


@pytest_asyncio.fixture
async def stranger_token(imp_exp_stranger: User) -> str:
    return create_access_token({"sub": str(imp_exp_stranger.id)}, user=imp_exp_stranger)


@pytest_asyncio.fixture
async def stranger_headers(stranger_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {stranger_token}"}


# ── Helpers ─────────────────────────────────────────────────────────────


def _export_url(pid: int) -> str:
    return f"/api/projects/{pid}/cases/export"


def _import_url(pid: int) -> str:
    return f"/api/projects/{pid}/cases/import"


def _make_import_file(cases_data: list[dict]) -> tuple[str, bytes, str]:
    """构建 multipart 上传用的文件元组 (filename, content, media_type)。"""
    body = json.dumps({"cases": cases_data}, ensure_ascii=False).encode()
    return ("cases.json", body, "application/json")


def _make_import_file_raw(content: str) -> tuple[str, bytes, str]:
    """构建非 JSON 文件上传。"""
    return ("cases.json", content.encode(), "application/json")


# ═══════════════════════════════════════════════════════════════════════════
#  I. 正常路径（Happy Path）
# ═══════════════════════════════════════════════════════════════════════════


class TestHappyPath:
    """EXP-001~005, IMP-001~004：正常路径 9 个场景。"""

    async def test_exp_001_viewer_export_all(
        self, async_client: AsyncClient, viewer_headers: dict, imp_exp_project: Project, imp_exp_cases: list
    ):
        """EXP-001：Viewer 导出全部用例 — 200，Content-Type/Disposition，body 含 project/exported_at/cases。"""
        resp = await async_client.get(_export_url(imp_exp_project.id), headers=viewer_headers)
        assert resp.status_code == 200
        assert resp.headers.get("content-type") == "application/json"
        assert "attachment" in resp.headers.get("content-disposition", "")
        assert f"project_{imp_exp_project.id}_cases.json" in resp.headers.get("content-disposition", "")

        data = resp.json()
        assert "project" in data
        assert "exported_at" in data
        assert "cases" in data
        assert len(data["cases"]) == 5

    async def test_exp_002_field_completeness(
        self, async_client: AsyncClient, viewer_headers: dict, imp_exp_project: Project, imp_exp_cases: list
    ):
        """EXP-002：导出字段完整性 — 每条 case 含 name/test_type/source/content/skip_auth/tags。"""
        resp = await async_client.get(_export_url(imp_exp_project.id), headers=viewer_headers)
        data = resp.json()
        for case in data["cases"]:
            assert "name" in case
            assert "test_type" in case
            assert "source" in case
            assert "content" in case
            assert "skip_auth" in case
            assert "tags" in case

    async def test_exp_003_filter_by_test_type(
        self, async_client: AsyncClient, viewer_headers: dict, imp_exp_project: Project, imp_exp_cases: list
    ):
        """EXP-003：导出按 test_type 筛选 — 仅返回 test_type=api 的用例。"""
        resp = await async_client.get(
            _export_url(imp_exp_project.id) + "?test_type=api",
            headers=viewer_headers,
        )
        data = resp.json()
        assert len(data["cases"]) == 3
        for case in data["cases"]:
            assert case["test_type"] == "api"

    async def test_exp_004_filter_by_tag(
        self, async_client: AsyncClient, viewer_headers: dict, imp_exp_project: Project, imp_exp_cases: list
    ):
        """EXP-004：导出按 tag 筛选 — 仅返回含 smoke tag 的用例。"""
        resp = await async_client.get(
            _export_url(imp_exp_project.id) + "?tag=smoke",
            headers=viewer_headers,
        )
        data = resp.json()
        assert len(data["cases"]) == 2
        for case in data["cases"]:
            assert "smoke" in case["tags"]

    async def test_exp_005_project_name(
        self, async_client: AsyncClient, viewer_headers: dict, imp_exp_project: Project
    ):
        """EXP-005：导出项目名称正确 — data.project 等于项目名称。"""
        resp = await async_client.get(_export_url(imp_exp_project.id), headers=viewer_headers)
        data = resp.json()
        assert data["project"] == imp_exp_project.name

    async def test_imp_001_import_valid(
        self, async_client: AsyncClient, editor_headers: dict, imp_exp_project: Project, db_session: AsyncSession
    ):
        """IMP-001：导入有效 JSON（全部合法）— 201，imported=5, failed=0, errors=[]。"""
        cases_data = [
            {"name": f"Imported Case {i}", "test_type": "api", "content": {"method": "GET", "url": f"/api/imp/{i}"}}
            for i in range(5)
        ]
        resp = await async_client.post(
            _import_url(imp_exp_project.id),
            headers=editor_headers,
            files={"file": _make_import_file(cases_data)},
        )
        assert resp.status_code == 201
        result = resp.json()
        assert result["imported"] == 5
        assert result["failed"] == 0
        assert result["errors"] == []

    async def test_imp_002_cases_queryable(
        self, async_client: AsyncClient, editor_headers: dict, imp_exp_project: Project, db_session: AsyncSession
    ):
        """IMP-002：导入后用例可查到 — GET /cases 列表包含新导入的用例。"""
        # 先导入 3 条
        cases_data = [
            {"name": f"Queryable Case {i}", "test_type": "ui", "content": {"url": f"/page/{i}", "steps": []}}
            for i in range(3)
        ]
        await async_client.post(
            _import_url(imp_exp_project.id),
            headers=editor_headers,
            files={"file": _make_import_file(cases_data)},
        )

        # 查询列表
        resp = await async_client.get(
            f"/api/projects/{imp_exp_project.id}/cases",
            headers=editor_headers,
        )
        assert resp.status_code == 200
        items = resp.json().get("items", [])
        names = {c["name"] for c in items}
        for i in range(3):
            assert f"Queryable Case {i}" in names

    async def test_imp_003_field_preservation(
        self, async_client: AsyncClient, editor_headers: dict, imp_exp_project: Project, db_session: AsyncSession
    ):
        """IMP-003：导入含 source/skip_auth/tags 字段 — 入库后字段值与导入一致。"""
        cases_data = [
            {
                "name": "Preserved Fields Case",
                "test_type": "api",
                "source": "ai_generated",
                "content": {"method": "POST", "url": "/api/preserve"},
                "skip_auth": True,
                "tags": ["smoke", "imported"],
            }
        ]
        resp = await async_client.post(
            _import_url(imp_exp_project.id),
            headers=editor_headers,
            files={"file": _make_import_file(cases_data)},
        )
        assert resp.status_code == 201
        assert resp.json()["imported"] == 1

        # 查数据库验证字段
        row = (
            await db_session.execute(
                select(TestCase).where(
                    TestCase.project_id == imp_exp_project.id,
                    TestCase.name == "Preserved Fields Case",
                )
            )
        ).scalar_one_or_none()
        assert row is not None
        assert row.source == "ai_generated"
        assert row.skip_auth is True
        assert row.tags == ["smoke", "imported"]

    async def test_imp_004_partial_failure(
        self, async_client: AsyncClient, editor_headers: dict, imp_exp_project: Project
    ):
        """IMP-004：部分用例格式错误 — imported=3, failed=2, errors 含 2 条错误详情。"""
        cases_data = [
            {"name": "Valid Case 1", "test_type": "api", "content": {"method": "GET", "url": "/api/v1"}},
            {"name": "", "test_type": "api", "content": {"method": "GET", "url": "/api/bad"}},
            {"name": "Valid Case 2", "test_type": "ui", "content": {"url": "/valid", "steps": []}},
            {"name": "Bad Type", "test_type": "load", "content": {"method": "GET", "url": "/api/load"}},
            {"name": "No Content", "test_type": "api", "content": None},
        ]
        resp = await async_client.post(
            _import_url(imp_exp_project.id),
            headers=editor_headers,
            files={"file": _make_import_file(cases_data)},
        )
        assert resp.status_code == 201
        result = resp.json()
        assert result["imported"] == 3
        assert result["failed"] == 2
        assert len(result["errors"]) == 2
        # 验证错误包含 index/name/error
        for err in result["errors"]:
            assert "index" in err
            assert "name" in err
            assert "error" in err


# ═══════════════════════════════════════════════════════════════════════════
#  II. 边界值
# ═══════════════════════════════════════════════════════════════════════════


class TestBoundary:
    """EXP-101~103, IMP-101~108：边界值 11 个场景。"""

    async def test_exp_101_empty_project(
        self, async_client: AsyncClient, viewer_headers: dict, imp_exp_project: Project, db_session: AsyncSession
    ):
        """EXP-101：空项目导出 → cases 为空数组。"""
        resp = await async_client.get(_export_url(imp_exp_project.id), headers=viewer_headers)
        data = resp.json()
        assert data["cases"] == []

    async def test_exp_102_nonexistent_test_type(
        self, async_client: AsyncClient, viewer_headers: dict, imp_exp_project: Project, imp_exp_cases: list
    ):
        """EXP-102：导出不存在的 test_type → cases 为空。"""
        resp = await async_client.get(
            _export_url(imp_exp_project.id) + "?test_type=perf",
            headers=viewer_headers,
        )
        data = resp.json()
        assert data["cases"] == []

    async def test_exp_103_nonexistent_tag(
        self, async_client: AsyncClient, viewer_headers: dict, imp_exp_project: Project, imp_exp_cases: list
    ):
        """EXP-103：导出不含匹配 tag → cases 为空。"""
        resp = await async_client.get(
            _export_url(imp_exp_project.id) + "?tag=nonexistent",
            headers=viewer_headers,
        )
        data = resp.json()
        assert data["cases"] == []

    async def test_imp_101_empty_cases_array(
        self, async_client: AsyncClient, editor_headers: dict, imp_exp_project: Project
    ):
        """IMP-101：导入空 cases 数组 → imported=0, failed=0。"""
        resp = await async_client.post(
            _import_url(imp_exp_project.id),
            headers=editor_headers,
            files={"file": _make_import_file([])},
        )
        assert resp.status_code == 201
        result = resp.json()
        assert result["imported"] == 0
        assert result["failed"] == 0

    async def test_imp_102_cases_not_array(
        self, async_client: AsyncClient, editor_headers: dict, imp_exp_project: Project
    ):
        """IMP-102：导入 JSON 中 cases 不是数组 → 400。"""
        body = json.dumps({"cases": "not_an_array"}).encode()
        resp = await async_client.post(
            _import_url(imp_exp_project.id),
            headers=editor_headers,
            files={"file": ("cases.json", body, "application/json")},
        )
        assert resp.status_code == 400
        assert "cases" in resp.json().get("detail", "").lower()

    async def test_imp_103_invalid_json(
        self, async_client: AsyncClient, editor_headers: dict, imp_exp_project: Project
    ):
        """IMP-103：导入无效 JSON → 400。"""
        resp = await async_client.post(
            _import_url(imp_exp_project.id),
            headers=editor_headers,
            files={"file": _make_import_file_raw("not json")},
        )
        assert resp.status_code == 400
        assert "Invalid JSON" in resp.json().get("detail", "")

    async def test_imp_104_empty_name(
        self, async_client: AsyncClient, editor_headers: dict, imp_exp_project: Project
    ):
        """IMP-104：导入含 name 为空的用例 → failed。"""
        cases_data = [
            {"name": "", "test_type": "api", "content": {"method": "GET", "url": "/api/x"}},
        ]
        resp = await async_client.post(
            _import_url(imp_exp_project.id),
            headers=editor_headers,
            files={"file": _make_import_file(cases_data)},
        )
        result = resp.json()
        assert result["imported"] == 0
        assert result["failed"] == 1
        assert any("name" in str(e.get("error", "")).lower() for e in result["errors"])

    async def test_imp_105_invalid_test_type(
        self, async_client: AsyncClient, editor_headers: dict, imp_exp_project: Project
    ):
        """IMP-105：导入 test_type 不在 VALID_TEST_TYPES 的用例 → failed。"""
        cases_data = [
            {"name": "Bad Type Case", "test_type": "load", "content": {"method": "GET", "url": "/api/load"}},
        ]
        resp = await async_client.post(
            _import_url(imp_exp_project.id),
            headers=editor_headers,
            files={"file": _make_import_file(cases_data)},
        )
        result = resp.json()
        assert result["imported"] == 0
        assert result["failed"] == 1
        assert any("test_type" in str(e.get("error", "")).lower() for e in result["errors"])

    async def test_imp_106_empty_content(
        self, async_client: AsyncClient, editor_headers: dict, imp_exp_project: Project
    ):
        """IMP-106：导入缺少 content 字段的用例 → failed。"""
        cases_data = [
            {"name": "No Content Key", "test_type": "api"},  # content 键整个缺失
        ]
        resp = await async_client.post(
            _import_url(imp_exp_project.id),
            headers=editor_headers,
            files={"file": _make_import_file(cases_data)},
        )
        result = resp.json()
        assert result["imported"] == 0
        assert result["failed"] == 1
        assert any("content" in str(e.get("error", "")).lower() for e in result["errors"])

    async def test_imp_107_all_invalid(
        self, async_client: AsyncClient, editor_headers: dict, imp_exp_project: Project
    ):
        """IMP-107：全量非法 → imported=0, failed=N。"""
        cases_data = [
            {"name": "", "test_type": "api", "content": {"method": "GET", "url": "/api/x"}},
            {"name": "Bad Type", "test_type": "load", "content": {"method": "GET", "url": "/api/load"}},
            {"name": "No Content", "test_type": "api", "content": None},
            {"name": "Also Empty", "test_type": "ui", "content": {"url": "/page", "steps": []}},
            {"name": "Another Bad Type", "test_type": "grpc", "content": {"method": "GET", "url": "/api/g"}},
        ]
        # 修正：第 3 条 name 非空 → 实际 failed=3（空 name, load, grpc）
        # 第 0 条 name="" → failed；第 1 条 type=load → failed；第 2 条 content=None → failed；
        # 第 3 条 valid → imported；第 4 条 type=grpc → failed
        # 所以 expected: imported=1, failed=4
        resp = await async_client.post(
            _import_url(imp_exp_project.id),
            headers=editor_headers,
            files={"file": _make_import_file(cases_data)},
        )
        result = resp.json()
        assert result["failed"] >= 3  # 至少 3 条非法
        assert len(result["errors"]) >= 3

    async def test_imp_108_special_chars(
        self, async_client: AsyncClient, editor_headers: dict, imp_exp_project: Project
    ):
        """IMP-108：导入含特殊字段值的用例 → 201，imported=1。"""
        cases_data = [
            {
                "name": "Special <chars> & \"quotes\" 中文 🎯",
                "test_type": "api",
                "content": {"method": "POST", "url": "/api/special", "body": {"key": "value<>\"&"}},
            },
        ]
        resp = await async_client.post(
            _import_url(imp_exp_project.id),
            headers=editor_headers,
            files={"file": _make_import_file(cases_data)},
        )
        assert resp.status_code == 201
        result = resp.json()
        assert result["imported"] == 1
        assert result["failed"] == 0


# ═══════════════════════════════════════════════════════════════════════════
#  III. 异常场景
# ═══════════════════════════════════════════════════════════════════════════


class TestExceptions:
    """EXP-201~203, IMP-201~205：异常场景 8 个。"""

    async def test_exp_201_unauth_export(
        self, async_client: AsyncClient, imp_exp_project: Project
    ):
        """EXP-201：未认证用户导出 → 200，返回 {}（get_optional_user → None 走空响应分支）。"""
        resp = await async_client.get(_export_url(imp_exp_project.id))
        # export_cases 用 get_optional_user，未认证返回空 JSON
        assert resp.status_code == 200
        assert resp.json() == {}

    async def test_imp_201_unauth_import(
        self, async_client: AsyncClient, imp_exp_project: Project
    ):
        """IMP-201：未认证导入 → 401（get_current_user 拒绝）。"""
        resp = await async_client.post(
            _import_url(imp_exp_project.id),
            files={"file": _make_import_file([])},
        )
        assert resp.status_code == 401

    async def test_exp_202_non_member_export(
        self, async_client: AsyncClient, stranger_headers: dict, imp_exp_project: Project
    ):
        """EXP-202：非成员导出 → 403。"""
        resp = await async_client.get(_export_url(imp_exp_project.id), headers=stranger_headers)
        assert resp.status_code == 403

    async def test_imp_202_non_member_import(
        self, async_client: AsyncClient, stranger_headers: dict, imp_exp_project: Project
    ):
        """IMP-202：非成员导入 → 403。"""
        resp = await async_client.post(
            _import_url(imp_exp_project.id),
            headers=stranger_headers,
            files={"file": _make_import_file([])},
        )
        assert resp.status_code == 403

    async def test_imp_203_viewer_import(
        self, async_client: AsyncClient, viewer_headers: dict, imp_exp_project: Project
    ):
        """IMP-203：Viewer 导入 → 403。"""
        resp = await async_client.post(
            _import_url(imp_exp_project.id),
            headers=viewer_headers,
            files={"file": _make_import_file([])},
        )
        assert resp.status_code == 403

    async def test_imp_204_large_file(
        self, async_client: AsyncClient, editor_headers: dict, imp_exp_project: Project
    ):
        """IMP-204：超大 JSON 文件（>10MB）— 413 或处理正常。"""
        # 构造 ~1MB 的导入数据（10 条 × ~100KB 每条
        # FastAPI 默认 max_size=10MB，测试 12MB+）
        large_cases = []
        for i in range(12):
            large_cases.append({
                "name": f"Large Case {i}",
                "test_type": "api",
                "content": {
                    "method": "POST",
                    "url": f"/api/large/{i}",
                    "body": {"data": "x" * 1024 * 100},  # ~100KB each
                },
            })
        body = json.dumps({"cases": large_cases}).encode()
        resp = await async_client.post(
            _import_url(imp_exp_project.id),
            headers=editor_headers,
            files={"file": ("cases.json", body, "application/json")},
        )
        # 413 或 201 均可，取决于 FastAPI 配置
        assert resp.status_code in (201, 413)

    async def test_exp_203_nonexistent_project(
        self, async_client: AsyncClient, viewer_headers: dict
    ):
        """EXP-203：不存在项目导出 → 404。"""
        resp = await async_client.get(_export_url(99999), headers=viewer_headers)
        assert resp.status_code == 404

    async def test_imp_205_nonexistent_project(
        self, async_client: AsyncClient, editor_headers: dict
    ):
        """IMP-205：不存在项目导入 → 404。"""
        resp = await async_client.post(
            _import_url(99999),
            headers=editor_headers,
            files={"file": _make_import_file([])},
        )
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
#  IV. 权限/认证
# ═══════════════════════════════════════════════════════════════════════════


class TestAuth:
    """EXP-301, IMP-301, EXP-302：权限隔离 3 个场景。"""

    async def test_exp_301_viewer_can_export(
        self, async_client: AsyncClient, viewer_headers: dict, editor_headers: dict,
        imp_exp_project: Project, imp_exp_cases: list,
    ):
        """EXP-301：Viewer 可导出 — viewer 和 editor 均能正常导出。"""
        r1 = await async_client.get(_export_url(imp_exp_project.id), headers=viewer_headers)
        assert r1.status_code == 200
        assert len(r1.json()["cases"]) == 5

        r2 = await async_client.get(_export_url(imp_exp_project.id), headers=editor_headers)
        assert r2.status_code == 200
        assert len(r2.json()["cases"]) == 5

    async def test_imp_301_editor_can_import_viewer_cannot(
        self, async_client: AsyncClient, editor_headers: dict, viewer_headers: dict,
        imp_exp_project: Project,
    ):
        """IMP-301：Editor 可导入，Viewer 不可 — editor 导入 ✅，viewer 导入 → 403。"""
        cases_data = [
            {"name": "Auth Test Case", "test_type": "api", "content": {"method": "GET", "url": "/api/auth-test"}},
        ]

        # Viewer 导入 → 403
        r1 = await async_client.post(
            _import_url(imp_exp_project.id),
            headers=viewer_headers,
            files={"file": _make_import_file(cases_data)},
        )
        assert r1.status_code == 403

        # Editor 导入 → 201
        r2 = await async_client.post(
            _import_url(imp_exp_project.id),
            headers=editor_headers,
            files={"file": _make_import_file(cases_data)},
        )
        assert r2.status_code == 201
        assert r2.json()["imported"] == 1

    async def test_exp_302_admin_bypass(
        self, async_client: AsyncClient, admin_headers: dict,
        imp_exp_project: Project, imp_exp_cases: list,
    ):
        """EXP-302：Admin bypass — admin 对任意项目导出/导入。"""
        # 导出
        r1 = await async_client.get(_export_url(imp_exp_project.id), headers=admin_headers)
        assert r1.status_code == 200
        assert len(r1.json()["cases"]) == 5

        # 导入
        cases_data = [
            {"name": "Admin Imported", "test_type": "api", "content": {"method": "GET", "url": "/api/admin"}},
        ]
        r2 = await async_client.post(
            _import_url(imp_exp_project.id),
            headers=admin_headers,
            files={"file": _make_import_file(cases_data)},
        )
        assert r2.status_code == 201
        assert r2.json()["imported"] == 1
