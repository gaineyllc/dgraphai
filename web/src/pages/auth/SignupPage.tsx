// @ts-nocheck
import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Eye, EyeOff, Loader2, AlertCircle, CheckCircle2 } from 'lucide-react'
import './Auth.css'

export function SignupPage() {
  const navigate = useNavigate()
  const [form,    setForm]    = useState({ name: '', email: '', company: '', password: '' })
  const [showPw,  setShowPw]  = useState(false)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState('')
  const [done,    setDone]    = useState(false)

  const pwStrength = (pw: string) => {
    let score = 0
    if (pw.length >= 8)              score++
    if (pw.length >= 12)             score++
    if (/[A-Z]/.test(pw))            score++
    if (/[0-9]/.test(pw))            score++
    if (/[^A-Za-z0-9]/.test(pw))     score++
    return score
  }
  const strength = pwStrength(form.password)
  const strengthLabel = ['', 'Weak', 'Fair', 'Good', 'Strong', 'Very strong'][strength] || ''
  const strengthColor = ['', '#f87171','#f59e0b','#fbbf24','#34d399','#10b981'][strength] || '#35354a'

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const r = await fetch('/api/auth/signup', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(form),
      })
      const data = await r.json()
      if (!r.ok) { setError(data.detail || 'Signup failed'); setLoading(false); return }
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
        <h2 className="auth-title">Account created!</h2>
        <p className="auth-sub">Check your email to verify your address. Redirecting…</p>
      </motion.div>
    </div>
  )

  return (
    <div className="auth-page">
      <motion.div className="auth-card"
        initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>

        <div className="auth-logo">
          <div className="auth-logo-icon">dg</div>
          <span>dgraph.ai</span>
        </div>
        <h1 className="auth-title">Create your account</h1>
        <p className="auth-sub">Start indexing your data in minutes</p>

        {error && <div className="auth-error"><AlertCircle size={14} /> {error}</div>}

        <form onSubmit={submit} className="auth-form">
          <div className="auth-field-row">
            <div className="auth-field">
              <label>Full name</label>
              <input type="text" value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                placeholder="Alice Smith" autoFocus required />
            </div>
            <div className="auth-field">
              <label>Company</label>
              <input type="text" value={form.company}
                onChange={e => setForm(f => ({ ...f, company: e.target.value }))}
                placeholder="Acme Corp" />
            </div>
          </div>

          <div className="auth-field">
            <label>Work email</label>
            <input type="email" value={form.email}
              onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
              placeholder="alice@acme.com" autoComplete="email" required />
          </div>

          <div className="auth-field">
            <label>Password</label>
            <div className="auth-password-wrap">
              <input
                type={showPw ? 'text' : 'password'}
                value={form.password}
                onChange={e => setForm(f => ({ ...f, password: e.target.value }))}
                placeholder="Min. 8 chars, uppercase + number"
                autoComplete="new-password" required
              />
              <button type="button" onClick={() => setShowPw(v => !v)} className="auth-pw-toggle">
                {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
            {form.password && (
              <div className="auth-pw-strength">
                <div className="auth-pw-bar">
                  {[1,2,3,4,5].map(i => (
                    <div key={i} className="auth-pw-segment"
                      style={{ background: i <= strength ? strengthColor : '#1a1a28' }} />
                  ))}
                </div>
                <span style={{ color: strengthColor }}>{strengthLabel}</span>
              </div>
            )}
          </div>

          <p className="auth-terms">
            By signing up you agree to our{' '}
            <a href="/terms" target="_blank">Terms of Service</a> and{' '}
            <a href="/privacy" target="_blank">Privacy Policy</a>.
          </p>

          <button type="submit" disabled={loading || strength < 2} className="auth-submit">
            {loading ? <Loader2 size={15} className="auth-spin" /> : null}
            {loading ? 'Creating account…' : 'Create account'}
          </button>
        </form>

        <p className="auth-footer">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </motion.div>
    </div>
  )
}
