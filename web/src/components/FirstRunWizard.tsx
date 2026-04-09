// @ts-nocheck
/**
 * First-run wizard — shown when tenant has zero connectors.
 * Guides new users from signup → first connector → agent token → done.
 *
 * Changes from v1:
 *  - Step 2 calls POST /api/agent/token to generate a REAL api key
 *  - Install commands show actual key, tenant, and cloud URL
 *  - Live agent status polling after token generated
 *  - Install tab switcher (Linux curl / Docker / Helm)
 */
import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Plug, HardDrive, Zap, Network, ChevronRight,
  CheckCircle, Server, Cloud, X, Copy, Check,
  Wifi, WifiOff, Loader2
} from 'lucide-react'
import { apiFetch } from '../lib/apiFetch'
import './FirstRunWizard.css'

const CONNECTOR_TYPES = [
  { id: 'local',      icon: '💻', name: 'Local folder',        desc: 'Files on this machine or a mounted drive' },
  { id: 'smb',        icon: '🗄️', name: 'NAS / SMB share',     desc: 'Synology, QNAP, Windows share, or any SMB server' },
  { id: 'aws-s3',     icon: '🪣', name: 'Amazon S3',           desc: 'Connect an S3 bucket' },
  { id: 'azure-blob', icon: '☁️', name: 'Azure Blob Storage',  desc: 'Connect Azure Blob Storage' },
  { id: 'sharepoint', icon: '📁', name: 'SharePoint / OneDrive',desc: 'Index SharePoint or OneDrive for Business' },
  { id: 'gcs',        icon: '🔵', name: 'Google Cloud Storage', desc: 'Index a GCS bucket' },
]

const STEPS = [
  { id: 'welcome',   label: 'Welcome'     },
  { id: 'connector', label: 'Add source'  },
  { id: 'agent',     label: 'Install agent'},
  { id: 'done',      label: 'Done'        },
]

interface AgentToken {
  agent_id: string
  api_key: string
  install_linux: string
  install_docker: string
  install_helm: string
}

interface Props { onDismiss?: () => void }

