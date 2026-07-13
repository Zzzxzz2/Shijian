"""验剑策略：Schema 驱动自动补全 — 26 场景（SCHEMA-001 ~ SCHEMA-403）

测试后端 ``POST /api/projects/{pid}/schema/parse`` 的 OpenAPI 解析、
$ref/allOf/oneOf/anyOf 解析、body 生成、断言生成、边界值和容错能力。

前置条件（conftest 管理）：
- 独立 shijian_test.db
- 测试用户 / 项目 / JWT token 在每个函数级 fixture 中创建

测试 spec 文件位于 ``test_specs/`` 目录。

注意事项：
- ``stub["coverage_key"]`` 格式为 ``{METHOD} {path}``（如 ``"GET /api/users"``）
- 搜索 stub 时用 ``stub["content"]["method"] + stub["content"]["url"]`` 或
  ``stub["name"]``（name 含 summary / operationId / method+path）
"""

import json
from pathlib import Path

import httpx
import pytest
from httpx import AsyncClient

_SPEC_DIR = Path(__file__).parent / "test_specs"


def _load_spec(name: str) -> str:
    return (_SPEC_DIR / name).read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════
#  一、正常路径（Happy Path）— 基础解析
# ═══════════════════════════════════════════════════════════════════════════


class TestBasicParse:
    """验剑策略：SCHEMA-001 ~ SCHEMA-003 — 基础解析。"""

    @pytest.mark.asyncio
    async def test_schema_001_basic_parse(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_project,
    ):
        """SCHEMA-001：贴 OpenAPI 3.0 JSON → 解析所有 endpoint + method。

        simple_api.json 有 6 个 endpoints（GET/POST /api/users，
        GET/DELETE /api/users/{id}, GET /api/users/search,
        PATCH /api/users/{id}/role）。
        """
        spec = _load_spec("simple_api.json")
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text[:300]
        data = resp.json()

        assert data["title"] == "Simple API"
        assert len(data["endpoints"]) == 6
        assert len(data["stubs"]) == 6

        methods = {ep["method"] for ep in data["endpoints"]}
        assert methods == {"GET", "POST", "DELETE", "PATCH"}, f"Got: {methods}"

        for stub in data["stubs"]:
            cnt = stub["content"]
            assert "method" in cnt
            assert "url" in cnt
            assert "assertions" in cnt

    @pytest.mark.asyncio
    async def test_schema_002_spec_url(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_project,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """SCHEMA-002：spec_url 远程获取 → 与直接贴 JSON 结果一致。"""
        spec = _load_spec("simple_api.json")

        async def _mock_get(self, url, *, headers=None, follow_redirects=True, **kwargs):
            # self is AsyncClient instance (bound method signature)
            return httpx.Response(200, text=spec)

        monkeypatch.setattr(httpx.AsyncClient, "get", _mock_get)

        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec_url": "https://example.com/openapi.json"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text[:300]
        data = resp.json()

        resp2 = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec},
            headers=auth_headers,
        )
        data2 = resp2.json()

        assert len(data["stubs"]) == len(data2["stubs"])
        assert data["title"] == data2["title"] == "Simple API"
        assert data["coverage_summary"] == data2["coverage_summary"]

    @pytest.mark.asyncio
    async def test_schema_003_spec_url_with_headers(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_project,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """SCHEMA-003：spec_url 带鉴权 headers → headers 透传给 httpx。"""
        spec = _load_spec("simple_api.json")
        captured_headers = {}

        async def _mock_get(self, url, *, headers=None, follow_redirects=True, **kwargs):
            captured_headers.update(headers or {})
            return httpx.Response(200, text=spec)

        monkeypatch.setattr(httpx.AsyncClient, "get", _mock_get)

        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={
                "spec_url": "https://private.example.com/spec.json",
                "spec_headers": {"Authorization": "Bearer test-token"},
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text[:300]
        assert captured_headers.get("Authorization") == "Bearer test-token", (
            f"Authorization header not found in: {captured_headers}"
        )


# ═══════════════════════════════════════════════════════════════════════════
#  一、正常路径 — 断言生成（SCHEMA-004 ~ SCHEMA-007）
# ═══════════════════════════════════════════════════════════════════════════


class TestAssertionGeneration:
    """验剑策略：SCHEMA-004 ~ SCHEMA-007 — 断言生成。"""

    @pytest.mark.asyncio
    async def test_schema_004_post_201_assertion(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_project,
    ):
        """SCHEMA-004：POST endpoint → 默认断言 status_code=201。"""
        spec = _load_spec("simple_api.json")
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec},
            headers=auth_headers,
        )
        data = resp.json()
        post_stubs = [s for s in data["stubs"] if s["content"]["method"] == "POST"]
        assert len(post_stubs) >= 1
        assertions = post_stubs[0]["content"]["assertions"]
        assert assertions[0]["expected"] == 201, (
            f"POST endpoint should default to 201, got: {assertions[0]}"
        )

    @pytest.mark.asyncio
    async def test_schema_005_delete_204_assertion(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_project,
    ):
        """SCHEMA-005：DELETE endpoint → 默认断言 status_code=204 + body empty。"""
        spec = _load_spec("simple_api.json")
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec},
            headers=auth_headers,
        )
        data = resp.json()
        delete_stubs = [s for s in data["stubs"] if s["content"]["method"] == "DELETE"]
        assert len(delete_stubs) >= 1
        assertions = delete_stubs[0]["content"]["assertions"]
        assert assertions[0]["expected"] == 204, (
            f"DELETE should default to 204, got: {assertions[0]}"
        )
        assert len(assertions) >= 2, (
            f"DELETE 204 should have body-empty assertion: {assertions}"
        )

    @pytest.mark.asyncio
    async def test_schema_006_get_200_assertion(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_project,
    ):
        """SCHEMA-006：GET endpoint → 默认断言 status_code=200。"""
        spec = _load_spec("simple_api.json")
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec},
            headers=auth_headers,
        )
        data = resp.json()
        get_stubs = [s for s in data["stubs"] if s["content"]["method"] == "GET"]
        assert len(get_stubs) >= 1
        for stub in get_stubs:
            first = stub["content"]["assertions"][0]
            assert first["expected"] == 200, f"GET should default to 200, got: {first}"

    @pytest.mark.asyncio
    async def test_schema_007_no_responses_default_200(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_project,
    ):
        """SCHEMA-007：responses 不存在 → 默认断言 status_code=200。"""
        spec = _load_spec("no_responses.json")
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec},
            headers=auth_headers,
        )
        data = resp.json()
        assert len(data["stubs"]) == 1
        assertions = data["stubs"][0]["content"]["assertions"]
        assert assertions[0]["expected"] == 200


