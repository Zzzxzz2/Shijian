# Contributing

1. Create a focused branch.
2. Do not commit generated data or credentials.
3. Run `python -m pytest -q --ignore=tests/e2e`.
4. Run `npm ci && npm run build:spa-css && npm run build` in `frontend/react-app`.
5. For executor, auth, Mock, Schedule or UI changes, also run `run_e2e.py` against local services.
6. Keep API behavior documented by FastAPI OpenAPI; update hand-written docs only for stable concepts and workflows.

Bug fixes should target the shared root cause and include the smallest regression test that would have failed before the fix.
