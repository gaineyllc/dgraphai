// @ts-nocheck
/**
 * Settings page — replaces the placeholder.
 * Tabs: Profile | Team | Security | Notifications | Billing | Danger Zone
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import {
  User, Users, Shield, Bell, CreditCard, AlertTriangle,
  CheckCircle, Loader2, Copy, Trash2, Plus, X, ExternalLink,
  Key, Smartphone, LogOut
} from 'lucide-react'
import { MFASetupPage } from './auth/MFASetupPage'
import './SettingsPage.css'

const token = () => localStorage.getItem('dgraphai_token') || ''
const authHeaders = () => ({ Authorization: `Bearer ${token()}`, 'Content-Type': 'application/json' })

const api = {
  profile:      ()     => fetch('/api/users/me',       { headers: authHeaders() }).then(r => r.json()),
  updateProfile:(b)    => fetch('/api/users/me',       { method: 'PATCH', headers: authHeaders(), body: JSON.stringify(b) }).then(r => r.json()),
  team:         ()     => fetch('/api/users',          { headers: authHeaders() }).then(r => r.json()),
  invite:       (b)    => fetch('/api/users/invite',   { method: 'POST',  headers: authHeaders(), body: JSON.stringify(b) }).then(r => r.json()),
  removeUser:   (id)   => fetch(`/api/users/${id}`,    { method: 'DELETE',headers: authHeaders() }).then(r => r.json()),
  billing:      ()     => fetch('/api/settings/billing',{ headers: authHeaders() }).then(r => r.json()),
  checkout:     (plan) => fetch('/api/settings/billing/checkout', { method: 'POST', headers: authHeaders(), body: JSON.stringify({ plan }) }).then(r => r.json()),
  notifs:       ()     => fetch('/api/settings/notifications', { headers: authHeaders() }).then(r => r.json()),
  updateNotifs: (b)    => fetch('/api/settings/notifications', { method: 'PATCH', headers: authHeaders(), body: JSON.stringify(b) }).then(r => r.json()),
  apiKeys:      ()     => fetch('/api/auth/api-keys',  { headers: authHeaders() }).then(r => r.json()),
  createKey:    (b)    => fetch('/api/auth/api-keys',  { method: 'POST',  headers: authHeaders(), body: JSON.stringify(b) }).then(r => r.json()),
  revokeKey:    (id)   => fetch(`/api/auth/api-keys/${id}`, { method: 'DELETE', headers: authHeaders() }).then(r => r.json()),
  sessions:     ()     => fetch('/api/auth/sessions',  { headers: authHeaders() }).then(r => r.json()),
  revokeSession:(id)   => fetch(`/api/auth/sessions/${id}`, { method: 'DELETE', headers: authHeaders() }).then(r => r.json()),
  changePw:     (b)    => fetch('/api/auth/change-password', { method: 'POST', headers: authHeaders(), body: JSON.stringify(b) }).then(r => r.json()),
  deleteTenant: (b)    => fetch('/api/settings/danger/delete-tenant', { method: 'POST', headers: authHeaders(), body: JSON.stringify(b) }).then(r => r.json()),
}

const TABS = [
  { id: 'profile',       label: 'Profile',        icon: User         },
  { id: 'team',          label: 'Team',            icon: Users        },
  { id: 'security',      label: 'Security',        icon: Shield       },
  { id: 'notifications', label: 'Notifications',   icon: Bell         },
  { id: 'billing',       label: 'Billing',         icon: CreditCard   },
  { id: 'danger',        label: 'Danger Zone',     icon: AlertTriangle},
]

export function SettingsPage() {
  const [tab, setTab] = useState('profile')

  return (
    <div className="settings-page">
      <div className="settings-header">
        <h1>Settings</h1>
        <p>Manage your account, team, and billing</p>
      </div>
      <div className="settings-layout">
        {/* Sidebar nav */}
        <nav className="settings-nav">
          {TABS.map(t => {
            const Icon = t.icon
            return (
              <button key={t.id}
                className={`settings-nav-item ${tab === t.id ? 'active' : ''} ${t.id === 'danger' ? 'danger' : ''}`}
                onClick={() => setTab(t.id)}>
                <Icon size={14} /> {t.label}
              </button>
            )
          })}
        </nav>

        {/* Content */}
        <div className="settings-content">
          <AnimatePresence mode="wait">
            <motion.div key={tab}
              initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0 }} transition={{ duration: 0.12 }}>
              {tab === 'profile'       && <ProfileTab />}
              {tab === 'team'          && <TeamTab />}
              {tab === 'security'      && <SecurityTab />}
              {tab === 'notifications' && <NotificationsTab />}
              {tab === 'billing'       && <BillingTab />}
              {tab === 'danger'        && <DangerTab />}
            </motion.div>
          </AnimatePresence>
        </div>
      </div>
    </div>
  )
}

