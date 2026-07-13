"""验剑策略：多厂商 LLM — 正常路径（LLM-001 ~ LLM-011）

外部 Provider 通过 httpx.MockTransport 拦截，不发起真实 HTTP 调用。
"""

from typing import Any

import httpx
import pytest

from services.ai_provider import FailoverProvider, get_provider
from services.ai_provider.base import GeneratePlanResult
from services.ai_provider.claude import ClaudeProvider
from services.ai_provider.gemini import GeminiProvider
from services.ai_provider.mock import MockProvider
from services.ai_provider.ollama import OllamaProvider
from services.ai_provider.openai_compat import OpenAICompatibleProvider


# ═══════════════════════════════════════════════════════════════════════════
#  1.1 各 Provider 独立调用
# ═══════════════════════════════════════════════════════════════════════════


class TestProviderIndependent:
    """验剑策略：LLM-001 ~ LLM-005 — 各 Provider 独立调用，返回有效用例。"""

    @pytest.mark.parametrize("provider_fixture,expected_cls", [
        ("mocked_openai_provider", OpenAICompatibleProvider),
        ("mocked_claude_provider", ClaudeProvider),
        ("mocked_gemini_provider", GeminiProvider),
        ("mocked_ollama_provider", OllamaProvider),
    ], ids=["deepseek", "claude", "gemini", "ollama"])
    def test_llm_001_004_provider_returns_valid_cases(
        self,
        request: Any,
        provider_fixture: str,
        expected_cls: type,
    ):
        """验剑策略：LLM-001~004 — 每个 Provider 返回 GeneratePlanResult，cases 非空。

        前置：配置有效 API Key（MockTransport 拦截）
        操作：provider.generate_plan("测试登录功能")
        预期：返回 result.cases 非空列表，每条包含 method/path/assertions
        """
        provider = request.getfixturevalue(provider_fixture)
        assert isinstance(provider, expected_cls), (
            f"期望 {expected_cls.__name__}，实际 {type(provider).__name__}"
        )

        result = provider.generate_plan(requirement="测试登录功能")
        assert isinstance(result, GeneratePlanResult), (
            f"应返回 GeneratePlanResult，实际 {type(result)}"
        )
        assert len(result.cases) > 0, "cases 应非空"
        # 验证每条用例包含必要字段
        for case in result.cases:
            assert "name" in case, f"用例缺少 name: {case}"
            assert "test_type" in case, f"用例缺少 test_type: {case}"
            assert "content" in case, f"用例缺少 content: {case}"
            content = case["content"]
            assert "method" in content, f"content 缺少 method: {case}"
            assert "url" in content or "path" in content, (
                f"content 缺少 url/path: {case}"
            )
        assert result.token_usage.input_tokens > 0, "input_tokens 应为正数"
        assert result.token_usage.output_tokens > 0, "output_tokens 应为正数"

    def test_llm_005_ollama_local(self, mocked_ollama_provider: OpenAICompatibleProvider):
        """验剑策略：LLM-005 — Ollama 本地运行，返回有效用例。

        MockTransport 模拟 Ollama 的 OpenAI 兼容端点响应。
        """
        result = mocked_ollama_provider.generate_plan(requirement="测试用户注册")
        assert isinstance(result, GeneratePlanResult)
        assert len(result.cases) > 0


# ═══════════════════════════════════════════════════════════════════════════
#  1.2 Failover 链路
# ═══════════════════════════════════════════════════════════════════════════


