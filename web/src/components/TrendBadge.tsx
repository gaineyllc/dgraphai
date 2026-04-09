// @ts-nocheck
/**
 * TrendBadge — shows delta/trend for security metrics.
 * Matches Wiz's ↓93% green / ↑10% red pill style.
 */
import { TrendingDown, TrendingUp, Minus } from 'lucide-react'
import './TrendBadge.css'

interface TrendBadgeProps {
  /** Percentage change — negative = improvement (fewer issues), positive = worse */
  pct:      number
  /** Override auto direction */
  direction?: 'up' | 'down' | 'flat'
  /** For security metrics: down = good (fewer issues). Set inverse=true for metrics where up = good */
  inverse?: boolean
  size?:    'sm' | 'md'
}

export function TrendBadge({ pct, direction, inverse = false, size = 'sm' }: TrendBadgeProps) {
  const dir = direction ?? (pct < 0 ? 'down' : pct > 0 ? 'up' : 'flat')
  const absPct = Math.abs(pct)

  // For security metrics: down (fewer issues) = positive/green
  // inverse=true means up = green (e.g. coverage metrics)
  const isPositive = inverse ? dir === 'up' : dir === 'down'

  const colorClass = isPositive ? 'trend-positive' : dir === 'flat' ? 'trend-flat' : 'trend-negative'
  const Icon = dir === 'down' ? TrendingDown : dir === 'up' ? TrendingUp : Minus
  const iconSize = size === 'sm' ? 10 : 12

  return (
    <span className={`trend-badge trend-badge-${size} ${colorClass}`}>
      <Icon size={iconSize} />
      {absPct.toFixed(absPct >= 10 ? 0 : 1)}%
    </span>
  )
}

/** MetricCard — matches Wiz's large-number + trend card design */
interface MetricCardProps {
  title:      string
  value:      number | string
  subtitle?:  string
  trend?:     { pct: number; inverse?: boolean }
  severity?:  'critical' | 'high' | 'medium' | 'low' | 'info'
  icon?:      React.ComponentType<{ size?: number; style?: any }>
  onClick?:   () => void
  className?: string
}

const SEVERITY_COLORS = {
  critical: '#dc2626',
  high:     '#f97316',
  medium:   '#f59e0b',
  low:      '#6b7280',
  info:     '#4f8ef7',
}

export function MetricCard({ title, value, subtitle, trend, severity, icon: Icon, onClick, className = '' }: MetricCardProps) {
  const color = severity ? SEVERITY_COLORS[severity] : '#4f8ef7'

  return (
    <div
      className={`metric-card ${className} ${onClick ? 'metric-card-clickable' : ''}`}
      style={{ '--mc': color } as any}
      onClick={onClick}
    >
      <div className="metric-card-header">
        {Icon && (
          <div className="metric-card-icon">
            <Icon size={16} style={{ color }} />
          </div>
        )}
        <span className="metric-card-title">{title}</span>
      </div>
      <div className="metric-card-body">
        <span className="metric-card-value" style={{ color }}>
          {typeof value === 'number' ? value.toLocaleString() : value}
        </span>
        {trend && (
          <TrendBadge pct={trend.pct} inverse={trend.inverse} />
        )}
      </div>
      {subtitle && <div className="metric-card-sub">{subtitle}</div>}
    </div>
  )
}
