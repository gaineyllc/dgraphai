// @ts-nocheck
/**
 * SeverityBadge — the universal severity visual language.
 * Matches Wiz's C/H/M/L circular badge system used throughout the platform.
 * Every security finding, CVE, alert, and issue gets one of these.
 */
import './SeverityBadge.css'

type Level = 'critical' | 'high' | 'medium' | 'low' | 'info' | 'none'

interface SeverityBadgeProps {
  level:    Level
  size?:    'sm' | 'md' | 'lg'  // sm=16px, md=20px (default), lg=28px
  showLabel?: boolean             // show full text label next to badge
  count?:   number                // optional count next to badge
}

const LEVEL_CONFIG: Record<Level, { letter: string; label: string; color: string; bg: string; textColor: string }> = {
  critical: { letter: 'C', label: 'Critical', color: '#dc2626', bg: '#dc2626', textColor: '#fff' },
  high:     { letter: 'H', label: 'High',     color: '#f97316', bg: '#f97316', textColor: '#fff' },
  medium:   { letter: 'M', label: 'Medium',   color: '#f59e0b', bg: '#f59e0b', textColor: '#fff' },
  low:      { letter: 'L', label: 'Low',      color: '#6b7280', bg: '#6b7280', textColor: '#fff' },
  info:     { letter: 'I', label: 'Info',     color: '#4f8ef7', bg: '#4f8ef7', textColor: '#fff' },
  none:     { letter: '—', label: 'None',     color: '#252535', bg: '#252535', textColor: '#55557a' },
}

const SIZE_MAP = { sm: 16, md: 20, lg: 28 }
const FONT_MAP = { sm: 9,  md: 11, lg: 13 }

export function SeverityBadge({ level, size = 'md', showLabel = false, count }: SeverityBadgeProps) {
  const cfg  = LEVEL_CONFIG[level] ?? LEVEL_CONFIG.none
  const px   = SIZE_MAP[size]
  const fs   = FONT_MAP[size]

  return (
    <span className="severity-badge-wrap">
      <span
        className="severity-badge"
        title={cfg.label}
        style={{
          width:           px,
          height:          px,
          background:      cfg.bg,
          fontSize:        fs,
          lineHeight:      `${px}px`,
        }}
      >
        {cfg.letter}
      </span>
      {showLabel && (
        <span className="severity-badge-label" style={{ color: cfg.color }}>
          {cfg.label}
        </span>
      )}
      {count !== undefined && (
        <span className="severity-badge-count">{count.toLocaleString()}</span>
      )}
    </span>
  )
}

/** Pill variant — shows "Critical (142)" style */
export function SeverityPill({ level, count }: { level: Level; count: number }) {
  const cfg = LEVEL_CONFIG[level] ?? LEVEL_CONFIG.none
  return (
    <span className="severity-pill" style={{ '--sc': cfg.color } as any}>
      <SeverityBadge level={level} size="sm" />
      <span className="severity-pill-count">{count.toLocaleString()}</span>
    </span>
  )
}

/** Row of pills for a findings summary */
export function SeverityRow({
  critical = 0, high = 0, medium = 0, low = 0
}: { critical?: number; high?: number; medium?: number; low?: number }) {
  return (
    <div className="severity-row">
      {critical > 0 && <SeverityPill level="critical" count={critical} />}
      {high     > 0 && <SeverityPill level="high"     count={high}     />}
      {medium   > 0 && <SeverityPill level="medium"   count={medium}   />}
      {low      > 0 && <SeverityPill level="low"      count={low}      />}
      {critical === 0 && high === 0 && medium === 0 && low === 0 && (
        <span style={{ fontSize: 12, color: '#10b981' }}>✓ No findings</span>
      )}
    </div>
  )
}

export type { Level as SeverityLevel }
