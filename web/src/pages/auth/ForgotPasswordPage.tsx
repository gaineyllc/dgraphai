// @ts-nocheck
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Loader2, AlertCircle, CheckCircle2 } from 'lucide-react'
import './Auth.css'

export function ForgotPasswordPage() {
  const [email,   setEmail]   = useState('')
  const [loading, setLoading] = useState(false)
  const [done,    setDone]    = useState(false)
  const [error,   setError]   = useState('')

  const submit = async (e) => {
    e.preventDefault()
    setLoading(true)
    try {
      await fetch('/api/auth/forgot-password', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ email }),
      })
      setDone(true)
    } catch {
      setError('Network error. Please try again.')
    }
    setLoading(false)
  }

  return (
    <div className="auth-page">
      <motion.div className="auth-card"
        initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>
        <div className="auth-logo"><div className="auth-logo-icon">dg</div><span>dgraph.ai</span></div>
        <h1 className="auth-title">Reset your password</h1>

        {done ? (
          <>
            <div className="auth-success-icon" style={{ marginTop: 16 }}><CheckCircle2 size={40} /></div>
            <p className="auth-sub" style={{ marginTop: 12, textAlign: 'center' }}>
              If an account exists for <strong>{email}</strong>, a reset link has been sent.
              Check your inbox.
            </p>
          </>
        ) : (
          <>
            <p className="auth-sub">Enter your email and we'll send a reset link.</p>
            {error && <div className="auth-error"><AlertCircle size={14} /> {error}</div>}
            <form onSubmit={submit} className="auth-form">
              <div className="auth-field">
                <label>Email</label>
                <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                  placeholder="you@company.com" autoFocus required />
              </div>
              <button type="submit" disabled={loading} className="auth-submit">
                {loading ? <Loader2 size={15} className="auth-spin" /> : null}
                {loading ? 'Sending…' : 'Send reset link'}
              </button>
            </form>
          </>
        )}

        <p className="auth-footer"><Link to="/login">← Back to sign in</Link></p>
      </motion.div>
    </div>
  )
}