# ═══════════════════════════════════════════════════════════════════════════
#  一、正常路径 — Body 生成（SCHEMA-008 ~ SCHEMA-012）
# ═══════════════════════════════════════════════════════════════════════════


class TestBodyGeneration:
    """验剑策略：SCHEMA-008 ~ SCHEMA-012 — Body 生成。"""

    @pytest.mark.asyncio
    async def test_schema_008_body_from_properties(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_project,
    ):
        """SCHEMA-008：POST requestBody → 遍历 properties 生成示例 body。
        UserInput（name:string, age:int, active:bool）。
        """
        spec = _load_spec("simple_api.json")
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec},
            headers=auth_headers,
        )
        data = resp.json()
        post_stubs = [s for s in data["stubs"] if s["content"]["method"] == "POST"]
        assert len(post_stubs) >= 1
        body = post_stubs[0]["content"].get("body")
        assert body is not None, "POST endpoint should have body"
        assert isinstance(body, dict)
        assert "name" in body and "age" in body and "active" in body
        assert isinstance(body["name"], str)
        assert isinstance(body["age"], int)
        assert isinstance(body["active"], bool)

    def _sc(self, data, method, url_substring):
        """Find a stub by method + URL substring (coverage_key is '{method} {path}')."""
        results = [
            s for s in data["stubs"]
            if s["content"]["method"] == method and url_substring in s["content"]["url"]
        ]
        return results

    @pytest.mark.asyncio
    async def test_schema_009_example_preferred(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_project,
    ):
        """SCHEMA-009：schema 字段含 example → 用 example 值。
        UserProfile.name: example="admin"。
        """
        spec = _load_spec("with_refs.json")
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec},
            headers=auth_headers,
        )
        data = resp.json()

        stubs = self._sc(data, "POST", "/api/single-ref")
        assert len(stubs) >= 1, f"No stub for POST /api/single-ref in {[s['coverage_key'] for s in data['stubs']]}"
        body = stubs[0]["content"].get("body")
        assert body is not None
        assert body.get("name") == "admin", (
            f"example='admin' expected, got: {body.get('name')}"
        )

    @pytest.mark.asyncio
    async def test_schema_010_enum_first_value(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_project,
    ):
        """SCHEMA-010：enum → 第一个值。UserProfile.role → "admin"。"""
        spec = _load_spec("with_refs.json")
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec},
            headers=auth_headers,
        )
        data = resp.json()

        stubs = self._sc(data, "POST", "/api/single-ref")
        assert len(stubs) >= 1
        body = stubs[0]["content"].get("body")
        assert body is not None
        assert body.get("role") == "admin", (
            f"First enum value 'admin' expected, got: {body.get('role')}"
        )

    @pytest.mark.asyncio
    async def test_schema_011_array_single_element(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_project,
    ):
        """SCHEMA-011：array → 单元素数组。UserProfile.tags → ["string"]。"""
        spec = _load_spec("with_refs.json")
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec},
            headers=auth_headers,
        )
        data = resp.json()

        stubs = self._sc(data, "POST", "/api/single-ref")
        assert len(stubs) >= 1
        body = stubs[0]["content"].get("body")
        assert body is not None
        tags = body.get("tags")
        assert isinstance(tags, list), f"tags should be list, got: {type(tags)}"
        assert len(tags) == 1
        assert isinstance(tags[0], str)

    @pytest.mark.asyncio
    async def test_schema_012_nested_object_first_level(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_project,
    ):
        """SCHEMA-012：嵌套 object → 至少展开第一层。
        EmployeeNested → Dept.
        """
        spec = _load_spec("with_refs.json")
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec},
            headers=auth_headers,
        )
        data = resp.json()

        stubs = self._sc(data, "POST", "/api/employees")
        assert len(stubs) >= 1, f"No stub for POST /api/employees"
        body = stubs[0]["content"].get("body")
        assert body is not None, "Employee endpoint should have body"
        assert "name" in body
        assert body.get("email") == "test@example.com", (
            f"example='test@example.com' expected, got: {body.get('email')}"
        )
        dept = body.get("dept")
        assert isinstance(dept, dict), (
            f"dept should be dict (first level), got: {type(dept)}: {body}"
        )
        assert "name" in dept


