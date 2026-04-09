// @ts-nocheck
/**
 * First-run wizard — shown when tenant has zero connectors.
 * Guides new users from signup → first connector → first scan → see graph.
 * Disappears permanently once a scan completes.
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Plug, HardDrive, Zap, Network, ChevronRight,
  CheckCircle, Server, Cloud, X
} from 'lucide-react'
import './FirstRunWizard.css'

const CONNECTOR_TYPES = [
  { id: 'local',      icon: '💻', name: 'Local folder',   desc: 'Index files on this machine or a mounted drive' },
  { id: 'smb',        icon: '🗄️', name: 'NAS / SMB Share', desc: 'Windows share, Synology, QNAP, or any SMB server' },
  { id: 'aws-s3',     icon: '🪣', name: 'Amazon S3',      desc: 'Connect an S3 bucket' },
  { id: 'azure-blob', icon: '☁️', name: 'Azure Blob',     desc: 'Connect Azure Blob Storage' },
  { id: 'sharepoint', icon: '📁', name: 'SharePoint',     desc: 'Index SharePoint / OneDrive for Business' },
  { id: 'gcs',        icon: '🔵', name: 'Google Cloud Storage', desc: 'Index a GCS bucket' },
]

const STEPS = [
  { id: 'welcome',   label: 'Welcome'    },
  { id: 'connector', label: 'Add source' },
  { id: 'agent',     label: 'Install agent'},
  { id: 'scan',      label: 'First scan'  },
]

interface Props {
  onDismiss?: () => void
}

export function FirstRunWizard({ onDismiss }: Props) {
  const navigate = useNavigate()
  const [step,       setStep]       = useState(0)
  const [connType,   setConnType]   = useState('')
  const [connConfig, setConnConfig] = useState<any>({})
  const [creating,   setCreating]   = useState(false)
  const [connId,     setConnId]     = useState('')
  const [dismissed,  setDismissed]  = useState(false)

  const dismiss = () => {
    setDismissed(true)
    onDismiss?.()
  }

  const createConnector = async () => {
    setCreating(true)
    const r = await fetch('/api/connectors', {
      method:  'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${localStorage.getItem('dgraphai_token')}`,
      },
      body: JSON.stringify({
        name:           connConfig.name || `My ${connType}`,
        connector_type: connType,
        config:         connConfig,
        routing_mode:   ['smb','local','nfs'].includes(connType) ? 'agent' : 'direct',
      }),
    })
    const data = await r.json()
    if (data.id) {
      setConnId(data.id)
      setStep(2)
    }
    setCreating(false)
  }

  if (dismissed) return null

  return (
    <AnimatePresence>
      <motion.div className="frw-overlay"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
        <motion.div className="frw-modal"
          initial={{ scale: .95, y: 20 }} animate={{ scale: 1, y: 0 }}
          exit={{ scale: .95, opacity: 0 }} transition={{ duration: 0.2 }}>

          {/* Progress */}
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
                <div className="frw-icon-hero">
                  <Network size={40} />
                </div>
                <h2>Welcome to dgraph.ai</h2>
                <p>
                  dgraph.ai builds a knowledge graph of everything in your data sources —
                  files, identities, relationships, security findings — all in one place.
                  Let's connect your first source.
                </p>
                <div className="frw-feature-list">
                  <div className="frw-feature"><Plug size={14} /><span>Connect SMB, S3, Azure, SharePoint, NFS</span></div>
                  <div className="frw-feature"><Zap size={14} /><span>AI enrichment: secrets, PII, face recognition</span></div>
                  <div className="frw-feature"><Network size={14} /><span>Graph explorer with 26 relationship types</span></div>
                </div>
                <button onClick={() => setStep(1)} className="frw-primary-btn">
                  Get started <ChevronRight size={14} />
                </button>
              </motion.div>
            )}

            {/* ── Step 1: Choose connector ── */}
            {step === 1 && (
              <motion.div key="connector" className="frw-body"
                initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
                <h2>Choose your data source</h2>
                <p>Where are the files you want to index?</p>

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
                  <motion.div className="frw-config-block" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                    <div className="frw-field">
                      <label>Connector name</label>
                      <input value={connConfig.name || ''} onChange={e => setConnConfig(c => ({ ...c, name: e.target.value }))}
                        placeholder={`My ${connType}`} />
                    </div>
                    {connType === 'local' && (
                      <div className="frw-field">
                        <label>Path to index</label>
                        <input value={connConfig.path || ''} onChange={e => setConnConfig(c => ({ ...c, path: e.target.value }))}
                          placeholder="/mnt/data or C:\Data" />
                      </div>
                    )}
                    {connType === 'smb' && (
                      <>
                        <div className="frw-field-row">
                          <div className="frw-field">
                            <label>Host / IP</label>
                            <input value={connConfig.host || ''} onChange={e => setConnConfig(c => ({ ...c, host: e.target.value }))}
                              placeholder="192.168.1.10" />
                          </div>
                          <div className="frw-field">
                            <label>Share name</label>
                            <input value={connConfig.share || ''} onChange={e => setConnConfig(c => ({ ...c, share: e.target.value }))}
                              placeholder="Media" />
                          </div>
                        </div>
                      </>
                    )}
                    {connType === 'aws-s3' && (
                      <div className="frw-field-row">
                        <div className="frw-field"><label>Bucket</label>
                          <input value={connConfig.bucket || ''} onChange={e => setConnConfig(c => ({ ...c, bucket: e.target.value }))} placeholder="my-bucket" />
                        </div>
                        <div className="frw-field"><label>Region</label>
                          <input value={connConfig.region || ''} onChange={e => setConnConfig(c => ({ ...c, region: e.target.value }))} placeholder="us-east-1" />
                        </div>
                      </div>
                    )}
                  </motion.div>
                )}

                <div className="frw-footer">
                  <button onClick={() => setStep(0)} className="frw-back-btn">← Back</button>
                  <button onClick={createConnector} disabled={!connType || creating} className="frw-primary-btn">
                    {creating ? 'Creating…' : 'Continue →'}
                  </button>
                </div>
              </motion.div>
            )}

            {/* ── Step 2: Install agent ── */}
            {step === 2 && (
              <motion.div key="agent" className="frw-body"
                initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
                <div className="frw-icon-hero"><Server size={36} /></div>
                <h2>Install the scanner agent</h2>
                <p>
                  dgraph-agent is a lightweight Go binary that runs on your infrastructure
                  and syncs metadata to dgraph.ai. No inbound ports. Outbound HTTPS only.
                </p>

                <div className="frw-install-tabs">
                  <div className="frw-install-tab">
                    <div className="frw-install-label">Helm (Kubernetes)</div>
                    <pre className="frw-code">{`helm install dgraph-agent oci://ghcr.io/gaineyllc/charts/dgraph-agent \\
  --set config.tenantId=YOUR_TENANT_ID \\
  --set credentials.apiKey=YOUR_API_KEY \\
  --set config.agentName="${connConfig.name || 'my-agent'}"`}</pre>
                  </div>
                  <div className="frw-install-tab">
                    <div className="frw-install-label">Docker</div>
                    <pre className="frw-code">{`docker run -d ghcr.io/gaineyllc/dgraph-agent:latest \\
  -e DGRAPH_AGENT_TENANT_ID=YOUR_TENANT_ID \\
  -e DGRAPH_AGENT_API_KEY=YOUR_API_KEY`}</pre>
                  </div>
                  <div className="frw-install-tab">
                    <div className="frw-install-label">Binary (Linux/macOS/Windows)</div>
                    <pre className="frw-code">{`# Download from github.com/gaineyllc/dgraphai/releases
./dgraph-agent --config config.yaml`}</pre>
                  </div>
                </div>

                <div className="frw-footer">
                  <button onClick={() => setStep(1)} className="frw-back-btn">← Back</button>
                  <button onClick={() => setStep(3)} className="frw-primary-btn">
                    Agent installed → Continue
                  </button>
                </div>
              </motion.div>
            )}

            {/* ── Step 3: Done ── */}
            {step === 3 && (
              <motion.div key="done" className="frw-body"
                initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }}>
                <div className="frw-icon-hero done"><CheckCircle size={48} /></div>
                <h2>You're all set!</h2>
                <p>
                  The scanner agent will start indexing your data shortly. Check the Indexer
                  dashboard to watch progress, or go straight to the graph.
                </p>
                <div className="frw-done-actions">
                  <button onClick={() => { navigate('/indexer'); dismiss() }} className="frw-secondary-btn">
                    Watch indexing progress
                  </button>
                  <button onClick={() => { navigate('/'); dismiss() }} className="frw-primary-btn">
                    <Network size={14} /> Open graph explorer
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
