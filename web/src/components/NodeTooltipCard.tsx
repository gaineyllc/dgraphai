// @ts-nocheck
/**
 * NodeTooltipCard — floating tooltip anchored to a graph node.
 *
 * Behavior:
 *  - Appears at the node's screen position on click
 *  - Disappears when user clicks anywhere outside it
 *  - Shows key properties: name, type, category, size, path
 *  - "Details →" button opens the full NodeDrawer
 *  - "Expand" button loads 1-hop neighbors into the graph
 *  - Draggable (user can move it away from overlapping nodes)
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  X, ExternalLink, Network, ChevronRight,
  File, Shield, Cpu, User, AlertTriangle,
} from 'lucide-react'
import './NodeTooltipCard.css'

const TYPE_ICONS: Record<string, any> = {
  File:          File,
  Directory:     Network,
  Person:        User,
  Vulnerability: AlertTriangle,
  Application:   Cpu,
  Certificate:   Shield,
}

const CATEGORY_COLORS: Record<string, string> = {
  code:       'var(--color-primary)',
  image:      'var(--color-secondary)',
  text:       'var(--color-tertiary)',
  audio:      '#a78bfa',
  video:      '#fb923c',
  executable: 'var(--color-critical)',
  archive:    '#f59e0b',
  document:   '#22d3ee',
  unknown:    'var(--text-tertiary)',
}

function fmtSize(bytes: number): string {
  if (!bytes) return '—'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

interface Props {
  node:      any
  position:  { x: number; y: number }  // screen coords from Cytoscape
  onClose:   () => void
  onDetails: () => void
  onExpand?: () => void
}

export function NodeTooltipCard({ node, position, onClose, onDetails, onExpand }: Props) {
  const cardRef  = useRef<HTMLDivElement>(null)
  const dragRef  = useRef<{ startX: number; startY: number; cardX: number; cardY: number } | null>(null)
  const [cardPos, setCardPos] = useState({ x: position.x + 16, y: position.y - 60 })
  const [dragging, setDragging] = useState(false)

  // Adjust so card stays in viewport
  useEffect(() => {
    if (!cardRef.current) return
    const { innerWidth, innerHeight } = window
    const rect = cardRef.current.getBoundingClientRect()
    let { x, y } = cardPos

    // Nudge left if overflows right
    if (x + rect.width > innerWidth - 16) x = innerWidth - rect.width - 16
    // Nudge up if overflows bottom
    if (y + rect.height > innerHeight - 16) y = position.y - rect.height - 8
    // Clamp to top/left
    x = Math.max(16, x)
    y = Math.max(16, y)

    if (x !== cardPos.x || y !== cardPos.y) setCardPos({ x, y })
  }, [node]) // eslint-disable-line react-hooks/exhaustive-deps

  // Close on outside click
  useEffect(() => {
    const handle = (e: MouseEvent) => {
      if (cardRef.current && !cardRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    // Small delay to avoid closing immediately on the same click that opened us
    const t = setTimeout(() => document.addEventListener('mousedown', handle), 100)
    return () => { clearTimeout(t); document.removeEventListener('mousedown', handle) }
  }, [onClose])

  // Drag to reposition
  const onMouseDown = useCallback((e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('button')) return // don't drag on button clicks
    e.preventDefault()
    dragRef.current = { startX: e.clientX, startY: e.clientY, cardX: cardPos.x, cardY: cardPos.y }
    setDragging(true)

    const onMove = (me: MouseEvent) => {
      if (!dragRef.current) return
      const dx = me.clientX - dragRef.current.startX
      const dy = me.clientY - dragRef.current.startY
      setCardPos({ x: dragRef.current.cardX + dx, y: dragRef.current.cardY + dy })
    }
    const onUp = () => {
      dragRef.current = null
      setDragging(false)
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }
    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }, [cardPos])

  const props = node.props ?? node
  const label = node.label ?? 'Node'
  const name  = props.name ?? props.path?.split('/').pop() ?? node.id ?? 'Unknown'
  const Icon  = TYPE_ICONS[label] ?? File
  const catColor = CATEGORY_COLORS[props.file_category ?? ''] ?? 'var(--text-tertiary)'

  return (
    <motion.div
      ref={cardRef}
      className={`ntc-card ${dragging ? 'ntc-dragging' : ''}`}
      style={{ left: cardPos.x, top: cardPos.y, '--cat': catColor } as any}
      initial={{ opacity: 0, scale: 0.92, y: 6 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.92, y: 4 }}
      transition={{ duration: 0.15, ease: [0.05, 0.7, 0.1, 1.0] }}
      onMouseDown={onMouseDown}
    >
      {/* Header */}
      <div className="ntc-header">
        <div className="ntc-icon" style={{ background: `color-mix(in srgb, var(--cat) 15%, transparent)` }}>
          <Icon size={14} style={{ color: 'var(--cat)' }} />
        </div>
        <div className="ntc-title-group">
          <div className="ntc-label">{label}</div>
          <div className="ntc-name" title={name}>{name}</div>
        </div>
        <button className="ntc-close" onClick={onClose} onMouseDown={e => e.stopPropagation()}>
          <X size={12} />
        </button>
      </div>

      {/* Key properties */}
      <div className="ntc-props">
        {props.file_category && (
          <div className="ntc-prop">
            <span className="ntc-prop-key">Category</span>
            <span className="ntc-prop-val" style={{ color: 'var(--cat)' }}>{props.file_category}</span>
          </div>
        )}
        {props.mime_type && props.mime_type !== 'application/octet-stream' && (
          <div className="ntc-prop">
            <span className="ntc-prop-key">Type</span>
            <span className="ntc-prop-val">{props.mime_type}</span>
          </div>
        )}
        {props.size != null && (
          <div className="ntc-prop">
            <span className="ntc-prop-key">Size</span>
            <span className="ntc-prop-val">{fmtSize(props.size)}</span>
          </div>
        )}
        {props.extension && (
          <div className="ntc-prop">
            <span className="ntc-prop-key">Extension</span>
            <span className="ntc-prop-val ntc-mono">{props.extension}</span>
          </div>
        )}
        {props.path && (
          <div className="ntc-prop ntc-prop-path">
            <span className="ntc-prop-key">Path</span>
            <span className="ntc-prop-val ntc-mono ntc-truncate" title={props.path}>{props.path}</span>
          </div>
        )}
        {props.sha256 && (
          <div className="ntc-prop">
            <span className="ntc-prop-key">SHA-256</span>
            <span className="ntc-prop-val ntc-mono" style={{ fontSize: 10 }}>{props.sha256.slice(0, 16)}…</span>
          </div>
        )}
        {/* paths array — shown if multiple agents have this file */}
        {Array.isArray(props.paths) && props.paths.length > 1 && (
          <div className="ntc-prop">
            <span className="ntc-prop-key">Paths</span>
            <span className="ntc-prop-val">{props.paths.length} locations</span>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="ntc-actions">
        {onExpand && (
          <button className="ntc-action-btn" onClick={onExpand} onMouseDown={e => e.stopPropagation()}>
            <Network size={12} /> Expand
          </button>
        )}
        <button className="ntc-action-btn ntc-action-primary" onClick={onDetails} onMouseDown={e => e.stopPropagation()}>
          Details <ChevronRight size={12} />
        </button>
      </div>
    </motion.div>
  )
}
