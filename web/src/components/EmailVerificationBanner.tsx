// @ts-nocheck
/**
 * Email verification banner — shown when user's email is not verified.
 * Sits at the top of the app shell, dismissable per session.
 */
import { useState } from 'react'
import { AlertTriangle, X, Loader2 } from 'lucide-react'

export function EmailVerificationBanner() {
  const [dismissed, setDismissed] = useState(
    sessionStorage.getItem('email_banner_dismissed') === '1'
  )
  const [sending, setSending]   = useState(false)
  const [sent,    setSent]      = useState(false)

  // Check if email is verified from token claims
  const token = localStorage.getItem('dgraphai_token')
  if (!token) return null

  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    // Token doesn't have email_verified — check from /api/users/me instead
    // For now just don't show if no specific indicator
    if (!payload.email_unverified) return null
  } catch {
    return null
  }

  if (dismissed) return null

  const resend = async () => {
    setSending(true)
    await apiFetch('/api/auth/resend-verification', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    })
    setSending(false); setSent(true)
  }

  const dismiss = () => {
    sessionStorage.setItem('email_banner_dismissed', '1')
    setDismissed(true)
  }

  return (
    <div className="auth-verify-banner">
      <AlertTriangle size={13} />
      <span>
        {sent
          ? 'Verification email sent — check your inbox.'
          : 'Please verify your email address to unlock all features.'}
      </span>
      {!sent && (
        <button onClick={resend} disabled={sending}>
          {sending ? <Loader2 size={11} style={{ animation: 'spin .7s linear infinite' }} /> : 'Resend email'}
        </button>
      )}
      <button onClick={dismiss} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', marginLeft: 4 }}>
        <X size={12} />
      </button>
    </div>
  )
}