class TestFailoverChain:
    """验剑策略：LLM-006 ~ LLM-008 — Failover 链式容错。"""

    @pytest.mark.asyncio
    async def test_llm_006_first_provider_succeeds(self):
        """验剑策略：LLM-006 — 首个 Provider 成功 → 返回该 Provider 结果。

        前置：failover_chain=["claude", "deepseek"]，Claude Key 有效但 DeepSeek Key 无效
        操作：FailoverProvider.generate_plan()
        预期：优先调用 Claude，成功返回，不尝试 DeepSeek
        """
        # Claude 会成功，DeepSeek 会失败（无 HTTP mock）
        claude_provider = ClaudeProvider(
            api_key="sk-claude-valid",
            base_url="https://api.anthropic.com/v1",
            model="claude-sonnet-4-20250514",
        )
        # 给 Claude 挂上 mock transport
        from conftest import _make_mock_handler, build_mocked_client
        claude_provider.client = build_mocked_client(
            _make_mock_handler(cases=[{"name": "Claude Result", "test_type": "api",
                                        "content": {"method": "GET", "url": "/api/test",
                                                     "assertions": []}}])
        )

        # DeepSeek 无 mock，调用时会真实连接 → 会失败，但 failover 应该不走到这里
        deepseek_provider = OpenAICompatibleProvider(
            api_key="sk-invalid",
            base_url="https://api.deepseek.com/v1",
            model="deepseek-chat",
        )
        # 不挂 mock — 但也不会被调用

        failover = FailoverProvider([claude_provider, deepseek_provider])
        result = await failover.generate_plan(requirement="测试登录")

        assert len(result.cases) == 1
        assert result.cases[0]["name"] == "Claude Result"
        assert result.failover_trace is None, "成功时不应有 failover_trace"

    @pytest.mark.asyncio
    async def test_llm_007_first_fails_second_succeeds(self):
        """验剑策略：LLM-007 — 首个 Provider 失败 → 自动切到第二个。

        前置：failover_chain=["claude", "deepseek"]，Claude Key 无效但 DeepSeek Key 有效
        操作：同上
        预期：Claude 调用失败（日志 warning），自动尝试 DeepSeek，返回 DeepSeek 结果
        """
        # Claude 失败（401 模拟）
        claude_provider = ClaudeProvider(
            api_key="sk-claude-bad",
            base_url="https://api.anthropic.com/v1",
            model="claude-sonnet-4-20250514",
        )
        from conftest import _make_mock_handler, build_mocked_client

        def _error_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                status_code=401,
                content=b'{"error": {"message": "invalid API key"}}',
                request=request,
            )
        claude_provider.client = build_mocked_client(_error_handler)

        # DeepSeek 成功
        deepseek_provider = OpenAICompatibleProvider(
            api_key="sk-deepseek-valid",
            base_url="https://api.deepseek.com/v1",
            model="deepseek-chat",
        )
        deepseek_provider.client = build_mocked_client(
            _make_mock_handler(cases=[{"name": "DeepSeek Result", "test_type": "api",
                                        "content": {"method": "GET", "url": "/api/test",
                                                     "assertions": []}}])
        )

        failover = FailoverProvider([claude_provider, deepseek_provider])
        result = await failover.generate_plan(requirement="测试登录")

        assert len(result.cases) == 1
        assert result.cases[0]["name"] == "DeepSeek Result"
        # failover_trace 应为 None（失败被 catch，不需要透传，因为最终成功了）
        # FailoverProvider 实现：只有全部失败才设 failover_trace
        assert result.failover_trace is None

    @pytest.mark.asyncio
    async def test_llm_008_all_fail_mock_fallback(self):
        """验剑策略：LLM-008 — 全部 Provider 不可用 → MockProvider 兜底 + failover_trace。

        前置：failover_chain=["claude", "deepseek"]，两个 Key 都无效
        操作：同上
        预期：两个 provider 均失败 → 返回 MockProvider 的预设用例，
              result.failover_trace 包含两条错误信息
        """
        from conftest import build_mocked_client

        # 两个都失败
        def _fail_401(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                status_code=401,
                content=b'{"error": {"message": "invalid API key"}}',
                request=request,
            )

        claude_provider = ClaudeProvider(api_key="sk-bad", base_url="http://test", model="c")
        claude_provider.client = build_mocked_client(_fail_401)

        deepseek_provider = OpenAICompatibleProvider(
            api_key="sk-bad", base_url="http://test", model="d",
        )
        deepseek_provider.client = build_mocked_client(_fail_401)

        failover = FailoverProvider([claude_provider, deepseek_provider])
        result = await failover.generate_plan(requirement="测试登录")

        # 应返回 MockProvider 的预设用例
        assert len(result.cases) > 0, "全挂后应返回 MockProvider 预设用例"
        # 验证是 MockProvider 的典型用例
        case_names = [c["name"] for c in result.cases]
        assert "正常登录" in case_names, f"应包含 MockProvider 的预设用例名: {case_names}"

        # failover_trace 应包含两条错误
        assert result.failover_trace is not None, "全挂后应设置 failover_trace"
        assert len(result.failover_trace) == 2, f"应有 2 条错误: {result.failover_trace}"
        assert "ClaudeProvider" in result.failover_trace[0]
        assert "OpenAICompatibleProvider" in result.failover_trace[1]


