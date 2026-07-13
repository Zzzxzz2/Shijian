/**
 * Shared mock data for coverage dashboard Playwright tests.
 * All 3 API endpoints (coverage, stats, runs) can be mocked per-scenario.
 */

/** Schema mode: 20 endpoints, 12 covered (60%) */
export function schemaCoverageData(overrides = {}) {
  const endpoints = Array.from({ length: 20 }, (_, i) => ({
    path: i < 12 ? `/api/v1/users/${i + 1}` : `/api/v1/items/${i + 1}`,
    method: i % 4 === 0 ? 'GET' : i % 4 === 1 ? 'POST' : i % 4 === 2 ? 'DELETE' : 'PATCH',
    covered: i < 12,
  }));

  return {
    mode: 'schema',
    endpoints_total: 20,
    endpoints_covered: 12,
    endpoints_uncovered: 8,
    endpoints,
    tests_by_type: { api: 15, ui: 8, perf: 3 },
    ...overrides,
  };
}

/** Simple mode (no OpenAPI) */
export function simpleCoverageData(overrides = {}) {
  return {
    mode: 'simple',
    endpoints_total: 0,
    endpoints_covered: 0,
    endpoints_uncovered: 0,
    endpoints: [],
    tests_by_type: {},
    ...overrides,
  };
}

/** Stats data */
export function statsData(overrides = {}) {
  return {
    test_cases: 26,
    test_runs: 12,
    test_type_counts: { api: 15, ui: 8, perf: 3 },
    ...overrides,
  };
}

/** Runs data — up to 20 records */
export function runsData(count = 20, overrides = {}) {
  const runs = Array.from({ length: count }, (_, i) => ({
    id: i + 1,
    status: 'completed',
    summary: { pass: 8 + (i % 5), fail: 2 - (i % 3) },
    created_at: new Date(Date.now() - i * 86400000).toISOString(),
  }));
  return { items: runs, total: runs.length, ...overrides };
}

/** Empty runs */
export function emptyRunsData() {
  return { items: [], total: 0 };
}

/** 100% coverage — all endpoints covered */
export function fullCoverageData() {
  const endpoints = Array.from({ length: 10 }, (_, i) => ({
    path: `/api/v1/endpoint/${i}`,
    method: i % 3 === 0 ? 'GET' : i % 3 === 1 ? 'POST' : 'PUT',
    covered: true,
  }));
  return {
    mode: 'schema',
    endpoints_total: 10,
    endpoints_covered: 10,
    endpoints_uncovered: 0,
    endpoints,
    tests_by_type: { api: 8, ui: 2 },
  };
}

/** 0% coverage */
export function zeroCoverageData() {
  const endpoints = Array.from({ length: 10 }, (_, i) => ({
    path: `/api/v1/uncovered/${i}`,
    method: i % 2 === 0 ? 'GET' : 'POST',
    covered: false,
  }));
  return {
    mode: 'schema',
    endpoints_total: 10,
    endpoints_covered: 0,
    endpoints_uncovered: 10,
    endpoints,
    tests_by_type: { api: 0 },
  };
}

/** Large project — 120 endpoints, 80 uncovered */
export function largeCoverageData() {
  // 120 endpoints, 40 covered (indices 80-119), 80 uncovered (indices 0-79)
  const endpoints = Array.from({ length: 120 }, (_, i) => ({
    path: `/api/v2/items/${i}`,
    method: i % 4 === 0 ? 'GET' : i % 4 === 1 ? 'POST' : i % 4 === 2 ? 'PUT' : 'DELETE',
    covered: i >= 80,
  }));
  return {
    mode: 'schema',
    endpoints_total: 120,
    endpoints_covered: 40,
    endpoints_uncovered: 80,
    endpoints,
    tests_by_type: { api: 30, ui: 10 },
  };
}

/** All runs failed */
export function allFailedRunsData(count = 5) {
  const runs = Array.from({ length: count }, (_, i) => ({
    id: i + 1,
    status: 'completed',
    summary: { pass: 0, fail: 10 },
    created_at: new Date(Date.now() - i * 86400000).toISOString(),
  }));
  return { items: runs, total: runs.length };
}

/** 0 endpoints (empty project) */
export function emptyCoverageData() {
  return {
    mode: 'schema',
    endpoints_total: 0,
    endpoints_covered: 0,
    endpoints_uncovered: 0,
    endpoints: [],
    tests_by_type: {},
  };
}

/** Abnormal endpoint data (missing fields) */
export function abnormalCoverageData() {
  const endpoints = [
    { path: '/api/ok', method: 'GET', covered: true },
    { covered: false },
    { path: '/api/partial', covered: true },
    null,
    { path: '/api/weird', method: 'POST', covered: false },
  ];
  return {
    mode: 'schema',
    endpoints_total: 5,
    endpoints_covered: 2,
    endpoints_uncovered: 3,
    endpoints,
    tests_by_type: { api: 3, ui: 0, perf: null },
  };
}

/** Set up API route mocks on the page */
export async function mockApi(page, coverage, stats, runs) {
  await page.route('**/api/projects/*/coverage', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(coverage),
    });
  });
  await page.route('**/api/projects/*/stats', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(stats),
    });
  });
  await page.route('**/api/projects/*/runs*', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(runs),
    });
  });
}