// ── Profile tab ────────────────────────────────────────────────────────────────
function ProfileTab() {
  const qc = useQueryClient()
  const { data: profile } = useQuery({ queryKey: ['profile'], queryFn: api.profile })
  const [name,  setName]  = useState('')
  const [saved, setSaved] = useState(false)

  const save = useMutation({
    mutationFn: () => api.updateProfile({ name: name || profile?.name }),
    onSuccess: () => { setSaved(true); setTimeout(() => setSaved(false), 2000); qc.invalidateQueries({ queryKey: ['profile'] }) },
  })

  return (
    <div className="settings-section">
      <h2>Profile</h2>
      <div className="settings-field">
        <label>Display name</label>
        <input value={name || profile?.name || ''} onChange={e => setName(e.target.value)}
          placeholder={profile?.name || 'Your name'} />
      </div>
      <div className="settings-field">
        <label>Email</label>
        <input value={profile?.email || ''} disabled />
        {profile && !profile.email_verified && (
          <span className="settings-field-hint warn">⚠ Email not verified</span>
        )}
      </div>
      <div className="settings-field">
        <label>Tenant</label>
        <input value={profile?.tenant?.name || ''} disabled />
        <span className="settings-field-hint">{profile?.tenant?.plan} plan · slug: {profile?.tenant?.slug}</span>
      </div>
      <button onClick={() => save.mutate()} disabled={save.isPending} className="settings-save-btn">
        {save.isPending ? <Loader2 size={13} className="settings-spin" /> : null}
        {saved ? <><CheckCircle size={13} /> Saved</> : 'Save changes'}
      </button>
    </div>
  )
}

