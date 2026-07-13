/**
 * Failure classification card — renders a test result's failure category
 * with color-coded border/background, icon, and remediation hint.
 *
 * Backward compatible: empty `failure_category` → 未分类 (gray).
 */
const CATEGORY_STYLES = {
  assertion_failed:  { bg: 'bg-red-500/10', border: 'border-red-500/30', icon: '❌', label: '断言失败' },
  timeout:           { bg: 'bg-orange-500/10', border: 'border-orange-500/30', icon: '⏱', label: '超时' },
  connection_error:  { bg: 'bg-yellow-500/10', border: 'border-yellow-500/30', icon: '🔌', label: '连接错误' },
  unexpected_status: { bg: 'bg-blue-500/10', border: 'border-blue-500/30', icon: '📊', label: '状态码不符' },
  execution_error:   { bg: 'bg-purple-500/10', border: 'border-purple-500/30', icon: '⚙', label: '配置错误' },
  internal_error:    { bg: 'bg-gray-500/10', border: 'border-gray-500/30', icon: '🛠', label: '系统错误' },
};

const FALLBACK_STYLE = { bg: 'bg-gray-500/5', border: 'border-gray-500/20', icon: '❓', label: '未分类' };

export default function FailureCard({ result }) {
  const detail = result?.detail || {};
  const category = detail.failure_category || '';
  const style = CATEGORY_STYLES[category] || FALLBACK_STYLE;

  // Duration formatting
  const dur = result?.duration_ms;
  const duration = dur != null
    ? (dur >= 1000 ? `${(dur / 1000).toFixed(1)}s` : `${Math.round(dur)}ms`)
    : null;

  return (
    <div className={`${style.bg} ${style.border} border rounded-xl p-4`}>
      {/* Header: icon + label + duration */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-lg">{style.icon}</span>
          <span className="font-semibold text-sm text-gray-200">{style.label}</span>
        </div>
        {duration && (
          <span className="text-xs text-gray-500 font-mono">{duration}</span>
        )}
      </div>

      {/* Failure message */}
      {detail.failure_message && (
        <p className="text-sm text-gray-300 mb-1 leading-relaxed">{detail.failure_message}</p>
      )}

      {/* Status code badge */}
      {detail.status_code && (
        <span className="inline-block px-2 py-0.5 rounded text-xs font-mono bg-surface-raised text-gray-400 border border-border mb-1">
          HTTP {detail.status_code}
        </span>
      )}

      {/* Remediation hint */}
      {detail.remediation_hint && (
        <p className="text-xs text-gray-500 mt-2 flex items-start gap-1">
          <span className="shrink-0">💡</span>
          <span>{detail.remediation_hint}</span>
        </p>
      )}
    </div>
  );
}