# ═══════════════════════════════════════════════════════════════════════════
#  1.4 单 Provider 模式
# ═══════════════════════════════════════════════════════════════════════════


class TestSingleProviderMode:
    """验剑策略：LLM-009 — 非 failover 模式，单 Provider 直接调用。"""

    def test_llm_009_single_provider_no_failover(
        self,
        mocked_openai_provider: OpenAICompatibleProvider,
    ):
        """验剑策略：LLM-009 — 单 Provider 直接调用，不经过 FailoverProvider。

        前置：project.ai_config.provider="deepseek"
        操作：generate_plan(...)
        预期：直接调用 DeepSeekProvider，不经过 FailoverProvider
        """
        # 直接调用 provider，不包装 FailoverProvider
        result = mocked_openai_provider.generate_plan(requirement="测试登录")
        assert isinstance(result, GeneratePlanResult)
        assert len(result.cases) > 0
        # 没有 failover_trace（非 failover 路径）
        assert result.failover_trace is None


# ═══════════════════════════════════════════════════════════════════════════
#  1.5 向后兼容
# ═══════════════════════════════════════════════════════════════════════════


class TestBackwardCompat:
    """验剑策略：LLM-010 ~ LLM-011 — 向后兼容。"""

    def test_llm_010_old_import_path(self):
        """验剑策略：LLM-010 — V2 旧代码 import 路径不受影响。

        前置：旧代码 from services.ai_provider import BaseAIProvider, get_provider
        操作：import 并实例化 get_provider
        预期：正常导入，功能正常（重导出层生效）
        """
        # V2 旧路径（services.ai_provider.py 重导出）
        from services.ai_provider import BaseAIProvider, get_provider as gp_old

        assert BaseAIProvider is not None
        # project=None → 应返回 MockProvider
        provider = gp_old(project=None)
        from services.ai_provider.mock import MockProvider
        assert isinstance(provider, MockProvider)

    def test_llm_011_v2_deepseek_unaffected(self):
        """验剑策略：LLM-011 — V2 已有 DeepSeek 调用完全不受影响。

        前置：已有项目的 ai_config 为空或 provider=默认值
        操作：老项目的 AI 生成用例流程
        预期：和 V2 行为完全一致
        """
        # ai_config={} → get_provider 默认走 "auto" → 解析为 ["deepseek"] 链
        # 无 api_keys → 回退 MockProvider
        from models import Project

        project = Project(
            name="Legacy",
            description="V2 legacy project",
            user_id=1,
            ai_config={},  # V2 旧项目没有 ai_config
        )
        provider = get_provider(project=project, api_keys=[])
        # 没有 API keys → 返回 MockProvider
        assert isinstance(provider, MockProvider), "无 Key 时应回退 MockProvider"

        result = provider.generate_plan(requirement="测试登录")
        assert len(result.cases) > 0
        assert result.token_usage.input_tokens == 0  # Mock 不计 token
