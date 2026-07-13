"""Perf Test Executor - Placeholder for performance test execution."""

from models import TestCase


async def execute_perf_case(case: TestCase, project_url: str) -> dict:
    """Placeholder for perf test execution."""
    return {
        "case_id": case.id,
        "status": "error",
        "detail": {"error": "Perf testing not implemented yet"},
        "duration_ms": 0,
        "error": "Perf testing not implemented yet",
    }