// ── Team tab ───────────────────────────────────────────────────────────────────
function TeamTab() {
  const qc = useQueryClient()
  const { data: members = [] } = useQuery({ queryKey: ['team'], queryFn: api.team })
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole,  setInviteRole]  = useState('analyst')
  const [inviting,    setInviting]    = useState(false)
  const [inviteDone,  setInviteDone]  = useState(false)

  const invite = async () => {
    setInviting(true)
    await api.invite({ email: inviteEmail, role: inviteRole })
    setInviting(false); setInviteDone(true); setInviteEmail('')
    setTimeout(() => setInviteDone(false), 3000)
  }

  const remove = useMutation({
    mutationFn: api.removeUser,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['team'] }),
  })

  return (
    <div className="settings-section">
      <h2>Team members</h2>

      {/* Invite */}
      <div className="settings-invite-row">
        <input value={inviteEmail} onChange={e => setInviteEmail(e.target.value)}
          placeholder="colleague@company.com" type="email" style={{ flex: 1 }} />
        <select value={inviteRole} onChange={e => setInviteRole(e.target.value)} className="settings-select">
          <option value="admin">Admin</option>
          <option value="analyst">Analyst</option>
          <option value="viewer">Viewer</option>
        </select>
        <button onClick={invite} disabled={!inviteEmail || inviting} className="settings-save-btn">
          {inviting ? <Loader2 size={13} className="settings-spin" /> : <Plus size={13} />}
          Invite
        </button>
      </div>
      {inviteDone && <p style={{ fontSize: 12, color: '#10b981', marginTop: 6 }}>✓ Invitation sent</p>}

      {/* Member list */}
      <div className="settings-member-list">
        {members.map(m => (
          <div key={m.id} className="settings-member">
            <div className="settings-member-avatar">{(m.name || m.email)[0].toUpperCase()}</div>
            <div className="settings-member-info">
              <div className="settings-member-name">{m.name || m.email}</div>
              <div className="settings-member-email">{m.email}</div>
            </div>
            <span className={`settings-role-badge settings-role-${m.role}`}>{m.role}</span>
            <button onClick={() => remove.mutate(m.id)} className="settings-icon-btn danger" title="Remove">
              <Trash2 size={13} />
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Security tab ───────────────────────────────────────────────────────────────
function SecurityTab() {
  const qc = useQueryClient()
  const { data: profile }  = useQuery({ queryKey: ['profile'],  queryFn: api.profile })
  const { data: keys = [] } = useQuery({ queryKey: ['api-keys'], queryFn: api.apiKeys })
  const { data: sessions = [] } = useQuery({ queryKey: ['sessions'], queryFn: api.sessions })

  const [showMFA,    setShowMFA]    = useState(false)
  const [newKeyName, setNewKeyName] = useState('')
  const [newKey,     setNewKey]     = useState<string | null>(null)
  const [changePw,   setChangePw]   = useState({ current: '', next: '', show: false })
  const [pwError,    setPwError]    = useState('')
  const [pwSaved,    setPwSaved]    = useState(false)

  const createKey = useMutation({
    mutationFn: () => api.createKey({ name: newKeyName }),
    onSuccess: (d) => { setNewKey(d.key); setNewKeyName(''); qc.invalidateQueries({ queryKey: ['api-keys'] }) },
  })

  const revokeKey = useMutation({
    mutationFn: api.revokeKey,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['api-keys'] }),
  })

  const revokeSession = useMutation({
    mutationFn: api.revokeSession,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sessions'] }),
  })

  const doChangePw = async () => {
    setPwError('')
    const r = await api.changePw({ current_password: changePw.current, new_password: changePw.next })
    if (r.status === 'ok') { setPwSaved(true); setChangePw({ current: '', next: '', show: false }) }
    else setPwError(r.detail || 'Failed')
  }

  return (
    <div className="settings-section">
      <h2>Security</h2>

      {/* MFA */}
      <div className="settings-card">
        <div className="settings-card-header">
          <Smartphone size={16} />
          <div>
            <div className="settings-card-title">Two-factor authentication</div>
            <div className="settings-card-sub">
              {profile?.mfa_enabled ? 'Enabled — your account is protected' : 'Not enabled — add extra security'}
            </div>
          </div>
          <button onClick={() => setShowMFA(v => !v)} className="settings-action-btn">
            {profile?.mfa_enabled ? 'Manage' : 'Enable MFA'}
          </button>
        </div>
        {showMFA && <div style={{ marginTop: 16 }}><MFASetupPage onDone={() => { setShowMFA(false); qc.invalidateQueries({ queryKey: ['profile'] }) }} /></div>}
      </div>

      {/* Change password */}
      <div className="settings-card">
        <div className="settings-card-header">
          <Key size={16} />
          <div>
            <div className="settings-card-title">Password</div>
            <div className="settings-card-sub">Change your account password</div>
          </div>
          <button onClick={() => setChangePw(p => ({ ...p, show: !p.show }))} className="settings-action-btn">
            Change
          </button>
        </div>
        {changePw.show && (
          <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 10 }}>
            {pwError && <div className="auth-error" style={{ fontSize: 12 }}>{pwError}</div>}
            {pwSaved && <p style={{ fontSize: 12, color: '#10b981' }}>✓ Password changed</p>}
            <input type="password" placeholder="Current password" value={changePw.current}
              onChange={e => setChangePw(p => ({ ...p, current: e.target.value }))}
              className="settings-input" />
            <input type="password" placeholder="New password" value={changePw.next}
              onChange={e => setChangePw(p => ({ ...p, next: e.target.value }))}
              className="settings-input" />
            <button onClick={doChangePw} className="settings-save-btn" style={{ alignSelf: 'flex-start' }}>
              Update password
            </button>
          </div>
        )}
      </div>

      {/* API keys */}
      <div className="settings-card">
        <div className="settings-card-title" style={{ marginBottom: 12 }}>API Keys</div>
        {newKey && (
          <div style={{ padding: '10px 14px', background: '#0a0a0f', border: '1px solid #10b981', borderRadius: 8, marginBottom: 12 }}>
            <div style={{ fontSize: 11, color: '#10b981', marginBottom: 6 }}>✓ Key created — copy it now, it won't be shown again</div>
            <div style={{ display: 'flex', gap: 8 }}>
              <code style={{ flex: 1, fontSize: 12, color: '#c8c8e0', fontFamily: 'monospace', wordBreak: 'break-all' }}>{newKey}</code>
              <button onClick={() => { navigator.clipboard.writeText(newKey); setNewKey(null) }} className="settings-action-btn">
                <Copy size={11} /> Copy & close
              </button>
            </div>
          </div>
        )}
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <input value={newKeyName} onChange={e => setNewKeyName(e.target.value)}
            placeholder="Key name (e.g. CI/CD)" className="settings-input" style={{ flex: 1 }} />
          <button onClick={() => createKey.mutate()} disabled={!newKeyName} className="settings-save-btn">
            <Plus size={13} /> Create
          </button>
        </div>
        {keys.map(k => (
          <div key={k.id} className="settings-member">
            <Key size={14} style={{ color: '#4f8ef7', flexShrink: 0 }} />
            <div className="settings-member-info">
              <div className="settings-member-name">{k.name}</div>
              <div className="settings-member-email">{k.prefix}… · last used {k.last_used_at ? new Date(k.last_used_at).toLocaleDateString() : 'never'}</div>
            </div>
            <button onClick={() => revokeKey.mutate(k.id)} className="settings-icon-btn danger"><Trash2 size={12} /></button>
          </div>
        ))}
      </div>

      {/* Sessions */}
      <div className="settings-card">
        <div className="settings-card-title" style={{ marginBottom: 12 }}>Active sessions</div>
        {sessions.map(s => (
          <div key={s.id} className="settings-member">
            <LogOut size={14} style={{ color: '#55557a', flexShrink: 0 }} />
            <div className="settings-member-info">
              <div className="settings-member-name">{s.ip_address || 'Unknown IP'}</div>
              <div className="settings-member-email">{s.user_agent?.slice(0, 60) || 'Unknown device'}</div>
            </div>
            <button onClick={() => revokeSession.mutate(s.id)} className="settings-icon-btn"><X size={12} /></button>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Notifications tab ──────────────────────────────────────────────────────────
function NotificationsTab() {
  const qc = useQueryClient()
  const { data: cfg } = useQuery({ queryKey: ['notifs'], queryFn: api.notifs })
  const [form, setForm] = useState<any>({})
  const [saved, setSaved] = useState(false)

  const current = { ...cfg, ...form }

  const save = useMutation({
    mutationFn: () => api.updateNotifs(current),
    onSuccess: () => { setSaved(true); setTimeout(() => setSaved(false), 2000); qc.invalidateQueries({ queryKey: ['notifs'] }) },
  })

  const field = (key: string, label: string, placeholder = '') => (
    <div className="settings-field">
      <label>{label}</label>
      <input value={current[key] || ''} onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
        placeholder={placeholder} />
    </div>
  )

  return (
    <div className="settings-section">
      <h2>Notifications</h2>

      <div className="settings-toggle-row">
        <div>
          <div className="settings-toggle-label">Email alerts</div>
          <div className="settings-toggle-sub">Receive security findings by email</div>
        </div>
        <label className="settings-toggle">
          <input type="checkbox" checked={current.email_alerts ?? true}
            onChange={e => setForm(f => ({ ...f, email_alerts: e.target.checked }))} />
          <span className="settings-toggle-slider" />
        </label>
      </div>

      <div className="settings-field">
        <label>Alert severity threshold</label>
        <select value={current.alert_severity_threshold || 'high'}
          onChange={e => setForm(f => ({ ...f, alert_severity_threshold: e.target.value }))}
          className="settings-select">
          <option value="critical">Critical only</option>
          <option value="high">High and above</option>
          <option value="medium">Medium and above</option>
          <option value="low">All</option>
        </select>
      </div>

      <div className="settings-section-divider">Integrations</div>

      {field('slack_webhook',  'Slack webhook URL',  'https://hooks.slack.com/...')}
      {field('teams_webhook',  'Teams webhook URL',  'https://outlook.office.com/webhook/...')}
      {field('pagerduty_key',  'PagerDuty integration key', 'PagerDuty routing key')}

      <button onClick={() => save.mutate()} disabled={save.isPending} className="settings-save-btn">
        {save.isPending ? <Loader2 size={13} className="settings-spin" /> : null}
        {saved ? <><CheckCircle size={13} /> Saved</> : 'Save'}
      </button>
    </div>
  )
}

// ── Billing tab ────────────────────────────────────────────────────────────────
function BillingTab() {
  const { data: billing, isLoading } = useQuery({ queryKey: ['billing'], queryFn: api.billing })
  const [upgrading, setUpgrading] = useState('')

  const upgrade = async (plan: string) => {
    setUpgrading(plan)
    const d = await api.checkout(plan)
    if (d.checkout_url) window.location.href = d.checkout_url
    if (d.redirect_url) window.location.href = d.redirect_url
    setUpgrading('')
  }

  const PLANS = [
    { id: 'starter',    name: 'Starter',    price: 'Free',   features: ['50K nodes included', '1 scanner agent', 'Basic inventory'] },
    { id: 'pro',        name: 'Pro',        price: '$299/mo', features: ['200K nodes included', '3 scanner agents', 'AI enrichment', 'API access'] },
    { id: 'business',   name: 'Business',   price: '$999/mo', features: ['2M nodes included', '10 agents', 'SSO/SCIM', 'Face recognition', 'Audit log'] },
    { id: 'enterprise', name: 'Enterprise', price: 'Custom',  features: ['Unlimited', 'Air-gapped', 'BYOK', 'SLA', 'Dedicated support'] },
  ]

  return (
    <div className="settings-section">
      <h2>Billing</h2>

      {billing && (
        <div className="settings-card" style={{ marginBottom: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div className="settings-card-title">{billing.plan} plan</div>
              <div className="settings-card-sub">Status: {billing.subscription_status || 'active'}</div>
            </div>
            {billing.portal_url && (
              <a href={billing.portal_url} target="_blank" rel="noopener noreferrer" className="settings-action-btn">
                <ExternalLink size={12} /> Manage billing
              </a>
            )}
          </div>
        </div>
      )}

      <div className="settings-plan-grid">
        {PLANS.map(p => (
          <div key={p.id} className={`settings-plan-card ${billing?.plan === p.id ? 'current' : ''}`}>
            {billing?.plan === p.id && <div className="settings-plan-current">Current</div>}
            <div className="settings-plan-name">{p.name}</div>
            <div className="settings-plan-price">{p.price}</div>
            <ul className="settings-plan-features">
              {p.features.map(f => <li key={f}>{f}</li>)}
            </ul>
            {billing?.plan !== p.id && (
              <button onClick={() => upgrade(p.id)} disabled={!!upgrading} className="settings-save-btn">
                {upgrading === p.id ? <Loader2 size={13} className="settings-spin" /> : null}
                {p.id === 'enterprise' ? 'Contact sales' : 'Upgrade'}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Danger zone ────────────────────────────────────────────────────────────────
function DangerTab() {
  const [confirm,  setConfirm]  = useState('')
  const [password, setPassword] = useState('')
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState('')
  const [done,     setDone]     = useState(false)

  const deleteAccount = async () => {
    if (confirm !== 'DELETE') return
    setLoading(true); setError('')
    const r = await api.deleteTenant({ confirm, password })
    if (r.status === 'queued') setDone(true)
    else setError(r.detail || 'Failed')
    setLoading(false)
  }

  return (
    <div className="settings-section">
      <h2 style={{ color: '#f87171' }}>Danger Zone</h2>

      <div className="settings-danger-card">
        <div className="settings-danger-header">
          <AlertTriangle size={18} style={{ color: '#f87171' }} />
          <div>
            <div className="settings-card-title">Delete tenant and all data</div>
            <div className="settings-card-sub">
              Permanently deletes all graph data, files, users, and configurations.
              This cannot be undone. Data will be erased within 72 hours (GDPR compliant).
            </div>
          </div>
        </div>

        {done ? (
          <p style={{ color: '#10b981', fontSize: 13, marginTop: 12 }}>
            ✓ Deletion queued. All data will be erased within 72 hours.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 16 }}>
            {error && <div className="auth-error" style={{ fontSize: 12 }}>{error}</div>}
            <input value={password} onChange={e => setPassword(e.target.value)}
              type="password" placeholder="Your password" className="settings-input" />
            <input value={confirm} onChange={e => setConfirm(e.target.value)}
              placeholder='Type DELETE to confirm' className="settings-input"
              style={{ borderColor: confirm && confirm !== 'DELETE' ? '#f87171' : undefined }} />
            <button onClick={deleteAccount}
              disabled={confirm !== 'DELETE' || !password || loading}
              className="settings-save-btn danger">
              {loading ? <Loader2 size={13} className="settings-spin" /> : <Trash2 size={13} />}
              Delete account permanently
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
