"""Request matching algorithm for the Mock replay engine.

Matching pipeline (nested filters):

1. method + path exact match          (required)
2. request_body match                 (only if request has body)
3. query_string match                 (only if request has query string)
4. Content-Type header match          (loose — ignore other headers)
5. Tie-breaking: priority desc → recorded_at desc
"""

import json
import logging
from typing import Any

from models import MockRecord

logger = logging.getLogger(__name__)


def find_best_match(
    records: list[MockRecord],
    method: str,
    path: str,
    query_string: str,
    request_headers: dict[str, str],
    request_body: str,
) -> MockRecord | None:
    """Run the matching pipeline against *records* (already filtered by project + enabled).

    Returns the single best matching record, or ``None``.
    """
    candidates: list[MockRecord] = list(records)

    # ── Layer 1: method + path already pre-filtered by caller ──────────

    # ── Layer 2: request_body match ───────────────────────────────────
    if request_body:
        body_candidates = _match_body(candidates, request_body)
        if not body_candidates:
            return None
        candidates = body_candidates

    # ── Layer 3: query_string match ──────────────────────────────────
    if query_string:
        qs_candidates = [r for r in candidates if r.query_string == query_string]
        if qs_candidates:
            candidates = qs_candidates

    # ── Layer 4: Content-Type header match ────────────────────────────
    ct = (request_headers.get("content-type") or "").lower()
    if ct:
        ct_candidates = [r for r in candidates if r.content_type.lower() == ct]
        if ct_candidates:
            candidates = ct_candidates

    # ── Tie-breaking ──────────────────────────────────────────────────
    if not candidates:
        return None

    # Sort by priority desc, then recorded_at desc
    candidates.sort(key=lambda r: (r.priority or 0, r.recorded_at or ""), reverse=True)
    return candidates[0]


def _match_body(candidates: list[MockRecord], request_body: str) -> list[MockRecord]:
    """Sub-filter: keep records whose stored request_body matches *request_body*."""
    matched: list[MockRecord] = []
    request_body_stripped = request_body.strip()

    for rec in candidates:
        stored_body = (rec.request_body or "").strip()
        if not stored_body:
            continue

        body_type = (rec.body_type or "text").lower()

        if body_type == "json":
            if _json_equal(stored_body, request_body_stripped):
                matched.append(rec)
        elif body_type == "binary":
            # Binary: only compare content_type + length (no byte-by-byte)
            if len(stored_body) == len(request_body_stripped):
                matched.append(rec)
        else:
            # Plain text: exact string match
            if stored_body == request_body_stripped:
                matched.append(rec)

    return matched


def _json_equal(a: str, b: str) -> bool:
    """Compare two JSON strings recursively, key-order independent."""
    try:
        obj_a = json.loads(a)
        obj_b = json.loads(b)
    except (json.JSONDecodeError, ValueError):
        return a.strip() == b.strip()  # fall back to string compare

    if isinstance(obj_a, dict) and isinstance(obj_b, dict):
        return _json_dict_equal(obj_a, obj_b)
    if isinstance(obj_a, list) and isinstance(obj_b, list):
        return _json_list_equal(obj_a, obj_b)
    return obj_a == obj_b


def _json_dict_equal(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if set(a.keys()) != set(b.keys()):
        return False
    for key in a:
        if not _json_value_equal(a[key], b[key]):
            return False
    return True


def _json_list_equal(a: list[Any], b: list[Any]) -> bool:
    if len(a) != len(b):
        return False
    return all(_json_value_equal(x, y) for x, y in zip(a, b))


def _json_value_equal(a: Any, b: Any) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        return _json_dict_equal(a, b)
    if isinstance(a, list) and isinstance(b, list):
        return _json_list_equal(a, b)
    return a == b
