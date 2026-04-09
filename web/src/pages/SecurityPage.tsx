// @ts-nocheck
/**
 * SecurityPage — Security Intelligence dashboard.
 * The Onyx Security demo surface.
 *
 * Shows real-time security findings from the graph:
 *   - EOL software inventory
 *   - Critical CVEs with active exploits
 *   - Exposed secrets in files
 *   - PII exposure map
 *   - Expiring/expired certificates
 *   - Unsigned executables
 *
 * Each panel is a live query against the graph DB.
 * Clicking any finding opens the full InspectionPane.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ShieldAlert, AlertTriangle, Lock, Key, FileText,
  Eye, Cpu, ChevronRight, RefreshCw, TrendingUp,
  CheckCircle, XCircle, Activity
} from 'lucide-react'
import { graphApi, type GraphNode } from '../lib/api'
import { InspectionPane } from '../components/InspectionPane'
import { SeverityBadge as SevBadge, SeverityRow } from '../components/SeverityBadge'
import { MetricCard, TrendBadge as TrendBadgeComp } from '../components/TrendBadge'
import { AnimatePresence } from 'framer-motion'
import '../components/inspection.css'
import './SecurityPage.css'

// ── Security query definitions ─────────────────────────────────────────────

const SECURITY_PANELS = [
  {
    id:       'secrets',
    title:    'Exposed Secrets',
    icon:     Lock,
    color:    '#f87171',
    severity: 'critical',
    cypher: `MATCH (f:File) WHERE f.contains_secrets = true
             RETURN f.path AS path, f.secret_types AS secret_types,
                    f.file_category AS category, f.modified AS modified
             ORDER BY f.modified DESC LIMIT 50`,
    columns: ['path', 'secret_types', 'category'],
    emptyMsg: 'No exposed secrets found',
  },
  {
    id:       'pii',
    title:    'PII Exposure',
    icon:     Eye,
    color:    '#fbbf24',
    severity: 'high',
    cypher: `MATCH (f:File) WHERE f.pii_detected = true
             RETURN f.path AS path, f.pii_types AS pii_types,
                    f.sensitivity_level AS sensitivity, f.size_bytes AS size_bytes
             ORDER BY f.sensitivity_level DESC LIMIT 100`,
    columns: ['path', 'pii_types', 'sensitivity'],
    emptyMsg: 'No PII-containing files found',
  },
  {
    id:       'eol',
    title:    'End-of-Life Software',
    icon:     AlertTriangle,
    color:    '#fb923c',
    severity: 'high',
    cypher: `MATCH (f:File) WHERE f.eol_status = 'eol'
             RETURN f.name AS name, f.file_version AS version,
                    f.company_name AS vendor, f.path AS path
             ORDER BY f.name LIMIT 100`,
    columns: ['name', 'version', 'vendor'],
    emptyMsg: 'No EOL applications found',
  },
  {
    id:       'cves',
    title:    'Critical CVEs',
    icon:     ShieldAlert,
    color:    '#f87171',
    severity: 'critical',
    cypher: `MATCH (f:File)-[:HAS_VULNERABILITY]->(v:Vulnerability)
             WHERE v.cvss_severity IN ['critical','high']
             RETURN f.name AS app, v.cve_id AS cve_id,
                    v.cvss_score AS score, v.cvss_severity AS severity,
                    v.exploit_available AS exploit, v.actively_exploited AS active
             ORDER BY v.cvss_score DESC LIMIT 50`,
    columns: ['app', 'cve_id', 'score', 'severity', 'active'],
    emptyMsg: 'No critical CVEs detected',
  },
  {
    id:       'certs',
    title:    'Certificate Issues',
    icon:     Key,
    color:    '#a78bfa',
    severity: 'medium',
    cypher: `MATCH (f:File) WHERE f.file_category = 'certificate'
               AND (f.cert_is_expired = true OR f.days_until_expiry < 30)
             RETURN f.cert_subject AS subject, f.cert_issuer AS issuer,
                    f.days_until_expiry AS days_left, f.cert_is_expired AS expired,
                    f.path AS path
             ORDER BY f.days_until_expiry ASC LIMIT 50`,
    columns: ['subject', 'days_left', 'expired'],
    emptyMsg: 'All certificates valid',
  },
  {
    id:       'unsigned',
    title:    'Unsigned Executables',
    icon:     Cpu,
    color:    '#94a3b8',
    severity: 'medium',
    cypher: `MATCH (f:File) WHERE f.file_category = 'executable'
               AND f.signed = false
             RETURN f.name AS name, f.company_name AS vendor,
                    f.path AS path, f.architecture AS arch
             ORDER BY f.name LIMIT 100`,
    columns: ['name', 'vendor', 'arch'],
    emptyMsg: 'All executables are signed',
  },
]

const SEVERITY_ORDER = { critical: 0, high: 1, medium: 2, low: 3 }

export function SecurityPage() {
  const [inspecting, setInspecting] = useState(null)
  const [expandedPanel, setExpandedPanel] = useState(null)

  return (
    <div className="security-page">
      <div className="sp-header">
        <div>
          <h1>Security Intelligence</h1>
          <p>Real-time security findings from your filesystem graph</p>
        </div>
      </div>

      {/* Wiz-style 3-column summary cards at top */}
      <div className="sp-summary-row">
        <MetricCard
          title="Secrets Exposed"
          value={0}
          subtitle="Files with hardcoded credentials"
          severity="critical"
          trend={{ pct: -5 }}
          icon={Lock}
        />
        <MetricCard
          title="PII Files"
          value={0}
          subtitle="Files containing personal data"
          severity="high"
          trend={{ pct: 3 }}
          icon={Eye}
        />
        <MetricCard
          title="Critical CVEs"
          value={0}
          subtitle="Actively exploited vulnerabilities"
          severity="critical"
          trend={{ pct: 0 }}
          icon={ShieldAlert}
        />
        <MetricCard
          title="Expired Certs"
          value={0}
          subtitle="Certificates past expiry"
          severity="medium"
          trend={{ pct: -12 }}
          icon={AlertTriangle}
        />
      </div>

      <div className="sp-grid">
        {SECURITY_PANELS.sort((a, b) =>
          (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9)
        ).map(panel => (
          <SecurityPanel
            key={panel.id}
            panel={panel}
            expanded={expandedPanel === panel.id}
            onExpand={() => setExpandedPanel(expandedPanel === panel.id ? null : panel.id)}
            onRowClick={row => {
              // Try to load the node for inspection
              if (row.path) {
                setInspecting({
                  id: row.path,
                  label: 'File',
                  name: row.path.split('/').pop() ?? row.path,
                  props: row,
                })
              }
            }}
          />
        ))}
      </div>

      <AnimatePresence>
        {inspecting && (
          <InspectionPane
            node={inspecting}
            onClose={() => setInspecting(null)}
          />
        )}
      </AnimatePresence>
    </div>
  )
}

