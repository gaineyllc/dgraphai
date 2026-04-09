import { apiFetch } from '../lib/apiFetch'
/**
 * InspectionPane — full node detail panel on the right side.
 *
 * Features:
 *   - Slides in from the right when a node is selected via "Details"
 *   - Draggable left edge to resize (expands into the graph canvas)
 *   - Tabbed: Overview | Raw Properties | Relationships | Actions
 *   - Security signals prominently displayed (PII, secrets, EOL, CVEs)
 *   - File preview for text/code files
 *   - Link to run a query scoped to this node
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  X, ChevronLeft, ChevronRight, AlertTriangle, ShieldAlert,
  FileText, Network, Zap, Copy, ExternalLink, Eye,
  Lock, Clock, HardDrive, Hash, Tag
} from 'lucide-react'
import type { GraphNode } from '../lib/api'

const MIN_WIDTH = 320
const MAX_WIDTH = 800
const DEFAULT_WIDTH = 420

type Tab = 'overview' | 'properties' | 'relationships' | 'actions'

interface Props {
  node:       GraphNode | null
  onClose:    () => void
  onExpand?:  (id: string) => void  // expand neighbors in graph
  className?: string
}

export function InspectionPane({ node, onClose, onExpand, className = '' }: Props) {
  const [width,   setWidth]   = useState(DEFAULT_WIDTH)
  const [tab,     setTab]     = useState<Tab>('overview')
  const [copying, setCopying] = useState(false)
  const dragRef               = useRef<{ startX: number; startWidth: number } | null>(null)

  // Reset to overview when node changes
  useEffect(() => { if (node) setTab('overview') }, [node?.id])

  // Drag to resize
  const onDragStart = useCallback((e: React.MouseEvent) => {
    dragRef.current = { startX: e.clientX, startWidth: width }
    e.preventDefault()

    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return
      const delta = dragRef.current.startX - ev.clientX
      setWidth(Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, dragRef.current.startWidth + delta)))
    }
    const onUp = () => {
      dragRef.current = null
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }, [width])

  const copyNodeId = async () => {
    if (!node) return
    await navigator.clipboard.writeText(node.id)
    setCopying(true)
    setTimeout(() => setCopying(false), 1200)
  }

  if (!node) return null

  const props = node.props ?? {}

  // Security signals
  const signals: Array<{ label: string; severity: string; icon: React.ElementType }> = []
  if (props.contains_secrets)    signals.push({ label: 'Exposed Secrets',   severity: 'critical', icon: Lock })
  if (props.pii_detected)        signals.push({ label: 'PII Detected',       severity: 'high',     icon: ShieldAlert })
  if (props.eol_status === 'eol') signals.push({ label: 'End of Life',       severity: 'high',     icon: AlertTriangle })
  if (props.cert_is_expired)     signals.push({ label: 'Certificate Expired', severity: 'critical', icon: Lock })
  if (props.actively_exploited)  signals.push({ label: 'Actively Exploited', severity: 'critical', icon: Zap })
  if (props.sensitivity_level === 'high') signals.push({ label: 'High Sensitivity', severity: 'high', icon: Eye })

  return (
    <AnimatePresence>
      <motion.div
        key={node.id}
        initial={{ x: '100%', opacity: 0 }}
        animate={{ x: 0,     opacity: 1 }}
        exit={{    x: '100%', opacity: 0 }}
        transition={{ type: 'spring', damping: 28, stiffness: 300 }}
        style={{ width }}
        className={`inspection-pane ${className}`}
      >
        {/* Drag handle */}
        <div
          className="ip-drag-handle"
          onMouseDown={onDragStart}
          title="Drag to resize"
        >
          <div className="ip-drag-indicator" />
        </div>

        {/* Header */}
        <div className="ip-header">
          <div className="ip-node-type">{node.label}</div>
          <div className="ip-node-name" title={node.name}>{node.name}</div>
          <div className="ip-header-actions">
            <button onClick={copyNodeId} className="ip-icon-btn" title="Copy node ID">
              {copying ? '✓' : <Copy size={14} />}
            </button>
            {onExpand && (
              <button onClick={() => onExpand(node.id)} className="ip-icon-btn" title="Expand in graph">
                <Network size={14} />
              </button>
            )}
            <button onClick={onClose} className="ip-icon-btn" title="Close">
              <X size={14} />
            </button>
          </div>
        </div>

        {/* Security signals banner */}
        {signals.length > 0 && (
          <div className="ip-signals">
            {signals.map(s => (
              <div key={s.label} className={`ip-signal ip-signal-${s.severity}`}>
                <s.icon size={12} />
                <span>{s.label}</span>
              </div>
            ))}
          </div>
        )}

        {/* Tabs */}
        <div className="ip-tabs">
          {(['overview', 'properties', 'relationships', 'actions'] as Tab[]).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`ip-tab ${tab === t ? 'ip-tab-active' : ''}`}
            >
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="ip-content">
          {tab === 'overview'  && <OverviewTab  node={node} props={props} />}
          {tab === 'properties'&& <PropertiesTab props={props} />}
          {tab === 'relationships' && <RelationshipsTab nodeId={node.id} />}
          {tab === 'actions'   && <ActionsTab node={node} />}
        </div>
      </motion.div>
    </AnimatePresence>
  )
}

