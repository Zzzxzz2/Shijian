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


SENSITIVE_FIELDS = SENSITIVE_HEADERS | {"password", "passwd", "secret", "client_secret", "token", "access_token", "refresh_token", "api_key", "apikey"}


def redact_data(value):
    """Redact common credential keys, URL credentials and sensitive query values."""
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
    if isinstance(value, dict):
        return {key: "[REDACTED]" if str(key).lower().replace("-", "_") in {k.replace("-", "_") for k in SENSITIVE_FIELDS} else redact_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_data(item) for item in value]
    if isinstance(value, str) and value.startswith(("http://", "https://", "/")):
        try:
            url = urlsplit(value)
            query = [(key, "[REDACTED]" if key.lower() in SENSITIVE_FIELDS else item) for key, item in parse_qsl(url.query, keep_blank_values=True)]
            return urlunsplit((url.scheme, url.netloc.split("@")[-1], url.path, urlencode(query), url.fragment)) if url.query or "@" in url.netloc else value
        except ValueError:
            return "[REDACTED URL]"
    return value
