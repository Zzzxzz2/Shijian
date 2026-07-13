"""Recorded 测试：录制 MockRecord → 一键转换 TestCase — 26 个场景覆盖（验剑策略）。

策略文件：``.omo/tests/test-plan-recorded-testing.md``
覆盖维度：
  正常路径 10 个（REC-001 ~ REC-010）
  边界值    9 个（REC-101 ~ REC-109）
  异常场景  4 个（REC-201 ~ REC-204）
  权限/认证 3 个（REC-301 ~ REC-303）

端点：POST /api/projects/{pid}/mocks/convert
请求：``{"mock_ids": [int, ...]}``
响应 201：``{"imported": int, "cases": [{"id": int, "name": str}]}``

转换逻辑（backend/routers/mock.py）：
- 逐条处理 mock_ids；单条缺失或跨项目 → continue 不阻塞
- URL = path + "?" + query_string（query_string 非空时）
- 敏感头过滤：_SENSITIVE_HEADERS
- JSON body 解析：body_type="json" + 非空 → json.loads()，失败保留原始
- 断言：status_code eq response_status
- name = "{method} {path} — 录制"
- source="recorded", test_type="api", tags=["recorded"]
"""

import json

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import create_access_token, hash_password
from models import MockRecord, Project, ProjectMembers, TestCase, User

pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════════════
#  Fixtures — 角色用户 + 项目 + MockRecord 辅助
# ═══════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def rec_owner(db_session) -> User:
    await db_session.execute(sa_delete(User).where(User.username == "rec_owner"))
    await db_session.commit()
    user = User(username="rec_owner", password_hash=hash_password("pass123"), role="user")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def rec_editor(db_session) -> User:
    await db_session.execute(sa_delete(User).where(User.username == "rec_editor"))
    await db_session.commit()
    user = User(username="rec_editor", password_hash=hash_password("pass123"), role="user")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def rec_viewer(db_session) -> User:
    await db_session.execute(sa_delete(User).where(User.username == "rec_viewer"))
    await db_session.commit()
    user = User(username="rec_viewer", password_hash=hash_password("pass123"), role="user")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def rec_stranger(db_session) -> User:
    await db_session.execute(sa_delete(User).where(User.username == "rec_stranger"))
    await db_session.commit()
    user = User(username="rec_stranger", password_hash=hash_password("pass123"), role="user")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def rec_project(
    db_session, rec_owner: User, rec_editor: User, rec_viewer: User
) -> Project:
    proj = Project(name="Recorded Test Project", user_id=rec_owner.id)
    db_session.add(proj)
    await db_session.commit()
    await db_session.refresh(proj)

    db_session.add(ProjectMembers(project_id=proj.id, user_id=rec_owner.id, role="owner"))
    db_session.add(ProjectMembers(project_id=proj.id, user_id=rec_editor.id, role="editor"))
    db_session.add(ProjectMembers(project_id=proj.id, user_id=rec_viewer.id, role="viewer"))
    await db_session.commit()
    return proj


# ── Tokens & Headers ────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def rec_owner_token(rec_owner: User) -> str:
    return create_access_token({"sub": str(rec_owner.id)})


@pytest_asyncio.fixture
async def rec_editor_token(rec_editor: User) -> str:
    return create_access_token({"sub": str(rec_editor.id)})


@pytest_asyncio.fixture
async def rec_viewer_token(rec_viewer: User) -> str:
    return create_access_token({"sub": str(rec_viewer.id)})


@pytest_asyncio.fixture
async def rec_stranger_token(rec_stranger: User) -> str:
    return create_access_token({"sub": str(rec_stranger.id)})


# ── MockRecord 工厂辅助 ───────────────────────────────────────────────


async def _make_record(
    db_session: AsyncSession,
    project_id: int,
    *,
    method: str = "GET",
    path: str = "/api/test",
    query_string: str = "",
    request_headers: dict | None = None,
    request_body: str | None = "",
    body_type: str = "text",
    response_status: int = 200,
) -> MockRecord:
    rec = MockRecord(
        project_id=project_id,
        enabled=True,
        source="auto",
        method=method,
        path=path,
        query_string=query_string,
        request_headers=request_headers or {},
        request_body=request_body or "",
        body_type=body_type,
        response_status=response_status,
        response_headers={},
        response_body="",
        response_body_type="text",
    )
    db_session.add(rec)
    await db_session.commit()
    await db_session.refresh(rec)
    return rec