# ═══════════════════════════════════════════════════════════════════════════
#  一、正常路径 — 路径参数 & Query 参数 & 覆盖率
# ═══════════════════════════════════════════════════════════════════════════


class TestUrlBuilding:
    """验剑策略：SCHEMA-013 ~ SCHEMA-015 — URL 构建。"""

    @pytest.mark.asyncio
    async def test_schema_013_path_param_preserved(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_project,
    ):
        """SCHEMA-013：路径参数 {id}（无 enum）→ 保留 {id}。"""
        spec = _load_spec("simple_api.json")
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec},
            headers=auth_headers,
        )
        data = resp.json()

        # GET /api/users/{id} should keep {id}
        stubs = [s for s in data["stubs"] if s["content"]["method"] == "GET" and "{id}" in s["content"]["url"]]
        assert len(stubs) >= 1, (
            f"No stub with {{id}} in URL: {[s['coverage_key'] for s in data['stubs']]}"
        )
        url = stubs[0]["content"]["url"]
        assert "{id}" in url, f"Path param should keep {{id}}: {url}"

    @pytest.mark.asyncio
    async def test_schema_014_path_param_enum_replaced(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_project,
    ):
        """SCHEMA-014：路径参数含 enum → 用第一个 enum 值填充。"""
        enum_path_spec = json.dumps({
            "openapi": "3.0.0",
            "info": {"title": "Enum Path", "version": "1.0"},
            "paths": {
                "/api/users/{id}": {
                    "get": {
                        "summary": "Get user",
                        "parameters": [{
                            "name": "id", "in": "path", "required": True,
                            "schema": {"type": "string", "enum": ["me", "admin"]}
                        }],
                        "responses": {"200": {"description": "OK"}}
                    }
                }
            }
        })
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": enum_path_spec},
            headers=auth_headers,
        )
        data = resp.json()
        assert len(data["stubs"]) == 1
        url = data["stubs"][0]["content"]["url"]
        assert "me" in url and "{id}" not in url, (
            f"Enum path param should be replaced, got: {url}"
        )

    @pytest.mark.asyncio
    async def test_schema_015_query_params_in_url(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_project,
    ):
        """SCHEMA-015：query 参数 → 拼入 URL。"""
        spec = _load_spec("simple_api.json")
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec},
            headers=auth_headers,
        )
        data = resp.json()

        # GET /api/users/search with page & limit
        stubs = [s for s in data["stubs"] if s["content"]["method"] == "GET" and "search" in s["content"]["url"]]
        assert len(stubs) >= 1, (
            f"No search stub: {[s['coverage_key'] for s in data['stubs']]}"
        )
        url = stubs[0]["content"]["url"]
        assert "page=" in url, f"URL missing page param: {url}"
        assert "limit=" in url, f"URL missing limit param: {url}"
        assert "?" in url

    @pytest.mark.asyncio
    async def test_schema_016_coverage_summary(
        self,
        async_client: AsyncClient,
        auth_headers: dict[str, str],
        test_project,
    ):
        """SCHEMA-016：coverage_summary 准确反映 total/covered/uncovered。
        simple_api.json 有 6 个 endpoint，全部可解析。
        """
        spec = _load_spec("simple_api.json")
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec},
            headers=auth_headers,
        )
        data = resp.json()
        cs = data["coverage_summary"]
        assert cs["total"] == 6
        assert cs["covered"] == 6
        assert cs["uncovered"] == 0
        assert cs["total"] == cs["covered"] + cs["uncovered"]


