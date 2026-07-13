"""Schema Driver — parse OpenAPI JSON into test-case stubs.

POST /api/projects/{pid}/schema/parse
  Accepts a raw OpenAPI JSON string or a URL pointing to one.
  Returns a list of test-case skeletons (one per endpoint + method),
  each with auto-generated assertions and example body.
"""

import json
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from database import db_retry, get_db
from models import User
from routers.deps import require_project_access
from schemas import (
    SchemaEndpointStub,
    SchemaParseRequest,
    SchemaParseResponse,
)
from services.security_vectors import SECURITY_VECTORS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects/{pid}/schema", tags=["schema-driver"])

# Preferred content-type order when deciding which schema to use for body generation
_PREFERRED_CT: list[str] = [
    "application/json",
    "application/x-www-form-urlencoded",
    "multipart/form-data",
]


# ══════════════════════════════════════════════════════════════════════════
#  Auth helper
# ══════════════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════════════
#  $ref / allOf / oneOf / anyOf resolver
# ══════════════════════════════════════════════════════════════════════════


def _resolve_ref(ref_path: str, openapi: dict) -> dict:
    """Resolve ``#/components/schemas/User`` into the actual dict.

    On resolution failure returns an empty dict and logs a warning
    (never crashes the whole parse).
    """
    parts = ref_path.lstrip("#").lstrip("/").split("/")
    obj: dict = openapi
    try:
        for part in parts:
            if isinstance(obj, dict):
                obj = obj.get(part, {})
            else:
                logger.warning("Cannot resolve $ref '%s' — intermediate '%s' is not a dict", ref_path, part)
                return {}
    except Exception:
        logger.warning("Failed to resolve $ref '%s'", ref_path, exc_info=True)
        return {}
    if not isinstance(obj, dict):
        logger.warning("$ref '%s' resolved to non-dict (%s), returning empty", ref_path, type(obj).__name__)
        return {}
    return obj


def _resolve_schema(schema: Any, openapi: dict) -> dict:
    """Recursively normalise a raw OpenAPI schema node.

    Handles ``$ref``, ``allOf`` (merge properties), ``oneOf`` / ``anyOf``
    (pick first variant), and plain dict / list values.
    """
    if not isinstance(schema, dict):
        # Scalar type entry like ``{"type": "string"}`` is a dict, so this
        # branch catches things like ``type: string`` at the item level
        # that isn't a dict, or None.
        return {}

    # $ref → resolve and re-enter
    if "$ref" in schema:
        resolved = _resolve_ref(schema["$ref"], openapi)
        return _resolve_schema(resolved, openapi)

    # allOf → merge properties from every sub-schema
    if "allOf" in schema:
        merged: dict[str, Any] = {"type": "object", "properties": {}}
        for item in schema["allOf"]:
            sub = _resolve_schema(item, openapi)
            sub_props = sub.get("properties", {}) if isinstance(sub, dict) else {}
            merged["properties"].update(sub_props)
        return merged

    # oneOf / anyOf → pick the first variant
    if "oneOf" in schema:
        return _resolve_schema(schema["oneOf"][0], openapi)
    if "anyOf" in schema:
        return _resolve_schema(schema["anyOf"][0], openapi)

    return schema


# ══════════════════════════════════════════════════════════════════════════
#  Body example generator
# ══════════════════════════════════════════════════════════════════════════


_SWAGGER_TYPE_DEFAULTS: dict[str, Any] = {
    "string": "string",
    "integer": 0,
    "number": 0.0,
    "boolean": False,
    "array": [],
    "object": {},
}


def _to_python_type(schema_type: str) -> object:
    """Map OpenAPI type name to a plausible Python literal."""
    return _SWAGGER_TYPE_DEFAULTS.get(schema_type, "string")


