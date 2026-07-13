/**
 * Animated stat card with border glow effect.
 * Uses CSS border-glow class for the animated gradient border.
 *
 * Props:
 *   title    — label text
 *   value    — primary number/string
 *   subtitle — optional secondary text (e.g. "/ 15")
 *   color    — accent color class: 'blue' | 'green' | 'purple' | 'orange' (default 'blue')
 */
export default function StatCard({ title, value, subtitle, color = 'blue' }) {
  const colorMap = {
    blue: 'from-blue-500/30 via-blue-400/10 to-blue-500/30',
    green: 'from-green-500/30 via-green-400/10 to-green-500/30',
    purple: 'from-purple-500/30 via-purple-400/10 to-purple-500/30',
    orange: 'from-orange-500/30 via-orange-400/10 to-orange-500/30',
  };

  const gradientClass = colorMap[color] || colorMap.blue;

  return (
    <div className="relative overflow-hidden rounded-xl bg-surface-raised border border-border group">
      {/* Animated border glow */}
      <div
        className={`absolute inset-0 rounded-xl bg-gradient-to-r ${gradientClass} opacity-40 group-hover:opacity-70 transition-opacity duration-500 pointer-events-none`}
        style={{ padding: '1px', WebkitMask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)', mask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)', WebkitMaskComposite: 'xor', maskComposite: 'exclude' }}
      />
      {/* Content */}
      <div className="relative p-4 bg-surface rounded-xl m-[1px]">
        <p className="text-xs text-gray-500 mb-1.5 tracking-wide uppercase">{title}</p>
        <div className="flex items-baseline gap-1">
          <span className="text-2xl font-bold text-gray-100">{value ?? '-'}</span>
          {subtitle != null && (
            <span className="text-sm text-gray-500">{subtitle}</span>
          )}
        </div>
      </div>
    </div>
  );
}
