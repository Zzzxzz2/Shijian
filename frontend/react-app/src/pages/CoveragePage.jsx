import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import api from '../lib/api';
import CoveragePieChart from '../components/charts/CoveragePieChart';
import TestTypeBarChart from '../components/charts/TestTypeBarChart';
import CoverageRadarChart from '../components/charts/CoverageRadarChart';
import ExecutionTrendChart from '../components/charts/ExecutionTrendChart';
import StatCard from '../components/ui/StatCard';
import UncoveredList from '../components/ui/UncoveredList';

/**
 * Coverage dashboard — dual mode:
 *   Schema mode: pie + bar + radar + uncovered list + trend
 *   Simple mode: stat cards + trend only
 */
export default function CoveragePage() {
  const { projectId } = useParams();

  // ── State ──
  const [coverage, setCoverage] = useState(null);   // GET /coverage
  const [stats, setStats] = useState(null);           // GET /stats
  const [runs, setRuns] = useState([]);               // GET /runs?limit=20
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // ── Data fetching ──
  const fetchAll = useCallback(async () => {
    setLoading(true);
    setError(null);

    const [coverageData, statsData, runsData] = await Promise.all([
      api.get(`/api/projects/${projectId}/coverage`).catch(() => null),
      api.get(`/api/projects/${projectId}/stats`).catch(() => null),
      api.get(`/api/projects/${projectId}/runs?limit=20`).catch(() => []),
    ]);

    setCoverage(coverageData);
    setStats(statsData);
    const runItems = Array.isArray(runsData) ? runsData : runsData?.items || [];
    setRuns(runItems);

    // Set error only when coverage itself failed unexpectedly (not 404 = Simple mode)
    // We detect this: if coverageData is null AND it's not a 404, show a subtle banner.
    // Since `optional` swallows everything, we differentiate via a stored flag.
    // For simplicity: if coverage returned null AND no data from any source, show error.
    if (!coverageData && !statsData && runItems.length === 0) {
      setError('数据加载失败');
    }
    setLoading(false);
  }, [projectId]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  // ── Derived data ──
  const isSchemaMode = coverage?.mode === 'schema';

  // Coverage counts: prefer API return, fallback to client-side calc
  const endpoints = coverage?.endpoints || [];
  const endpointsTotal = coverage?.endpoints_total ?? endpoints.length;
  const endpointsCovered = coverage?.endpoints_covered ?? endpoints.filter((e) => e != null && e.covered).length;
  const endpointsUncovered = coverage?.endpoints_uncovered ?? endpoints.filter((e) => e != null && !e.covered).length;

  // Stats
  const totalCases = stats?.test_cases ?? 0;
  const totalRuns = stats?.test_runs ?? 0;

  // Pass rate from last run
  const lastRun = runs[0];
  let passRate = null;
  if (lastRun?.summary) {
    let s = lastRun.summary;
    if (typeof s === 'string') {
      try { s = JSON.parse(s); } catch { s = null; }
    }
    const total = (s?.pass || 0) + (s?.fail || 0);
    if (total > 0) passRate = Math.round(((s?.pass || 0) / total) * 100);
  }

  // Tests by type
  const testsByType = coverage?.tests_by_type || stats?.test_type_counts || {};

  // ── Loading state ──
  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-8">
        {/* Skeleton header */}
        <div className="mb-6">
          <div className="skeleton h-5 w-40 mb-2" />
          <div className="skeleton h-3 w-60" />
        </div>
        {/* Skeleton stat cards */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton h-24 rounded-xl" />
          ))}
        </div>
        {/* Skeleton chart area */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton h-64 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  // ── Error banner (shown above data when coverage failed, never replaces header) ──
  const showErrorBanner = error && !coverage;

  // ── Render ──
  return (
    <div className="max-w-7xl mx-auto px-4 py-8 animate-fade-in">
      {/* ── Header ── */}
      <div className="mb-6">
        <a
          href={`/app.html#/projects/${projectId}`}
          className="text-sm text-gray-500 hover:text-accent-blue transition-colors inline-flex items-center gap-1 mb-2"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          返回项目
        </a>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-100">覆盖率仪表盘</h1>
            <p className="text-sm text-gray-500 mt-0.5">
              {isSchemaMode ? 'Schema 模式' : 'Simple 模式'}
              {isSchemaMode && (
                <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-accent-blue/10 text-accent-blue border border-accent-blue/20">
                  OpenAPI 已导入
                </span>
              )}
            </p>
          </div>
          <button
            onClick={fetchAll}
            className="px-3 py-1.5 text-sm text-gray-400 bg-surface-raised border border-border rounded-lg hover:bg-surface-overlay hover:text-gray-200 transition-colors flex items-center gap-1.5"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            刷新
          </button>
        </div>
      </div>

      {/* ── Error banner ── */}
      {showErrorBanner && (
        <div className="mb-4 p-3 bg-accent-red/10 border border-accent-red/30 rounded-lg text-center">
          <p className="text-sm text-accent-red">{error}</p>
        </div>
      )}

      {/* ── Top stat cards ── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        {isSchemaMode ? (
          <>
            <StatCard
              title="API 覆盖率"
              value={`${endpointsCovered} / ${endpointsTotal}`}
              subtitle={endpointsTotal > 0 ? `(${((endpointsCovered / endpointsTotal) * 100).toFixed(1)}%)` : ''}
              color="blue"
            />
            <StatCard title="总用例数" value={totalCases || '-'} subtitle={totalRuns ? `${totalRuns} 次执行` : ''} color="purple" />
            <StatCard
              title="末次通过率"
              value={passRate != null ? `${passRate}%` : '-'}
              subtitle={lastRun ? new Date(lastRun.created_at).toLocaleDateString('zh-CN') : ''}
              color={passRate != null && passRate >= 80 ? 'green' : 'orange'}
            />
          </>
        ) : (
          <>
            <StatCard title="总用例数" value={totalCases || '-'} subtitle="全部类型" color="blue" />
            <StatCard title="执行次数" value={totalRuns || '-'} subtitle="总计" color="purple" />
            <StatCard
              title="末次通过率"
              value={passRate != null ? `${passRate}%` : '-'}
              subtitle={lastRun ? new Date(lastRun.created_at).toLocaleDateString('zh-CN') : ''}
              color={passRate != null && passRate >= 80 ? 'green' : 'orange'}
            />
          </>
        )}
      </div>

      {/* ── Charts area ── */}
      {isSchemaMode ? (
        <>
          {/* Schema mode: pie + bar + radar */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <CoveragePieChart covered={endpointsCovered} uncovered={endpointsUncovered} />
            <TestTypeBarChart testsByType={testsByType} />
            <CoverageRadarChart testsByType={testsByType} />
          </div>

          {/* Trend chart */}
          <div className="mb-6">
            <ExecutionTrendChart runs={runs} />
          </div>

          {/* Uncovered endpoints */}
          <div className="mb-6">
            <UncoveredList endpoints={endpoints} filter="uncovered" />
          </div>
        </>
      ) : (
        <>
          {/* Simple mode: trend chart only */}
          <div className="mb-6">
            <ExecutionTrendChart runs={runs} />
          </div>

          {/* Show all endpoints if available */}
          {endpoints.length > 0 && (
            <div className="mb-6">
              <UncoveredList endpoints={endpoints} filter="all" />
            </div>
          )}
        </>
      )}
    </div>
  );
}