def _generate_body_example(request_body: dict | None, openapi: dict) -> Any:
    """Build an example request body from *request_body* schema.

    Returns ``None`` when no usable schema is found.
    """
    if not request_body:
        return None

    content = request_body.get("content", {})
    if not content:
        return None

    # Walk preferred content-types in priority order
    body_schema: dict | None = None
    for ct in _PREFERRED_CT:
        if ct in content:
            body_schema = content[ct].get("schema", {})
            break

    if not body_schema:
        # Fall back to whatever first content-type is available
        first_ct = next(iter(content.values()), None)
        if first_ct is None:
            return None
        body_schema = first_ct.get("schema", {})

    resolved = _resolve_schema(body_schema, openapi)
    if not isinstance(resolved, dict):
        return None

    return _generate_from_schema(resolved, openapi)


def _generate_from_schema(schema: dict, openapi: dict) -> Any:
    """Generate a concrete example value from a resolved schema dict."""
    schema_type = schema.get("type", "object")
    enum_values = schema.get("enum")
    example = schema.get("example")

    # Explicit example wins
    if example is not None:
        return example

    # Enum → first value
    if enum_values:
        return enum_values[0]

    if schema_type == "object":
        props = schema.get("properties", {})
        result: dict[str, Any] = {}
        for prop_name, prop_schema in props.items():
            resolved = _resolve_schema(prop_schema, openapi)
            result[prop_name] = _generate_from_schema(resolved, openapi)
        return result

    if schema_type == "array":
        items = schema.get("items", {})
        resolved_items = _resolve_schema(items, openapi)
        return [_generate_from_schema(resolved_items, openapi)]

    # Primitive type
    return _to_python_type(schema_type)


# ══════════════════════════════════════════════════════════════════════════
#  Assertion generator
# ══════════════════════════════════════════════════════════════════════════


def _generate_assertions(method: str, detail: dict) -> list[dict]:
    """Produce a list of assertion dicts from *detail[responses]*.

    - 2xx status code from the first matching success response.
    - POST prefers 201 over 200; DELETE prefers 204 over 200.
    - 204 → extra assertion that body is empty.
    """
    responses = detail.get("responses", {})
    assertions: list[dict] = []

    # Determine target status code
    target_status: int | None = None

    # Custom preference for POST/DELETE
    if method == "post" and "201" in responses:
        target_status = 201
    elif method == "delete" and "204" in responses:
        target_status = 204

    # Fall back to the first 2xx
    if target_status is None:
        for code_str in sorted(responses.keys()):
            if code_str.startswith("2"):
                try:
                    target_status = int(code_str)
                    break
                except ValueError:
                    continue

    if target_status is None:
        target_status = 200

    assertions.append({
        "type": "status_code",
        "target": "status_code",
        "operator": "eq",
        "expected": target_status,
    })

    # 204 No Content → body must be empty
    if target_status == 204:
        assertions.append({
            "type": "body_contains",
            "target": "response_body",
            "operator": "eq",
            "expected": "",
        })

    return assertions


# ══════════════════════════════════════════════════════════════════════════
#  SchemaFuzz — fuzz-case generator
# ══════════════════════════════════════════════════════════════════════════


_FUZZ_REGISTRY: dict[str, list[Any]] = {
    "string": [
        "",
        "A" * 5000,
        "<script>alert(1)</script>",
        "' OR '1'='1",
        None,
        12345,
    ],
    "integer": [
        0,
        -1,
        2**53,
        1.5,
        "string_value",
    ],
    "boolean": [
        True,
        False,
        None,
        "true",
    ],
    "array": [
        [],
        [1],
        list(range(1000)),
        "not_array",
    ],
    "object": [
        {},
        {"extra_field": "x"},
        None,
    ],
}


def _fuzz_values_for_type(param_type: str) -> list[Any]:
    """Return fuzz values for an OpenAPI parameter type."""
    if param_type == "number":
        return _FUZZ_REGISTRY["integer"][:]
    return _FUZZ_REGISTRY.get(param_type, _FUZZ_REGISTRY["string"][:])


