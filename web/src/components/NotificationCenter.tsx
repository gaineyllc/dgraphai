// @ts-nocheck
/**
 * In-app notification center — bell icon in the sidebar.
 * Pulls recent alerts + system events and shows them as a dropdown.
 * Marks notifications as read on open.
 */
import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Bell, X, CheckCheck, AlertTriangle, Shield, RefreshCw, Info } from 'lucide-react'
import { apiFetch } from '../lib/apiFetch'
import './NotificationCenter.css'

const api = {
  list:     ()    => apiFetch('/api/alerts/notifications').then(r => r.json()),
  markRead: (ids) => apiFetch('/api/alerts/notifications/read', {
    method: 'POST', body: JSON.stringify({ ids }),
  }).then(r => r.json()),
  markAll:  ()    => apiFetch('/api/alerts/notifications/read-all', { method: 'POST' }).then(r => r.json()),
}

const SEVERITY_ICON = {
  critical: <AlertTriangle size={13} style={{ color: '#f87171' }} />,
  high:     <AlertTriangle size={13} style={{ color: '#fb923c' }} />,
  medium:   <Shield       size={13} style={{ color: '#fbbf24' }} />,
  low:      <Info         size={13} style={{ color: '#4f8ef7' }} />,
  info:     <Info         size={13} style={{ color: '#8888aa' }} />,
}

export function NotificationCenter() {
  const qc       = useQueryClient()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const { data, isLoading } = useQuery({
    queryKey: ['notifications'],
    queryFn:  api.list,
    refetchInterval: 30_000,
    // Fall back gracefully if endpoint doesn't exist yet
    retry: false,
    onError: () => {},
  })

  const notifications = data?.notifications ?? []
  const unread = notifications.filter(n => !n.read_at).length

  const markRead = useMutation({
    mutationFn: api.markRead,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
  })

  const markAll = useMutation({
    mutationFn: api.markAll,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
  })

  // Close on outside click
  useEffect(() => {
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // Mark visible notifications as read on open
  useEffect(() => {
    if (open && unread > 0) {
      const unreadIds = notifications.filter(n => !n.read_at).map(n => n.id)
      if (unreadIds.length) markRead.mutate(unreadIds)
    }
  }, [open])

  return (
    <div ref={ref} className="notif-wrap">
      {/* Bell button */}
      <button
        className={`notif-bell ${open ? 'active' : ''}`}
        onClick={() => setOpen(v => !v)}
        title="Notifications"
      >
        <Bell size={16} />
        {unread > 0 && (
          <span className="notif-badge">{unread > 9 ? '9+' : unread}</span>
        )}
      </button>

      {/* Dropdown */}
      <AnimatePresence>
        {open && (
          <motion.div
            className="notif-panel"
            initial={{ opacity: 0, y: -8, scale: .97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.12 }}
          >
            {/* Header */}
            <div className="notif-header">
              <span>Notifications</span>
              <div style={{ display: 'flex', gap: 4 }}>
                {notifications.some(n => !n.read_at) && (
                  <button onClick={() => markAll.mutate()} className="notif-action-btn" title="Mark all read">
                    <CheckCheck size={13} />
                  </button>
                )}
                <button onClick={() => setOpen(false)} className="notif-action-btn">
                  <X size={13} />
                </button>
              </div>
            </div>

            {/* List */}
            <div className="notif-list">
              {isLoading ? (
                <div className="notif-empty"><RefreshCw size={16} className="notif-spin" /></div>
              ) : notifications.length === 0 ? (
                <div className="notif-empty">
                  <Bell size={20} style={{ color: '#252535' }} />
                  <span>No notifications</span>
                </div>
              ) : (
                notifications.slice(0, 20).map(n => (
                  <div
                    key={n.id}
                    className={`notif-item ${!n.read_at ? 'unread' : ''}`}
                    onClick={() => {
                      if (n.link) { navigate(n.link); setOpen(false) }
                    }}
                  >
                    <div className="notif-icon">
                      {SEVERITY_ICON[n.severity ?? 'info']}
                    </div>
                    <div className="notif-body">
                      <div className="notif-title">{n.title}</div>
                      {n.message && <div className="notif-message">{n.message}</div>}
                      <div className="notif-time">{relTime(n.created_at)}</div>
                    </div>
                    {!n.read_at && <div className="notif-dot" />}
                  </div>
                ))
              )}
            </div>

            {notifications.length > 0 && (
              <div className="notif-footer">
                <button onClick={() => { navigate('/audit'); setOpen(false) }} className="notif-view-all">
                  View audit log →
                </button>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function relTime(iso: string) {
  if (!iso) return ''
  const ms = Date.now() - new Date(iso).getTime()
  const m  = Math.floor(ms / 60_000)
  const h  = Math.floor(ms / 3_600_000)
  const d  = Math.floor(ms / 86_400_000)
  if (m < 1)  return 'just now'
  if (m < 60) return `${m}m ago`
  if (h < 24) return `${h}h ago`
  return `${d}d ago`
}
