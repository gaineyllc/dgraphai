// @ts-nocheck
/**
 * Email verification page — handles the link clicked from the verification email.
 * Token is passed as ?token=... query param.
 */
import { useEffect, useState } from 'react'
import { useSearchParams, Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { CheckCircle2, XCircle, Loader2 } from 'lucide-react'
import './Auth.css'

export function VerifyEmailPage() {
  const [searchParams] = useSearchParams()
  const navigate        = useNavigate()
  const token           = searchParams.get('token') || ''
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [message, setMessage] = useState('')

  useEffect(() => {
    if (!token) {
      setStatus('error')
      setMessage('No verification token found. Please check your email link.')
      return
    }
    verify(token)
  }, [token])

  const verify = async (t: string) => {
    try {
      const r = await fetch(`/api/auth/verify-email?token=${encodeURIComponent(t)}`, {
        method: 'POST',
      })
      const data = await r.json()
      if (r.ok) {
        setStatus('success')
        setMessage('Your email address has been verified.')
        // Redirect to app after 2.5s if already logged in
        if (localStorage.getItem('dgraphai_token')) {
          setTimeout(() => navigate('/'), 2500)
        }
      } else {
        setStatus('error')
        setMessage(data.detail || 'Verification failed. The link may have expired.')
      }
    } catch {
      setStatus('error')
      setMessage('Network error. Please try again.')
    }
  }

  return (
    <div className="auth-page">
      <motion.div className="auth-card"
        initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>
        <div className="auth-logo"><div className="auth-logo-icon">dg</div><span>dgraph.ai</span></div>

        {status === 'loading' && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, padding: '24px 0' }}>
            <Loader2 size={36} style={{ color: '#4f8ef7', animation: 'spin .7s linear infinite' }} />
            <p className="auth-sub" style={{ textAlign: 'center' }}>Verifying your email…</p>
          </div>
        )}

        {status === 'success' && (
          <>
            <div className="auth-success-icon"><CheckCircle2 size={48} /></div>
            <h2 className="auth-title" style={{ textAlign: 'center' }}>Email verified!</h2>
            <p className="auth-sub" style={{ textAlign: 'center' }}>{message}</p>
            {localStorage.getItem('dgraphai_token')
              ? <p className="auth-sub" style={{ textAlign: 'center', marginTop: 8 }}>Redirecting to app…</p>
              : <Link to="/login" className="auth-submit" style={{ textDecoration: 'none', textAlign: 'center', marginTop: 16 }}>
                  Sign in →
                </Link>
            }
          </>
        )}

        {status === 'error' && (
          <>
            <div style={{ display: 'flex', justifyContent: 'center', color: '#f87171', marginBottom: 12 }}>
              <XCircle size={48} />
            </div>
            <h2 className="auth-title" style={{ textAlign: 'center' }}>Verification failed</h2>
            <p className="auth-sub" style={{ textAlign: 'center' }}>{message}</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 16 }}>
              <Link to="/login" style={{ textDecoration: 'none' }}>
                <button className="auth-submit" style={{ width: '100%' }}>Sign in</button>
              </Link>
            </div>
          </>
        )}

        <p className="auth-footer"><Link to="/login">← Back to sign in</Link></p>
      </motion.div>
    </div>
  )
}
