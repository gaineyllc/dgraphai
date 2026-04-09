/**
 * NodeTooltip — floating quick-look card that appears on node click.
 *
 * Shows the most important attributes for the node type up front.
 * Has a "Details →" button that opens the full InspectionPane.
 * Scrollable, dismissible, keyboard-accessible.
 *
 * Positioning: anchored to the click position in the graph canvas,
 * constrained to stay within the viewport.
 */
import { useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  FileText, Folder, User, MapPin, Building2,
  Tag, Cpu, ShieldAlert, Key, X, ChevronRight,
  Clock, HardDrive, Eye
} from 'lucide-react'
import type { GraphNode } from '../lib/api'

// ── Node type → primary attributes ───────────────────────────────────────────

const NODE_PRIMARY_ATTRS: Record<string, string[]> = {
  File:          ['file_category', 'size_bytes', 'resolution', 'hdr_type', 'modified',
                  'eol_status', 'contains_secrets', 'pii_detected', 'sensitivity_level'],
  Directory:     ['file_count', 'total_bytes', 'host', 'share'],
  Person:        ['name', 'known', 'face_cluster_id'],
  FaceCluster:   ['label', 'face_count'],
  Location:      ['city', 'country', 'latitude', 'longitude'],
  Organization:  ['name', 'type'],
  Topic:         ['name'],
  Application:   ['version_string', 'company_name', 'eol_status', 'cve_count',
                  'signed', 'architecture'],
  Vendor:        ['website'],
  Vulnerability: ['cve_id', 'cvss_score', 'cvss_severity', 'exploit_available',
                  'actively_exploited'],
  Certificate:   ['cert_subject', 'cert_issuer', 'days_until_expiry', 'cert_is_expired'],
}

const NODE_ICONS: Record<string, React.ElementType> = {
  File:          FileText,
  Directory:     Folder,
  Person:        User,
  FaceCluster:   User,
  Location:      MapPin,
  Organization:  Building2,
  Topic:         Tag,
  Application:   Cpu,
  Vulnerability: ShieldAlert,
  Certificate:   Key,
}

// ── Severity / status badge helpers ──────────────────────────────────────────

function StatusBadge({ value, field }: { value: unknown; field: string }) {
  if (value === null || value === undefined || value === '') return null

  // Boolean flags
  if (field === 'contains_secrets' && value === true)
    return <span className="badge badge-red">⚠ Secrets</span>
  if (field === 'pii_detected' && value === true)
    return <span className="badge badge-yellow">🔒 PII</span>
  if (field === 'actively_exploited' && value === true)
    return <span className="badge badge-red">🔴 Actively Exploited</span>
  if (field === 'exploit_available' && value === true)
    return <span className="badge badge-yellow">⚡ Exploit Available</span>
  if (field === 'cert_is_expired' && value === true)
    return <span className="badge badge-red">Expired</span>
  if (field === 'signed' && value === false)
    return <span className="badge badge-yellow">Unsigned</span>

  // EOL status
  if (field === 'eol_status') {
    if (value === 'eol') return <span className="badge badge-red">EOL</span>
    if (value === 'supported') return <span className="badge badge-green">Supported</span>
    return <span className="badge badge-gray">{String(value)}</span>
  }

  // CVSS severity
  if (field === 'cvss_severity') {
    const colors: Record<string, string> = {
      critical: 'badge-red', high: 'badge-orange',
      medium: 'badge-yellow', low: 'badge-green',
    }
    return <span className={`badge ${colors[String(value)] ?? 'badge-gray'}`}>{String(value).toUpperCase()}</span>
  }

  // Sensitivity level
  if (field === 'sensitivity_level') {
    const colors: Record<string, string> = {
      high: 'badge-red', medium: 'badge-yellow', low: 'badge-green'
    }
    return <span className={`badge ${colors[String(value)] ?? 'badge-gray'}`}>{String(value)}</span>
  }

  return null
}

function formatValue(field: string, value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (field === 'size_bytes' || field === 'total_bytes') {
    const n = Number(value)
    if (n > 1e9) return `${(n/1e9).toFixed(2)} GB`
    if (n > 1e6) return `${(n/1e6).toFixed(1)} MB`
    if (n > 1e3) return `${(n/1e3).toFixed(0)} KB`
    return `${n} B`
  }
  if (field === 'modified') {
    const d = new Date(Number(value) * 1000)
    return d.toLocaleDateString()
  }
  if (field === 'days_until_expiry') return `${value} days`
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  const s = String(value)
  return s.length > 40 ? s.slice(0, 40) + '…' : s
}

// ── Component ─────────────────────────────────────────────────────────────────

interface Props {
  node:     GraphNode
  position: { x: number; y: number }
  onClose:  () => void
  onDetails: () => void
}

export function NodeTooltip({ node, position, onClose, onDetails }: Props) {
  const ref      = useRef<HTMLDivElement>(null)
  const Icon     = NODE_ICONS[node.label] ?? FileText
  const props    = node.props ?? {}
  const attrKeys = NODE_PRIMARY_ATTRS[node.label] ?? Object.keys(props).slice(0, 8)
  const attrs    = attrKeys.filter(k => props[k] != null && props[k] !== '')

  // Constrain to viewport
  const viewW    = window.innerWidth
  const viewH    = window.innerHeight
  const W        = 280
  const left     = Math.min(position.x + 12, viewW - W - 16)
  const top      = Math.min(position.y, viewH - 400)

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose()
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [onClose])

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, scale: 0.92, y: -4 }}
      animate={{ opacity: 1, scale: 1,    y: 0  }}
      exit={{    opacity: 0, scale: 0.92, y: -4 }}
      transition={{ duration: 0.12 }}
      style={{ left, top, width: W, position: 'fixed', zIndex: 9999 }}
      className="node-tooltip"
    >
      {/* Header */}
      <div className="nt-header">
        <div className="nt-icon">
          <Icon size={14} />
        </div>
        <div className="nt-title-block">
          <div className="nt-title">{node.name}</div>
          <div className="nt-label">{node.label}</div>
        </div>
        <button onClick={onClose} className="nt-close" aria-label="Close">
          <X size={12} />
        </button>
      </div>

      {/* Attributes — scrollable */}
      <div className="nt-body">
        {attrs.length === 0 ? (
          <div className="nt-empty">No attributes to display</div>
        ) : attrs.map(key => {
          const val   = props[key]
          const badge = <StatusBadge field={key} value={val} />
          const label = key.replace(/_/g, ' ')

          return (
            <div key={key} className="nt-row">
              <span className="nt-key">{label}</span>
              {badge
                ? <span className="nt-val">{badge}</span>
                : <span className="nt-val">{formatValue(key, val)}</span>
              }
            </div>
          )
        })}
      </div>

      {/* Footer */}
      <div className="nt-footer">
        <div className="nt-id">{node.id.slice(0, 8)}…</div>
        <button onClick={onDetails} className="nt-details-btn">
          Details
          <ChevronRight size={12} />
        </button>
      </div>
    </motion.div>
  )
}
