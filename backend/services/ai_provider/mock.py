"""MockProvider — no-API-key dev/test fallback."""

from .base import BaseAIProvider, GeneratePlanResult, TokenUsage


class MockProvider(BaseAIProvider):
    """No-API-key dev/test fallback — returns preset example cases."""

    def generate_plan(self, requirement: str, context: str = "") -> GeneratePlanResult:
        return GeneratePlanResult(
            cases=[
                {
                    "name": "正常登录",
                    "test_type": "api",
                    "content": {
                        "method": "POST",
                        "url": "/api/auth/login",
                        "body": {"username": "test", "password": "test"},
                        "assertions": [
                            {"type": "status_code", "target": "status_code", "operator": "eq", "expected": 200}
                        ],
                    },
                },
                {
                    "name": "密码错误",
                    "test_type": "api",
                    "content": {
                        "method": "POST",
                        "url": "/api/auth/login",
                        "body": {"username": "test", "password": "wrong"},
                        "assertions": [
                            {"type": "status_code", "target": "status_code", "operator": "eq", "expected": 401}
                        ],
                    },
                },
            ],
            token_usage=TokenUsage(input_tokens=0, output_tokens=0),
        )
