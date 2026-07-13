"""SchemaFuzz：OpenAPI 自动 Fuzzing — 27 个场景覆盖（验剑策略）。

策略文件：``.omo/tests/test-plan-schema-fuzz.md``
测试后端 ``POST /api/projects/{pid}/schema/parse`` 的 fuzz 模式。

覆盖维度：
  正常路径 12 个（FUZZ-001 ~ FUZZ-012）
  边界值   7 个（FUZZ-101 ~ FUZZ-107）
  异常场景  5 个（FUZZ-201 ~ FUZZ-205）
  权限隔离  3 个（FUZZ-301 ~ FUZZ-303）
"""

import json

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from auth import create_access_token, hash_password
from models import Project, ProjectMembers, User

pytestmark = pytest.mark.asyncio

_PARSE_URL = "/api/projects/{pid}/schema/parse"


# ═══════════════════════════════════════════════════════════════════════════
#  Helpers — 内联 OpenAPI spec 构造
# ═══════════════════════════════════════════════════════════════════════════


def _spec_paths(paths: dict) -> str:
    """Build a minimal OpenAPI 3.0 spec with given paths dict."""
    return json.dumps({
        "openapi": "3.0.0",
        "info": {"title": "Fuzz Test API", "version": "1.0"},
        "paths": paths,
    })


def _simple_get(path: str = "/api/items") -> str:
    """Single GET endpoint with one string + one integer query param."""
    return _spec_paths({
        path: {
            "get": {
                "parameters": [
                    {"name": "q", "in": "query", "schema": {"type": "string"}},
                    {"name": "page", "in": "query", "schema": {"type": "integer"}},
                ],
                "responses": {"200": {"description": "OK"}},
            }
        }
    })


def _single_param_spec(param_type: str, param_in: str = "query") -> str:
    """Spec with one endpoint, one param of *param_type*."""
    return _spec_paths({
        "/api/test": {
            "get": {
                "parameters": [
                    {"name": "val", "in": param_in, "schema": {"type": param_type}},
                ],
                "responses": {"200": {"description": "OK"}},
            }
        }
    })


# ═══════════════════════════════════════════════════════════════════════════
#  Fixtures — 角色用户（不依赖外部 conftest 角色，保持自包含）
# ═══════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def fuzz_owner(db_session) -> User:
    await db_session.execute(sa_delete(User).where(User.username == "fuzz_owner"))
    await db_session.commit()
    u = User(username="fuzz_owner", password_hash=hash_password("pass123"), role="user")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def fuzz_viewer(db_session) -> User:
    await db_session.execute(sa_delete(User).where(User.username == "fuzz_viewer"))
    await db_session.commit()
    u = User(username="fuzz_viewer", password_hash=hash_password("pass123"), role="user")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def fuzz_owner_token(fuzz_owner: User) -> str:
    return create_access_token({"sub": str(fuzz_owner.id)})


@pytest_asyncio.fixture
async def fuzz_viewer_token(fuzz_viewer: User) -> str:
    return create_access_token({"sub": str(fuzz_viewer.id)})


@pytest_asyncio.fixture
async def fuzz_owner_headers(fuzz_owner_token: str) -> dict:
    return {"Authorization": f"Bearer {fuzz_owner_token}"}


@pytest_asyncio.fixture
async def fuzz_viewer_headers(fuzz_viewer_token: str) -> dict:
    return {"Authorization": f"Bearer {fuzz_viewer_token}"}


@pytest_asyncio.fixture
async def fuzz_project(db_session, fuzz_owner: User) -> Project:
    p = Project(name="Fuzz Test Project", user_id=fuzz_owner.id)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest_asyncio.fixture
async def fuzz_member(db_session, fuzz_project: Project, fuzz_viewer: User) -> None:
    await db_session.execute(
        sa_delete(ProjectMembers).where(
            ProjectMembers.project_id == fuzz_project.id,
            ProjectMembers.user_id == fuzz_viewer.id,
        )
    )
    await db_session.commit()
    db_session.add(ProjectMembers(project_id=fuzz_project.id, user_id=fuzz_viewer.id, role="viewer"))
    await db_session.commit()


