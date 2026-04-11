// @ts-nocheck
/**
 * PoliciesPage — central control plane for all agent behavior.
 *
 * Tabs:
 *   1. Scan Policy       — what to scan, schedules, exclusions
 *   2. Enrichment        — local AI vs platform AI vs cloud SaaS, which enrichers to run
 *   3. Data Streaming    — pull actual file content from agents, file preview, export
 *   4. Data Modification — read/write/update/delete permissions per connector
 *   5. Access Control    — service account config, Windows / Linux / macOS
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Shield, Scan, Cpu, Download, Edit3, Lock,
  Plus, Trash2, Check, ChevronDown, ChevronRight,
  AlertTriangle, Info, Server, Globe, Laptop,
  Eye, EyeOff, Save, RefreshCw, Zap,
} from 'lucide-react'
import { apiFetch } from '../lib/apiFetch'
import { PageHeader, Skeleton, EmptyState } from '../components/PageShell'
import './PoliciesPage.css'

// ── Types ─────────────────────────────────────────────────────────────────────

interface ScanPolicy {
  id:                string
  name:              string
  connector_ids:     string[]
  schedule:          string  // manual | 1h | 6h | 12h | 24h | weekly
  max_file_size_mb:  number
  exclude_patterns:  string[]
  include_hidden:    boolean
  follow_symlinks:   boolean
  enabled:           boolean
}

interface EnrichmentPolicy {
  mode:              'disabled' | 'agent_local' | 'platform' | 'saas'
  features: {
    file_classification: boolean  // MIME type, category
    secret_scanning:     boolean  // credentials, API keys, tokens
    pii_detection:       boolean  // names, emails, SSNs, etc.
    binary_analysis:     boolean  // PE/ELF/Mach-O analysis
    code_summarization:  boolean  // AI summary of code files
    image_ocr:           boolean  // extract text from images
    language_detection:  boolean  // detect file language
  }
  agent_model:       string  // local Ollama model for agent-side enrichment
  max_file_size_mb:  number  // max file size to enrich
  priority:          'low' | 'normal' | 'high'
}

interface StreamingPolicy {
  enabled:           boolean
  require_auth:      boolean
  max_file_size_mb:  number
  allowed_extensions: string[]
  log_access:        boolean
  rate_limit_rpm:    number  // requests per minute per user
}

interface ModificationPolicy {
  allow_read:        boolean
  allow_write:       boolean
  allow_delete:      boolean
  allow_rename:      boolean
  require_approval:  boolean
  audit_all_writes:  boolean
}

interface AccessPolicy {
  windows_service_account:  string
  linux_service_account:    string
  macos_service_account:    string
  use_host_permissions:     boolean  // agent runs as service account so host ACLs apply
  drop_elevated:            boolean  // drop elevated privileges after startup
}

// ── Default values ────────────────────────────────────────────────────────────

const DEFAULT_ENRICHMENT: EnrichmentPolicy = {
  mode: 'agent_local',
  features: {
    file_classification: true,
    secret_scanning:     true,
    pii_detection:       true,
    binary_analysis:     false,
    code_summarization:  false,
    image_ocr:           false,
    language_detection:  true,
  },
  agent_model:      'qwen2.5-coder:32b',
  max_file_size_mb: 50,
  priority:         'normal',
}

const DEFAULT_STREAMING: StreamingPolicy = {
  enabled:            false,
  require_auth:       true,
  max_file_size_mb:   100,
  allowed_extensions: [],
  log_access:         true,
  rate_limit_rpm:     60,
}

const DEFAULT_MODIFICATION: ModificationPolicy = {
  allow_read:       true,
  allow_write:      false,
  allow_delete:     false,
  allow_rename:     false,
  require_approval: true,
  audit_all_writes: true,
}

const DEFAULT_ACCESS: AccessPolicy = {
  windows_service_account: 'NT AUTHORITY\\NetworkService',
  linux_service_account:   'dgraph-agent',
  macos_service_account:   '_dgraph-agent',
  use_host_permissions:    true,
  drop_elevated:           true,
}

// ── Tabs ──────────────────────────────────────────────────────────────────────

const TABS = [
  { id: 'scan',         label: 'Scan',           icon: Scan    },
  { id: 'enrichment',   label: 'Enrichment',      icon: Cpu     },
  { id: 'streaming',    label: 'Data Streaming',  icon: Download},
  { id: 'modification', label: 'Modification',    icon: Edit3   },
  { id: 'access',       label: 'Access Control',  icon: Lock    },
]

// ── Main page ─────────────────────────────────────────────────────────────────

export function PoliciesPage() {
  const [tab, setTab] = useState('scan')

  return (
    <div className="policies-page">
      <PageHeader
        title="Policies"
        subtitle="Control how agents scan, enrich, stream, and modify data"
        badge="Security"
      />

      {/* Tab bar */}
      <div className="pol-tabs">
        {TABS.map(t => (
          <button
            key={t.id}
            className={`pol-tab ${tab === t.id ? 'active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            <t.icon size={15} />
            {t.label}
          </button>
        ))}
      </div>

      <div className="pol-content">
        {tab === 'scan'         && <ScanTab />}
        {tab === 'enrichment'   && <EnrichmentTab />}
        {tab === 'streaming'    && <StreamingTab />}
        {tab === 'modification' && <ModificationTab />}
        {tab === 'access'       && <AccessTab />}
      </div>
    </div>
  )
}

// ── Scan tab ──────────────────────────────────────────────────────────────────

function ScanTab() {
  const { data: connectors = [] } = useQuery({
    queryKey: ['connectors'],
    queryFn: () => apiFetch('/api/connectors').then(r => r.json()),
  })

  return (
    <div className="pol-section-grid">

      <div className="pol-card">
        <div className="pol-card-header">
          <h3>Default Scan Settings</h3>
          <p>Applied to all connectors unless overridden per-connector</p>
        </div>
        <div className="pol-fields">
          <FieldRow label="Schedule" hint="How often agents run full scans">
            <select className="pol-select">
              <option value="manual">Manual only</option>
              <option value="6h">Every 6 hours</option>
              <option value="12h">Every 12 hours</option>
              <option value="24h" selected>Daily</option>
              <option value="weekly">Weekly</option>
            </select>
          </FieldRow>
          <FieldRow label="Max file size" hint="Files larger than this are skipped during content scanning">
            <div className="pol-input-suffix">
              <input type="number" className="pol-input" defaultValue={500} min={1} />
              <span>MB</span>
            </div>
          </FieldRow>
          <FieldRow label="Include hidden files" hint="Scan dot-files and system directories">
            <Toggle defaultChecked={false} />
          </FieldRow>
          <FieldRow label="Follow symlinks" hint="Follow symbolic links during directory traversal">
            <Toggle defaultChecked={false} />
          </FieldRow>
          <FieldRow label="Exclude patterns" hint="Glob patterns to skip, one per line">
            <textarea
              className="pol-textarea"
              defaultValue={".git\nnode_modules\n__pycache__\n.DS_Store\n*.tmp"}
              rows={5}
            />
          </FieldRow>
        </div>
        <div className="pol-card-footer">
          <button className="btn btn-primary btn-sm"><Save size={13} /> Save changes</button>
        </div>
      </div>

      <div className="pol-card">
        <div className="pol-card-header">
          <h3>Connector Schedules</h3>
          <p>Per-connector schedule overrides</p>
        </div>
        {connectors.length === 0 ? (
          <EmptyState
            title="No connectors yet"
            desc="Add a connector to configure per-connector scan schedules"
            compact
          />
        ) : (
          <div className="pol-connector-list">
            {connectors.map((c: any) => (
              <div key={c.id} className="pol-connector-row">
                <div className="pol-connector-info">
                  <span className="pol-connector-name">{c.name}</span>
                  <span className="pol-connector-type">{c.connector_type}</span>
                </div>
                <select className="pol-select pol-select-sm">
                  <option>Use default</option>
                  <option>Manual</option>
                  <option>Every 1h</option>
                  <option>Every 6h</option>
                  <option selected>Daily</option>
                  <option>Weekly</option>
                </select>
              </div>
            ))}
          </div>
        )}
      </div>

    </div>
  )
}

// ── Enrichment tab ────────────────────────────────────────────────────────────

function EnrichmentTab() {
  const [mode, setMode] = useState<EnrichmentPolicy['mode']>('agent_local')

  const modes = [
    {
      id:    'disabled',
      label: 'Disabled',
      icon:  EyeOff,
      desc:  'No AI enrichment. Only file metadata (name, size, hash) is collected.',
      color: 'var(--text-tertiary)',
    },
    {
      id:    'agent_local',
      label: 'Agent local',
      icon:  Laptop,
      desc:  'Enrichment runs on the agent machine using a local Ollama model. File content never leaves the host.',
      color: 'var(--color-secondary)',
    },
    {
      id:    'platform',
      label: 'Platform (self-hosted)',
      icon:  Server,
      desc:  'Enrichment runs on your self-hosted dgraph.ai instance. File content is transferred over your internal network.',
      color: 'var(--color-primary)',
    },
    {
      id:    'saas',
      label: 'dgraph.ai SaaS',
      icon:  Globe,
      desc:  'Enrichment runs in the dgraph.ai cloud. File content is encrypted in transit. Only available on Business+ plans.',
      color: 'var(--color-tertiary)',
    },
  ]

  const features = [
    { key: 'file_classification', label: 'File classification',  desc: 'MIME type, category, language — uses extension + magic bytes',     local: true,  platform: true,  saas: true },
    { key: 'secret_scanning',     label: 'Secret scanning',      desc: 'API keys, passwords, tokens, certificates in file content',         local: true,  platform: true,  saas: true },
    { key: 'pii_detection',       label: 'PII detection',        desc: 'Names, emails, SSNs, phone numbers, addresses',                    local: true,  platform: true,  saas: true },
    { key: 'binary_analysis',     label: 'Binary analysis',      desc: 'PE/ELF/Mach-O header parsing, entropy, import table analysis',     local: true,  platform: true,  saas: true },
    { key: 'language_detection',  label: 'Language detection',   desc: 'Natural language detection for text files',                         local: true,  platform: true,  saas: true },
    { key: 'code_summarization',  label: 'Code summarization',   desc: 'AI-generated summary of what a code file does (LLM required)',     local: false, platform: true,  saas: true },
    { key: 'image_ocr',           label: 'Image OCR',            desc: 'Extract text from screenshots, photos, documents (vision model)',   local: false, platform: true,  saas: true },
  ]

  return (
    <div className="pol-section-grid">

      <div className="pol-card pol-card-wide">
        <div className="pol-card-header">
          <h3>Enrichment Mode</h3>
          <p>Where AI enrichment processing happens. This affects what data leaves the agent host.</p>
        </div>

        <div className="pol-mode-grid">
          {modes.map(m => (
            <button
              key={m.id}
              className={`pol-mode-card ${mode === m.id ? 'selected' : ''}`}
              style={{ '--mc': m.color } as any}
              onClick={() => setMode(m.id as any)}
            >
              <div className="pol-mode-icon">
                <m.icon size={20} />
              </div>
              <div className="pol-mode-label">{m.label}</div>
              <div className="pol-mode-desc">{m.desc}</div>
              {mode === m.id && <div className="pol-mode-check"><Check size={14} /></div>}
            </button>
          ))}
        </div>
      </div>

      {mode === 'agent_local' && (
        <div className="pol-card">
          <div className="pol-card-header">
            <h3>Local Model Config</h3>
            <p>Ollama model used for agent-side enrichment</p>
          </div>
          <div className="pol-fields">
            <FieldRow label="Ollama model" hint="Must be installed on each agent machine">
              <input className="pol-input" defaultValue="qwen2.5-coder:32b" placeholder="e.g. llama3.2, qwen2.5-coder:32b" />
            </FieldRow>
            <FieldRow label="Ollama endpoint" hint="Leave blank to use default localhost:11434">
              <input className="pol-input" placeholder="http://localhost:11434" />
            </FieldRow>
            <FieldRow label="Max file size to enrich" hint="Files larger than this skip AI enrichment">
              <div className="pol-input-suffix">
                <input type="number" className="pol-input" defaultValue={10} />
                <span>MB</span>
              </div>
            </FieldRow>
          </div>
          <div className="pol-info-banner">
            <Info size={14} />
            <span>The agent pulls the model from Ollama before the first enrichment run. Make sure Ollama is running on each agent host. See the <a href="#">agent setup guide</a>.</span>
          </div>
        </div>
      )}

      <div className="pol-card pol-card-wide">
        <div className="pol-card-header">
          <h3>Enrichment Features</h3>
          <p>Choose which enrichment features to enable. Features marked ✗ are not available for your selected mode.</p>
        </div>
        <div className="pol-feature-table">
          <div className="pol-feature-header">
            <span>Feature</span>
            <span>Enabled</span>
          </div>
          {features.map(f => {
            const available = mode === 'disabled' ? false :
                              mode === 'agent_local' ? f.local :
                              mode === 'platform' ? f.platform : f.saas
            return (
              <div key={f.key} className={`pol-feature-row ${!available ? 'unavailable' : ''}`}>
                <div className="pol-feature-info">
                  <span className="pol-feature-name">{f.label}</span>
                  <span className="pol-feature-desc">{f.desc}</span>
                  {!available && <span className="pol-feature-badge">Not available in {mode} mode</span>}
                </div>
                <Toggle defaultChecked={available && ['file_classification','secret_scanning','pii_detection','language_detection'].includes(f.key)} disabled={!available} />
              </div>
            )
          })}
        </div>
        <div className="pol-card-footer">
          <button className="btn btn-primary btn-sm"><Save size={13} /> Save enrichment policy</button>
        </div>
      </div>

    </div>
  )
}

// ── Data streaming tab ────────────────────────────────────────────────────────

function StreamingTab() {
  const [enabled, setEnabled] = useState(false)

  return (
    <div className="pol-section-grid">

      <div className="pol-card pol-card-wide">
        <div className="pol-card-header">
          <h3>Data Streaming</h3>
          <p>Pull actual file content from remote agent machines through the platform. Requires agent v0.2+ with streaming support.</p>
        </div>

        <div className="pol-warn-banner">
          <AlertTriangle size={14} />
          <div>
            <strong>Security consideration</strong>
            <p>Enabling data streaming allows file content to be pulled from agent machines through the platform. All access is authenticated, logged, and rate-limited. Consider your compliance requirements before enabling.</p>
          </div>
        </div>

        <div className="pol-fields">
          <FieldRow label="Enable data streaming" hint="Allow platform users to preview and download files from agents">
            <Toggle checked={enabled} onChange={setEnabled} />
          </FieldRow>
        </div>

        {enabled && (
          <>
            <div className="pol-fields">
              <FieldRow label="Require authentication" hint="Users must have a valid session to stream files">
                <Toggle defaultChecked={true} />
              </FieldRow>
              <FieldRow label="Max file size" hint="Files larger than this cannot be streamed">
                <div className="pol-input-suffix">
                  <input type="number" className="pol-input" defaultValue={100} />
                  <span>MB</span>
                </div>
              </FieldRow>
              <FieldRow label="Rate limit" hint="Maximum streaming requests per user per minute">
                <div className="pol-input-suffix">
                  <input type="number" className="pol-input" defaultValue={60} />
                  <span>req/min</span>
                </div>
              </FieldRow>
              <FieldRow label="Log all access" hint="Write an audit log entry for every file streamed">
                <Toggle defaultChecked={true} />
              </FieldRow>
              <FieldRow label="Allowed file types" hint="Leave blank to allow all types. Comma-separated extensions.">
                <input className="pol-input" placeholder=".pdf, .txt, .md, .json, .py (leave blank for all)" />
              </FieldRow>
              <FieldRow label="Blocked file types" hint="Always blocked, even if allowed types is blank">
                <input className="pol-input" defaultValue=".exe, .dll, .so, .dylib, .key, .pem, .p12" />
              </FieldRow>
            </div>

            <div className="pol-info-banner">
              <Info size={14} />
              <span>The streaming API endpoint is <code>GET /api/stream/file?agent_id=&path=</code>. SDK support available in Python and TypeScript SDKs.</span>
            </div>
          </>
        )}

        <div className="pol-card-footer">
          <button className="btn btn-primary btn-sm"><Save size={13} /> Save streaming policy</button>
        </div>
      </div>

      <div className="pol-card">
        <div className="pol-card-header">
          <h3>Feature Roadmap</h3>
          <p>Upcoming streaming capabilities</p>
        </div>
        <div className="pol-roadmap-list">
          {[
            { label: 'File preview in browser', status: 'planned' },
            { label: 'ZIP/archive browsing', status: 'planned' },
            { label: 'Real-time file tail', status: 'planned' },
            { label: 'Bulk export (ZIP)', status: 'planned' },
            { label: 'Selective sync to local', status: 'planned' },
          ].map(r => (
            <div key={r.label} className="pol-roadmap-row">
              <span>{r.label}</span>
              <span className={`pol-roadmap-badge ${r.status}`}>{r.status}</span>
            </div>
          ))}
        </div>
      </div>

    </div>
  )
}

// ── Data modification tab ─────────────────────────────────────────────────────

function ModificationTab() {
  return (
    <div className="pol-section-grid">

      <div className="pol-card pol-card-wide">
        <div className="pol-card-header">
          <h3>Data Modification Policy</h3>
          <p>Control what operations the platform can perform on files through the agent. All operations are audited.</p>
        </div>

        <div className="pol-warn-banner">
          <AlertTriangle size={14} />
          <div>
            <strong>Write operations are disabled by default</strong>
            <p>Enabling write, delete, or rename operations allows the platform to modify files on agent machines. This is irreversible for delete operations. Enable only if required.</p>
          </div>
        </div>

        <div className="pol-permission-grid">
          {[
            { key: 'read',    label: 'Read',    desc: 'Read file metadata and content', icon: Eye,       default: true,  safe: true  },
            { key: 'write',   label: 'Write',   desc: 'Create or overwrite files',      icon: Edit3,     default: false, safe: false },
            { key: 'delete',  label: 'Delete',  desc: 'Permanently delete files',       icon: Trash2,    default: false, safe: false },
            { key: 'rename',  label: 'Rename',  desc: 'Rename or move files',           icon: RefreshCw, default: false, safe: false },
          ].map(p => (
            <div key={p.key} className={`pol-permission-card ${!p.safe ? 'destructive' : ''}`}>
              <div className="pol-perm-icon">
                <p.icon size={18} />
              </div>
              <div className="pol-perm-info">
                <span className="pol-perm-name">{p.label}</span>
                <span className="pol-perm-desc">{p.desc}</span>
              </div>
              <Toggle defaultChecked={p.default} />
            </div>
          ))}
        </div>

        <div className="pol-fields" style={{ marginTop: 24 }}>
          <FieldRow label="Require approval for writes" hint="Write/delete/rename operations require a second admin to approve">
            <Toggle defaultChecked={true} />
          </FieldRow>
          <FieldRow label="Audit all write operations" hint="Write a detailed audit log entry for every file modification">
            <Toggle defaultChecked={true} />
          </FieldRow>
        </div>

        <div className="pol-card-footer">
          <button className="btn btn-primary btn-sm"><Save size={13} /> Save modification policy</button>
        </div>
      </div>

    </div>
  )
}

// ── Access control tab ────────────────────────────────────────────────────────

function AccessTab() {
  return (
    <div className="pol-section-grid">

      <div className="pol-card pol-card-wide">
        <div className="pol-card-header">
          <h3>Agent Service Accounts</h3>
          <p>Configure the OS service account the agent runs under. Using a dedicated service account means file access policies are enforced at the host OS level — the agent can only access files the service account has permission to read.</p>
        </div>

        <div className="pol-platform-tabs">
          <PlatformSection
            platform="Windows"
            icon="⊞"
            fields={[
              { label: 'Service account', key: 'win_account', default: 'NT AUTHORITY\\NetworkService', hint: 'The Windows account the agent service runs as. Recommended: a dedicated domain service account with read-only access to target shares.' },
              { label: 'Install as Windows Service', key: 'win_service', type: 'bool', default: true, hint: 'Register dgraph-agent as a Windows Service (auto-start on login, runs in background)' },
              { label: 'Use SYSTEM account', key: 'win_system', type: 'bool', default: false, hint: 'Run as SYSTEM (full access). Not recommended — use a restricted service account instead.' },
            ]}
            note="Run the installer as Administrator: .\\install-windows.ps1 -ApiKey dga_xxx -ServiceAccount 'DOMAIN\\dgraph-svc'"
          />
          <PlatformSection
            platform="Linux"
            icon="🐧"
            fields={[
              { label: 'Service account', key: 'linux_account', default: 'dgraph-agent', hint: 'Linux user account the agent runs as. The installer creates this user automatically.' },
              { label: 'Install as systemd service', key: 'linux_systemd', type: 'bool', default: true, hint: 'Register as a systemd service (auto-start, restart on failure)' },
              { label: 'Drop capabilities after startup', key: 'linux_caps', type: 'bool', default: true, hint: 'Drop all Linux capabilities after initialization. Agent runs with minimal privileges.' },
            ]}
            note="Install: curl -L https://api.dgraph.ai/install.sh | sudo DGRAPH_AGENT_API_KEY=dga_xxx bash"
          />
          <PlatformSection
            platform="macOS"
            icon=""
            fields={[
              { label: 'Service account', key: 'mac_account', default: '_dgraph-agent', hint: 'macOS service account (prefixed with _ by convention). The installer creates a system user.' },
              { label: 'Install as LaunchDaemon', key: 'mac_daemon', type: 'bool', default: true, hint: 'Register as a launchd daemon (auto-start, runs as root for file access, then drops to service account)' },
              { label: 'Full Disk Access', key: 'mac_fda', type: 'bool', default: false, hint: 'Grant Full Disk Access via MDM profile. Required to scan protected directories (Desktop, Documents, Downloads, iCloud).' },
            ]}
            note="macOS: sudo ./install-macos.sh --api-key dga_xxx. Requires Full Disk Access for complete scanning."
          />
        </div>

        <div className="pol-fields" style={{ marginTop: 24 }}>
          <FieldRow label="Enforce host-level permissions" hint="Agent only accesses files the service account can read. Ensures OS ACLs are respected.">
            <Toggle defaultChecked={true} />
          </FieldRow>
          <FieldRow label="Drop elevated privileges after startup" hint="Agent drops to service account after connecting to platform. Reduces attack surface.">
            <Toggle defaultChecked={true} />
          </FieldRow>
        </div>

        <div className="pol-card-footer">
          <button className="btn btn-primary btn-sm"><Save size={13} /> Save access policy</button>
        </div>
      </div>

    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────────

function PlatformSection({ platform, icon, fields, note }: any) {
  const [open, setOpen] = useState(platform === 'Windows')
  return (
    <div className="pol-platform-section">
      <button className="pol-platform-header" onClick={() => setOpen(!open)}>
        <span className="pol-platform-icon">{icon}</span>
        <span className="pol-platform-name">{platform}</span>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
      </button>
      {open && (
        <div className="pol-platform-body">
          {fields.map((f: any) => (
            <FieldRow key={f.key} label={f.label} hint={f.hint}>
              {f.type === 'bool'
                ? <Toggle defaultChecked={f.default} />
                : <input className="pol-input" defaultValue={f.default} />
              }
            </FieldRow>
          ))}
          {note && (
            <div className="pol-platform-note">
              <code>{note}</code>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function FieldRow({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="pol-field-row">
      <div className="pol-field-label">
        <span>{label}</span>
        {hint && <span className="pol-field-hint">{hint}</span>}
      </div>
      <div className="pol-field-control">{children}</div>
    </div>
  )
}

function Toggle({ defaultChecked, checked, onChange, disabled }: any) {
  const [on, setOn] = useState(defaultChecked ?? false)
  const isControlled = checked !== undefined
  const value = isControlled ? checked : on
  return (
    <button
      className={`pol-toggle ${value ? 'on' : ''} ${disabled ? 'disabled' : ''}`}
      onClick={() => { if (disabled) return; isControlled ? onChange?.(!value) : setOn(!on) }}
      role="switch"
      aria-checked={value}
      disabled={disabled}
    >
      <span className="pol-toggle-thumb" />
    </button>
  )
}
