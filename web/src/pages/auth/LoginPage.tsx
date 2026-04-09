// @ts-nocheck
/**
 * Login page — email/password + MFA.
 * Clean, minimal dark design consistent with the rest of the platform.
 */
import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Eye, EyeOff, Loader2, AlertCircle, ShieldCheck } from 'lucide-react'
import './Auth.css'

export function LoginPage() {
  const navigate = useNavigate()
  const [email,      setEmail]    = useState('')
  const [password,   setPassword] = useState('')
  const [mfaCode,    setMFACode]  = useState('')
  const [showPw,     setShowPw]   = useState(false)
  const [needsMFA,   setNeedsMFA] = useState(false)
  const [loading,    setLoading]  = useState(false)
  const [error,      setError]    = useState('')

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const body: any = { email, password }
      if (needsMFA) body.mfa_code = mfaCode

      const r = await fetch('/api/auth/login', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(body),
      })
      const data = await r.json()

      if (r.status === 401 && r.headers.get('X-MFA-Required')) {
        setNeedsMFA(true)
        setLoading(false)
        return
      }

      if (!r.ok) {
        setError(data.detail || 'Login failed')
        setLoading(false)
        return
      }

      // Store token + redirect
      localStorage.setItem('dgraphai_token', data.token)
      navigate('/')
    } catch {
      setError('Network error. Please try again.')
      setLoading(false)
    }
  }

  return (
    <div className="auth-page">
      <motion.div className="auth-card"
        initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}>

        <div className="auth-logo">
          <div className="auth-logo-icon">dg</div>
          <span>dgraph.ai</span>
        </div>

        <h1 className="auth-title">Sign in</h1>
        <p className="auth-sub">Welcome back to your knowledge graph</p>

        {error && (
          <div className="auth-error">
            <AlertCircle size={14} /> {error}
          </div>
        )}

        <form onSubmit={submit} className="auth-form">
          {!needsMFA ? (
            <>
              <div className="auth-field">
                <label>Email</label>
                <input
                  type="email" value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  autoComplete="email" autoFocus required
                />
              </div>

              <div className="auth-field">
                <label>
                  Password
                  <Link to="/forgot-password" className="auth-field-link">Forgot?</Link>
                </label>
                <div className="auth-password-wrap">
                  <input
                    type={showPw ? 'text' : 'password'}
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    placeholder="••••••••"
                    autoComplete="current-password" required
                  />
                  <button type="button" onClick={() => setShowPw(v => !v)} className="auth-pw-toggle">
                    {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </div>
            </>
          ) : (
            <div className="auth-mfa-block">
              <div className="auth-mfa-icon"><ShieldCheck size={28} /></div>
              <p className="auth-mfa-title">Two-factor authentication</p>
              <p className="auth-mfa-sub">Enter the 6-digit code from your authenticator app</p>
              <input
                type="text" inputMode="numeric" pattern="\d{6}"
                value={mfaCode} onChange={e => setMFACode(e.target.value)}
                placeholder="000000" maxLength={6}
                autoFocus className="auth-mfa-input"
              />
            </div>
          )}

          <button type="submit" disabled={loading} className="auth-submit">
            {loading ? <Loader2 size={15} className="auth-spin" /> : null}
            {loading ? 'Signing in…' : needsMFA ? 'Verify' : 'Sign in'}
          </button>
        </form>

        <div className="auth-divider"><span>or</span></div>

        <div className="auth-sso-buttons">
          <a href="/api/auth/saml/login" className="auth-sso-btn">
            Sign in with SSO (SAML)
          </a>
        </div>

        <p className="auth-footer">
          Don't have an account? <Link to="/signup">Sign up</Link>
        </p>
      </motion.div>
    </div>
  )
}
