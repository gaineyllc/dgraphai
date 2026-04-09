// @ts-nocheck
/**
 * Audit Log — shows all platform actions for this tenant.
 * Required for SOC 2, HIPAA, and enterprise security reviews.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Shield, Search, Download, RefreshCw, ChevronDown, User, CheckCircle, XCircle, AlertTriangle } from 'lucide-react'
import './AuditLogPage.css'

const token = () => localStorage.getItem('dgraphai_token') || ''

const api = {
  list: (action: string, offset: number, limit: number) =>
    fetch(`/api/audit?action=${encodeURIComponent(action)}&offset=${offset}&limit=${limit}`, {
      headers: { Authorization: `Bearer ${token()}` },
    }).then(r => r.json()),
}

const STATUS_ICON = {
  success: <CheckCircle  size={12} style={{ color: '#10b981' }} />,
  failure: <XCircle      size={12} style={{ color: '#f87171' }} />,
  error:   <AlertTriangle size={12} style={{ color: '#f59e0b' }} />,
}

const ACTION_GROUPS = [
  { label: 'All', value: '' },
  { label: 'Auth', value: 'auth.' },
  { label: 'Connectors', value: 'connector.' },
  { label: 'Queries', value: 'query.' },
  { label: 'Users', value: 'user.' },
  { label: 'Settings', value: 'settings.' },
  { label: 'Exports', value: 'export.' },
]

const PAGE_SIZE = 50

export function AuditLogPage() {
  const [actionFilter, setActionFilter] = useState('')
  const [offset,       setOffset]       = useState(0)
  const [expanded,     setExpanded]     = useState<string | null>(null)

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ['audit-log', actionFilter, offset],
    queryFn:  () => api.list(actionFilter, offset, PAGE_SIZE),
    refetchInterval: 30_000,
  })

  const entries = data?.entries ?? []
  const hasMore = entries.length === PAGE_SIZE

  const exportCSV = () => {
    const rows = entries.map(e => [
      e.created_at, e.action, e.resource || '', e.status,
      e.user_id || 'system', e.ip_address || '',
    ])
    const csv = ['Timestamp,Action,Resource,Status,User,IP']
      .concat(rows.map(r => r.map(v => `"${v}"`).join(',')))
      .join('\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
    const a   = document.createElement('a')
    a.href = url; a.download = `audit-log-${new Date().toISOString().split('T')[0]}.csv`; a.click()
  }

  return (
    <div className="audit-page">
      <div className="audit-header">
        <div>
          <h1>Audit Log</h1>
          <p>Immutable record of all actions in this workspace</p>
        </div>
        <div className="audit-header-actions">
          <button onClick={() => refetch()} className="audit-btn-ghost" disabled={isFetching}>
            <RefreshCw size={13} className={isFetching ? 'audit-spin' : ''} /> Refresh
          </button>
          <button onClick={exportCSV} className="audit-btn-ghost">
            <Download size={13} /> Export CSV
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="audit-filters">
        <div className="audit-filter-tabs">
          {ACTION_GROUPS.map(g => (
            <button key={g.value}
              className={`audit-filter-tab ${actionFilter === g.value ? 'active' : ''}`}
              onClick={() => { setActionFilter(g.value); setOffset(0) }}>
              {g.label}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="audit-loading">Loading audit log…</div>
      ) : (
        <>
          <div className="audit-table-wrap">
            <table className="audit-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Action</th>
                  <th>Resource</th>
                  <th>User</th>
                  <th>IP</th>
                  <th>Status</th>
                  <th style={{ width: 24 }} />
                </tr>
              </thead>
              <tbody>
                {entries.map(e => (
                  <>
                    <motion.tr key={e.id}
                      className={`audit-row ${expanded === e.id ? 'expanded' : ''}`}
                      onClick={() => setExpanded(v => v === e.id ? null : e.id)}
                      initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                      <td className="audit-ts">
                        {e.created_at ? new Date(e.created_at).toLocaleString() : '—'}
                      </td>
                      <td>
                        <span className={`audit-action audit-action-${e.action?.split('.')[0]}`}>
                          {e.action}
                        </span>
                      </td>
                      <td className="audit-resource">{e.resource || <span className="audit-null">—</span>}</td>
                      <td className="audit-user">
                        <User size={11} />
                        {e.user_id ? e.user_id.slice(0, 8) + '…' : 'system'}
                      </td>
                      <td className="audit-ip">{e.ip_address || '—'}</td>
                      <td>{STATUS_ICON[e.status] ?? STATUS_ICON.success}</td>
                      <td>
                        <ChevronDown size={12} className={`audit-chevron ${expanded === e.id ? 'rotated' : ''}`} />
                      </td>
                    </motion.tr>
                    {expanded === e.id && (
                      <tr key={`${e.id}-detail`} className="audit-detail-row">
                        <td colSpan={7}>
                          <div className="audit-detail">
                            <div className="audit-detail-grid">
                              <div><span>Action</span><code>{e.action}</code></div>
                              <div><span>Status</span><code>{e.status}</code></div>
                              {e.user_id && <div><span>User ID</span><code>{e.user_id}</code></div>}
                              {e.ip_address && <div><span>IP Address</span><code>{e.ip_address}</code></div>}
                              {e.resource && <div><span>Resource</span><code>{e.resource}</code></div>}
                            </div>
                            {e.details && Object.keys(e.details).length > 0 && (
                              <div className="audit-detail-json">
                                <pre>{JSON.stringify(e.details, null, 2)}</pre>
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                ))}
                {entries.length === 0 && (
                  <tr><td colSpan={7} className="audit-empty">No audit events found</td></tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="audit-pagination">
            <button onClick={() => setOffset(o => Math.max(0, o - PAGE_SIZE))}
              disabled={offset === 0} className="audit-btn-ghost">
              ← Previous
            </button>
            <span className="audit-page-info">
              {offset + 1}–{offset + entries.length}
            </span>
            <button onClick={() => setOffset(o => o + PAGE_SIZE)}
              disabled={!hasMore} className="audit-btn-ghost">
              Next →
            </button>
          </div>
        </>
      )}
    </div>
  )
}
