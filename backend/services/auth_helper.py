"""Auth helper: get authentication token from project auth_config.

Used by executor.py (pre-run token injection) and projects.py (test-auth endpoint).
"""

import httpx


async def _get_auth_token(auth_config: dict, project_url: str = "") -> str | None:
    """Get an auth token based on the given auth_config dict.

    Supports two modes:
    - Mode A: call a login API endpoint to obtain a token
    - Mode B: use a pre-configured static token value

    Returns the raw token string, or None if auth is disabled or extraction fails.
    """
    auth = auth_config or {}
    if not auth.get("enabled"):
        return None

    # Mode B: static token value
    if auth.get("token_value"):
        return auth["token_value"]

    # Mode A: call login endpoint
    if auth.get("login_url"):
        login_url = auth["login_url"]
        if not login_url.startswith("http"):
            base = (project_url or "").rstrip("/")
            if not base:
                base = "http://localhost:8002"
            login_url = base + (login_url if login_url.startswith("/") else "/" + login_url)

        login_body = auth.get("login_body", {})
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(login_url, json=login_body)
            if resp.status_code == 200:
                data = resp.json()
                token_path = auth.get("token_json_path", "token")
                parts = token_path.split(".")
                obj = data
                for p in parts:
                    if isinstance(obj, dict) and p in obj:
                        obj = obj[p]
                    else:
                        return None
                return str(obj) if obj else None

    return None