def _build_fuzz_url(path: str, detail: dict, fuzz_param: dict, fuzz_val: Any) -> str:
    """Build a URL where *fuzz_param* is replaced with *fuzz_val*.

    Other parameters keep their normal generated values (mimicking
    ``_build_url`` but with one deliberately broken parameter).
    """
    parameters = detail.get("parameters", [])
    fuzz_name = fuzz_param.get("name", "")
    fuzz_in = fuzz_param.get("in")

    # Start with the path, substitute path params
    result = path
    for param in parameters:
        if param.get("in") == "path":
            name = param.get("name", "")
            placeholder = "{" + name + "}"
            if placeholder not in result:
                continue
            val = str(fuzz_val) if fuzz_val is not None else "null" if name == fuzz_name else ""
            if name == fuzz_name:
                # Use the fuzz value
                result = result.replace(placeholder, val, 1)
            else:
                # Normal value
                schema = _resolve_schema(param.get("schema", {}), {})
                enum_vals = schema.get("enum", []) or param.get("enum", [])
                if enum_vals:
                    result = result.replace(placeholder, str(enum_vals[0]), 1)
                else:
                    result = result.replace(placeholder, str(_to_python_type(schema.get("type", "string"))), 1)

    # Query parameters
    query_parts: list[str] = []
    for param in parameters:
        if param.get("in") == "query":
            name = param.get("name", "")
            if name == fuzz_name and fuzz_in == "query":
                val = str(fuzz_val) if fuzz_val is not None else "null"
                query_parts.append(f"{name}={val}")
            else:
                schema = _resolve_schema(param.get("schema", {}), {})
                val = param.get("example") or schema.get("example")
                if val is None:
                    enum_vals = schema.get("enum", []) or param.get("enum", [])
                    if enum_vals:
                        val = enum_vals[0]
                    else:
                        val = _to_python_type(schema.get("type", "string"))
                query_parts.append(f"{name}={val}")

    if query_parts:
        result = result + "?" + "&".join(query_parts)

    return result


def _generate_fuzz_cases(
    method: str,
    path: str,
    detail: dict,
    openapi: dict,
    max_fuzz: int,
) -> list[SchemaEndpointStub]:
    """Generate fuzz test-case stubs for one endpoint.

    For each parameter (path / query / body), produces one stub per
    fuzz value.  Capped at *max_fuzz* stubs per endpoint.
    """
    stubs: list[SchemaEndpointStub] = []
    parameters = detail.get("parameters", [])
    generated = 0

    # ── Fuzz path / query parameters ───────────────────────────────────
    for param in parameters:
        if generated >= max_fuzz:
            break
        p_in = param.get("in")
        if p_in not in ("path", "query"):
            continue

        schema = _resolve_schema(param.get("schema", {}), openapi) or {}
        param_type = schema.get("type", "string")

        for fuzz_val in _fuzz_values_for_type(param_type):
            if generated >= max_fuzz:
                break

            fuzz_url = _build_fuzz_url(path, detail, param, fuzz_val)
            name = param.get("name", "")
            display_val = repr(fuzz_val)[:60]

            content: dict[str, Any] = {
                "method": method.upper(),
                "url": fuzz_url,
                "headers": {},
                "body": None,
                "assertions": [
                    {
                        "type": "status_code",
                        "target": "status_code",
                        "operator": "ne",
                        "expected": 500,
                    },
                ],
            }

            stubs.append(SchemaEndpointStub(
                name=f"[fuzz] {method.upper()} {path} — param:{name}={display_val}",
                test_type="api",
                source="fuzz",
                content=content,
                coverage_key=f"{method.upper()} {path}",
            ))
            generated += 1

    # ── Fuzz request body ──────────────────────────────────────────────
    request_body = detail.get("requestBody")
    if request_body and generated < max_fuzz:
        content_info = request_body.get("content", {})
        body_schema: dict | None = None
        for ct in _PREFERRED_CT:
            if ct in content_info:
                body_schema = content_info[ct].get("schema", {})
                break
        if not body_schema and content_info:
            body_schema = next(iter(content_info.values()), {}).get("schema", {})

        if body_schema:
            resolved = _resolve_schema(body_schema, openapi)
            body_type = resolved.get("type", "object") if isinstance(resolved, dict) else "object"

            for fuzz_val in _fuzz_values_for_type(body_type):
                if generated >= max_fuzz:
                    break

                display_val = repr(fuzz_val)[:60]

                content: dict[str, Any] = {
                    "method": method.upper(),
                    "url": _build_url(path, detail),
                    "headers": {},
                    "body": fuzz_val,
                    "assertions": [
                        {
                            "type": "status_code",
                            "target": "status_code",
                            "operator": "ne",
                            "expected": 500,
                        },
                    ],
                }

                stubs.append(SchemaEndpointStub(
                    name=f"[fuzz] {method.upper()} {path} — body:{display_val}",
                    test_type="api",
                    source="fuzz",
                    content=content,
                    coverage_key=f"{method.upper()} {path}",
                ))
                generated += 1

    return stubs


