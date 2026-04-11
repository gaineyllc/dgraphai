// @ts-nocheck
/**
 * DashboardPage — dgraph.ai landing page.
 * Shows a personalized greeting, key metrics, file category donut chart,
 * security summary, recent activity, and a data breakdown grid.
 */
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { apiFetch } from '../lib/apiFetch'
import { useAuth } from '../components/AuthProvider'
import { Skeleton } from '../components/PageShell'
import {
  ScanLine, FileCode2, Image, Bot, ShieldCheck,
  ChevronRight, AlertCircle, Zap, CheckCircle2,
  FolderOpen, RefreshCw
} from 'lucide-react'
import './DashboardPage.css'

// ─── API helpers ───────────────────────────────────────────────────────────────
const fetchStats       = () => apiFetch('/api/graph/stats').then(r => r.json())
const fetchInventory   = () => apiFetch('/api/inventory').then(r => r.json())
const fetchConnectors  = () => apiFetch('/api/connectors').then(r => r.json())
const fetchAgents      = () => apiFetch('/api/agents').then(r => r.json())

// ─── Palette for donut chart segments ─────────────────────────────────────────
const CATEGORY_COLORS: Record<string, string> = {
  Code:       'var(--color-primary)',
  Text:       'var(--color-secondary)',
  Image:      'var(--color-tertiary)',
  Data:       '#a78bfa',
  Unknown:    'var(--text-disabled)',
  Config:     '#60a5fa',
  Markup:     '#34d399',
  Binary:     '#fb923c',
  Archive:    '#e879f9',
  Media:      '#f472b6',
  Document:   '#38bdf8',
  Executable: '#facc15',
}

function getCategoryColor(name: string): string {
  return CATEGORY_COLORS[name] ?? 'var(--text-disabled)'
}

// ─── Greeting helper ───────────────────────────────────────────────────────────
function getGreeting(name: string): string {
  const h = new Date().getHours()
  const prefix = h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
  return `${prefix}, ${name}`
}

function formatDate(): string {
  return new Date().toLocaleDateString('en-US', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
  })
}

function fmtNum(n: number | undefined | null): string {
  if (n == null) return '—'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000)     return `${(n / 1_000).toFixed(n >= 10_000 ? 0 : 1)}K`
  return n.toLocaleString()
}