@pytest_asyncio.fixture
async def three_records(db_session, rec_project: Project) -> list[MockRecord]:
    """REC-001 前置：3 条有效 MockRecord（method 各不相同）。"""
    ids = []
    for method, path in [("GET", "/api/users"), ("POST", "/api/login"), ("DELETE", "/api/items/1")]:
        rec = await _make_record(db_session, rec_project.id, method=method, path=path)
        ids.append(rec)
    return ids


# ═══════════════════════════════════════════════════════════════════════════
#  I.  正常路径（Happy Path）
# ═══════════════════════════════════════════════════════════════════════════


class TestHappyPath:
    """REC-001 ~ REC-010：正常路径 10 个场景。"""

    async def test_rec_001_convert_three_records(
        self, async_client: AsyncClient, rec_project: Project, rec_editor_token: str, db_session: AsyncSession
    ):
        """REC-001：转换 3 条有效 MockRecord → imported=3, cases 含 3 条。"""
        recs = []
        for method, path in [("GET", "/a"), ("POST", "/b"), ("PUT", "/c")]:
            rec = await _make_record(db_session, rec_project.id, method=method, path=path)
            recs.append(rec)

        resp = await async_client.post(
            f"/api/projects/{rec_project.id}/mocks/convert",
            json={"mock_ids": [r.id for r in recs]},
            headers={"Authorization": f"Bearer {rec_editor_token}"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["imported"] == 3
        assert len(body["cases"]) == 3
        for c in body["cases"]:
            assert "id" in c
            assert "name" in c

    async def test_rec_002_cases_listed_after_convert(
        self, async_client: AsyncClient, rec_project: Project, rec_editor_token: str, db_session: AsyncSession
    ):
        """REC-002：转换后用例可在用例列表查到。"""
        rec = await _make_record(db_session, rec_project.id, method="GET", path="/api/listme")
        resp = await async_client.post(
            f"/api/projects/{rec_project.id}/mocks/convert",
            json={"mock_ids": [rec.id]},
            headers={"Authorization": f"Bearer {rec_editor_token}"},
        )
        assert resp.status_code == 201
        converted = resp.json()
        case_id = converted["cases"][0]["id"]

        # 在用例列表中查找
        resp2 = await async_client.get(
            f"/api/projects/{rec_project.id}/cases",
            headers={"Authorization": f"Bearer {rec_editor_token}"},
        )
        assert resp2.status_code == 200
        data = resp2.json()
        case_ids = [c["id"] for c in data["items"]]
        assert case_id in case_ids

    async def test_rec_003_name_format(
        self, async_client: AsyncClient, rec_project: Project, rec_editor_token: str, db_session: AsyncSession
    ):
        """REC-003：name 格式为 "{method} {path} — 录制"。"""
        rec = await _make_record(db_session, rec_project.id, method="GET", path="/api/users")
        resp = await async_client.post(
            f"/api/projects/{rec_project.id}/mocks/convert",
            json={"mock_ids": [rec.id]},
            headers={"Authorization": f"Bearer {rec_editor_token}"},
        )
        assert resp.status_code == 201
        assert resp.json()["cases"][0]["name"] == "GET /api/users — 录制"

    async def test_rec_004_content_fields(
        self, async_client, rec_project, rec_editor_token, db_session
    ):
        """REC-004：content 包含 method/url/headers/body/assertions。

        验证 content 中的 method 大写、url 正确拼接、headers 为 dict、
        body 按类型处理、assertions 为数组。
        """
        rec = await _make_record(
            db_session, rec_project.id,
            method="post",
            path="/api/data",
            query_string="",
            request_headers={"content-type": "application/json", "x-custom": "val"},
            request_body='{"key":"val"}',
            body_type="json",
            response_status=201,
        )

        resp = await async_client.post(
            f"/api/projects/{rec_project.id}/mocks/convert",
            json={"mock_ids": [rec.id]},
            headers={"Authorization": f"Bearer {rec_editor_token}"},
        )
        assert resp.status_code == 201

        # 从 DB 查生成的 TestCase 验证 content
        case_id = resp.json()["cases"][0]["id"]
        result = await db_session.execute(select(TestCase).where(TestCase.id == case_id))
        case = result.scalars().first()
        assert case is not None
        content = case.content
        assert content["method"] == "POST"
        assert content["url"] == "/api/data"
        assert isinstance(content["headers"], dict)
        assert isinstance(content["assertions"], list)

    async def test_rec_005_assertion_status_code(
        self, async_client, rec_project, rec_editor_token, db_session
    ):
        """REC-005：断言为 status_code eq response_status。"""
        rec = await _make_record(db_session, rec_project.id, method="GET", path="/api/status", response_status=201)

        resp = await async_client.post(
            f"/api/projects/{rec_project.id}/mocks/convert",
            json={"mock_ids": [rec.id]},
            headers={"Authorization": f"Bearer {rec_editor_token}"},
        )
        assert resp.status_code == 201

        case_id = resp.json()["cases"][0]["id"]
        result = await db_session.execute(select(TestCase).where(TestCase.id == case_id))
        case = result.scalars().first()
        assertions = case.content["assertions"]
        assert len(assertions) == 1
        assert assertions[0] == {
            "type": "status_code",
            "target": "status_code",
            "operator": "eq",
            "expected": 201,
        }

    async def test_rec_006_source_and_tags(
        self, async_client, rec_project, rec_editor_token, db_session
    ):
        """REC-006：source="recorded", test_type="api", tags=["recorded"]。"""
        rec = await _make_record(db_session, rec_project.id)
        resp = await async_client.post(
            f"/api/projects/{rec_project.id}/mocks/convert",
            json={"mock_ids": [rec.id]},
            headers={"Authorization": f"Bearer {rec_editor_token}"},
        )
        assert resp.status_code == 201

        case_id = resp.json()["cases"][0]["id"]
        result = await db_session.execute(select(TestCase).where(TestCase.id == case_id))
        case = result.scalars().first()
        assert case.source == "recorded"
        assert case.test_type == "api"
        assert case.tags == ["recorded"]

    async def test_rec_007_url_with_query_string(
        self, async_client, rec_project, rec_editor_token, db_session
    ):
        """REC-007：URL 含 query_string → url 包含 "path?query_string"。"""
        rec = await _make_record(db_session, rec_project.id, path="/api/search", query_string="q=test")
        resp = await async_client.post(
            f"/api/projects/{rec_project.id}/mocks/convert",
            json={"mock_ids": [rec.id]},
            headers={"Authorization": f"Bearer {rec_editor_token}"},
        )
        assert resp.status_code == 201

        case_id = resp.json()["cases"][0]["id"]
        result = await db_session.execute(select(TestCase).where(TestCase.id == case_id))
        case = result.scalars().first()
        assert case.content["url"] == "/api/search?q=test"

    async def test_rec_008_json_body_parsed(
        self, async_client, rec_project, rec_editor_token, db_session
    ):
        """REC-008：JSON body 解析为 dict。"""
        rec = await _make_record(
            db_session, rec_project.id,
            method="POST", path="/api/data",
            request_body='{"key": "val"}',
            body_type="json",
        )
        resp = await async_client.post(
            f"/api/projects/{rec_project.id}/mocks/convert",
            json={"mock_ids": [rec.id]},
            headers={"Authorization": f"Bearer {rec_editor_token}"},
        )
        assert resp.status_code == 201

        case_id = resp.json()["cases"][0]["id"]
        result = await db_session.execute(select(TestCase).where(TestCase.id == case_id))
        case = result.scalars().first()
        assert case.content["body"] == {"key": "val"}

    async def test_rec_009_non_json_body_stays_string(
        self, async_client, rec_project, rec_editor_token, db_session
    ):
        """REC-009：非 JSON body 保留原始字符串。"""
        rec = await _make_record(
            db_session, rec_project.id,
            method="POST", path="/api/raw",
            request_body="plain text",
            body_type="text",
        )
        resp = await async_client.post(
            f"/api/projects/{rec_project.id}/mocks/convert",
            json={"mock_ids": [rec.id]},
            headers={"Authorization": f"Bearer {rec_editor_token}"},
        )
        assert resp.status_code == 201

        case_id = resp.json()["cases"][0]["id"]
        result = await db_session.execute(select(TestCase).where(TestCase.id == case_id))
        case = result.scalars().first()
        assert case.content["body"] == "plain text"

    async def test_rec_010_empty_body(
        self, async_client, rec_project, rec_editor_token, db_session
    ):
        """REC-010：空 body → content.body = ""。"""
        rec = await _make_record(db_session, rec_project.id, request_body=None)
        resp = await async_client.post(
            f"/api/projects/{rec_project.id}/mocks/convert",
            json={"mock_ids": [rec.id]},
            headers={"Authorization": f"Bearer {rec_editor_token}"},
        )
        assert resp.status_code == 201

        case_id = resp.json()["cases"][0]["id"]
        result = await db_session.execute(select(TestCase).where(TestCase.id == case_id))
        case = result.scalars().first()
        assert case.content["body"] == ""


# ═══════════════════════════════════════════════════════════════════════════
#  II. 边界值
# ═══════════════════════════════════════════════════════════════════════════


class TestBoundary:
    """REC-101 ~ REC-109：边界值 9 个场景。"""

    async def test_rec_101_partial_missing_skipped(
        self, async_client, rec_project, rec_editor_token, db_session
    ):
        """REC-101：部分 mock_id 不存在 → 跳过不阻塞。"""
        r1 = await _make_record(db_session, rec_project.id, method="GET", path="/a")
        r2 = await _make_record(db_session, rec_project.id, method="POST", path="/b")

        resp = await async_client.post(
            f"/api/projects/{rec_project.id}/mocks/convert",
            json={"mock_ids": [r1.id, 99999, r2.id]},
            headers={"Authorization": f"Bearer {rec_editor_token}"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["imported"] == 2
        assert len(body["cases"]) == 2

    async def test_rec_102_all_missing(
        self, async_client, rec_project, rec_editor_token
    ):
        """REC-102：全部 mock_id 不存在 → imported=0, cases=[]。"""
        resp = await async_client.post(
            f"/api/projects/{rec_project.id}/mocks/convert",
            json={"mock_ids": [99999, 88888]},
            headers={"Authorization": f"Bearer {rec_editor_token}"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["imported"] == 0
        assert body["cases"] == []

    async def test_rec_103_cross_project_skipped(
        self, async_client, rec_project, rec_editor_token, db_session, rec_owner: User
    ):
        """REC-103：跨项目 mock_id 被跳过。

        为 rec_project 的同一个项目创建其他项目的 MockRecord → 应被跳过。
        这里直接在 rec_project 下创一个记录，然后 99999 作为跨项目 ID，
        之前 test_rec_101 已覆盖这个模式。更精确：创建属于其他项目的记录。
        """
        # 创建另一个项目
        other = Project(name="Other Project", user_id=rec_owner.id)
        db_session.add(other)
        await db_session.commit()
        await db_session.refresh(other)

        # 在 other 项目下创建记录
        other_rec = await _make_record(db_session, other.id, method="GET", path="/other")

        resp = await async_client.post(
            f"/api/projects/{rec_project.id}/mocks/convert",
            json={"mock_ids": [other_rec.id]},
            headers={"Authorization": f"Bearer {rec_editor_token}"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["imported"] == 0
        assert body["cases"] == []

    async def test_rec_104_empty_mock_ids(
        self, async_client, rec_project, rec_editor_token
    ):
        """REC-104：空 mock_ids → imported=0。"""
        resp = await async_client.post(
            f"/api/projects/{rec_project.id}/mocks/convert",
            json={"mock_ids": []},
            headers={"Authorization": f"Bearer {rec_editor_token}"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["imported"] == 0
        assert body["cases"] == []

    async def test_rec_105_sensitive_headers_filtered(
        self, async_client, rec_project, rec_editor_token, db_session
    ):
        """REC-105：敏感头全部过滤。"""
        rec = await _make_record(
            db_session, rec_project.id,
            request_headers={
                "Host": "example.com",
                "Cookie": "session=abc",
                "Authorization": "Bearer tok",
                "X-Api-Key": "secret",
                "Content-Length": "42",
                "X-Forwarded-For": "1.2.3.4",
                "Content-Type": "application/json",
            },
        )

        resp = await async_client.post(
            f"/api/projects/{rec_project.id}/mocks/convert",
            json={"mock_ids": [rec.id]},
            headers={"Authorization": f"Bearer {rec_editor_token}"},
        )
        assert resp.status_code == 201

        case_id = resp.json()["cases"][0]["id"]
        result = await db_session.execute(select(TestCase).where(TestCase.id == case_id))
        case = result.scalars().first()
        headers = case.content["headers"]
        assert "Host" not in headers and "host" not in headers
        assert "Cookie" not in headers and "cookie" not in headers
        assert "Authorization" not in headers and "authorization" not in headers
        assert "X-Api-Key" not in headers and "x-api-key" not in headers
        assert "Content-Length" not in headers and "content-length" not in headers
        assert "X-Forwarded-For" not in headers and "x-forwarded-for" not in headers
        # 非敏感头应保留
        assert headers.get("Content-Type") == "application/json" or headers.get("content-type") == "application/json"

    async def test_rec_106_non_sensitive_headers_preserved(
        self, async_client, rec_project, rec_editor_token, db_session
    ):
        """REC-106：非敏感头保留。"""
        rec = await _make_record(
            db_session, rec_project.id,
            request_headers={
                "Content-Type": "application/json",
                "Accept": "text/html",
                "X-Request-Id": "abc-123",
            },
        )

        resp = await async_client.post(
            f"/api/projects/{rec_project.id}/mocks/convert",
            json={"mock_ids": [rec.id]},
            headers={"Authorization": f"Bearer {rec_editor_token}"},
        )
        assert resp.status_code == 201

        case_id = resp.json()["cases"][0]["id"]
        result = await db_session.execute(select(TestCase).where(TestCase.id == case_id))
        case = result.scalars().first()
        headers = case.content["headers"]
        assert "Content-Type" in headers or "content-type" in headers
        assert "Accept" in headers or "accept" in headers
        assert "X-Request-Id" in headers or "x-request-id" in headers

    async def test_rec_107_invalid_json_body_fallback(
        self, async_client, rec_project, rec_editor_token, db_session
    ):
        """REC-107：JSON body 解析失败 → 保留原始字符串。"""
        rec = await _make_record(
            db_session, rec_project.id,
            method="POST", path="/api/broken",
            request_body="{broken json}",
            body_type="json",
        )

        resp = await async_client.post(
            f"/api/projects/{rec_project.id}/mocks/convert",
            json={"mock_ids": [rec.id]},
            headers={"Authorization": f"Bearer {rec_editor_token}"},
        )
        assert resp.status_code == 201

        case_id = resp.json()["cases"][0]["id"]
        result = await db_session.execute(select(TestCase).where(TestCase.id == case_id))
        case = result.scalars().first()
        assert case.content["body"] == "{broken json}"

    async def test_rec_108_status_204(
        self, async_client, rec_project, rec_editor_token, db_session
    ):
        """REC-108：response_status=204 → 断言 204。"""
        rec = await _make_record(db_session, rec_project.id, response_status=204)

        resp = await async_client.post(
            f"/api/projects/{rec_project.id}/mocks/convert",
            json={"mock_ids": [rec.id]},
            headers={"Authorization": f"Bearer {rec_editor_token}"},
        )
        assert resp.status_code == 201

        case_id = resp.json()["cases"][0]["id"]
        result = await db_session.execute(select(TestCase).where(TestCase.id == case_id))
        case = result.scalars().first()
        assert case.content["assertions"][0]["expected"] == 204

    async def test_rec_109_bulk_50_records(
        self, async_client, rec_project, rec_editor_token, db_session
    ):
        """REC-109：大量 mock_ids（50+）→ 全部正常转换。"""
        ids = []
        for i in range(50):
            r = await _make_record(db_session, rec_project.id, method="GET", path=f"/api/item/{i}")
            ids.append(r.id)

        resp = await async_client.post(
            f"/api/projects/{rec_project.id}/mocks/convert",
            json={"mock_ids": ids},
            headers={"Authorization": f"Bearer {rec_editor_token}"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["imported"] == 50
        assert len(body["cases"]) == 50


# ═══════════════════════════════════════════════════════════════════════════
#  III. 异常场景
# ═══════════════════════════════════════════════════════════════════════════


class TestExceptions:
    """REC-201 ~ REC-204：异常场景 4 个。"""

    async def test_rec_201_unauth(
        self, async_client, rec_project
    ):
        """REC-201：未认证 → 401。"""
        resp = await async_client.post(
            f"/api/projects/{rec_project.id}/mocks/convert",
            json={"mock_ids": [1]},
        )
        assert resp.status_code == 401

    async def test_rec_202_non_member(
        self, async_client, rec_project, rec_stranger_token
    ):
        """REC-202：非成员 → 403。"""
        resp = await async_client.post(
            f"/api/projects/{rec_project.id}/mocks/convert",
            json={"mock_ids": [1]},
            headers={"Authorization": f"Bearer {rec_stranger_token}"},
        )
        assert resp.status_code == 403

    async def test_rec_203_viewer_forbidden(
        self, async_client, rec_project, rec_viewer_token
    ):
        """REC-203：Viewer → 403。"""
        resp = await async_client.post(
            f"/api/projects/{rec_project.id}/mocks/convert",
            json={"mock_ids": [1]},
            headers={"Authorization": f"Bearer {rec_viewer_token}"},
        )
        assert resp.status_code == 403

    async def test_rec_204_nonexistent_project(
        self, async_client, rec_editor_token
    ):
        """REC-204：不存在项目 → 404。"""
        resp = await async_client.post(
            "/api/projects/99999/mocks/convert",
            json={"mock_ids": [1]},
            headers={"Authorization": f"Bearer {rec_editor_token}"},
        )
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
#  IV. 权限/认证
# ═══════════════════════════════════════════════════════════════════════════


class TestAuth:
    """REC-301 ~ REC-303：权限/认证 3 个场景。"""

    async def test_rec_301_editor_can_convert(
        self, async_client, rec_project, rec_editor_token, db_session
    ):
        """REC-301：Editor 可执行转换 → 201。"""
        rec = await _make_record(db_session, rec_project.id)
        resp = await async_client.post(
            f"/api/projects/{rec_project.id}/mocks/convert",
            json={"mock_ids": [rec.id]},
            headers={"Authorization": f"Bearer {rec_editor_token}"},
        )
        assert resp.status_code == 201

    async def test_rec_302_viewer_cannot(
        self, async_client, rec_project, rec_viewer_token, db_session
    ):
        """REC-302：Viewer 不可执行 → 403。"""
        rec = await _make_record(db_session, rec_project.id)
        resp = await async_client.post(
            f"/api/projects/{rec_project.id}/mocks/convert",
            json={"mock_ids": [rec.id]},
            headers={"Authorization": f"Bearer {rec_viewer_token}"},
        )
        assert resp.status_code == 403

    async def test_rec_303_admin_bypass(
        self, async_client, rec_project, db_session
    ):
        """REC-303：Admin bypass → 201。"""
        from auth import create_access_token
        # 创建 admin 用户并加到项目
        await db_session.execute(sa_delete(User).where(User.username == "rec_admin"))
        await db_session.commit()
        admin = User(username="rec_admin", password_hash=hash_password("admin123"), role="admin")
        db_session.add(admin)
        await db_session.commit()
        await db_session.refresh(admin)

        admin_token = create_access_token({"sub": str(admin.id)}, user=admin)

        rec = await _make_record(db_session, rec_project.id)
        resp = await async_client.post(
            f"/api/projects/{rec_project.id}/mocks/convert",
            json={"mock_ids": [rec.id]},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 201