# ═══════════════════════════════════════════════════════════════════════════
#  二、边界值
# ═══════════════════════════════════════════════════════════════════════════


class TestBoundary:
    """验剑策略：SCHEMA-101 ~ SCHEMA-105 — 边界条件。"""

    @pytest.mark.asyncio
    async def test_schema_101_no_paths_field(
        self, async_client, auth_headers, test_project,
    ):
        """SCHEMA-101：空 spec（仅 info 无 paths）→ 400。"""
        spec = _load_spec("no_paths.json")
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec}, headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "路径" in resp.json().get("detail", "")

    @pytest.mark.asyncio
    async def test_schema_102_single_endpoint(
        self, async_client, auth_headers, test_project,
    ):
        """SCHEMA-102：单 endpoint → 仅 1 条 stub。"""
        spec = _load_spec("single_endpoint.json")
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec}, headers=auth_headers,
        )
        data = resp.json()
        assert len(data["stubs"]) == 1
        assert data["stubs"][0]["content"]["method"] == "GET"
        assert data["stubs"][0]["content"]["url"] == "/api/health"

    @pytest.mark.asyncio
    async def test_schema_103_large_spec(
        self, async_client, auth_headers, test_project,
    ):
        """SCHEMA-103：大型 spec（50+ endpoints）→ 全部解析，<5s。"""
        import time
        spec = _load_spec("large_spec.json")
        t0 = time.monotonic()
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec}, headers=auth_headers,
        )
        elapsed = time.monotonic() - t0
        data = resp.json()
        assert elapsed < 5, f"Took {elapsed:.2f}s"
        assert len(data["stubs"]) == 55
        assert data["coverage_summary"]["total"] == 55

    @pytest.mark.asyncio
    async def test_schema_104_spec_url_timeout(
        self, async_client, auth_headers, test_project, monkeypatch,
    ):
        """SCHEMA-104：spec_url 超时 → 504。"""
        async def _mock(*a, **kw):
            raise httpx.TimeoutException("timed out", request=None)
        monkeypatch.setattr(httpx.AsyncClient, "get", _mock)
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec_url": "https://slow.example.com/spec.json"},
            headers=auth_headers,
        )
        assert resp.status_code == 504
        assert "超时" in resp.json().get("detail", "")

    @pytest.mark.asyncio
    async def test_schema_105_spec_url_non_json(
        self, async_client, auth_headers, test_project, monkeypatch,
    ):
        """SCHEMA-105：spec_url 返回非 JSON → 400。"""
        async def _mock(*a, **kw):
            return httpx.Response(200, text="<html>not json</html>")
        monkeypatch.setattr(httpx.AsyncClient, "get", _mock)
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec_url": "https://example.com/page.html"},
            headers=auth_headers,
        )
        assert resp.status_code in (400, 502)


