import { useState, useEffect, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import api from '../lib/api';
import FailureCard from '../components/ui/FailureCard';

/**
 * Run detail page — shows execution summary + per-case results
 * with failure classification cards (p1f).
 *
 * Data sources:
 *   GET /api/projects/{pid}/runs/{rid}         → run metadata + cases
 *   GET /api/projects/{pid}/runs/{rid}/results → per-case results
 */
export default function RunDetailPage() {
  const { projectId, runId } = useParams();

  // ── State ──
  const [run, setRun] = useState(null);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // ── Fetch ──
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);

    const [runData, resultsData] = await Promise.all([
      api.get(`/api/projects/${projectId}/runs/${runId}`).catch((e) => {
        setError(e?.detail || '加载运行详情失败');
        return null;
      }),
      api.get(`/api/projects/${projectId}/runs/${runId}/results`).catch(() => []),
    ]);

    setRun(runData);
    setResults(Array.isArray(resultsData) ? resultsData : []);
    setLoading(false);
  }, [projectId, runId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // ── Derive summary ──
  const summary = (() => {
    if (!run?.summary) return null;
    const raw = typeof run.summary === 'string' ? (() => {
      try { return JSON.parse(run.summary); } catch { return null; }
    })() : run.summary;
    return raw;
  })();

  const totalPass = summary?.pass ?? results.filter((r) => r.status === 'pass').length;
  const totalFail = summary?.fail ?? results.filter((r) => r.status === 'fail').length;
  const totalError = summary?.error ?? results.filter((r) => r.status === 'error').length;
  const total = totalPass + totalFail + totalError;

  // Map case_id → case name
  const caseMap = {};
  if (run?.cases) {
    for (const c of run.cases) {
      caseMap[c.id] = c.name;
    }
  }

  // ── Duration formatting ──
  const fmtDuration = (ms) => {
    if (ms == null) return null;
    return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
  };

  const runDuration =
    run?.started_at && run?.finished_at
      ? (new Date(run.finished_at) - new Date(run.started_at))
      : null;

  // ── Loading ──
  if (loading) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-8">
        <div className="skeleton h-5 w-48 mb-2" />
        <div className="skeleton h-3 w-72 mb-6" />
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 mb-6">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="skeleton h-20 rounded-xl" />
          ))}
        </div>
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="skeleton h-24 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  // ── Error ──
  if (error && !run) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-8">
        <div className="p-6 bg-red-500/10 border border-red-500/30 rounded-xl text-center">
          <p className="text-red-400 mb-2">{error}</p>
          <Link
            to={`/projects/${projectId}/coverage`}
            className="text-sm text-accent-blue hover:underline"
          >
            ← 返回仪表盘
          </Link>
        </div>
      </div>
    );
  }

  // ── Status badge ──
  const statusBadge = (() => {
    const s = run?.status;
    if (s === 'running') return { label: '运行中', cls: 'bg-blue-500/20 text-blue-400 border-blue-500/30' };
    if (s === 'queued') return { label: '排队中', cls: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30' };
    if (run?.result === 'pass') return { label: '通过', cls: 'bg-green-500/20 text-green-400 border-green-500/30' };
    if (run?.result === 'fail') return { label: '失败', cls: 'bg-red-500/20 text-red-400 border-red-500/30' };
    return { label: s || '未知', cls: 'bg-gray-500/20 text-gray-400 border-gray-500/30' };
  })();

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 animate-fade-in">
      {/* ── Header ── */}
      <div className="mb-6">
        <Link
          to={`/projects/${projectId}/coverage`}
          className="text-sm text-gray-500 hover:text-accent-blue transition-colors inline-flex items-center gap-1 mb-3"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          返回仪表盘
        </Link>

        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <h1 className="text-xl font-bold text-gray-100">执行详情</h1>
            <p className="text-sm text-gray-500 mt-0.5">
              #{runId}
              {run?.created_at && (
                <span className="ml-2">· {new Date(run.created_at).toLocaleString('zh-CN')}</span>
              )}
              {runDuration != null && (
                <span className="ml-2">· 耗时 {fmtDuration(runDuration)}</span>
              )}
            </p>
          </div>
          <span className={`px-2.5 py-1 rounded-lg text-xs font-medium border ${statusBadge.cls}`}>
            {statusBadge.label}
          </span>
        </div>
      </div>

      {/* ── Summary stat cards ── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <div className="bg-surface-raised border border-border rounded-xl p-3 text-center">
          <p className="text-2xl font-bold text-gray-100">{total}</p>
          <p className="text-xs text-gray-500 mt-0.5">总用例</p>
        </div>
        <div className="bg-surface-raised border border-border rounded-xl p-3 text-center">
          <p className="text-2xl font-bold text-green-400">{totalPass}</p>
          <p className="text-xs text-gray-500 mt-0.5">通过</p>
        </div>
        <div className="bg-surface-raised border border-border rounded-xl p-3 text-center">
          <p className="text-2xl font-bold text-red-400">{totalFail}</p>
          <p className="text-xs text-gray-500 mt-0.5">失败</p>
        </div>
        <div className="bg-surface-raised border border-border rounded-xl p-3 text-center">
          <p className="text-2xl font-bold text-orange-400">{totalError}</p>
          <p className="text-xs text-gray-500 mt-0.5">错误</p>
        </div>
      </div>

      {/* ── Results list ── */}
      <div className="space-y-3">
        {results.length === 0 && (
          <div className="text-center py-12 text-gray-500">
            <p className="text-sm">暂无执行结果</p>
          </div>
        )}

        {results.map((r) => {
          const caseName = caseMap[r.case_id] || `用例 #${r.case_id}`;
          const isPass = r.status === 'pass';

          return (
            <div
              key={r.id}
              className={`rounded-xl border ${
                isPass
                  ? 'border-green-500/20 bg-green-500/5'
                  : 'border-border bg-surface-raised'
              } overflow-hidden`}
            >
              {/* Case header */}
              <div className="px-4 py-3 flex items-center justify-between border-b border-border/50">
                <div className="flex items-center gap-2 min-w-0">
                  <span className={`w-2 h-2 rounded-full shrink-0 ${
                    isPass ? 'bg-green-400' : r.status === 'error' ? 'bg-orange-400' : 'bg-red-400'
                  }`} />
                  <span className="text-sm font-medium text-gray-200 truncate">{caseName}</span>
                  <span className={`text-xs px-1.5 py-0.5 rounded font-mono ${
                    isPass
                      ? 'bg-green-500/10 text-green-400'
                      : r.status === 'error'
                        ? 'bg-orange-500/10 text-orange-400'
                        : 'bg-red-500/10 text-red-400'
                  }`}>
                    {r.status}
                  </span>
                </div>
                {r.duration_ms != null && (
                  <span className="text-xs text-gray-500 font-mono shrink-0 ml-2">
                    {fmtDuration(r.duration_ms)}
                  </span>
                )}
              </div>

              {/* Body: FailureCard or pass placeholder */}
              <div className="px-4 py-3">
                {isPass ? (
                  <div className="flex items-center gap-2 text-sm text-green-400/70">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    所有断言通过
                  </div>
                ) : (
                  <FailureCard result={r} />
                )}
              </div>

              {/* Expandable result details */}
              {r.detail && Object.keys(r.detail).length > 0 && (
                <div className="px-4 pb-3">
                  <details className="group">
                    <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-300 transition-colors">
                      查看请求详情
                    </summary>
                    <pre className="mt-2 p-3 bg-surface rounded-lg text-xs text-gray-400 overflow-auto max-h-48 font-mono">
                      {JSON.stringify(r.detail, null, 2)}
                    </pre>
                  </details>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* ── Refresh button (for running runs) ── */}
      {run?.status === 'running' && (
        <div className="mt-6 text-center">
          <button
            onClick={fetchData}
            className="px-4 py-2 text-sm text-accent-blue bg-accent-blue/10 border border-accent-blue/20 rounded-lg hover:bg-accent-blue/20 transition-colors inline-flex items-center gap-2"
          >
            <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            刷新状态
          </button>
        </div>
      )}
    </div>
  );
}
