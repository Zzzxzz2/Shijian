/**
 * Staggered list of uncovered API endpoints.
 *
 * Props:
 *   endpoints — array of { path, method, covered }
 *   filter    — optional filter: 'uncovered' (default) | 'covered' | 'all'
 */
export default function UncoveredList({ endpoints, filter = 'uncovered' }) {
  const items = (endpoints || []).filter(Boolean).filter((ep) => {
    if (filter === 'uncovered') return !ep.covered;
    if (filter === 'covered') return ep.covered;
    return true;
  });

  if (items.length === 0) {
    return (
      <div className="chart-container">
        <h3 className="text-sm font-medium text-gray-400 mb-3">端点覆盖详情</h3>
        <div className="text-center py-8">
          <p className="text-lg text-gray-500 mb-1">🎉 全部已覆盖</p>
          <p className="text-xs text-gray-600">
            {filter === 'uncovered'
              ? '所有 API 端点都已有测试用例覆盖'
              : '暂无端点数据'}
          </p>
        </div>
      </div>
    );
  }

  // Group by method for better readability
  const methodColors = {
    GET: 'text-accent-green bg-green-500/10 border-green-500/20',
    POST: 'text-accent-blue bg-blue-500/10 border-blue-500/20',
    PUT: 'text-accent-orange bg-orange-500/10 border-orange-500/20',
    PATCH: 'text-accent-orange bg-orange-500/10 border-orange-500/20',
    DELETE: 'text-accent-red bg-red-500/10 border-red-500/20',
  };

  return (
    <div className="chart-container">
      <h3 className="text-sm font-medium text-gray-400 mb-3">
        {filter === 'uncovered' ? `未覆盖端点（${items.length} 个）` : `端点列表（${items.length} 个）`}
      </h3>
      <div className="space-y-1 max-h-80 overflow-y-auto">
        {items.map((ep, idx) => {
          const method = (ep.method || 'GET').toUpperCase();
          const colors = methodColors[method] || 'text-gray-400 bg-gray-500/10 border-gray-500/20';
          const statusColor = ep.covered ? 'text-accent-green' : 'text-gray-500';

          return (
            <div
              key={`${ep.method}-${ep.path}-${idx}`}
              className="flex items-center gap-3 px-3 py-2 rounded-lg bg-surface-overlay/50 hover:bg-surface-overlay transition-colors animate-slide-in"
              style={{ animationDelay: `${idx * 30}ms`, animationFillMode: 'both' }}
            >
              <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-mono font-medium border ${colors}`}>
                {method}
              </span>
              <span className="flex-1 text-sm text-gray-300 font-mono truncate">
                {ep.path}
              </span>
              <span className={`text-xs ${statusColor}`}>
                {ep.covered ? '✓ 已覆盖' : '未测试'}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