function SecurityPanel({ panel, expanded, onExpand, onRowClick }) {
  const Icon = panel.icon

  const { data = [], isLoading, refetch, dataUpdatedAt } = useQuery({
    queryKey: ['security', panel.id],
    queryFn:  () => graphApi.query(panel.cypher),
    refetchInterval: 60_000,
    retry: 1,
  })

  const count = data.length
  const hasFindings = count > 0

  const displayRows = expanded ? data : data.slice(0, 5)

  return (
    <div className={`sp-panel sp-panel-${panel.severity} ${expanded ? 'sp-panel-expanded' : ''}`}
         style={{ '--panel-color': panel.color } as any}>

      <div className="sp-panel-header" onClick={onExpand}>
        <div className="sp-panel-icon" style={{ background: `${panel.color}15`, color: panel.color }}>
          <Icon size={16} />
        </div>
        <div className="sp-panel-title-block">
          <div className="sp-panel-title">{panel.title}</div>
          <div className="sp-panel-meta">
            {isLoading
              ? 'Querying…'
              : hasFindings
                ? <span style={{ color: panel.color }}>{count} finding{count !== 1 ? 's' : ''}</span>
                : <span className="sp-no-findings"><CheckCircle size={11} /> {panel.emptyMsg}</span>
            }
          </div>
        </div>
        <div className="sp-panel-actions">
          {!isLoading && (
            <button
              onClick={e => { e.stopPropagation(); refetch() }}
              className="sp-refresh-btn"
              title="Refresh"
            >
              <RefreshCw size={12} />
            </button>
          )}
          {isLoading && <div className="sp-spinner" style={{ borderTopColor: panel.color }} />}
          <SeverityBadge severity={panel.severity} />
          <ChevronRight
            size={14}
            className={`sp-chevron ${expanded ? 'sp-chevron-down' : ''}`}
          />
        </div>
      </div>

      {hasFindings && (
        <div className="sp-panel-body">
          <table className="sp-table">
            <thead>
              <tr>
                {panel.columns.map(col => (
                  <th key={col}>{col.replace(/_/g, ' ')}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {displayRows.map((row, i) => (
                <tr key={i} onClick={() => onRowClick(row)} className="sp-row">
                  {panel.columns.map(col => (
                    <td key={col}>
                      <SecurityCell col={col} value={row[col]} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>

          {!expanded && count > 5 && (
            <button className="sp-show-more" onClick={onExpand}>
              Show all {count} findings <ChevronRight size={12} />
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function SecurityCell({ col, value }) {
  if (value === null || value === undefined) return <span className="sp-null">—</span>

  if (col === 'severity') {
    const c = { critical: 'sp-sev-critical', high: 'sp-sev-high', medium: 'sp-sev-medium' }
    return <span className={`sp-sev-badge ${c[value] ?? ''}`}>{String(value).toUpperCase()}</span>
  }
  if (col === 'active' || col === 'exploit') {
    return value
      ? <span className="sp-sev-badge sp-sev-critical">YES</span>
      : <span className="sp-null">No</span>
  }
  if (col === 'expired') {
    return value
      ? <span className="sp-sev-badge sp-sev-critical">EXPIRED</span>
      : <span className="sp-sev-badge sp-sev-medium">Expiring</span>
  }
  if (col === 'days_left') {
    const n = Number(value)
    if (n < 0)   return <span className="sp-sev-badge sp-sev-critical">Expired</span>
    if (n < 7)   return <span className="sp-sev-badge sp-sev-critical">{n}d</span>
    if (n < 30)  return <span className="sp-sev-badge sp-sev-high">{n}d</span>
    return <span className="sp-sev-badge sp-sev-medium">{n}d</span>
  }
  if (col === 'score') {
    const n = Number(value)
    const c = n >= 9 ? 'sp-sev-critical' : n >= 7 ? 'sp-sev-high' : 'sp-sev-medium'
    return <span className={`sp-sev-badge ${c}`}>{n.toFixed(1)}</span>
  }
  if (col === 'path') {
    const s = String(value)
    const short = s.length > 50 ? '…' + s.slice(-48) : s
    return <span className="sp-path" title={s}>{short}</span>
  }
  if (col === 'sensitivity') {
    const c = { high: 'sp-sev-critical', medium: 'sp-sev-high', low: 'sp-sev-medium' }
    return <span className={`sp-sev-badge ${c[value] ?? ''}`}>{String(value)}</span>
  }

  const s = String(value)
  return <span title={s.length > 40 ? s : undefined}>{s.length > 40 ? s.slice(0, 38) + '…' : s}</span>
}

function SeverityBadge({ severity }) {
  const config = {
    critical: { label: 'Critical', cls: 'sp-sev-critical' },
    high:     { label: 'High',     cls: 'sp-sev-high' },
    medium:   { label: 'Medium',   cls: 'sp-sev-medium' },
    low:      { label: 'Low',      cls: 'sp-sev-low' },
  }[severity] ?? { label: severity, cls: '' }
  return <span className={`sp-sev-badge ${config.cls}`}>{config.label}</span>
}


