"""Small HTTP-data safety helpers shared by executors and Mock recording."""

from collections.abc import Mapping


SENSITIVE_HEADERS = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "set-cookie",
    "x-api-key",
}


def redact_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    """Keep useful request metadata without persisting credentials."""
    return {
        key: "[REDACTED]" if key.lower() in SENSITIVE_HEADERS else value
        for key, value in (headers or {}).items()
    }
