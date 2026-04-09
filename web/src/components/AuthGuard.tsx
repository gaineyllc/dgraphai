// @ts-nocheck
/**
 * AuthGuard — wraps all protected routes.
 * Redirects to /login if not authenticated.
 * Shows email verification banner if email is unverified.
 */
import { useEffect, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { isAuthenticated, getCurrentUser } from '../lib/auth'
import { FirstRunWizard } from './FirstRunWizard'

const PUBLIC_ROUTES = ['/login', '/signup', '/forgot-password', '/reset-password', '/verify-email', '/accept-invite']

interface Props {
  children: React.ReactNode
}

export function AuthGuard({ children }: Props) {
  const navigate  = useNavigate()
  const location  = useLocation()
  const [checked, setChecked] = useState(false)
  const [showWizard, setShowWizard] = useState(false)

  useEffect(() => {
    const isPublic = PUBLIC_ROUTES.some(r => location.pathname.startsWith(r))
    if (!isPublic && !isAuthenticated()) {
      navigate('/login', { state: { from: location.pathname }, replace: true })
      return
    }
    if (!isPublic && isAuthenticated()) {
      // Check if first-run wizard should show
      checkFirstRun()
    }
    setChecked(true)
  }, [location.pathname])

  const checkFirstRun = async () => {
    try {
      const r = await fetch('/api/connectors', {
        headers: { Authorization: `Bearer ${localStorage.getItem('dgraphai_token')}` },
      })
      const connectors = await r.json()
      // Show wizard if no connectors and not on wizard-incompatible pages
      const skipPages = ['/settings', '/login', '/signup', '/audit']
      if (Array.isArray(connectors) && connectors.length === 0 &&
          !skipPages.some(p => location.pathname.startsWith(p))) {
        setShowWizard(true)
      }
    } catch { /* ignore */ }
  }

  if (!checked) {
    return (
      <div style={{ display: 'flex', height: '100vh', alignItems: 'center', justifyContent: 'center', background: '#0a0a0f' }}>
        <div style={{ width: 32, height: 32, borderRadius: '50%', border: '3px solid #1a1a28', borderTopColor: '#4f8ef7', animation: 'spin .7s linear infinite' }} />
      </div>
    )
  }

  return (
    <>
      {showWizard && (
        <FirstRunWizard onDismiss={() => setShowWizard(false)} />
      )}
      {children}
    </>
  )
}