# ══════════════════════════════════════════════════════════════════════════
#  Security-case generator
# ══════════════════════════════════════════════════════════════════════════


def _generate_security_cases(
    method: str,
    path: str,
    detail: dict,
    openapi: dict,
    max_cases: int = 100,
) -> list[SchemaEndpointStub]:
    """Generate security attack test-case stubs for one endpoint.

    Injects known attack payloads (SQLi / XSS / path traversal / etc.)
    into matching parameter locations (query / body / path / header).
    """
    stubs: list[SchemaEndpointStub] = []
    parameters = detail.get("parameters", [])
    generated = 0

    def _add_stub(payload, category_name, param_name, loc, display=""):
        nonlocal generated
        if generated >= max_cases:
            return
        url = _build_url(path, detail)

        content: dict[str, Any] = {
            "method": method.upper(),
            "url": url,
            "headers": {},
            "body": None,
            "assertions": [
                {"type": "status_code", "target": "status_code", "operator": "ne", "expected": 500},
            ],
        }

        # Inject payload at the right location
        if loc == "header" and isinstance(payload, dict):
            content["headers"].update(payload)
        elif loc in ("query", "path"):
            # Can't easily inject into a specific query param via _build_url,
            # so we embed it in the existing URL
            sep = "&" if "?" in url else "?"
            content["url"] = f"{url}{sep}{param_name}={payload}"
        elif loc == "body":
            if isinstance(payload, dict):
                content["body"] = payload
            else:
                content["body"] = str(payload)

        stubs.append(SchemaEndpointStub(
            name=f"[security] {category_name} {method.upper()} {path} — {display or param_name}",
            test_type="api",
            source="security",
            content=content,
            coverage_key=f"{method.upper()} {path}",
        ))
        generated += 1

    # ── Inject into path / query / header params ───────────────────────
    for param in parameters:
        if generated >= max_cases:
            break
        p_in = param.get("in")
        if p_in not in ("query", "path", "header"):
            continue
        p_name = param.get("name", "")
        param_schema = param.get("schema", {})

        for cat_name, cat in SECURITY_VECTORS.items():
            if generated >= max_cases:
                break
            if p_in not in cat.get("target", []):
                continue
            # type_hint filter
            type_hint = cat.get("type_hint")
            if type_hint == "object":
                continue   # object-only category, skip non-body
            if type_hint == "json":
                continue

            for payload in cat["payloads"]:
                if generated >= max_cases:
                    break
                if isinstance(payload, dict) and p_in != "header":
                    continue  # dict payloads only for headers (header_injection)
                _add_stub(payload, cat_name, p_name, p_in)

    # ── Inject into request body ───────────────────────────────────────
    request_body = detail.get("requestBody")
    if request_body and generated < max_cases:
        content_info = request_body.get("content", {})
        body_schema: dict | None = None
        for ct in _PREFERRED_CT:
            if ct in content_info:
                body_schema = content_info[ct].get("schema", {})
                break
        if not body_schema and content_info:
            body_schema = next(iter(content_info.values()), {}).get("schema", {})

        body_type = "string"
        if body_schema:
            resolved = _resolve_schema(body_schema, openapi)
            body_type = resolved.get("type", "string") if isinstance(resolved, dict) else "string"

        for cat_name, cat in SECURITY_VECTORS.items():
            if generated >= max_cases:
                break
            if "body" not in cat.get("target", []):
                continue
            type_hint = cat.get("type_hint")

            for payload in cat["payloads"]:
                if generated >= max_cases:
                    break
                # type_hint filter
                if type_hint == "object" and body_type != "object":
                    continue
                if type_hint == "json" and body_type == "string":
                    # nosql_injection: inject JSON expression string into body
                    _add_stub(payload, cat_name, "body", "body", display=str(payload)[:40])
                elif type_hint is None and isinstance(payload, str):
                    # string payloads for string/any body
                    _add_stub(payload, cat_name, "body", "body", display=str(payload)[:40])
                elif type_hint is None and isinstance(payload, dict) and body_type == "object":
                    _add_stub(payload, cat_name, "body", "body", display=str(list(payload.keys())))
                elif type_hint == "object" and isinstance(payload, dict):
                    _add_stub(payload, cat_name, "body", "body", display=str(list(payload.keys())))

    return stubs


