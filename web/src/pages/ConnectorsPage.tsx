// @ts-nocheck
/**
 * ConnectorsPage — full connector management surface.
 *
 * Shows:
 *   - All configured connectors as rich cards
 *   - Per-connector: type icon, health status, performance metrics, warnings/errors
 *   - Add connector modal with type picker → dynamic config form → scanner agent selector
 *   - Connection test before save
 *   - Edit / delete / scan now per connector
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Plus, RefreshCw, CheckCircle, XCircle, AlertTriangle,
  HardDrive, Cloud, Server, Zap, Settings, Trash2,
  ChevronRight, Wifi, WifiOff, BarChart3, Clock,
  FileText, Activity, X, TestTube2, Database
} from 'lucide-react'
import './ConnectorsPage.css'

// ── API calls ─────────────────────────────────────────────────────────────────

const api = {
  getTypes: ()      => apiFetch('/api/connectors/types').then(r => r.json()),
  list:     ()      => apiFetch('/api/connectors').then(r => r.json()),
  create:   (body)  => apiFetch('/api/connectors', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) }).then(r => r.json()),
  update:   (id, b) => apiFetch(`/api/connectors/${id}`, { method: 'PATCH', headers: {'Content-Type':'application/json'}, body: JSON.stringify(b) }).then(r => r.json()),
  delete:   (id)    => apiFetch(`/api/connectors/${id}`, { method: 'DELETE' }).then(r => r.json()),
  test:     (id)    => apiFetch(`/api/connectors/${id}/test`, { method: 'POST' }).then(r => r.json()),
  agents:   (id)    => apiFetch(`/api/connectors/${id}/agents`).then(r => r.json()),
  getAgents:()      => apiFetch('/api/scanner/register').catch(() => ({ json: () => [] })),
}

// ── Type metadata ─────────────────────────────────────────────────────────────

const TYPE_ICONS: Record<string, string> = {
  'aws-s3':     '🪣', 'azure-blob': '☁️', 'gcs': '🔵',
  'sharepoint': '📁', 'smb': '🗄️', 'nfs': '📡', 'local': '💻',
}
const TYPE_COLORS: Record<string, string> = {
  'aws-s3': '#f97316', 'azure-blob': '#0ea5e9', 'gcs': '#3b82f6',
  'sharepoint': '#10b981', 'smb': '#8b5cf6', 'nfs': '#6366f1', 'local': '#6b7280',
}
const HEALTH_CONFIG = {
  healthy: { color: '#10b981', icon: CheckCircle,  label: 'Healthy'  },
  warning: { color: '#f59e0b', icon: AlertTriangle, label: 'Warning'  },
  error:   { color: '#f87171', icon: XCircle,       label: 'Error'    },
  unknown: { color: '#55557a', icon: Clock,          label: 'Not scanned' },
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function ConnectorsPage() {
  const qc = useQueryClient()
  const [showAdd, setShowAdd]   = useState(false)
  const [editing, setEditing]   = useState(null)

  const { data: connectors = [], isLoading } = useQuery({
    queryKey: ['connectors'],
    queryFn:  api.list,
    refetchInterval: 30_000,
  })

  const { data: types = [] } = useQuery({
    queryKey: ['connector-types'],
    queryFn:  api.getTypes,
  })

  const deleteConn = useMutation({
    mutationFn: api.delete,
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['connectors'] }),
  })

  const testConn = useMutation({
    mutationFn: api.test,
    onSuccess:  () => qc.invalidateQueries({ queryKey: ['connectors'] }),
  })

  const healthCounts = {
    healthy: connectors.filter(c => c.health?.status === 'healthy').length,
    warning: connectors.filter(c => c.health?.status === 'warning').length,
    error:   connectors.filter(c => c.health?.status === 'error').length,
  }

  return (
    <div className="connectors-page">
      {/* Header */}
      <div className="cp-header">
        <div>
          <h1>Connectors</h1>
          <p>Data sources connected to your dgraph.ai knowledge graph</p>
        </div>
        <button className="cp-add-btn" onClick={() => setShowAdd(true)}>
          <Plus size={14} /> Add connector
        </button>
      </div>

      {/* Health summary bar */}
      {connectors.length > 0 && (
        <div className="cp-health-bar">
          <div className="cp-hb-item cp-hb-healthy">
            <CheckCircle size={13} /> {healthCounts.healthy} healthy
          </div>
          {healthCounts.warning > 0 && (
            <div className="cp-hb-item cp-hb-warning">
              <AlertTriangle size={13} /> {healthCounts.warning} warning
            </div>
          )}
          {healthCounts.error > 0 && (
            <div className="cp-hb-item cp-hb-error">
              <XCircle size={13} /> {healthCounts.error} error
            </div>
          )}
          <div className="cp-hb-total">{connectors.length} total</div>
        </div>
      )}

      {/* Connector grid */}
      {isLoading ? (
        <div className="cp-loading">Loading connectors…</div>
      ) : connectors.length === 0 ? (
        <EmptyState onAdd={() => setShowAdd(true)} />
      ) : (
        <div className="cp-grid">
          {connectors.map(c => (
            <ConnectorCard
              key={c.id}
              connector={c}
              onTest={() => testConn.mutate(c.id)}
              onEdit={() => setEditing(c)}
              onDelete={() => { if (confirm(`Delete "${c.name}"?`)) deleteConn.mutate(c.id) }}
              testing={testConn.isPending && testConn.variables === c.id}
            />
          ))}
        </div>
      )}

      {/* Add / Edit modal */}
      <AnimatePresence>
        {(showAdd || editing) && (
          <ConnectorModal
            types={types}
            initial={editing}
            onClose={() => { setShowAdd(false); setEditing(null) }}
            onSave={() => {
              qc.invalidateQueries({ queryKey: ['connectors'] })
              setShowAdd(false)
              setEditing(null)
            }}
          />
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Connector card ─────────────────────────────────────────────────────────────

function ConnectorCard({ connector: c, onTest, onEdit, onDelete, testing }) {
  const [expanded, setExpanded] = useState(false)
  const color  = TYPE_COLORS[c.connector_type] ?? '#6b7280'
  const icon   = TYPE_ICONS[c.connector_type] ?? '🔌'
  const health = HEALTH_CONFIG[c.health?.status ?? 'unknown']
  const HealthIcon = health.icon

  return (
    <motion.div
      layout
      className={`cp-card cp-card-${c.health?.status ?? 'unknown'}`}
      style={{ '--type-color': color } as any}
    >
      {/* Card header */}
      <div className="cp-card-header">
        <div className="cp-card-icon" style={{ background: `${color}15` }}>
          <span style={{ fontSize: 20 }}>{icon}</span>
        </div>
        <div className="cp-card-title-block">
          <div className="cp-card-name">{c.name}</div>
          <div className="cp-card-type">{c.connector_type}</div>
        </div>
        <div className="cp-card-health" style={{ color: health.color }}>
          <HealthIcon size={14} />
          <span>{health.label}</span>
        </div>
      </div>

      {/* Warning / error banners */}
      {c.health?.errors?.length > 0 && (
        <div className="cp-banner cp-banner-error">
          <XCircle size={12} />
          <span>{c.health.errors[0]}</span>
        </div>
      )}
      {c.health?.warnings?.length > 0 && !c.health?.errors?.length && (
        <div className="cp-banner cp-banner-warning">
          <AlertTriangle size={12} />
          <span>{c.health.warnings[0]}</span>
        </div>
      )}

      {/* Metrics row */}
      <div className="cp-metrics">
        <MetricPill icon={FileText} label="Files" value={fmt(c.health?.total_files ?? 0)} />
        <MetricPill icon={Clock}    label="Last scan"
                    value={c.health?.last_scan_at ? relTime(c.health.last_scan_at) : 'Never'} />
        {c.health?.last_scan_duration_secs && (
          <MetricPill icon={Activity} label="Duration"
                      value={`${c.health.last_scan_duration_secs.toFixed(1)}s`} />
        )}
        {c.health?.throughput_fps && (
          <MetricPill icon={BarChart3} label="Throughput"
                      value={`${c.health.throughput_fps.toFixed(0)} f/s`} />
        )}
      </div>

      {/* Scanner agent routing */}
      {c.scanner_agent && (
        <div className="cp-agent-row">
          <div className={`cp-agent-dot ${c.scanner_agent.is_online ? 'cp-agent-online' : 'cp-agent-offline'}`} />
          <span className="cp-agent-label">via</span>
          <span className="cp-agent-name">{c.scanner_agent.name}</span>
          <span className="cp-agent-platform">{c.scanner_agent.platform}</span>
          {!c.scanner_agent.is_online && (
            <span className="cp-agent-offline-warn">offline</span>
          )}
        </div>
      )}
      {!c.scanner_agent && (
        <div className="cp-agent-row cp-agent-direct">
          <Server size={11} />
          <span>Direct connection from backend</span>
        </div>
      )}

      {/* Tags */}
      {c.tags?.length > 0 && (
        <div className="cp-tags">
          {c.tags.map(t => <span key={t} className="cp-tag">{t}</span>)}
        </div>
      )}

      {/* Actions */}
      <div className="cp-card-actions">
        <button
          onClick={onTest}
          disabled={testing}
          className="cp-action-btn"
          title="Test connection"
        >
          {testing ? <RefreshCw size={12} className="cp-spin" /> : <TestTube2 size={12} />}
          Test
        </button>
        <button onClick={onEdit}   className="cp-action-btn" title="Edit"><Settings size={12} /> Edit</button>
        <button onClick={onDelete} className="cp-action-btn cp-action-danger" title="Delete"><Trash2 size={12} /></button>

        {/* Test result */}
        {c.health?.last_test_result === true && (
          <span className="cp-test-ok"><CheckCircle size={11} /> OK</span>
        )}
        {c.health?.last_test_result === false && (
          <span className="cp-test-fail" title={c.health?.last_test_msg}>
            <XCircle size={11} /> Failed
          </span>
        )}
      </div>
    </motion.div>
  )
}

function MetricPill({ icon: Icon, label, value }) {
  return (
    <div className="cp-metric">
      <Icon size={10} />
      <span className="cp-metric-label">{label}</span>
      <span className="cp-metric-value">{value}</span>
    </div>
  )
}

// ── Add/Edit modal ────────────────────────────────────────────────────────────

function ConnectorModal({ types, initial, onClose, onSave }) {
  const [step, setStep]             = useState(initial ? 2 : 1)  // 1=pick type, 2=configure
  const [selectedType, setType]     = useState(initial?.connector_type ?? null)
  const [form, setForm]             = useState(initial ?? {})
  const [config, setConfig]         = useState(initial?.config ?? {})
  const [agentId, setAgentId]       = useState(initial?.scanner_agent?.id ?? '')
  const [routingMode, setRouting]   = useState(initial?.routing_mode ?? 'auto')
  const [testing, setTesting]       = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [saving, setSaving]         = useState(false)
  const [error, setError]           = useState('')

  const { data: scannerAgents = [] } = useQuery({
    queryKey: ['scanner-agents-list'],
    queryFn:  () => apiFetch('/api/connectors/00000000-0000-0000-0000-000000000000/agents').then(r => r.ok ? r.json() : []),
  })

  const typeInfo = types.find(t => t.id === selectedType)
  const schema   = typeInfo?.config_schema?.properties ?? {}
  const required = typeInfo?.config_schema?.required ?? []
  const routingModes = typeInfo?.routing_modes ?? ['direct', 'agent', 'auto']
  const needsAgent = routingMode === 'agent' || (routingMode === 'auto' && routingModes.length === 1 && routingModes[0] === 'agent')

  const doTest = async () => {
    setTesting(true); setTestResult(null)
    try {
      const cls = { connector_type: selectedType, config }
      const r = await apiFetch('/api/connectors/test', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cls),
      })
      const d = await r.json()
      setTestResult(d)
    } catch (e) {
      setTestResult({ success: false, message: String(e) })
    } finally {
      setTesting(false)
    }
  }

  const doSave = async () => {
    setSaving(true); setError('')
    try {
      const body = {
        name:             form.name || typeInfo?.name || selectedType,
        description:      form.description ?? '',
        connector_type:   selectedType,
        config,
        tags:             form.tags ?? [],
        scanner_agent_id: agentId || null,
        routing_mode:     routingMode,
      }
      if (initial) {
        await api.update(initial.id, body)
      } else {
        await api.create(body)
      }
      onSave()
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <motion.div
      className="cp-modal-overlay"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <motion.div
        className="cp-modal"
        initial={{ scale: .95, y: 10 }} animate={{ scale: 1, y: 0 }} exit={{ scale: .95, y: 10 }}
      >
        <div className="cp-modal-header">
          <h2>{initial ? 'Edit connector' : 'Add connector'}</h2>
          <button onClick={onClose} className="cp-modal-close"><X size={16} /></button>
        </div>

        {/* Step 1: Type picker */}
        {step === 1 && (
          <div className="cp-type-grid">
            {types.map(t => (
              <button
                key={t.id}
                className={`cp-type-card ${selectedType === t.id ? 'cp-type-selected' : ''}`}
                onClick={() => { setType(t.id); setStep(2) }}
                style={{ '--tc': TYPE_COLORS[t.id] ?? '#6b7280' } as any}
              >
                <span className="cp-tc-icon">{TYPE_ICONS[t.id] ?? '🔌'}</span>
                <div className="cp-tc-name">{t.name}</div>
                <div className="cp-tc-desc">{t.description}</div>
              </button>
            ))}
          </div>
        )}

        {/* Step 2: Configuration */}
        {step === 2 && typeInfo && (
          <div className="cp-modal-body">
            {/* Type badge */}
            <div className="cp-modal-type-badge">
              <span>{TYPE_ICONS[selectedType]}</span>
              <span>{typeInfo.name}</span>
              {!initial && <button className="cp-change-type" onClick={() => setStep(1)}>Change</button>}
            </div>

            {/* Name + description */}
            <div className="cp-field">
              <label>Name *</label>
              <input
                value={form.name ?? ''}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                placeholder={`My ${typeInfo.name}`}
              />
            </div>
            <div className="cp-field">
              <label>Description</label>
              <input
                value={form.description ?? ''}
                onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                placeholder="Optional description"
              />
            </div>

            {/* Dynamic config fields from schema */}
            <div className="cp-field-group-label">Connection settings</div>
            {Object.entries(schema).map(([key, field]: any) => (
              <div key={key} className="cp-field">
                <label>
                  {field.title ?? key}
                  {required.includes(key) && <span className="cp-required">*</span>}
                </label>
                {field.type === 'boolean' ? (
                  <div className="cp-toggle-row">
                    <input
                      type="checkbox"
                      checked={config[key] ?? field.default ?? false}
                      onChange={e => setConfig(c => ({ ...c, [key]: e.target.checked }))}
                    />
                    {field.description && <span className="cp-field-hint">{field.description}</span>}
                  </div>
                ) : (
                  <input
                    type={field.format === 'password' ? 'password' : 'text'}
                    value={config[key] ?? field.default ?? ''}
                    onChange={e => setConfig(c => ({ ...c, [key]: e.target.value }))}
                    placeholder={field.placeholder ?? field.description ?? ''}
                  />
                )}
              </div>
            ))}

            {/* Routing mode + scanner agent */}
            <div className="cp-field-group-label">Routing</div>
            {routingModes.length > 1 ? (
              <div className="cp-field">
                <label>Routing mode</label>
                <select value={routingMode} onChange={e => setRouting(e.target.value)}>
                  {routingModes.includes('direct') && <option value="direct">Direct (backend → source)</option>}
                  {routingModes.includes('agent')  && <option value="agent">Via scanner agent</option>}
                  {routingModes.includes('auto')   && <option value="auto">Auto (prefer direct)</option>}
                </select>
                <span className="cp-field-hint">
                  {routingMode === 'direct' && 'Backend connects directly. Best for cloud sources (S3, Azure, GCS).'}
                  {routingMode === 'agent'  && 'Traffic routes through an on-prem scanner agent. Required for internal networks.'}
                  {routingMode === 'auto'   && 'Uses direct when reachable, falls back to agent.'}
                </span>
              </div>
            ) : (
              <div className="cp-field-hint cp-routing-required">
                <Server size={12} /> This connector type requires an on-prem scanner agent.
              </div>
            )}

            {(routingMode === 'agent' || routingModes.length === 1) && (
              <div className="cp-field">
                <label>Scanner agent {needsAgent && <span className="cp-required">*</span>}</label>
                <select value={agentId} onChange={e => setAgentId(e.target.value)}>
                  <option value="">— Select agent —</option>
                  {scannerAgents.map(a => (
                    <option key={a.id} value={a.id} disabled={!a.is_online}>
                      {a.name} ({a.platform}){!a.is_online ? ' — offline' : ''}
                    </option>
                  ))}
                </select>
                {scannerAgents.length === 0 && (
                  <span className="cp-field-hint cp-warn">
                    No scanner agents registered. Deploy a scanner agent first.
                  </span>
                )}
              </div>
            )}

            {/* Test connection */}
            <div className="cp-test-row">
              <button onClick={doTest} disabled={testing} className="cp-test-btn">
                {testing ? <RefreshCw size={13} className="cp-spin" /> : <TestTube2 size={13} />}
                Test connection
              </button>
              {testResult && (
                <span className={`cp-test-result ${testResult.success ? 'cp-test-ok' : 'cp-test-fail'}`}>
                  {testResult.success ? <CheckCircle size={12} /> : <XCircle size={12} />}
                  {testResult.message}
                </span>
              )}
            </div>

            {error && <div className="cp-error">{error}</div>}
          </div>
        )}

        <div className="cp-modal-footer">
          <button onClick={onClose} className="cp-btn-cancel">Cancel</button>
          {step === 2 && (
            <button
              onClick={doSave}
              disabled={saving || !form.name || !selectedType}
              className="cp-btn-save"
            >
              {saving ? <RefreshCw size={13} className="cp-spin" /> : <Database size={13} />}
              {initial ? 'Save changes' : 'Add connector'}
            </button>
          )}
        </div>
      </motion.div>
    </motion.div>
  )
}

function EmptyState({ onAdd }) {
  return (
    <div className="cp-empty">
      <div className="cp-empty-icon">
        <Cloud size={32} />
      </div>
      <h3>No connectors yet</h3>
      <p>Connect your first data source to start building the knowledge graph.</p>
      <div className="cp-empty-types">
        {['aws-s3','azure-blob','sharepoint','smb','gcs','local'].map(t => (
          <span key={t} className="cp-empty-type">
            {TYPE_ICONS[t]} {t}
          </span>
        ))}
      </div>
      <button onClick={onAdd} className="cp-add-btn">
        <Plus size={14} /> Add your first connector
      </button>
    </div>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmt(n: number) {
  if (n >= 1e6) return `${(n/1e6).toFixed(1)}M`
  if (n >= 1e3) return `${(n/1e3).toFixed(0)}K`
  return String(n)
}

function relTime(iso: string) {
  const d = new Date(iso)
  const now = Date.now()
  const diff = now - d.getTime()
  const h = Math.floor(diff / 3600000)
  if (h < 1)  return `${Math.floor(diff/60000)}m ago`
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h/24)}d ago`
}