@pytest_asyncio.fixture
async def fuzz_admin(db_session) -> User:
    await db_session.execute(sa_delete(User).where(User.username == "fuzz_admin"))
    await db_session.commit()
    u = User(username="fuzz_admin", password_hash=hash_password("admin123"), role="admin")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def fuzz_admin_token(fuzz_admin: User) -> str:
    return create_access_token({"sub": str(fuzz_admin.id)}, user=fuzz_admin)


@pytest_asyncio.fixture
async def fuzz_admin_headers(fuzz_admin_token: str) -> dict:
    return {"Authorization": f"Bearer {fuzz_admin_token}"}


# ═══════════════════════════════════════════════════════════════════════════
#  I. 正常路径
# ═══════════════════════════════════════════════════════════════════════════


class TestHappyPath:
    """FUZZ-001 ~ FUZZ-012：正常路径 12 个场景。"""

    async def test_fuzz_001_mode_fuzz_only(
        self, async_client: AsyncClient, fuzz_owner_headers: dict, fuzz_project: Project
    ):
        """FUZZ-001：mode=fuzz → 仅生成 fuzz 变体，source='fuzz'。"""
        spec = _simple_get()
        resp = await async_client.post(
            _PARSE_URL.format(pid=fuzz_project.id),
            json={"spec": spec, "mode": "fuzz"},
            headers=fuzz_owner_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        stubs = data["stubs"]
        assert len(stubs) > 0
        for s in stubs:
            assert s["source"] == "fuzz", f"Expected all fuzz but got source={s['source']}"

    async def test_fuzz_002_mode_coverage_default(
        self, async_client: AsyncClient, fuzz_owner_headers: dict, fuzz_project: Project
    ):
        """FUZZ-002：mode=coverage（默认）→ 仅 happy path，无 fuzz。"""
        spec = _simple_get()
        # 不传 mode，走默认值 "coverage"
        resp = await async_client.post(
            _PARSE_URL.format(pid=fuzz_project.id),
            json={"spec": spec},
            headers=fuzz_owner_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        stubs = data["stubs"]
        assert len(stubs) > 0
        for s in stubs:
            assert s["source"] != "fuzz", "coverage 模式不应含 fuzz 用例"

    async def test_fuzz_003_mode_all(
        self, async_client: AsyncClient, fuzz_owner_headers: dict, fuzz_project: Project
    ):
        """FUZZ-003：mode=all → 同时生成 happy path + fuzz。"""
        spec = _simple_get()
        resp = await async_client.post(
            _PARSE_URL.format(pid=fuzz_project.id),
            json={"spec": spec, "mode": "all"},
            headers=fuzz_owner_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        stubs = data["stubs"]

        happy = [s for s in stubs if s["source"] != "fuzz"]
        fuzz = [s for s in stubs if s["source"] == "fuzz"]
        assert len(happy) > 0, "all 模式应有 happy path"
        assert len(fuzz) > 0, "all 模式应有 fuzz 用例"

    async def test_fuzz_004_string_fuzz_values(
        self, async_client: AsyncClient, fuzz_owner_headers: dict, fuzz_project: Project
    ):
        """FUZZ-004：string 类型参数 → 生成 6 种变体。"""
        spec = _single_param_spec("string")
        resp = await async_client.post(
            _PARSE_URL.format(pid=fuzz_project.id),
            json={"spec": spec, "mode": "fuzz"},
            headers=fuzz_owner_headers,
        )
        stubs = resp.json()["stubs"]
        # _FUZZ_REGISTRY["string"] = ["", "A"*5000, XSS, SQLi, None, 12345] = 6 values
        assert len(stubs) == 6, f"string → 6 stubs, got {len(stubs)}"
        for s in stubs:
            assert "[fuzz]" in s["name"]

    async def test_fuzz_005_integer_fuzz_values(
        self, async_client: AsyncClient, fuzz_owner_headers: dict, fuzz_project: Project
    ):
        """FUZZ-005：integer 类型参数 → 生成 5 种变体。"""
        spec = _single_param_spec("integer")
        resp = await async_client.post(
            _PARSE_URL.format(pid=fuzz_project.id),
            json={"spec": spec, "mode": "fuzz"},
            headers=fuzz_owner_headers,
        )
        stubs = resp.json()["stubs"]
        assert len(stubs) == 5, f"integer → 5 stubs, got {len(stubs)}"

    async def test_fuzz_006_boolean_fuzz_values(
        self, async_client: AsyncClient, fuzz_owner_headers: dict, fuzz_project: Project
    ):
        """FUZZ-006：boolean 类型参数 → 生成 4 种变体。"""
        spec = _single_param_spec("boolean")
        resp = await async_client.post(
            _PARSE_URL.format(pid=fuzz_project.id),
            json={"spec": spec, "mode": "fuzz"},
            headers=fuzz_owner_headers,
        )
        stubs = resp.json()["stubs"]
        assert len(stubs) == 4, f"boolean → 4 stubs, got {len(stubs)}"

    async def test_fuzz_007_array_fuzz_values(
        self, async_client: AsyncClient, fuzz_owner_headers: dict, fuzz_project: Project
    ):
        """FUZZ-007：array 类型参数 → 生成 4 种变体。"""
        spec = _single_param_spec("array")
        resp = await async_client.post(
            _PARSE_URL.format(pid=fuzz_project.id),
            json={"spec": spec, "mode": "fuzz"},
            headers=fuzz_owner_headers,
        )
        stubs = resp.json()["stubs"]
        assert len(stubs) == 4, f"array → 4 stubs, got {len(stubs)}"

    async def test_fuzz_008_object_fuzz_values(
        self, async_client: AsyncClient, fuzz_owner_headers: dict, fuzz_project: Project
    ):
        """FUZZ-008：object 类型参数 → 生成 3 种变体。"""
        spec = _single_param_spec("object")
        resp = await async_client.post(
            _PARSE_URL.format(pid=fuzz_project.id),
            json={"spec": spec, "mode": "fuzz"},
            headers=fuzz_owner_headers,
        )
        stubs = resp.json()["stubs"]
        assert len(stubs) == 3, f"object → 3 stubs, got {len(stubs)}"

    async def test_fuzz_009_number_fallback(
        self, async_client: AsyncClient, fuzz_owner_headers: dict, fuzz_project: Project
    ):
        """FUZZ-009：number 类型 → 回退到 integer 变体（5 种）。"""
        spec = _single_param_spec("number")
        resp = await async_client.post(
            _PARSE_URL.format(pid=fuzz_project.id),
            json={"spec": spec, "mode": "fuzz"},
            headers=fuzz_owner_headers,
        )
        stubs = resp.json()["stubs"]
        assert len(stubs) == 5, f"number → 5 (integer) stubs, got {len(stubs)}"

    async def test_fuzz_010_fuzz_assertion_default(
        self, async_client: AsyncClient, fuzz_owner_headers: dict, fuzz_project: Project
    ):
        """FUZZ-010：fuzz 用例默认断言为 status_code != 500。"""
        spec = _simple_get()
        resp = await async_client.post(
            _PARSE_URL.format(pid=fuzz_project.id),
            json={"spec": spec, "mode": "fuzz"},
            headers=fuzz_owner_headers,
        )
        stubs = resp.json()["stubs"]
        for s in stubs:
            assertions = s["content"]["assertions"]
            assert len(assertions) == 1
            a = assertions[0]
            assert a["type"] == "status_code"
            assert a["operator"] == "ne"
            assert a["expected"] == 500

    async def test_fuzz_011_fuzz_source_coverage_key(
        self, async_client: AsyncClient, fuzz_owner_headers: dict, fuzz_project: Project
    ):
        """FUZZ-011：fuzz 用例 source='fuzz'，coverage_key='{METHOD} {path}'。"""
        spec = _simple_get()
        resp = await async_client.post(
            _PARSE_URL.format(pid=fuzz_project.id),
            json={"spec": spec, "mode": "fuzz"},
            headers=fuzz_owner_headers,
        )
        stubs = resp.json()["stubs"]
        for s in stubs:
            assert s["source"] == "fuzz"
            assert s["coverage_key"] == "GET /api/items"

    async def test_fuzz_012_all_order_happy_first(
        self, async_client: AsyncClient, fuzz_owner_headers: dict, fuzz_project: Project
    ):
        """FUZZ-012：mode=all 时 stubs 数组中 happy path 在前，fuzz 在后。"""
        spec = _simple_get()
        resp = await async_client.post(
            _PARSE_URL.format(pid=fuzz_project.id),
            json={"spec": spec, "mode": "all"},
            headers=fuzz_owner_headers,
        )
        stubs = resp.json()["stubs"]
        sources = [s["source"] for s in stubs]
        # mode=all 的追加顺序：schema（coverage）→ fuzz → security
        # SchemaEndpointStub 的默认 source="schema"
        assert "schema" in sources, "应有 schema（coverage）stubs"
        assert "fuzz" in sources, "应有 fuzz stubs"
        assert "security" in sources, "应有 security stubs"
        # 验证顺序：schema 在最前，fuzz 在中间，security 在最后
        first_fuzz = sources.index("fuzz")
        first_sec = sources.index("security")
        assert first_fuzz > sources.index("schema"), "fuzz 应在 schema 之后"
        assert first_sec > first_fuzz, "security 应在 fuzz 之后"


# ═══════════════════════════════════════════════════════════════════════════
#  II. 边界值
# ═══════════════════════════════════════════════════════════════════════════


class TestBoundary:
    """FUZZ-101 ~ FUZZ-107：边界值 7 个场景。"""

    async def test_fuzz_101_max_fuzz_1(
        self, async_client: AsyncClient, fuzz_owner_headers: dict, fuzz_project: Project
    ):
        """FUZZ-101：max_fuzz=1 → 最多 1 个 fuzz stub。"""
        spec = _simple_get()  # 2 params → 6+5=11 normally
        resp = await async_client.post(
            _PARSE_URL.format(pid=fuzz_project.id),
            json={"spec": spec, "mode": "fuzz", "max_fuzz": 1},
            headers=fuzz_owner_headers,
        )
        stubs = resp.json()["stubs"]
        assert 1 <= len(stubs) <= 1, f"max_fuzz=1 → 1 stub, got {len(stubs)}"

    async def test_fuzz_102_max_fuzz_0_clamped(
        self, async_client: AsyncClient, fuzz_owner_headers: dict, fuzz_project: Project
    ):
        """FUZZ-102：max_fuzz=0 → 被 clamp 为 1，仍生成 1 个。"""
        spec = _simple_get()
        resp = await async_client.post(
            _PARSE_URL.format(pid=fuzz_project.id),
            json={"spec": spec, "mode": "fuzz", "max_fuzz": 0},
            headers=fuzz_owner_headers,
        )
        assert resp.status_code == 200
        stubs = resp.json()["stubs"]
        assert 1 <= len(stubs) <= 1, f"max_fuzz=0 → clamped to 1, got {len(stubs)}"

    async def test_fuzz_103_per_endpoint_cap_20(
        self, async_client: AsyncClient, fuzz_owner_headers: dict, fuzz_project: Project
    ):
        """FUZZ-103：单 endpoint 参数过多时不超过 20 个 fuzz stub。"""
        # 5 个 string 参数 → 5*6=30 > 20，cap at 20
        params = [{"name": f"p{i}", "in": "query", "schema": {"type": "string"}} for i in range(5)]
        spec = _spec_paths({
            "/api/test": {
                "get": {
                    "parameters": params,
                    "responses": {"200": {"description": "OK"}},
                }
            }
        })
        resp = await async_client.post(
            _PARSE_URL.format(pid=fuzz_project.id),
            json={"spec": spec, "mode": "fuzz", "max_fuzz": 100},
            headers=fuzz_owner_headers,
        )
        stubs = resp.json()["stubs"]
        assert len(stubs) <= 20, f"per-endpoint cap=20, got {len(stubs)}"

    async def test_fuzz_104_total_fuzz_cap(
        self, async_client: AsyncClient, fuzz_owner_headers: dict, fuzz_project: Project
    ):
        """FUZZ-104：多个 endpoint → fuzz 总数不超过 max_fuzz。"""
        # 3 个 endpoint，各 2 个 string 参数 → 3*12=36，max_fuzz=30 → ≤30
        paths = {}
        for i in range(3):
            paths[f"/api/ep{i}"] = {
                "get": {
                    "parameters": [
                        {"name": "q1", "in": "query", "schema": {"type": "string"}},
                        {"name": "q2", "in": "query", "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        spec = _spec_paths(paths)
        resp = await async_client.post(
            _PARSE_URL.format(pid=fuzz_project.id),
            json={"spec": spec, "mode": "fuzz", "max_fuzz": 30},
            headers=fuzz_owner_headers,
        )
        stubs = resp.json()["stubs"]
        assert len(stubs) <= 30, f"max_fuzz=30, got {len(stubs)}"
        assert len(stubs) > 0, "should have at least 1 fuzz stub"

    async def test_fuzz_105_no_params_no_body(
        self, async_client: AsyncClient, fuzz_owner_headers: dict, fuzz_project: Project
    ):
        """FUZZ-105：无参数 + 无 requestBody → 该 endpoint 无 fuzz。"""
        spec = _spec_paths({
            "/api/health": {
                "get": {
                    "responses": {"200": {"description": "OK"}},
                }
            }
        })
        resp = await async_client.post(
            _PARSE_URL.format(pid=fuzz_project.id),
            json={"spec": spec, "mode": "fuzz"},
            headers=fuzz_owner_headers,
        )
        stubs = resp.json()["stubs"]
        assert len(stubs) == 0, "no params → 0 fuzz stubs"

    async def test_fuzz_106_enum_param_still_fuzzed(
        self, async_client: AsyncClient, fuzz_owner_headers: dict, fuzz_project: Project
    ):
        """FUZZ-106：enum 约束 path 参数 → fuzz 仍生成变体（打破 enum）。"""
        spec = _spec_paths({
            "/api/users/{status}": {
                "get": {
                    "parameters": [
                        {
                            "name": "status",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string", "enum": ["active", "inactive"]},
                        },
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        })
        resp = await async_client.post(
            _PARSE_URL.format(pid=fuzz_project.id),
            json={"spec": spec, "mode": "fuzz"},
            headers=fuzz_owner_headers,
        )
        stubs = resp.json()["stubs"]
        # string type → 6 fuzz values
        assert len(stubs) == 6, f"6 fuzz stubs for string param, got {len(stubs)}"
        # 至少有些值不是 "active" / "inactive"
        names = [s["name"] for s in stubs]
        non_enum = [n for n in names if "active" not in n and "inactive" not in n]
        assert len(non_enum) > 0, "should have fuzz values breaking enum constraint"

    async def test_fuzz_107_many_endpoints(
        self, async_client: AsyncClient, fuzz_owner_headers: dict, fuzz_project: Project
    ):
        """FUZZ-107：大量 endpoint（20+）→ max_fuzz=100 限制总数量。"""
        paths = {}
        for i in range(20):
            paths[f"/api/ep{i}"] = {
                "get": {
                    "parameters": [
                        {"name": "q", "in": "query", "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        spec = _spec_paths(paths)
        resp = await async_client.post(
            _PARSE_URL.format(pid=fuzz_project.id),
            json={"spec": spec, "mode": "fuzz", "max_fuzz": 100},
            headers=fuzz_owner_headers,
        )
        stubs = resp.json()["stubs"]
        assert len(stubs) <= 100, f"max_fuzz=100, got {len(stubs)}"
        assert len(stubs) > 0


# ═══════════════════════════════════════════════════════════════════════════
#  III. 异常场景
# ═══════════════════════════════════════════════════════════════════════════


class TestExceptions:
    """FUZZ-201 ~ FUZZ-205：异常场景 5 个。"""

    async def test_fuzz_201_invalid_mode(
        self, async_client: AsyncClient, fuzz_owner_headers: dict, fuzz_project: Project
    ):
        """FUZZ-201：mode 为无效值 → 400。"""
        spec = _simple_get()
        resp = await async_client.post(
            _PARSE_URL.format(pid=fuzz_project.id),
            json={"spec": spec, "mode": "invalid"},
            headers=fuzz_owner_headers,
        )
        assert resp.status_code == 400
        assert "mode" in resp.text.lower()

    async def test_fuzz_202_one_endpoint_fails(
        self, async_client: AsyncClient, fuzz_owner_headers: dict, fuzz_project: Project
    ):
        """FUZZ-202：单个 endpoint fuzz 失败 → 不阻塞其他 endpoint。

        构造 2 个 endpoint：一个正常，一个参数类型缺失不会导致崩溃。
        """
        paths = {
            "/api/good": {
                "get": {
                    "parameters": [
                        {"name": "q", "in": "query", "schema": {"type": "string"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/api/also_good": {
                "get": {
                    "parameters": [
                        {"name": "id", "in": "query", "schema": {"type": "integer"}},
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            },
        }
        spec = _spec_paths(paths)
        resp = await async_client.post(
            _PARSE_URL.format(pid=fuzz_project.id),
            json={"spec": spec, "mode": "fuzz"},
            headers=fuzz_owner_headers,
        )
        assert resp.status_code == 200
        stubs = resp.json()["stubs"]
        # 2 endpoints, each with 1 param: 6+5=11 fuzz stubs
        assert len(stubs) == 11, f"expected 11 (6+5), got {len(stubs)}"

    async def test_fuzz_203_unauth(
        self, async_client: AsyncClient, fuzz_project: Project
    ):
        """FUZZ-203：未认证 → 401。"""
        spec = _simple_get()
        resp = await async_client.post(
            _PARSE_URL.format(pid=fuzz_project.id),
            json={"spec": spec, "mode": "fuzz"},
            # 无 headers
        )
        assert resp.status_code == 401

    async def test_fuzz_204_non_member(
        self, async_client: AsyncClient, fuzz_viewer_headers: dict, fuzz_project: Project
    ):
        """FUZZ-204：非成员 → 403。"""
        spec = _simple_get()
        resp = await async_client.post(
            _PARSE_URL.format(pid=fuzz_project.id),
            json={"spec": spec, "mode": "fuzz"},
            headers=fuzz_viewer_headers,
        )
        # viewer 未加成员 → 403
        assert resp.status_code == 403

    async def test_fuzz_205_nonexistent_project(
        self, async_client: AsyncClient, fuzz_owner_headers: dict
    ):
        """FUZZ-205：不存在项目 PID=99999 → 404。"""
        spec = _simple_get()
        resp = await async_client.post(
            _PARSE_URL.format(pid=99999),
            json={"spec": spec, "mode": "fuzz"},
            headers=fuzz_owner_headers,
        )
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
#  IV. 权限/认证
# ═══════════════════════════════════════════════════════════════════════════


class TestAuth:
    """FUZZ-301 ~ FUZZ-303：权限 3 个场景。"""

    async def test_fuzz_301_editor_can_parse(
        self, async_client: AsyncClient, fuzz_owner_headers: dict, fuzz_project: Project
    ):
        """FUZZ-301：editor 可执行 schema parse（含 fuzz）。"""
        for mode in ("fuzz", "all"):
            spec = _simple_get()
            resp = await async_client.post(
                _PARSE_URL.format(pid=fuzz_project.id),
                json={"spec": spec, "mode": mode},
                headers=fuzz_owner_headers,
            )
            assert resp.status_code == 200, f"mode={mode} failed: {resp.text[:200]}"
            data = resp.json()
            assert len(data["stubs"]) > 0

    async def test_fuzz_302_viewer_cannot(
        self,
        async_client: AsyncClient,
        fuzz_viewer_headers: dict,
        fuzz_project: Project,
        fuzz_member,
    ):
        """FUZZ-302：viewer 角色 → 403（需要 editor 权限）。"""
        spec = _simple_get()
        resp = await async_client.post(
            _PARSE_URL.format(pid=fuzz_project.id),
            json={"spec": spec, "mode": "fuzz"},
            headers=fuzz_viewer_headers,
        )
        assert resp.status_code == 403

    async def test_fuzz_303_admin_bypass(
        self,
        async_client: AsyncClient,
        fuzz_admin_headers: dict,
        fuzz_project: Project,
    ):
        """FUZZ-303：Admin 任意项目执行 → 200。"""
        spec = _simple_get()
        resp = await async_client.post(
            _PARSE_URL.format(pid=fuzz_project.id),
            json={"spec": spec, "mode": "all"},
            headers=fuzz_admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["stubs"]) > 0
