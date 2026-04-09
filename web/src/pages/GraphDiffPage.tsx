// @ts-nocheck
/**
 * Graph Diff — "What changed since last scan?"
 * Shows nodes added/modified in the last N hours, grouped by type.
 * This is the feature that brings users back daily — makes scans feel alive.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Clock, TrendingUp, FileText, User, Shield, Database,
  ArrowUpRight, RefreshCw, ChevronRight, Sparkles, AlertTriangle
} from 'lucide-react'
import { apiFetch } from '../lib/apiFetch'
import './GraphDiffPage.css'

const TIME_OPTIONS = [
  { label: '1 hour',   hours: 1   },
  { label: '6 hours',  hours: 6   },
  { label: '24 hours', hours: 24  },
  { label: '3 days',   hours: 72  },
  { label: '7 days',   hours: 168 },
]

const TYPE_META: Record<string, { icon: any; color: string; label: string }> = {
  File:          { icon: FileText,    color: '#4f8ef7', label: 'Files' },
  Person:        { icon: User,        color: '#f472b6', label: 'People' },
  Vulnerability: { icon: Shield,      color: '#f87171', label: 'CVEs' },
  Application:   { icon: Database,    color: '#8b5cf6', label: 'Applications' },
  Certificate:   { icon: AlertTriangle, color: '#fbbf24', label: 'Certificates' },
}

const api = {
  diff: (hours: number) =>
    apiFetch(`/api/graph/intel/diff?since_hours=${hours}&limit=200`).then(r => r.json()),
}

export function GraphDiffPage() {
  const navigate = useNavigate()
  const [hours, setHours] = useState(24)

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ['graph-diff', hours],
    queryFn:  () => api.diff(hours),
    refetchInterval: 60_000,
  })

  const total    = data?.total_new ?? 0
  const byType   = data?.by_type   ?? {}
  const nodes    = data?.recent_nodes ?? []

  // Security-relevant findings in this window
  const findings = nodes.filter(n =>
    n.labels?.includes('Vulnerability') ||
    n.file_category === 'certificate' ||
    n.contains_secrets ||
    n.pii_detected
  )

  return (
    <div className="diff-page">
      {/* Header */}
      <div className="diff-header">
        <div className="diff-header-left">
          <div className="diff-header-icon"><TrendingUp size={20} /></div>
          <div>
            <h1>What changed</h1>
            <p>New and updated nodes across your knowledge graph</p>
          </div>
        </div>
        <div className="diff-header-right">
          <div className="diff-time-tabs">
            {TIME_OPTIONS.map(o => (
              <button
                key={o.hours}
                className={`diff-time-tab ${hours === o.hours ? 'active' : ''}`}
                onClick={() => setHours(o.hours)}
              >
                {o.label}
              </button>
            ))}
          </div>
          <button onClick={() => refetch()} className="diff-refresh-btn" disabled={isFetching}>
            <RefreshCw size={13} className={isFetching ? 'diff-spin' : ''} />
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="diff-loading">
          <RefreshCw size={20} className="diff-spin" />
          <span>Loading changes…</span>
        </div>
      ) : (
        <>
          {/* Summary row */}
          {total === 0 ? (
            <div className="diff-empty">
              <Sparkles size={32} />
              <h3>No changes in the last {TIME_OPTIONS.find(o => o.hours === hours)?.label}</h3>
              <p>Everything looks the same since your last scan.</p>
            </div>
          ) : (
            <>
              <div className="diff-summary-row">
                <div className="diff-total-card">
                  <div className="diff-total-num">{fmt(total)}</div>
                  <div className="diff-total-label">new or updated nodes</div>
                </div>
                {Object.entries(byType).map(([type, count]) => {
                  const meta = TYPE_META[type] ?? { icon: Database, color: '#6b7280', label: type }
                  const Icon = meta.icon
                  return (
                    <motion.div key={type} className="diff-type-card"
                      style={{ '--c': meta.color } as any}
                      initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
                      <Icon size={16} />
                      <div className="diff-type-count">{fmt(count as number)}</div>
                      <div className="diff-type-label">{meta.label}</div>
                    </motion.div>
                  )
                })}
              </div>

              {/* Security findings banner */}
              {findings.length > 0 && (
                <motion.div className="diff-findings-banner"
                  initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                  <AlertTriangle size={16} />
                  <span>
                    <strong>{findings.length} security-relevant</strong> node{findings.length > 1 ? 's' : ''} detected in this window
                  </span>
                  <button
                    onClick={() => navigate(`/security`)}
                    className="diff-findings-link">
                    View in Security <ArrowUpRight size={11} />
                  </button>
                </motion.div>
              )}

              {/* Node list */}
              <div className="diff-section-title">Recent nodes</div>
              <div className="diff-node-list">
                {nodes.map((node, i) => {
                  const type    = node.labels?.[0] ?? 'Node'
                  const meta    = TYPE_META[type] ?? { icon: Database, color: '#6b7280', label: type }
                  const Icon    = meta.icon
                  const name    = node.name ?? 'Unknown'
                  const indexed = node.indexed_at ? relTime(node.indexed_at) : ''
                  const isNew   = node.indexed_at && isWithinHours(node.indexed_at, 1)

                  return (
                    <motion.div key={node.id ?? i}
                      className="diff-node-row"
                      style={{ '--c': meta.color } as any}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: Math.min(i, 12) * 0.025 }}
                      onClick={() => navigate(`/query?q=${encodeURIComponent(`MATCH (n) WHERE id(n) = '${node.id}' RETURN n`)}`)}
                    >
                      <div className="diff-node-icon"><Icon size={13} /></div>
                      <div className="diff-node-body">
                        <div className="diff-node-name">{name}</div>
                        <div className="diff-node-meta">
                          <span className="diff-node-type">{type}</span>
                          {node.file_category && <span className="diff-node-cat">{node.file_category}</span>}
                        </div>
                      </div>
                      <div className="diff-node-right">
                        {isNew && <span className="diff-new-badge">NEW</span>}
                        <span className="diff-node-time">{indexed}</span>
                        <ChevronRight size={12} className="diff-node-arrow" />
                      </div>
                    </motion.div>
                  )
                })}
              </div>

              {nodes.length >= 200 && (
                <div className="diff-truncated">
                  Showing 200 most recent — <button
                    onClick={() => navigate('/query?q=' + encodeURIComponent(
                      `MATCH (n) WHERE n.tenant_id = $tid AND n.indexed_at > datetime() - duration('PT${hours}H') RETURN n ORDER BY n.indexed_at DESC LIMIT 1000`
                    ))}>
                    view all in Graph Explorer
                  </button>
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  )
}

function fmt(n: number) {
  if (n >= 1_000_000) return `${(n/1_000_000).toFixed(1)}M`
  if (n >= 1_000)     return `${(n/1_000).toFixed(n >= 10_000 ? 0 : 1)}K`
  return n.toLocaleString()
}

function relTime(iso: string) {
  const ms = Date.now() - new Date(iso).getTime()
  const h  = Math.floor(ms / 3_600_000)
  const m  = Math.floor(ms / 60_000)
  if (m < 1)  return 'just now'
  if (m < 60) return `${m}m ago`
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h/24)}d ago`
}

function isWithinHours(iso: string, hours: number) {
  return Date.now() - new Date(iso).getTime() < hours * 3_600_000
}