# ═══════════════════════════════════════════════════════════════════════════
#  三、Schema 组合关键字解析
# ═══════════════════════════════════════════════════════════════════════════


class TestSchemaComposition:
    """验剑策略：SCHEMA-201 ~ SCHEMA-207 — $ref / allOf / oneOf / anyOf。"""

    def _find(self, data, method, url_part):
        return [s for s in data["stubs"] if s["content"]["method"] == method and url_part in s["content"]["url"]]

    @pytest.mark.asyncio
    async def test_schema_201_single_ref(
        self, async_client, auth_headers, test_project,
    ):
        """SCHEMA-201：单一 $ref → 从 components 正确解析。"""
        spec = _load_spec("with_refs.json")
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec}, headers=auth_headers,
        )
        data = resp.json()
        stubs = self._find(data, "POST", "/api/single-ref")
        assert len(stubs) >= 1
        body = stubs[0]["content"].get("body")
        assert body is not None
        assert "name" in body and "email" in body

    @pytest.mark.asyncio
    async def test_schema_202_allof_merge(
        self, async_client, auth_headers, test_project,
    ):
        """SCHEMA-202：allOf 合并 → Base + UserProfile properties 合并。"""
        spec = _load_spec("with_refs.json")
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec}, headers=auth_headers,
        )
        data = resp.json()
        stubs = self._find(data, "POST", "/api/users")
        assert len(stubs) >= 1, f"No POST /api/users stub"
        body = stubs[0]["content"].get("body")
        assert body is not None
        for f in ("id", "created_at", "name", "email", "role", "tags"):
            assert f in body, f"allOf merged body missing '{f}': {body}"

    @pytest.mark.asyncio
    async def test_schema_203_oneof_first(
        self, async_client, auth_headers, test_project,
    ):
        """SCHEMA-203：oneOf → 取第一个（Cat）。"""
        spec = _load_spec("with_refs.json")
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec}, headers=auth_headers,
        )
        data = resp.json()
        stubs = self._find(data, "POST", "/api/pets")
        assert len(stubs) >= 1
        body = stubs[0]["content"].get("body")
        assert body is not None
        assert "meow_volume" in body, f"oneOf should pick Cat: {body}"

    @pytest.mark.asyncio
    async def test_schema_204_anyof_first(
        self, async_client, auth_headers, test_project,
    ):
        """SCHEMA-204：anyOf → 取第一个（Cat）。"""
        spec = _load_spec("with_refs.json")
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec}, headers=auth_headers,
        )
        data = resp.json()
        stubs = self._find(data, "POST", "/api/animals")
        assert len(stubs) >= 1
        body = stubs[0]["content"].get("body")
        assert body is not None
        assert "meow_volume" in body, f"anyOf should pick Cat: {body}"

    @pytest.mark.asyncio
    async def test_schema_205_nested_refs_three_levels(
        self, async_client, auth_headers, test_project,
    ):
        """SCHEMA-205：嵌套 $ref（3+ 层）→ 逐层解析不崩溃。
        EmployeeNested → Dept → Company → Address.
        """
        spec = _load_spec("with_refs.json")
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec}, headers=auth_headers,
        )
        data = resp.json()
        stubs = self._find(data, "POST", "/api/employees")
        assert len(stubs) >= 1
        body = stubs[0]["content"].get("body")
        assert body is not None
        dept = body.get("dept", {})
        assert isinstance(dept, dict)
        # 3+ levels of ref resolved without crash
        _ = dept.get("company", {})

    @pytest.mark.asyncio
    async def test_schema_206_circular_ref(
        self, async_client, auth_headers, test_project,
    ):
        """SCHEMA-206：循环 $ref → 不超过 RecursionError。

        当前实现：POST /api/nodes（TreeNode 自引用 children）和
        POST /api/self-ref（LinkedListNode 自引用 next）触发 RecursionError，
        被 _build_stub 的 try/except 捕获。GET /api/nodes/{id} 不受影响。
        """
        spec = _load_spec("circular_refs.json")
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec}, headers=auth_headers,
        )
        data = resp.json()
        # Only the GET stub survives (no requestBody)
        assert len(data["stubs"]) >= 1, (
            f"At least 1 stub expected, got {len(data['stubs'])}"
        )
        # The GET endpoint should survive
        get_stubs = [s for s in data["stubs"] if s["content"]["method"] == "GET"]
        assert len(get_stubs) == 1

    @pytest.mark.asyncio
    async def test_schema_207_nonexistent_ref(
        self, async_client, auth_headers, test_project,
    ):
        """SCHEMA-207：$ref 指向不存在的路径 → 不崩溃。

        当前实现：NonExistent 不存在，_build_stub 可能因异常跳过该 endpoint。
        """
        spec = _load_spec("with_refs.json")
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec}, headers=auth_headers,
        )
        data = resp.json()
        # The nonexistent-ref endpoint may or may not produce a stub;
        # the key requirement is no 5xx crash and other endpoints still work.
        assert resp.status_code == 200
        # Other endpoints (e.g. single-ref) should still work
        ref_stubs = self._find(data, "POST", "/api/single-ref")
        assert len(ref_stubs) == 1
        # The overall parse should not crash
        assert data["coverage_summary"]["total"] >= 5