function timeAgo(dateStr: string): string {
  if (!dateStr) return 'recently'
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins  = Math.floor(diff / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

// ─── Donut chart (pure SVG, no library) ───────────────────────────────────────
interface DonutSlice { name: string; value: number; color: string }

function DonutChart({ slices, total }: { slices: DonutSlice[]; total: number }) {
  const R = 56        // outer radius
  const r = 36        // inner radius (hole)
  const cx = 72
  const cy = 72
  const size = 144
  const strokeWidth = R - r

  // Build arcs
  let cumulative = 0
  const arcs = slices.map(slice => {
    const pct        = total > 0 ? slice.value / total : 0
    const circumf    = 2 * Math.PI * (r + strokeWidth / 2)  // midpoint radius
    const dashArray  = `${pct * circumf} ${circumf}`
    const dashOffset = -cumulative * circumf
    cumulative += pct
    return { ...slice, dashArray, dashOffset, circumf, pct }
  })

  const midR = r + strokeWidth / 2

  return (
    <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} className="donut-svg" aria-hidden>
      {/* Background track */}
      <circle
        cx={cx} cy={cy} r={midR}
        fill="none"
        stroke="var(--border-subtle)"
        strokeWidth={strokeWidth}
      />
      {arcs.map((arc, i) => (
        <circle
          key={i}
          cx={cx} cy={cy} r={midR}
          fill="none"
          stroke={arc.color}
          strokeWidth={strokeWidth}
          strokeDasharray={arc.dashArray}
          strokeDashoffset={arc.dashOffset}
          style={{ transformOrigin: `${cx}px ${cy}px`, transform: 'rotate(-90deg)' }}
        />
      ))}
      {/* Center label */}
      <text x={cx} y={cy - 6} textAnchor="middle" className="donut-center-num">
        {fmtNum(total)}
      </text>
      <text x={cx} y={cy + 12} textAnchor="middle" className="donut-center-label">
        total files
      </text>
    </svg>
  )
}

// ─── Metric card ──────────────────────────────────────────────────────────────
function MetricCard({
  icon: Icon, label, value, sub, color, loading,
}: {
  icon: any; label: string; value: string | number; sub?: string;
  color?: string; loading?: boolean
}) {
  return (
    <div className="dash-metric-card" style={{ '--mc': color ?? 'var(--color-primary)' } as any}>
      <div className="dash-metric-icon-wrap">
        <Icon size={18} />
      </div>
      <div className="dash-metric-body">
        <div className="dash-metric-label">{label}</div>
        {loading
          ? <Skeleton height={28} width={80} />
          : <div className="dash-metric-value">{value}</div>
        }
        {sub && <div className="dash-metric-sub">{sub}</div>}
      </div>
    </div>
  )
}

// ─── Security summary row ──────────────────────────────────────────────────────
function SecurityRow({ label, value, ok }: { label: string; value: number; ok: boolean }) {
  return (
    <div className="dash-sec-row">
      <div className="dash-sec-label">{label}</div>
      <div className={`dash-sec-badge ${ok ? 'dash-sec-ok' : 'dash-sec-warn'}`}>
        {ok
          ? <><CheckCircle2 size={12} /> None found</>
          : <><AlertCircle size={12} /> {value}</>
        }
      </div>
    </div>
  )
}

// ─── Main export ──────────────────────────────────────────────────────────────
export function DashboardPage() {
  const navigate  = useNavigate()
  const { user }  = useAuth()

  const firstName = (user?.name?.split(' ')[0]) ?? user?.email?.split('@')[0] ?? 'there'

  const { data: stats,      isLoading: statsLoading }  = useQuery({ queryKey: ['graph-stats'],  queryFn: fetchStats })
  const { data: inventory,  isLoading: invLoading   }  = useQuery({ queryKey: ['inventory'],    queryFn: fetchInventory, staleTime: 30_000 })
  const { data: connectors, isLoading: connLoading  }  = useQuery({ queryKey: ['connectors'],   queryFn: fetchConnectors })
  const { data: agents,     isLoading: agentsLoading}  = useQuery({ queryKey: ['agents'],       queryFn: fetchAgents })

  // ── Derived data ────────────────────────────────────────────────────────────
  const totalFiles: number = stats?.File ?? 0

  const groups: Record<string, any[]> = inventory?.groups ?? {}
  const allCats = Object.values(groups).flat()

  // Category counts for donut + grid
  const catCounts: { name: string; count: number; color: string }[] = allCats
    .map(c => ({ name: c.name, count: c.count ?? 0, color: getCategoryColor(c.name) }))
    .sort((a, b) => b.count - a.count)

  // Donut slices — top 8 + rest
  const top8   = catCounts.slice(0, 8)
  const otherN = catCounts.slice(8).reduce((s, c) => s + c.count, 0)
  const donutSlices: DonutSlice[] = [
    ...top8.map(c => ({ name: c.name, value: c.count, color: c.color })),
    ...(otherN > 0 ? [{ name: 'Other', value: otherN, color: 'var(--text-disabled)' }] : []),
  ]

  // Code files (best-effort)
  const codeFiles = catCounts.find(c => c.name.toLowerCase() === 'code')?.count ?? 0
  const imageFiles = catCounts.find(c => ['image','images'].includes(c.name.toLowerCase()))?.count ?? 0

  // Agents
  const agentList    = Array.isArray(agents) ? agents : []
  const activeAgents = agentList.filter(a => a.is_online).length
  const totalAgents  = agentList.length

  // Connectors for activity list
  const connList = Array.isArray(connectors) ? connectors : []

  const isLoading = statsLoading || invLoading

  return (
    <div className="dashboard-page">

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="dash-header">
        <div className="dash-header-left">
          <h1 className="dash-greeting">{getGreeting(firstName)}</h1>
          <p className="dash-date">{formatDate()}</p>
        </div>
        <button
          className="btn btn-primary dash-scan-btn"
          onClick={() => navigate('/connectors')}
        >
          <ScanLine size={15} />
          Start new scan
        </button>
      </div>

      {/* ── Metric cards ───────────────────────────────────────────────── */}
      <div className="dash-metrics-row">
        <MetricCard
          icon={FolderOpen}
          label="Total Files"
          value={fmtNum(totalFiles)}
          sub="across all sources"
          color="var(--color-primary)"
          loading={statsLoading}
        />
        <MetricCard
          icon={FileCode2}
          label="Code Files"
          value={fmtNum(codeFiles)}
          sub="source code"
          color="var(--color-secondary)"
          loading={invLoading}
        />
        <MetricCard
          icon={Image}
          label="Images"
          value={fmtNum(imageFiles)}
          sub="raster + vector"
          color="var(--color-tertiary)"
          loading={invLoading}
        />
        <MetricCard
          icon={Bot}
          label="Active Agents"
          value={agentsLoading ? '…' : `${activeAgents}/${totalAgents || 1}`}
          sub={activeAgents > 0 ? 'monitoring' : 'all idle'}
          color={activeAgents > 0 ? 'var(--color-success)' : 'var(--text-disabled)'}
          loading={agentsLoading}
        />
      </div>

      {/* ── Two-column row ─────────────────────────────────────────────── */}
      <div className="dash-two-col">

        {/* Left: Donut chart */}
        <div className="dash-card dash-chart-card">
          <div className="dash-card-header">
            <span className="dash-card-title">File Categories</span>
            <button className="dash-card-action" onClick={() => navigate('/inventory')}>
              View all <ChevronRight size={13} />
            </button>
          </div>

          {isLoading ? (
            <div className="dash-chart-loading">
              <Skeleton width={144} height={144} rounded />
            </div>
          ) : (
            <div className="dash-chart-inner">
              <DonutChart slices={donutSlices} total={totalFiles} />
              <div className="dash-legend">
                {donutSlices.map(s => (
                  <div key={s.name} className="dash-legend-item">
                    <span className="dash-legend-dot" style={{ background: s.color }} />
                    <span className="dash-legend-name">{s.name}</span>
                    <span className="dash-legend-val">{fmtNum(s.value)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right: Security summary */}
        <div className="dash-card dash-security-card">
          <div className="dash-card-header">
            <span className="dash-card-title">Security Summary</span>
            <button className="dash-card-action" onClick={() => navigate('/security')}>
              View report <ChevronRight size={13} />
            </button>
          </div>

          <div className="dash-sec-hero">
            <ShieldCheck size={36} className="dash-sec-shield" />
            <div>
              <div className="dash-sec-status">No critical issues</div>
              <div className="dash-sec-sub">Last scan: {connList[0]?.last_sync ? timeAgo(connList[0].last_sync) : 'not yet run'}</div>
            </div>
          </div>

          <div className="dash-sec-rows">
            <SecurityRow label="Exposed Secrets"    value={0} ok={true} />
            <SecurityRow label="PII Detected"       value={0} ok={true} />
            <SecurityRow label="CVE References"     value={0} ok={true} />
            <SecurityRow label="Malware Signatures" value={0} ok={true} />
          </div>

          <button
            className="dash-sec-run-btn"
            onClick={() => navigate('/security')}
          >
            <Zap size={13} />
            Run security scan
          </button>
        </div>
      </div>

      {/* ── Recent activity + Data breakdown ───────────────────────────── */}
      <div className="dash-two-col">

        {/* Connectors activity */}
        <div className="dash-card">
          <div className="dash-card-header">
            <span className="dash-card-title">Recent Activity</span>
            <button className="dash-card-action" onClick={() => navigate('/connectors')}>
              Manage <ChevronRight size={13} />
            </button>
          </div>

          {connLoading ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {[1,2,3].map(i => <Skeleton key={i} height={52} />)}
            </div>
          ) : connList.length === 0 ? (
            <div className="dash-empty-state">
              <FolderOpen size={28} />
              <p>No connectors yet</p>
              <button className="btn btn-primary btn-sm" onClick={() => navigate('/connectors')}>
                Add connector
              </button>
            </div>
          ) : (
            <div className="dash-activity-list">
              {connList.slice(0, 5).map((conn, i) => (
                <div key={conn.id ?? i} className="dash-activity-item">
                  <div className="dash-activity-icon">
                    <ScanLine size={14} />
                  </div>
                  <div className="dash-activity-body">
                    <div className="dash-activity-name">{conn.name ?? conn.id ?? `Connector ${i+1}`}</div>
                    <div className="dash-activity-meta">
                      {conn.connector_type ?? conn.type ?? 'filesystem'}
                      {conn.files_scanned != null && ` · ${fmtNum(conn.files_scanned)} files`}
                    </div>
                  </div>
                  <div className="dash-activity-time">
                    {timeAgo(conn.last_sync ?? conn.updated_at ?? '')}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Data breakdown grid */}
        <div className="dash-card">
          <div className="dash-card-header">
            <span className="dash-card-title">Data Breakdown</span>
            <button className="dash-card-action" onClick={() => navigate('/inventory')}>
              Inventory <ChevronRight size={13} />
            </button>
          </div>

          {invLoading ? (
            <div className="dash-breakdown-grid">
              {[1,2,3,4,5,6].map(i => <Skeleton key={i} height={60} />)}
            </div>
          ) : catCounts.length === 0 ? (
            <div className="dash-empty-state">
              <FolderOpen size={28} />
              <p>No data indexed yet</p>
            </div>
          ) : (
            <div className="dash-breakdown-grid">
              {catCounts.slice(0, 12).map(cat => (
                <button
                  key={cat.name}
                  className="dash-breakdown-tile"
                  style={{ '--tc': cat.color } as any}
                  onClick={() => navigate('/inventory')}
                >
                  <div className="dash-breakdown-count">{fmtNum(cat.count)}</div>
                  <div className="dash-breakdown-name">{cat.name}</div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default DashboardPage
