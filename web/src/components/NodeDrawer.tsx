// @ts-nocheck
/**
 * NodeDrawer — resizable right-side drawer for full node inspection.
 *
 * Features:
 *  - Slides in from the right with M3 emphasized-decel easing
 *  - Resizable by dragging the left edge (280–720px)
 *  - Shows ALL node attributes, organized by category
 *  - SHA-256 with copy button
 *  - paths[] array if multiple agents serve this file
 *  - "Explore in graph" button
 *  - "Find similar" button (same category/extension)
 *  - Keyboard: Escape to close
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  X, Copy, Check, ExternalLink, Network, Search,
  File, Shield, Cpu, User, AlertTriangle,
  Clock, Hash, HardDrive, Tag, Link, Layers,
} from 'lucide-react'
import './NodeDrawer.css'

const MIN_WIDTH = 320
const MAX_WIDTH = 720
const DEFAULT_WIDTH = 420

function fmt(val: any): string {
  if (val == null) return '—'
  if (typeof val === 'boolean') return val ? 'Yes' : 'No'
  if (typeof val === 'number') {
    if (val > 1024 * 1024) return (val / 1024 / 1024).toFixed(2) + ' MB'
    if (val > 1024) return (val / 1024).toFixed(1) + ' KB'
    return String(val)
  }
  if (Array.isArray(val)) return val.join(', ')
  return String(val)
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button className="nd-copy-btn" onClick={copy} title="Copy">
      {copied ? <Check size={11} /> : <Copy size={11} />}
    </button>
  )
}

const PROP_GROUPS = [
  {
    label: 'Identity',
    icon: File,
    keys: ['name', 'path', 'extension', 'mime_type', 'file_category', 'labels'],
  },
  {
    label: 'Content',
    icon: Hash,
    keys: ['sha256', 'xxhash', 'size'],
  },
  {
    label: 'Timestamps',
    icon: Clock,
    keys: ['modified_at', 'created_at', 'indexed_at'],
  },
  {
    label: 'Source',
    icon: Network,
    keys: ['connector_id', 'protocol', 'host', 'share', 'paths'],
  },
  {
    label: 'Enrichment',
    icon: Layers,
    keys: ['contains_secrets', 'contains_pii', 'secret_types', 'pii_types',
           'language', 'encoding', 'summary', 'entities', 'sentiment'],
  },
  {
    label: 'Security',
    icon: Shield,
    keys: ['signed', 'company_name', 'entropy', 'file_type', 'architecture',
           'imports', 'exports', 'risk_assessment'],
  },
]

interface Props {
  node:       any
  onClose:    () => void
  onExplore?: (id: string) => void
  onFindSimilar?: (node: any) => void
}

export function NodeDrawer({ node, onClose, onExplore, onFindSimilar }: Props) {
  const [width, setWidth] = useState(DEFAULT_WIDTH)
  const dragging = useRef(false)
  const startX   = useRef(0)
  const startW   = useRef(0)

  // Keyboard close
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])

  // Resize drag from left edge
  const onResizeMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    dragging.current = true
    startX.current   = e.clientX
    startW.current   = width

    const onMove = (me: MouseEvent) => {
      if (!dragging.current) return
      const dx  = startX.current - me.clientX  // dragging left = wider
      const newW = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, startW.current + dx))
      setWidth(newW)
    }
    const onUp = () => {
      dragging.current = false
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [width])

  const props = node.props ?? node
  const label = node.label ?? 'Node'
  const name  = props.name ?? props.path?.split('/').pop() ?? node.id ?? 'Unknown'
  const allProps = { ...props }

  // Build grouped sections — only show keys that have values
  const sections = PROP_GROUPS.map(g => ({
    ...g,
    items: g.keys
      .map(k => ({ key: k, value: allProps[k] }))
      .filter(({ value }) => value != null && value !== '' && !(Array.isArray(value) && value.length === 0)),
  })).filter(s => s.items.length > 0)

  // Collect ungrouped keys
  const groupedKeys = new Set(PROP_GROUPS.flatMap(g => g.keys))
  const extra = Object.entries(allProps)
    .filter(([k]) => !groupedKeys.has(k) && !['id', 'tenant_id', 'labels'].includes(k))

  const isMono = (key: string) => ['sha256', 'xxhash', 'id', 'connector_id', 'tenant_id'].includes(key)
  const isCopyable = (key: string) => ['sha256', 'xxhash', 'path'].includes(key)

  return (
    <motion.div
      className="nd-overlay"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.15 }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <motion.div
        className="nd-drawer"
        style={{ width }}
        initial={{ x: '100%' }}
        animate={{ x: 0 }}
        exit={{ x: '100%' }}
        transition={{ duration: 0.3, ease: [0.05, 0.7, 0.1, 1.0] }}
      >
        {/* Resize handle */}
        <div className="nd-resize-handle" onMouseDown={onResizeMouseDown} title="Drag to resize" />

        {/* Header */}
        <div className="nd-header">
          <div className="nd-header-left">
            <span className="nd-type-badge">{label}</span>
            <h2 className="nd-title" title={name}>{name}</h2>
          </div>
          <div className="nd-header-actions">
            {onFindSimilar && (
              <button className="nd-hdr-btn" onClick={() => onFindSimilar(node)} title="Find similar files">
                <Search size={15} />
              </button>
            )}
            {onExplore && (
              <button className="nd-hdr-btn" onClick={() => onExplore(node.id)} title="Explore in graph">
                <Network size={15} />
              </button>
            )}
            <button className="nd-hdr-btn nd-hdr-close" onClick={onClose} title="Close (Esc)">
              <X size={15} />
            </button>
          </div>
        </div>

        {/* Properties */}
        <div className="nd-body">
          {/* paths array — shown prominently if multiple agents have this file */}
          {Array.isArray(allProps.paths) && allProps.paths.length > 0 && (
            <div className="nd-section nd-paths-section">
              <div className="nd-section-label">
                <Link size={12} />
                {allProps.paths.length} path{allProps.paths.length !== 1 ? 's' : ''} to this file
              </div>
              <div className="nd-paths-list">
                {allProps.paths.map((p: string, i: number) => (
                  <div key={i} className="nd-path-row">
                    <span className="nd-path-text">{p}</span>
                    <CopyButton text={p} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {sections.map(section => (
            <div key={section.label} className="nd-section">
              <div className="nd-section-label">
                <section.icon size={12} /> {section.label}
              </div>
              <div className="nd-props-grid">
                {section.items.map(({ key, value }) => (
                  <div key={key} className="nd-prop-row">
                    <span className="nd-prop-key">{key.replace(/_/g, ' ')}</span>
                    <div className="nd-prop-val-wrap">
                      <span className={`nd-prop-val ${isMono(key) ? 'nd-mono' : ''}`}>
                        {key === 'sha256' || key === 'xxhash'
                          ? (String(value).slice(0, 24) + '…')
                          : fmt(value)
                        }
                      </span>
                      {isCopyable(key) && <CopyButton text={String(value)} />}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}

          {/* Extra ungrouped properties */}
          {extra.length > 0 && (
            <div className="nd-section">
              <div className="nd-section-label"><Tag size={12} /> Additional attributes</div>
              <div className="nd-props-grid">
                {extra.map(([key, value]) => (
                  <div key={key} className="nd-prop-row">
                    <span className="nd-prop-key">{key.replace(/_/g, ' ')}</span>
                    <span className={`nd-prop-val ${isMono(key) ? 'nd-mono' : ''}`}>{fmt(value)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer actions */}
        <div className="nd-footer">
          {onFindSimilar && (
            <button className="btn btn-secondary btn-sm" onClick={() => onFindSimilar(node)}>
              <Search size={13} /> Find similar
            </button>
          )}
          {onExplore && (
            <button className="btn btn-primary btn-sm" onClick={() => onExplore(node.id)}>
              <Network size={13} /> Explore in graph
            </button>
          )}
        </div>
      </motion.div>
    </motion.div>
  )
}