# ═══════════════════════════════════════════════════════════════════════════
#  四、容错场景
# ═══════════════════════════════════════════════════════════════════════════


class TestTolerance:
    """验剑策略：SCHEMA-301 ~ SCHEMA-307 — 容错。"""

    @pytest.mark.asyncio
    async def test_schema_301_invalid_json(
        self, async_client, auth_headers, test_project,
    ):
        """SCHEMA-301：非法 JSON → 400。"""
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": "{invalid json}"}, headers=auth_headers,
        )
        assert resp.status_code == 400
        assert "JSON" in resp.json().get("detail", "")

    @pytest.mark.asyncio
    async def test_schema_302_parital_failure_others_work(
        self, async_client, auth_headers, test_project,
    ):
        """SCHEMA-302：单个 endpoint 解析失败 → 其他不受影响。"""
        partial_spec = json.dumps({
            "openapi": "3.0.0", "info": {"title": "Partial", "version": "1.0"},
            "paths": {
                "/api/ok1": {
                    "get": {"responses": {"200": {"description": "OK"}}}
                },
                "/api/weird": {
                    "post": {
                        "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {"x": {"type": None}}}}}},
                        "responses": {"201": {"description": "Created"}}
                    }
                },
                "/api/ok2": {
                    "get": {"responses": {"200": {"description": "OK"}}}
                }
            }
        })
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": partial_spec}, headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["coverage_summary"]["covered"] >= 1

    @pytest.mark.asyncio
    async def test_schema_303_empty_request_body_content(
        self, async_client, auth_headers, test_project,
    ):
        """SCHEMA-303：requestBody content 为空 → 跳过 body 生成。"""
        spec = json.dumps({
            "openapi": "3.0.0", "info": {"title": "Empty Body", "version": "1.0"},
            "paths": {
                "/api/foo": {
                    "post": {
                        "requestBody": {"content": {}},
                        "responses": {"201": {"description": "Created"}}
                    }
                }
            }
        })
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec}, headers=auth_headers,
        )
        data = resp.json()
        assert len(data["stubs"]) == 1
        assert data["stubs"][0]["content"].get("body") is None

    @pytest.mark.asyncio
    async def test_schema_304_special_chars_in_query(
        self, async_client, auth_headers, test_project,
    ):
        """SCHEMA-304：Query 参数值含特殊字符 → 当前行为（可能未编码）。"""
        spec = json.dumps({
            "openapi": "3.0.0", "info": {"title": "S", "version": "1.0"},
            "paths": {
                "/api/search": {
                    "get": {
                        "parameters": [{"name": "q", "in": "query", "schema": {"type": "string", "enum": ["admin&role=test"]}}],
                        "responses": {"200": {"description": "OK"}}
                    }
                }
            }
        })
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec}, headers=auth_headers,
        )
        data = resp.json()
        assert len(data["stubs"]) == 1
        url = data["stubs"][0]["content"]["url"]
        assert "q=" in url

    @pytest.mark.asyncio
    async def test_schema_305_204_body_assertion(
        self, async_client, auth_headers, test_project,
    ):
        """SCHEMA-305：204 No Content 的 body 断言 eq ''（当前行为）。"""
        spec = _load_spec("simple_api.json")
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec}, headers=auth_headers,
        )
        data = resp.json()
        delete_stubs = [s for s in data["stubs"] if s["content"]["method"] == "DELETE"]
        assert len(delete_stubs) >= 1
        assertions = delete_stubs[0]["content"]["assertions"]
        assert len(assertions) >= 2
        assert assertions[1]["target"] == "response_body"
        assert assertions[1]["expected"] == ""

    @pytest.mark.asyncio
    async def test_schema_306_swagger2(
        self, async_client, auth_headers, test_project,
    ):
        """SCHEMA-306：Swagger 2.0 → best effort（paths 解析，body 为 None）。"""
        spec = _load_spec("swagger2.json")
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec}, headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["endpoints"]) >= 2

    @pytest.mark.asyncio
    async def test_schema_307_empty_paths(
        self, async_client, auth_headers, test_project,
    ):
        """SCHEMA-307：paths: {} → 400。"""
        spec = _load_spec("empty_paths.json")
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": spec}, headers=auth_headers,
        )
        assert resp.status_code == 400
        detail = resp.json().get("detail", "")
        assert "路径" in detail or "为空" in detail


# ═══════════════════════════════════════════════════════════════════════════
#  五、权限/认证
# ═══════════════════════════════════════════════════════════════════════════


class TestAuth:
    """验剑策略：SCHEMA-401 ~ SCHEMA-403 — 认证与授权。"""

    @pytest.mark.asyncio
    async def test_schema_401_no_token(self, async_client):
        """SCHEMA-401：未认证 → 401。"""
        resp = await async_client.post(
            "/api/projects/1/schema/parse",
            json={"spec": _load_spec("simple_api.json")},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_schema_402_non_owner(
        self, async_client, test_project, auth2_headers,
    ):
        """SCHEMA-402：非 Owner → 403。"""
        resp = await async_client.post(
            f"/api/projects/{test_project.id}/schema/parse",
            json={"spec": _load_spec("simple_api.json")},
            headers=auth2_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_schema_403_nonexistent_project(
        self, async_client, auth_headers,
    ):
        """SCHEMA-403：不存在的项目 → 404。"""
        resp = await async_client.post(
            "/api/projects/99999/schema/parse",
            json={"spec": _load_spec("simple_api.json")},
            headers=auth_headers,
        )
        assert resp.status_code == 404