// ── Tabs ──────────────────────────────────────────────────────────────────────

function OverviewTab({ node, props }: { node: GraphNode; props: Record<string, unknown> }) {
  const groups: Array<{ title: string; fields: string[] }> = []

  if (node.label === 'File') {
    groups.push(
      { title: 'Identity',  fields: ['name', 'extension', 'file_category', 'mime_type'] },
      { title: 'Size & Time', fields: ['size_bytes', 'modified', 'created', 'sha256'] },
      { title: 'Location', fields: ['path', 'host', 'share', 'protocol'] },
      { title: 'Media',    fields: ['width', 'height', 'duration_secs', 'resolution', 'hdr_type', 'video_codec', 'audio_codec'] },
      { title: 'Document', fields: ['author', 'page_count', 'word_count', 'language', 'summary'] },
      { title: 'Security', fields: ['contains_secrets', 'secret_types', 'pii_detected', 'pii_types', 'sensitivity_level', 'signed', 'signature_valid'] },
    )
  } else if (node.label === 'Application') {
    groups.push(
      { title: 'Identity',   fields: ['product_name', 'company_name', 'file_version', 'architecture'] },
      { title: 'Lifecycle',  fields: ['eol_status', 'latest_version', 'version_behind', 'eol_date'] },
      { title: 'Security',   fields: ['cve_count', 'critical_cve_count', 'signed', 'is_packed', 'entropy'] },
    )
  } else if (node.label === 'Certificate') {
    groups.push(
      { title: 'Identity',  fields: ['cert_subject', 'cert_issuer', 'serial'] },
      { title: 'Validity',  fields: ['cert_valid_from', 'cert_valid_to', 'days_until_expiry', 'cert_is_expired'] },
      { title: 'Technical', fields: ['cert_key_algorithm', 'key_size', 'cert_fingerprint', 'is_ca', 'is_self_signed'] },
    )
  } else if (node.label === 'Vulnerability') {
    groups.push(
      { title: 'Identity',  fields: ['cve_id', 'cvss_score', 'cvss_severity'] },
      { title: 'Status',    fields: ['exploit_available', 'actively_exploited', 'published_date', 'patched_in_version'] },
      { title: 'Details',   fields: ['description'] },
    )
  } else {
    groups.push({ title: 'Attributes', fields: Object.keys(props).slice(0, 20) })
  }

  return (
    <div className="ip-overview">
      {groups.map(group => {
        const visible = group.fields.filter(f => props[f] != null && props[f] !== '')
        if (visible.length === 0) return null
        return (
          <div key={group.title} className="ip-group">
            <div className="ip-group-title">{group.title}</div>
            {visible.map(field => (
              <div key={field} className="ip-field">
                <div className="ip-field-label">{field.replace(/_/g, ' ')}</div>
                <div className="ip-field-value">
                  <FieldValue field={field} value={props[field]} />
                </div>
              </div>
            ))}
          </div>
        )
      })}
    </div>
  )
}

function PropertiesTab({ props }: { props: Record<string, unknown> }) {
  return (
    <div className="ip-properties">
      {Object.entries(props)
        .filter(([, v]) => v != null)
        .map(([k, v]) => (
          <div key={k} className="ip-prop-row">
            <div className="ip-prop-key">{k}</div>
            <div className="ip-prop-val">{JSON.stringify(v)}</div>
          </div>
        ))
      }
    </div>
  )
}

