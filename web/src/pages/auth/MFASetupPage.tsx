// @ts-nocheck
/**
 * MFA enrollment page — accessible from Settings > Security.
 * Shows QR code, secret, backup codes, and confirmation step.
 */
import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { ShieldCheck, Copy, AlertCircle, CheckCircle2, Loader2 } from 'lucide-react'
import './Auth.css'

const api = {
  enroll: () => fetch('/api/auth/mfa/enroll', {
    method: 'POST',
    headers: { Authorization: `Bearer ${localStorage.getItem('dgraphai_token')}` },
  }).then(r => r.json()),
  verify: (code: string) => fetch('/api/auth/mfa/verify-enrollment', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('dgraphai_token')}` },
    body:    JSON.stringify({ code }),
  }).then(r => r.json()),
}

export function MFASetupPage({ onDone }: { onDone?: () => void }) {
  const [step,   setStep]   = useState<'setup' | 'verify' | 'done'>('setup')
  const [code,   setCode]   = useState('')
  const [error,  setError]  = useState('')
  const [copied, setCopied] = useState(false)

  const { data: enrollment, isLoading } = useQuery({
    queryKey: ['mfa-enroll'],
    queryFn:  api.enroll,
  })

  const verifyMutation = useMutation({
    mutationFn: api.verify,
    onSuccess: (data) => {
      if (data.status === 'enrolled') {
        setStep('done')
        setTimeout(() => onDone?.(), 2000)
      } else {
        setError(data.detail || 'Verification failed')
      }
    },
    onError: () => setError('Network error'),
  })

  const copySecret = () => {
    navigator.clipboard.writeText(enrollment?.secret || '')
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (isLoading) return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
      <Loader2 size={24} className="auth-spin" style={{ color: '#4f8ef7' }} />
    </div>
  )

  return (
    <motion.div className="auth-card" style={{ maxWidth: 480 }}
      initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>

      {step === 'setup' && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
            <ShieldCheck size={22} style={{ color: '#4f8ef7' }} />
            <h2 className="auth-title" style={{ margin: 0 }}>Set up two-factor authentication</h2>
          </div>
          <p className="auth-sub" style={{ marginBottom: 20 }}>
            Scan this QR code with your authenticator app (Google Authenticator, Authy, 1Password, etc.)
          </p>

          {enrollment?.qr_code_png && (
            <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
              <img
                src={`data:image/png;base64,${enrollment.qr_code_png}`}
                alt="MFA QR Code"
                style={{ width: 180, height: 180, border: '1px solid #252535', borderRadius: 10 }}
              />
            </div>
          )}

          <div style={{ background: '#0a0a0f', border: '1px solid #1a1a28', borderRadius: 8, padding: '10px 14px', marginBottom: 16 }}>
            <div style={{ fontSize: 10, color: '#35354a', textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 4 }}>
              Manual entry secret
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <code style={{ fontSize: 13, color: '#c8c8e0', fontFamily: 'monospace', flex: 1, wordBreak: 'break-all' }}>
                {enrollment?.secret}
              </code>
              <button onClick={copySecret} style={{ background: 'none', border: '1px solid #252535', borderRadius: 6, padding: '4px 8px', color: '#55557a', cursor: 'pointer', fontSize: 11, whiteSpace: 'nowrap' }}>
                {copied ? '✓ Copied' : <><Copy size={11} /> Copy</>}
              </button>
            </div>
          </div>

          <button onClick={() => setStep('verify')} className="auth-submit">
            Next: verify code →
          </button>
        </>
      )}

      {step === 'verify' && (
        <>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, marginBottom: 20 }}>
            <ShieldCheck size={32} style={{ color: '#4f8ef7' }} />
            <h2 className="auth-title" style={{ margin: 0 }}>Verify your authenticator</h2>
            <p className="auth-sub" style={{ textAlign: 'center', margin: 0 }}>
              Enter the 6-digit code from your app to confirm setup
            </p>
          </div>

          {error && <div className="auth-error" style={{ marginBottom: 12 }}><AlertCircle size={14} /> {error}</div>}

          <input
            type="text" inputMode="numeric" pattern="\d{6}" maxLength={6}
            value={code} onChange={e => setCode(e.target.value)}
            placeholder="000000"
            className="auth-mfa-input"
            style={{ margin: '0 auto 16px', display: 'block' }}
            autoFocus
          />
          <button
            onClick={() => verifyMutation.mutate(code)}
            disabled={code.length !== 6 || verifyMutation.isPending}
            className="auth-submit"
          >
            {verifyMutation.isPending ? <Loader2 size={15} className="auth-spin" /> : null}
            {verifyMutation.isPending ? 'Verifying…' : 'Enable MFA'}
          </button>

          {enrollment?.backup_codes?.length > 0 && (
            <div style={{ marginTop: 20, padding: 14, background: '#0a0a0f', border: '1px solid #252535', borderRadius: 10 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: '#f59e0b', marginBottom: 8 }}>
                ⚠ Save your backup codes — shown only once
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                {enrollment.backup_codes.map((c, i) => (
                  <code key={i} style={{ fontSize: 12, color: '#c8c8e0', fontFamily: 'monospace', padding: '3px 6px', background: '#12121a', borderRadius: 5 }}>{c}</code>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {step === 'done' && (
        <div style={{ textAlign: 'center', padding: '20px 0' }}>
          <div className="auth-success-icon"><CheckCircle2 size={48} /></div>
          <h2 className="auth-title" style={{ marginTop: 12 }}>MFA enabled!</h2>
          <p className="auth-sub">Your account is now protected with two-factor authentication.</p>
        </div>
      )}
    </motion.div>
  )
}