# ══════════════════════════════════════════════════════════════════════════
#  URL builder (path params + query params)
# ══════════════════════════════════════════════════════════════════════════


def _build_url(path: str, detail: dict) -> str:
    """Build an example URL with query parameters baked in.

    Path parameters like ``{id}`` that have an ``enum`` constraint are
    replaced with the first enum value; others stay as ``{param}``.
    """
    parameters = detail.get("parameters", [])

    # Path-parameter enum substitution
    for param in parameters:
        if isinstance(param, dict) and param.get("in") == "path":
            name = param.get("name", "")
            placeholder = "{" + name + "}"
            if placeholder in path:
                enum_vals = _resolve_schema(param.get("schema", {}), {}).get("enum", [])
                if not enum_vals:
                    # Also check param-level enum (non-schema OpenAPI style)
                    enum_vals = param.get("enum", [])
                if enum_vals:
                    path = path.replace(placeholder, str(enum_vals[0]), 1)

    # Query parameters → append as ?key=val&key=val
    query_parts: list[str] = []
    for param in parameters:
        if isinstance(param, dict) and param.get("in") == "query":
            name = param.get("name", "")
            if not name:
                continue
            schema = param.get("schema", {})
            resolved = _resolve_schema(schema, {})
            # Determine value: example > enum[0] > type default
            value = param.get("example") or resolved.get("example")
            if value is None:
                enum_vals = resolved.get("enum", []) or param.get("enum", [])
                if enum_vals:
                    value = enum_vals[0]
                else:
                    value = _to_python_type(resolved.get("type", "string"))
            query_parts.append(f"{name}={value}")

    if query_parts:
        path = path + "?" + "&".join(query_parts)

    return path


# ══════════════════════════════════════════════════════════════════════════
#  Endpoint stub builder
# ══════════════════════════════════════════════════════════════════════════


def _build_stub(
    method: str,
    path: str,
    detail: dict,
    openapi: dict,
) -> SchemaEndpointStub:
    """Build a single ``SchemaEndpointStub`` from an OpenAPI path item."""
    summary = detail.get("summary", "")
    operation_id = detail.get("operationId", "")
    name_parts = [m for m in [summary, operation_id, f"{method.upper()} {path}"] if m]
    name = " — ".join(name_parts)

    url = _build_url(path, detail)

    content: dict[str, Any] = {
        "method": method.upper(),
        "url": url,
        "headers": {},
        "body": _generate_body_example(detail.get("requestBody"), openapi),
        "assertions": _generate_assertions(method, detail),
    }

    return SchemaEndpointStub(
        name=name,
        coverage_key=f"{method.upper()} {path}",
        content=content,
    )


# ══════════════════════════════════════════════════════════════════════════
#  Routing
# ══════════════════════════════════════════════════════════════════════════


