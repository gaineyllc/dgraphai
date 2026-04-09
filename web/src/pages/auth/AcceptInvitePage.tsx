// @ts-nocheck
/**
 * Accept invitation page — shown when clicking the invite email link.
 * Shows tenant name, inviter, role, and lets the user set a password.
 */
import { useState, useEffect } from 'react'
import { useSearchParams, useNavigate, Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Eye, EyeOff, Loader2, AlertCircle, CheckCircle2, Users } from 'lucide-react'
import './Auth.css'

export function AcceptInvitePage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const token = searchParams.get('token') || ''

  const [name,     setName]     = useState('')
  const [password, setPassword] = useState('')
  const [confirm,  setConfirm]  = useState('')
  const [showPw,   setShowPw]   = useState(false)
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState('')
  const [done,     setDone]     = useState(false)

  // Validate token exists
  if (!token) return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-error"><AlertCircle size={14} /> Invalid or missing invitation token.</div>
        <p className="auth-footer"><Link to="/login">Back to sign in</Link></p>
      </div>
    </div>
  )

  const mismatch = confirm && password !== confirm

  const submit = async (e) => {
    e.preventDefault()
    if (mismatch) return
    setError(''); setLoading(true)
    try {
      const r = await fetch('/api/users/accept-invite', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ token, password, name }),
      })
      const data = await r.json()
      if (!r.ok) { setError(data.detail || 'Failed to accept invite'); setLoading(false); return }

      localStorage.setItem('dgraphai_token', data.token)
      setDone(true)
      setTimeout(() => navigate('/'), 2000)
    } catch {
      setError('Network error. Please try again.')
      setLoading(false)
    }
  }

  if (done) return (
    <div className="auth-page">
      <motion.div className="auth-card" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
        <div className="auth-success-icon"><CheckCircle2 size={48} /></div>
        <h2 className="auth-title" style={{ textAlign: 'center' }}>Welcome aboard!</h2>
        <p className="auth-sub" style={{ textAlign: 'center' }}>Your account is ready. Redirecting…</p>
      </motion.div>
    </div>
  )

  return (
    <div className="auth-page">
      <motion.div className="auth-card"
        initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>
        <div className="auth-logo"><div className="auth-logo-icon">dg</div><span>dgraph.ai</span></div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
          <div style={{ width: 38, height: 38, borderRadius: 10, background: 'rgba(79,142,247,.12)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Users size={18} style={{ color: '#4f8ef7' }} />
          </div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: '#e2e2f0' }}>You've been invited</div>
            <div style={{ fontSize: 12, color: '#55557a' }}>Set up your account to get started</div>
          </div>
        </div>

        {error && <div className="auth-error"><AlertCircle size={14} /> {error}</div>}

        <form onSubmit={submit} className="auth-form">
          <div className="auth-field">
            <label>Your name</label>
            <input type="text" value={name} onChange={e => setName(e.target.value)}
              placeholder="Alice Smith" autoFocus required />
          </div>

          <div className="auth-field">
            <label>Password</label>
            <div className="auth-password-wrap">
              <input type={showPw ? 'text' : 'password'} value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="Min. 8 chars, uppercase + number"
                autoComplete="new-password" required />
              <button type="button" onClick={() => setShowPw(v => !v)} className="auth-pw-toggle">
                {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>

          <div className="auth-field">
            <label>Confirm password</label>
            <input type="password" value={confirm}
              onChange={e => setConfirm(e.target.value)}
              placeholder="Repeat password" autoComplete="new-password" required
              style={{ borderColor: mismatch ? '#f87171' : undefined }}
            />
            {mismatch && <span style={{ fontSize: 11, color: '#f87171' }}>Passwords don't match</span>}
          </div>

          <button type="submit"
            disabled={loading || !!mismatch || !name || password.length < 8}
            className="auth-submit">
            {loading ? <Loader2 size={15} className="auth-spin" /> : null}
            {loading ? 'Setting up account…' : 'Accept invitation'}
          </button>
        </form>

        <p className="auth-footer">Already have an account? <Link to="/login">Sign in</Link></p>
      </motion.div>
    </div>
  )
}