export function FirstRunWizard({ onDismiss }: Props) {
  const navigate = useNavigate()
  const [step,        setStep]        = useState(0)
  const [connType,    setConnType]    = useState('')
  const [connConfig,  setConnConfig]  = useState<any>({})
  const [creating,    setCreating]    = useState(false)
  const [connId,      setConnId]      = useState('')
  const [token,       setToken]       = useState<AgentToken | null>(null)
  const [tokenLoading,setTokenLoading]= useState(false)
  const [installTab,  setInstallTab]  = useState<'linux'|'docker'|'helm'>('linux')
  const [copied,      setCopied]      = useState(false)
  const [agentOnline, setAgentOnline] = useState(false)
  const [dismissed,   setDismissed]  = useState(false)

  const dismiss = () => { setDismissed(true); onDismiss?.() }

  // ── Generate agent token when entering step 2 ─────────────────────────────
  const generateToken = useCallback(async () => {
    if (token) return   // already generated
    setTokenLoading(true)
    try {
      const data = await apiFetch(`/api/agent/token?name=${encodeURIComponent(connConfig.name || 'my-agent')}`, { method: 'POST' })
      setToken(data)
    } catch (e) {
      console.error('Failed to generate agent token', e)
    } finally {
      setTokenLoading(false)
    }
  }, [token, connConfig.name])

  // ── Poll for agent heartbeat after token generated ─────────────────────────
  useEffect(() => {
    if (!token || agentOnline || step !== 2) return
    const interval = setInterval(async () => {
      try {
        const data = await apiFetch(`/api/agents/${token.agent_id}`)
        if (data.is_online) {
          setAgentOnline(true)
          clearInterval(interval)
        }
      } catch {}
    }, 5000)
    return () => clearInterval(interval)
  }, [token, agentOnline, step])

  // ── Create connector ──────────────────────────────────────────────────────
  const createConnector = async () => {
    setCreating(true)
    try {
      const data = await apiFetch('/api/connectors', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name:           connConfig.name || `My ${connType}`,
          connector_type: connType,
          config:         connConfig,
          routing_mode:   ['smb','local','nfs'].includes(connType) ? 'agent' : 'direct',
        }),
      })
      if (data.id) setConnId(data.id)
      setStep(2)
      generateToken()
    } finally {
      setCreating(false)
    }
  }

  // ── Copy to clipboard ─────────────────────────────────────────────────────
  const copy = (text: string) => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const currentCmd = token
    ? installTab === 'linux'  ? token.install_linux
    : installTab === 'docker' ? token.install_docker
    : token.install_helm
    : ''

  if (dismissed) return null

  return (
    <AnimatePresence>
      <motion.div className="frw-overlay"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
        <motion.div className="frw-modal"
          initial={{ scale: .95, y: 20 }} animate={{ scale: 1, y: 0 }}
          exit={{ scale: .95, opacity: 0 }} transition={{ duration: 0.2 }}>

          {/* Progress bar */}
          <div className="frw-progress">
            {STEPS.map((s, i) => (
              <div key={s.id} className={`frw-step ${i === step ? 'active' : ''} ${i < step ? 'done' : ''}`}>
                <div className="frw-step-dot">
                  {i < step ? <CheckCircle size={12} /> : <span>{i + 1}</span>}
                </div>
                <span>{s.label}</span>
                {i < STEPS.length - 1 && <div className="frw-step-line" />}
              </div>
            ))}
          </div>

          <button onClick={dismiss} className="frw-close"><X size={15} /></button>

          <AnimatePresence mode="wait">

            {/* ── Step 0: Welcome ── */}
            {step === 0 && (
              <motion.div key="welcome" className="frw-body"
                initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
                <div className="frw-icon-hero"><Network size={40} /></div>
                <h2>Welcome to dgraph.ai</h2>
                <p>
                  dgraph.ai maps your entire filesystem into a security knowledge graph —
                  exposing secrets, PII, CVEs, and access patterns across all your data sources.
                </p>
                <div className="frw-feature-list">
                  <div className="frw-feature"><Plug size={14} /><span>Connect SMB, S3, Azure, SharePoint, local drives</span></div>
                  <div className="frw-feature"><Zap size={14} /><span>AI enrichment — secrets, PII, binary analysis</span></div>
                  <div className="frw-feature"><Network size={14} /><span>Graph explorer with 26 relationship types</span></div>
                </div>
                <button onClick={() => setStep(1)} className="frw-primary-btn">
                  Get started <ChevronRight size={14} />
                </button>
              </motion.div>
            )}

            {/* ── Step 1: Choose + configure connector ── */}
            {step === 1 && (
              <motion.div key="connector" className="frw-body"
                initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
                <h2>Choose your data source</h2>
                <p>Where are the files you want to map?</p>

                <div className="frw-conn-grid">
                  {CONNECTOR_TYPES.map(ct => (
                    <button key={ct.id}
                      className={`frw-conn-card ${connType === ct.id ? 'selected' : ''}`}
                      onClick={() => setConnType(ct.id)}>
                      <span className="frw-conn-icon">{ct.icon}</span>
                      <div className="frw-conn-name">{ct.name}</div>
                      <div className="frw-conn-desc">{ct.desc}</div>
                    </button>
                  ))}
                </div>

                {connType && (
                  <motion.div className="frw-config-block"
                    initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                    <div className="frw-field">
                      <label>Name this connection</label>
                      <input
                        value={connConfig.name || ''}
                        onChange={e => setConnConfig((c: any) => ({ ...c, name: e.target.value }))}
                        placeholder={`My ${CONNECTOR_TYPES.find(c => c.id === connType)?.name}`}
                      />
                    </div>
                    {connType === 'local' && (
                      <div className="frw-field">
                        <label>Path to index</label>
                        <input value={connConfig.path || ''} onChange={e => setConnConfig((c: any) => ({ ...c, path: e.target.value }))}
                          placeholder="/mnt/data or C:\Data" />
                      </div>
                    )}
                    {connType === 'smb' && (
                      <div className="frw-field-row">
                        <div className="frw-field">
                          <label>Host / IP</label>
                          <input value={connConfig.host || ''} onChange={e => setConnConfig((c: any) => ({ ...c, host: e.target.value }))}
                            placeholder="192.168.1.10" />
                        </div>
                        <div className="frw-field">
                          <label>Share name</label>
                          <input value={connConfig.share || ''} onChange={e => setConnConfig((c: any) => ({ ...c, share: e.target.value }))}
                            placeholder="Media" />
                        </div>
                      </div>
                    )}
                    {connType === 'aws-s3' && (
                      <div className="frw-field-row">
                        <div className="frw-field"><label>Bucket</label>
                          <input value={connConfig.bucket || ''} onChange={e => setConnConfig((c: any) => ({ ...c, bucket: e.target.value }))} placeholder="my-bucket" />
                        </div>
                        <div className="frw-field"><label>Region</label>
                          <input value={connConfig.region || ''} onChange={e => setConnConfig((c: any) => ({ ...c, region: e.target.value }))} placeholder="us-east-1" />
                        </div>
                      </div>
                    )}
                  </motion.div>
                )}

                <div className="frw-footer">
                  <button onClick={() => setStep(0)} className="frw-back-btn">← Back</button>
                  <button onClick={createConnector} disabled={!connType || creating} className="frw-primary-btn">
                    {creating ? <><Loader2 size={14} className="frw-spin" /> Creating…</> : 'Continue →'}
                  </button>
                </div>
              </motion.div>
            )}

            {/* ── Step 2: Install agent with REAL token ── */}
            {step === 2 && (
              <motion.div key="agent" className="frw-body"
                initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
                <div className="frw-icon-hero"><Server size={36} /></div>
                <h2>Install the scanner agent</h2>
                <p>
                  A lightweight Go binary that runs on your infrastructure.
                  Outbound HTTPS only — no inbound ports required.
                </p>

                {tokenLoading ? (
                  <div className="frw-token-loading">
                    <Loader2 size={20} className="frw-spin" />
                    <span>Generating your API key…</span>
                  </div>
                ) : token ? (
                  <>
                    {/* Agent status pill */}
                    <div className={`frw-agent-status ${agentOnline ? 'online' : 'waiting'}`}>
                      {agentOnline
                        ? <><Wifi size={13} /> Agent connected</>
                        : <><WifiOff size={13} /> Waiting for agent to connect…</>
                      }
                    </div>

                    {/* Key warning */}
                    <div className="frw-key-warning">
                      <span>⚠</span> This API key is shown once. Copy it now — it cannot be retrieved later.
                    </div>

                    {/* Install tab switcher */}
                    <div className="frw-install-tabs-nav">
                      {(['linux','docker','helm'] as const).map(t => (
                        <button key={t} className={`frw-tab-btn ${installTab === t ? 'active' : ''}`}
                          onClick={() => setInstallTab(t)}>
                          {t === 'linux' ? 'Linux / macOS' : t === 'docker' ? 'Docker' : 'Helm (K8s)'}
                        </button>
                      ))}
                    </div>

                    <div className="frw-code-block">
                      <pre className="frw-code">{currentCmd}</pre>
                      <button className="frw-copy-btn" onClick={() => copy(currentCmd)}>
                        {copied ? <Check size={13} /> : <Copy size={13} />}
                        {copied ? 'Copied' : 'Copy'}
                      </button>
                    </div>
                  </>
                ) : (
                  <div className="frw-token-error">
                    Failed to generate API key.
                    <button onClick={generateToken} className="frw-text-btn">Retry</button>
                  </div>
                )}

                <div className="frw-footer">
                  <button onClick={() => setStep(1)} className="frw-back-btn">← Back</button>
                  <button
                    onClick={() => setStep(3)}
                    className={`frw-primary-btn ${agentOnline ? 'frw-btn-success' : ''}`}
                  >
                    {agentOnline ? <><CheckCircle size={14} /> Agent connected →</> : 'Skip for now →'}
                  </button>
                </div>
              </motion.div>
            )}

            {/* ── Step 3: Done ── */}
            {step === 3 && (
              <motion.div key="done" className="frw-body"
                initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
                <div className="frw-icon-hero done"><CheckCircle size={48} /></div>
                <h2>{agentOnline ? 'You\'re live!' : 'You\'re all set!'}</h2>
                <p>
                  {agentOnline
                    ? `Your agent is connected and indexing ${connConfig.name || 'your data'}. The graph will populate in a few minutes.`
                    : 'Your connector is configured. Once you install the agent, it will start indexing automatically.'}
                </p>
                <div className="frw-done-actions">
                  <button onClick={() => { navigate('/indexer'); dismiss() }} className="frw-secondary-btn">
                    Watch indexing
                  </button>
                  <button onClick={() => { navigate('/'); dismiss() }} className="frw-primary-btn">
                    <Network size={14} /> Open graph →
                  </button>
                </div>
              </motion.div>
            )}

          </AnimatePresence>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  )
}