@router.post("/parse")
@db_retry()
async def parse_openapi_schema(
    pid: int,
    data: SchemaParseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Parse an OpenAPI spec and return a list of test-case stubs.

    Accepts either a raw JSON string (``spec``) or a downloadable URL
    (``spec_url``).  The spec is never stored — only parsed in memory.
    """
    # ── Project guard ─────────────────────────────────────────────────
    await require_project_access(pid, current_user, db, "editor")

    # ── Source resolution ─────────────────────────────────────────────
    spec_str: str | None = None
    source: str = "direct"

    if data.spec_url and data.spec_url.strip():
        source = "url"
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(
                    data.spec_url,
                    headers=data.spec_headers or {},
                    follow_redirects=True,
                )
            if resp.status_code >= 400:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"URL 返回的不是有效 JSON，HTTP {resp.status_code}",
                )
            spec_str = resp.text
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="获取 spec URL 超时（60 秒）",
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"无法访问 spec URL：{exc}",
            )

    if spec_str is None and data.spec and data.spec.strip():
        source = "direct"
        spec_str = data.spec

    if not spec_str:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="请提供 spec（JSON 字符串）或 spec_url（可下载的 OpenAPI JSON URL）",
        )

    # ── JSON parse ────────────────────────────────────────────────────
    try:
        openapi: dict = json.loads(spec_str)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"JSON 解析失败：{exc}",
        )

    if not isinstance(openapi, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="JSON 根节点必须是对象（dict）",
        )

    # ── Extract paths ─────────────────────────────────────────────────
    paths = openapi.get("paths")
    if not isinstance(paths, dict) or not paths:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未找到 API 路径定义（paths 字段缺失或为空）",
        )

    # ── Mode validation ───────────────────────────────────────────────
    mode = (data.mode or "coverage").strip().lower()
    if mode not in ("coverage", "fuzz", "all", "security"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"mode 必须为 coverage / fuzz / all / security，收到: {mode}",
        )
    max_fuzz = max(data.max_fuzz, 1)
    fuzz_count = 0

    # ── Build stubs ───────────────────────────────────────────────────
    stubs: list[SchemaEndpointStub] = []
    raw_endpoints: list[dict] = []
    http_methods = ("get", "post", "put", "patch", "delete")

    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method in http_methods:
            detail = methods.get(method)
            if not isinstance(detail, dict):
                continue  # skip non-dict entries (e.g. parameters, x-tagGroups)

            raw_endpoints.append({
                "path": path,
                "method": method.upper(),
                "summary": detail.get("summary", ""),
                "operationId": detail.get("operationId", ""),
            })

            # 三路追加：coverage/all → happy path
            if mode in ("coverage", "all"):
                try:
                    stub = _build_stub(method, path, detail, openapi)
                    stubs.append(stub)
                except Exception:
                    logger.exception("Failed to build stub for %s %s", method.upper(), path)
                    # Best effort — one broken endpoint doesn't block the rest

            # 三路追加：fuzz/all → fuzz cases
            if mode in ("fuzz", "all") and fuzz_count < max_fuzz:
                try:
                    per_endpoint = min(20, max_fuzz - fuzz_count)
                    fuzz_cases = _generate_fuzz_cases(
                        method=method,
                        path=path,
                        detail=detail,
                        openapi=openapi,
                        max_fuzz=per_endpoint,
                    )
                    if fuzz_cases:
                        stubs.extend(fuzz_cases)
                        fuzz_count += len(fuzz_cases)
                except Exception:
                    logger.exception("Failed to fuzz %s %s", method.upper(), path)

            # 三路追加：security/all → security cases（对每个端点最多 3 类各 2 条）
            if mode in ("security", "all"):
                try:
                    sec_cases = _generate_security_cases(
                        method=method,
                        path=path,
                        detail=detail,
                        openapi=openapi,
                        max_cases=6,
                    )
                    if sec_cases:
                        stubs.extend(sec_cases)
                except Exception:
                    logger.exception("Failed to generate security cases for %s %s", method.upper(), path)

    # ── Spec metadata ─────────────────────────────────────────────────
    info = openapi.get("info", {}) or {}
    spec_title = (info.get("title", "") or "")[:255]
    spec_version = (info.get("version", "") or "")[:50]

    return SchemaParseResponse(
        title=spec_title,
        endpoints=raw_endpoints,
        stubs=stubs,
        spec_title=spec_title,
        spec_version=spec_version,
        coverage_summary={
            "total": len(raw_endpoints),
            "covered": len(stubs),
            "uncovered": len(raw_endpoints) - len(stubs),
        },
    )
