"""验剑策略：即时执行（Quick Test）— HTTP 层（QT-001, 005, 101, 102, 207, 301, 304）

AI 生成链通过 httpx.MockTransport 拦截，不发起真实 API 调用。
"""

import pytest
import httpx


# ═══════════════════════════════════════════════════════════════════════════
#  一、正常路径
# ═══════════════════════════════════════════════════════════════════════════


class TestHappyPathHTTP:
    """验剑策略：QT-001, QT-005 — HTTP 请求-响应。"""

    @pytest.mark.asyncio
    async def test_qt_001_post_returns_task_id_and_ws_url(
        self,
        async_client: httpx.AsyncClient,
        test_project,
        auth_headers: dict[str, str],
    ):
        """验剑策略：QT-001 — POST 即时执行 → 返回 task_id + ws_url（不阻塞）。

        前置：用户已认证，有项目，AI Key 有效
        操作：POST /api/quick-test body {"prompt": "测试登录接口", "project_id": ...}
        预期：立即返回 {"task_id": "qt_...", "ws_url": "/ws/quick-test/qt_..."}，状态码 200
        """
        resp = await async_client.post(
            "/api/quick-test",
            json={"prompt": "测试登录接口", "project_id": test_project.id},
            headers=auth_headers,
        )
        assert resp.status_code == 200, (
            f"应返回 200，实际 {resp.status_code}: {resp.text[:200]}"
        )
        data = resp.json()
        assert "task_id" in data, f"响应应包含 task_id: {data}"
        assert data["task_id"].startswith("qt_"), f"task_id 应以 qt_ 开头: {data['task_id']}"
        assert "ws_url" in data, f"响应应包含 ws_url: {data}"
        assert f"/ws/quick-test/{data['task_id']}" == data["ws_url"], (
            f"ws_url 应与 task_id 对应: {data}"
        )

    @pytest.mark.asyncio
    async def test_qt_005_with_context_doc_ids(
        self,
        async_client: httpx.AsyncClient,
        db_session,
        test_project,
        auth_headers: dict[str, str],
    ):
        """验剑策略：QT-005 — 携带 context_doc_ids → AI 生成时参考文档内容。

        前置：项目有已上传的文档
        操作：POST /api/quick-test body {"prompt": "...", "project_id": ..., "context_doc_ids": [id]}
        预期：正常返回 task_id + ws_url，不崩溃
        """
        # 先创建一份文档
        from models import Document
        doc = Document(
            project_id=test_project.id,
            filename="test-api.md",
            doc_type="md",
            file_path="/dev/null/test-api.md",
            content_text="# 登录接口\nPOST /api/login 接受 username/password，返回 token",
        )
        db_session.add(doc)
        await db_session.commit()
        await db_session.refresh(doc)

        resp = await async_client.post(
            "/api/quick-test",
            json={
                "prompt": "测试登录",
                "project_id": test_project.id,
                "context_doc_ids": [doc.id],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, (
            f"携带 context_doc_ids 应返回 200，实际 {resp.status_code}: {resp.text[:200]}"
        )
        data = resp.json()
        assert data["task_id"].startswith("qt_")


# ═══════════════════════════════════════════════════════════════════════════
#  二、边界值
# ═══════════════════════════════════════════════════════════════════════════


class TestBoundaryHTTP:
    """验剑策略：QT-101, QT-102 — 边界条件。"""

    @pytest.mark.asyncio
    async def test_qt_101_empty_prompt(
        self,
        async_client: httpx.AsyncClient,
        test_project,
        auth_headers: dict[str, str],
    ):
        """验剑策略：QT-101 — prompt 为空字符串。

        操作：POST body {"prompt": "", "project_id": ...}
        预期：Pydantic 校验返回 422（如果已加 min_length=1）或 AI 生成 0 条用例
        """
        resp = await async_client.post(
            "/api/quick-test",
            json={"prompt": "", "project_id": test_project.id},
            headers=auth_headers,
        )
        # Pydantic 校验未约束空字符串 → 返回 200，后续 WS 中 done.total=0
        assert resp.status_code in (200, 422), (
            f"空 prompt 应返回 200 或 422，实际 {resp.status_code}"
        )
        if resp.status_code == 200:
            data = resp.json()
            assert "task_id" in data

    @pytest.mark.asyncio
    async def test_qt_102_long_prompt(
        self,
        async_client: httpx.AsyncClient,
        test_project,
        auth_headers: dict[str, str],
    ):
        """验剑策略：QT-102 — prompt 超长（>5000 字符）。

        操作：prompt 为超长文本
        预期：正常生成并执行，不截断崩溃
        """
        long_prompt = "测试所有功能。" * 1000  # ~7000 字符
        resp = await async_client.post(
            "/api/quick-test",
            json={"prompt": long_prompt, "project_id": test_project.id},
            headers=auth_headers,
        )
        assert resp.status_code == 200, (
            f"长 prompt 应返回 200，实际 {resp.status_code}: {resp.text[:200]}"
        )
        data = resp.json()
        assert data["task_id"].startswith("qt_")


# ═══════════════════════════════════════════════════════════════════════════
#  四、权限/认证
# ═══════════════════════════════════════════════════════════════════════════


class TestAuthHTTP:
    """验剑策略：QT-301, QT-207, QT-304 — 认证与授权。"""

    @pytest.mark.asyncio
    async def test_qt_301_no_token_returns_401(
        self,
        async_client: httpx.AsyncClient,
        test_project,
    ):
        """验剑策略：QT-301 — 未认证用户 POST → 401。

        操作：无 JWT token 调用 POST /api/quick-test
        预期：返回 401 Unauthorized
        """
        resp = await async_client.post(
            "/api/quick-test",
            json={"prompt": "测试", "project_id": test_project.id},
        )
        assert resp.status_code == 401, (
            f"无认证应返回 401，实际 {resp.status_code}: {resp.text[:200]}"
        )

    @pytest.mark.asyncio
    async def test_qt_207_non_owner_returns_404(
        self,
        async_client: httpx.AsyncClient,
        test_project,
        auth2_headers: dict[str, str],
    ):
        """验剑策略：QT-207 — 非项目所有者 POST → 404。

        前置：用户 B 对用户 A 的 project_id 发起 quick-test
        操作：POST quick-test
        预期：返回 403（非项目成员）
        """
        resp = await async_client.post(
            "/api/quick-test",
            json={"prompt": "测试", "project_id": test_project.id},
            headers=auth2_headers,
        )
        assert resp.status_code == 403, (
            f"非 Owner 应返回 403，实际 {resp.status_code}: {resp.text[:200]}"
        )

    @pytest.mark.asyncio
    async def test_qt_304_non_member_returns_403(
        self,
        async_client: httpx.AsyncClient,
        test_project,
        auth2_headers: dict[str, str],
    ):
        """验剑策略：QT-304 — 非项目成员调用 → 403。

        V2 实现：require_project_access 使用 ProjectMembers 判定，
        非 Owner 返回 403。
        """
        resp = await async_client.post(
            "/api/quick-test",
            json={"prompt": "测试", "project_id": test_project.id},
            headers=auth2_headers,
        )
        assert resp.status_code == 403, (
            f"非 Owner 应返回 403，实际 {resp.status_code}: {resp.text[:200]}"
        )
