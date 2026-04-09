// @ts-nocheck
/**
 * Node context menu — right-click menu in graph explorer.
 * Actions: expand neighborhood, find attack paths, view details,
 *          add to collection, copy ID, open in inventory.
 */
import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Network, GitBranch, ExternalLink, Copy,
  FolderPlus, Shield, ChevronRight, X
} from 'lucide-react'
import './NodeContextMenu.css'

interface Props {
  node:     { id: string; label: string; name: string; props?: any }
  position: { x: number; y: number }
  onClose:  () => void
  onExpand: (nodeId: string, hops: number) => void
  onAttackPath: (fromId: string) => void
}

export function NodeContextMenu({ node, position, onClose, onExpand, onAttackPath }: Props) {
  const navigate  = useNavigate()
  const menuRef   = useRef<HTMLDivElement>(null)

  // Close on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [onClose])

  // Adjust position to keep menu on screen
  const style: any = {
    position: 'fixed',
    left:     Math.min(position.x, window.innerWidth  - 240),
    top:      Math.min(position.y, window.innerHeight - 320),
    zIndex:   500,
  }

  const actions = [
    {
      icon: Network,
      label: 'Expand 1 hop',
      sub:   'Show immediate connections',
      action: () => { onExpand(node.id, 1); onClose() },
    },
    {
      icon: Network,
      label: 'Expand 2 hops',
      sub:   'Show extended neighborhood',
      action: () => { onExpand(node.id, 2); onClose() },
    },
    { divider: true },
    {
      icon: GitBranch,
      label: 'Find attack paths',
      sub:   'Show paths from this node',
      action: () => { onAttackPath(node.id); onClose() },
    },
    {
      icon: Shield,
      label: 'Exposure score',
      sub:   'See risk assessment',
      action: () => {
        navigate(`/query?q=${encodeURIComponent(`MATCH (n) WHERE id(n) = '${node.id}' RETURN n`)}&inspect=${node.id}`)
        onClose()
      },
    },
    { divider: true },
    {
      icon: ExternalLink,
      label: 'Open in full query',
      sub:   'View in query workspace',
      action: () => {
        navigate(`/query?q=${encodeURIComponent(`MATCH (n:${node.label}) WHERE id(n) = '${node.id}' RETURN n`)}`)
        onClose()
      },
    },
    {
      icon: Copy,
      label: 'Copy node ID',
      sub:   node.id?.slice(0, 20) + '…',
      action: () => { navigator.clipboard.writeText(node.id); onClose() },
    },
    { divider: true },
    {
      icon: FolderPlus,
      label: 'Add to collection',
      sub:   'Group this node',
      action: () => {
        // TODO: open collection picker modal
        onClose()
      },
    },
  ]

  return (
    <AnimatePresence>
      <motion.div
        ref={menuRef}
        className="ctx-menu"
        style={style}
        initial={{ opacity: 0, scale: .95, y: -4 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: .95 }}
        transition={{ duration: 0.1 }}
      >
        {/* Header */}
        <div className="ctx-header">
          <div className="ctx-node-label">{node.label}</div>
          <div className="ctx-node-name" title={node.name}>{node.name}</div>
          <button onClick={onClose} className="ctx-close"><X size={11} /></button>
        </div>

        {/* Actions */}
        <div className="ctx-actions">
          {actions.map((a, i) =>
            a.divider ? (
              <div key={i} className="ctx-divider" />
            ) : (
              <button key={i} className="ctx-action" onClick={a.action}>
                <a.icon size={13} className="ctx-action-icon" />
                <div className="ctx-action-body">
                  <span className="ctx-action-label">{a.label}</span>
                  {a.sub && <span className="ctx-action-sub">{a.sub}</span>}
                </div>
              </button>
            )
          )}
        </div>
      </motion.div>
    </AnimatePresence>
  )
}
