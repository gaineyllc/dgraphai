// @ts-nocheck
import { useState } from 'react'
import { useSearchParams, useNavigate, Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Eye, EyeOff, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react'
import './Auth.css'

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const navigate       = useNavigate()
  const token          = searchParams.get('token') || ''

  const [password,  setPassword]  = useState('')
  const [confirm,   setConfirm]   = useState('')
  const [showPw,    setShowPw]    = useState(false)
  const [loading,   setLoading]   = useState(false)
  const [error,     setError]     = useState('')
  const [done,      setDone]      = useState(false)

  const mismatch = confirm && password !== confirm

  const submit = async (e) => {
    e.preventDefault()
    if (mismatch) return
    setError(''); setLoading(true)
    try {
      const r = await fetch('/api/auth/reset-password', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ token, new_password: password }),
      })
      const data = await r.json()
      if (!r.ok) { setError(data.detail || 'Reset failed'); setLoading(false); return }
      setDone(true)
      setTimeout(() => navigate('/login'), 2500)
    } catch {
      setError('Network error. Please try again.')
      setLoading(false)
    }
  }

  if (!token) return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-error"><AlertCircle size={14} /> Invalid or missing reset token.</div>
        <p className="auth-footer"><Link to="/forgot-password">Request a new reset link</Link></p>
      </div>
    </div>
  )

  return (
    <div className="auth-page">
      <motion.div className="auth-card"
        initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>
        <div className="auth-logo"><div className="auth-logo-icon">dg</div><span>dgraph.ai</span></div>

        {done ? (
          <>
            <div className="auth-success-icon" style={{ marginTop: 16 }}><CheckCircle2 size={40} /></div>
            <h2 className="auth-title" style={{ textAlign: 'center' }}>Password reset!</h2>
            <p className="auth-sub" style={{ textAlign: 'center' }}>Redirecting to sign in…</p>
          </>
        ) : (
          <>
            <h1 className="auth-title">Set new password</h1>
            <p className="auth-sub">Choose a strong password for your account.</p>
            {error && <div className="auth-error"><AlertCircle size={14} /> {error}</div>}
            <form onSubmit={submit} className="auth-form">
              <div className="auth-field">
                <label>New password</label>
                <div className="auth-password-wrap">
                  <input type={showPw ? 'text' : 'password'} value={password}
                    onChange={e => setPassword(e.target.value)}
                    placeholder="Min. 8 chars, uppercase + number"
                    autoComplete="new-password" autoFocus required />
                  <button type="button" onClick={() => setShowPw(v => !v)} className="auth-pw-toggle">
                    {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </div>
              <div className="auth-field">
                <label>Confirm password</label>
                <input type="password" value={confirm}
                  onChange={e => setConfirm(e.target.value)}
                  placeholder="Repeat password"
                  autoComplete="new-password" required
                  style={{ borderColor: mismatch ? '#f87171' : undefined }}
                />
                {mismatch && <span style={{ fontSize: 11, color: '#f87171' }}>Passwords don't match</span>}
              </div>
              <button type="submit" disabled={loading || !!mismatch || password.length < 8} className="auth-submit">
                {loading ? <Loader2 size={15} className="auth-spin" /> : null}
                {loading ? 'Resetting…' : 'Set new password'}
              </button>
            </form>
          </>
        )}
        <p className="auth-footer"><Link to="/login">← Back to sign in</Link></p>
      </motion.div>
    </div>
  )
}