function RelationshipsTab({ nodeId }: { nodeId: string }) {
  const [data, setData] = useState<{ nodes: unknown[]; edges: unknown[] } | null>(null)

  useEffect(() => {
    apiFetch(`/api/graph/node/${encodeURIComponent(nodeId)}/neighbors?depth=1&limit=50`)
      .then(r => r.json())
      .then(setData)
      .catch(() => {})
  }, [nodeId])

  if (!data) return <div className="ip-loading">Loading relationships…</div>

  const edges = (data.edges as Array<{ type: string; source: string; target: string }>) ?? []
  const nodes = (data.nodes as GraphNode[]) ?? []

  return (
    <div className="ip-relationships">
      <div className="ip-rel-summary">{edges.length} relationships · {nodes.length - 1} neighbors</div>
      {edges.map((e, i) => {
        const neighbor = nodes.find(n => n.id === (e.source === nodeId ? e.target : e.source))
        const dir      = e.source === nodeId ? '→' : '←'
        return (
          <div key={i} className="ip-rel-row">
            <span className="ip-rel-type">{e.type}</span>
            <span className="ip-rel-dir">{dir}</span>
            <span className="ip-rel-name">{(neighbor as GraphNode)?.name ?? '…'}</span>
            <span className="ip-rel-label">{(neighbor as GraphNode)?.label}</span>
          </div>
        )
      })}
    </div>
  )
}

function ActionsTab({ node }: { node: GraphNode }) {
  const isFile = node.label === 'File'
  const path   = node.props?.path as string | undefined

  return (
    <div className="ip-actions">
      <div className="ip-actions-group">
        <div className="ip-actions-title">Graph</div>
        <button className="ip-action-btn">
          <Network size={14} /> Expand neighbors (depth 2)
        </button>
        <button className="ip-action-btn">
          <Hash size={14} /> Find similar files
        </button>
        <button className="ip-action-btn">
          <Tag size={14} /> Add tag
        </button>
      </div>
      {isFile && path && (
        <div className="ip-actions-group">
          <div className="ip-actions-title">File Actions</div>
          <button className="ip-action-btn ip-action-btn-warn">
            <FileText size={14} /> Propose move
          </button>
          <button className="ip-action-btn ip-action-btn-danger">
            <X size={14} /> Propose deletion
          </button>
        </div>
      )}
      <div className="ip-actions-group">
        <div className="ip-actions-title">Query</div>
        <button className="ip-action-btn">
          <ExternalLink size={14} /> Open in Query Editor
        </button>
      </div>
    </div>
  )
}

function FieldValue({ field, value }: { field: string; value: unknown }) {
  if (value === null || value === undefined) return <span className="fv-null">—</span>

  // Boolean signals
  if (typeof value === 'boolean') {
    if (field === 'contains_secrets' && value) return <span className="badge badge-red">Yes</span>
    if (field === 'pii_detected'     && value) return <span className="badge badge-yellow">Yes</span>
    if (field === 'cert_is_expired'  && value) return <span className="badge badge-red">Expired</span>
    if (field === 'actively_exploited'&& value) return <span className="badge badge-red">Yes</span>
    if (field === 'signed' && !value)           return <span className="badge badge-yellow">Unsigned</span>
    return <span className="fv-bool">{value ? 'Yes' : 'No'}</span>
  }

  if (field === 'size_bytes' || field === 'total_bytes') {
    const n = Number(value)
    if (n > 1e9) return <span>{(n/1e9).toFixed(2)} GB</span>
    if (n > 1e6) return <span>{(n/1e6).toFixed(1)} MB</span>
    return <span>{(n/1e3).toFixed(0)} KB</span>
  }

  if (field === 'eol_status') {
    const colors: Record<string, string> = { eol: 'badge-red', supported: 'badge-green' }
    return <span className={`badge ${colors[String(value)] ?? 'badge-gray'}`}>{String(value)}</span>
  }

  if (field === 'cvss_severity') {
    const colors: Record<string, string> = {
      critical: 'badge-red', high: 'badge-orange', medium: 'badge-yellow', low: 'badge-green'
    }
    return <span className={`badge ${colors[String(value)] ?? 'badge-gray'}`}>{String(value).toUpperCase()}</span>
  }

  if (field === 'sensitivity_level') {
    const colors: Record<string, string> = { high: 'badge-red', medium: 'badge-yellow', low: 'badge-green' }
    return <span className={`badge ${colors[String(value)] ?? 'badge-gray'}`}>{String(value)}</span>
  }

  if (field === 'summary') {
    return <span className="fv-summary">{String(value)}</span>
  }

  const s = String(value)
  return <span title={s.length > 60 ? s : undefined}>{s.length > 60 ? s.slice(0, 60) + '…' : s}</span>
}

