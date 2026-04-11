// @ts-nocheck
/**
 * AgentsPage — agent fleet management and health monitoring.
 *
 * Shows:
 *   - All registered agents with online/offline status
 *   - Fleet groups with latency mesh visualization
 *   - Per-agent telemetry (files indexed, version, OS, last seen)
 *   - Create/edit fleets, assign connectors to fleets
 *   - Fleet mesh: SVG latency graph between agents
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Server, Wifi, WifiOff, Plus, Trash2, Network,
  Activity, Clock, HardDrive, Cpu, RefreshCw,
  ChevronRight, Shield, Zap, AlertTriangle,
} from 'lucide-react'
import { apiFetch } from '../lib/apiFetch'
import { PageHeader, Skeleton, EmptyState } from '../components/PageShell'
import { useNavigate } from 'react-router-dom'
import './AgentsPage.css'

// ── Data fetching ─────────────────────────────────────────────────────────────

const fetchAgents  = () => apiFetch('/api/agents').then(r => r.json())
const fetchFleets  = () => apiFetch('/api/fleets').then(r => r.json())

function timeAgo(iso: string | null): string {
  if (!iso) return 'never'
  const ms = Date.now() - new Date(iso).getTime()
  if (ms < 60_000) return `${Math.floor(ms / 1000)}s ago`
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m ago`
  return `${Math.floor(ms / 3_600_000)}h ago`
}

function fmtFiles(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(0) + 'K'
  return String(n)
}

// ── Agent card ────────────────────────────────────────────────────────────────

function AgentCard({ agent, onRevoke }: { agent: any; onRevoke: (id: string) => void }) {
  const online = agent.is_online
  const connStatuses: Record<string, string> = agent.connector_statuses ?? {}

  return (
    <div className={`agent-card ${online ? 'online' : 'offline'}`}>
      <div className="agent-card-header">
        <div className="agent-status-dot" />
        <div className="agent-info">
          <div className="agent-name">{agent.name}</div>
          <div className="agent-meta">
            {agent.hostname && <span>{agent.hostname}</span>}
            {agent.os && <span className="agent-os">{agent.os}</span>}
            {agent.version && <span className="agent-version">v{agent.version}</span>}
          </div>
        </div>
        <div className={`agent-online-badge ${online ? 'on' : 'off'}`}>
          {online ? <><Wifi size={11} /> Online</> : <><WifiOff size={11} /> Offline</>}
        </div>
      </div>

      <div className="agent-stats">
        <div className="agent-stat">
          <HardDrive size={12} />
          <span>{fmtFiles(agent.files_indexed)} files</span>
        </div>
        <div className="agent-stat">
          <Clock size={12} />
          <span>{timeAgo(agent.last_seen_at)}</span>
        </div>
      </div>

      {Object.entries(connStatuses).length > 0 && (
        <div className="agent-connectors">
          {Object.entries(connStatuses).map(([id, status]) => (
            <span key={id} className={`agent-conn-badge ${status}`}>
              {status}
            </span>
          ))}
        </div>
      )}

      <div className="agent-actions">
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => onRevoke(agent.id)}
          title="Revoke this agent's API key"
        >
          <Trash2 size={12} /> Revoke
        </button>
      </div>
    </div>
  )
}

// ── Fleet mesh SVG ────────────────────────────────────────────────────────────

function FleetMesh({ mesh, agents }: { mesh: any; agents: any[] }) {
  if (!mesh?.edges?.length) {
    return (
      <div className="fleet-mesh-empty">
        <Activity size={20} />
        <span>No mesh data yet — agents haven't probed each other</span>
      </div>
    )
  }

  const agentMap = Object.fromEntries(agents.map(a => [a.agent_id, a]))
  const n = agents.length
  const cx = 120, cy = 120, r = 80

  // Place agents in a circle
  const positions: Record<string, { x: number; y: number }> = {}
  agents.forEach((a, i) => {
    const angle = (i / n) * 2 * Math.PI - Math.PI / 2
    positions[a.agent_id] = {
      x: cx + r * Math.cos(angle),
      y: cy + r * Math.sin(angle),
    }
  })

  const QUALITY_COLORS: Record<string, string> = {
    excellent: '#34d399',
    good:      '#60a5fa',
    fair:      '#f59e0b',
    poor:      '#f04545',
  }

  return (
    <svg className="fleet-mesh-svg" viewBox="0 0 240 240">
      {/* Edges */}
      {mesh.edges.map((edge: any, i: number) => {
        const from = positions[edge.from]
        const to   = positions[edge.to]
        if (!from || !to) return null
        const color = QUALITY_COLORS[edge.quality] ?? '#6b7280'
        const mid = { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 }
        return (
          <g key={i}>
            <line
              x1={from.x} y1={from.y} x2={to.x} y2={to.y}
              stroke={color} strokeWidth="1.5" strokeOpacity="0.6"
            />
            <text x={mid.x} y={mid.y} textAnchor="middle"
              fontSize="7" fill={color} dy="-3">
              {edge.latency_ms.toFixed(1)}ms
            </text>
          </g>
        )
      })}
      {/* Nodes */}
      {agents.map(a => {
        const pos = positions[a.agent_id]
        if (!pos) return null
        return (
          <g key={a.agent_id}>
            <circle
              cx={pos.x} cy={pos.y} r="12"
              fill={a.is_online ? 'var(--color-primary-container)' : 'var(--surface-3)'}
              stroke={a.is_online ? 'var(--color-primary)' : 'var(--border-default)'}
              strokeWidth="1.5"
            />
            <text x={pos.x} y={pos.y + 4} textAnchor="middle"
              fontSize="7" fill="var(--text-primary)" fontWeight="bold">
              {a.name.slice(0, 3).toUpperCase()}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

// ── Fleet card ────────────────────────────────────────────────────────────────

function FleetCard({ fleet, agents }: { fleet: any; agents: any[] }) {
  const [showMesh, setShowMesh] = useState(false)
  const { data: fleetDetail } = useQuery({
    queryKey: ['fleet', fleet.id],
    queryFn: () => apiFetch(`/api/fleets/${fleet.id}`).then(r => r.json()),
    enabled: showMesh,
  })

  const { data: mesh } = useQuery({
    queryKey: ['fleet-mesh', fleet.id],
    queryFn: () => apiFetch(`/api/fleets/${fleet.id}/mesh`).then(r => r.json()),
    enabled: showMesh,
    refetchInterval: 30_000,
  })

  const fleetAgents = (fleetDetail?.members ?? []) as any[]
  const online = fleetAgents.filter(a => a.is_online).length
  const status = fleetDetail?.status ?? 'unknown'

  return (
    <div className={`fleet-card status-${status}`}>
      <div className="fleet-header">
        <div className="fleet-status-indicator" />
        <div className="fleet-info">
          <div className="fleet-name">{fleet.name}</div>
          <div className="fleet-meta">
            {fleet.agent_ids?.length ?? 0} agents · {online}/{fleet.agent_ids?.length ?? 0} online
          </div>
        </div>
        <div className={`fleet-status-badge ${status}`}>{status}</div>
      </div>

      {fleet.description && (
        <div className="fleet-desc">{fleet.description}</div>
      )}

      <div className="fleet-strategy">
        <Zap size={11} />
        <span>Strategy: {fleet.scan_strategy?.replace('_', ' ')}</span>
      </div>

      <div className="fleet-agent-pills">
        {(fleet.agent_ids ?? []).map((id: string) => {
          const a = agents.find(ag => ag.id === id)
          return (
            <span key={id} className={`fleet-agent-pill ${a?.is_online ? 'online' : 'offline'}`}>
              {a?.name ?? id.slice(0, 8)}
            </span>
          )
        })}
      </div>

      <button
        className="fleet-mesh-toggle"
        onClick={() => setShowMesh(!showMesh)}
      >
        <Network size={13} />
        {showMesh ? 'Hide mesh' : 'View latency mesh'}
        <ChevronRight size={12} className={showMesh ? 'rotated' : ''} />
      </button>

      {showMesh && (
        <div className="fleet-mesh-panel">
          <FleetMesh mesh={mesh} agents={fleetAgents} />
        </div>
      )}
    </div>
  )
}

// ── Create fleet modal ────────────────────────────────────────────────────────

function CreateFleetModal({ agents, onClose, onCreated }: any) {
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [selectedAgents, setSelectedAgents] = useState<string[]>([])
  const [strategy, setStrategy] = useState('round_robin')
  const qc = useQueryClient()

  const create = useMutation({
    mutationFn: () => apiFetch('/api/fleets', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, description: desc, agent_ids: selectedAgents, scan_strategy: strategy }),
    }).then(r => r.json()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['fleets'] })
      onCreated()
      onClose()
    },
  })

  const toggle = (id: string) =>
    setSelectedAgents(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-card">
        <div className="modal-header">
          <h3>Create fleet</h3>
          <button className="modal-close" onClick={onClose}>✕</button>
        </div>
        <div className="modal-body">
          <div className="form-field">
            <label>Fleet name</label>
            <input className="pol-input" value={name} onChange={e => setName(e.target.value)} placeholder="NAS Fleet" />
          </div>
          <div className="form-field">
            <label>Description (optional)</label>
            <input className="pol-input" value={desc} onChange={e => setDesc(e.target.value)} placeholder="3 agents covering the Synology cluster" />
          </div>
          <div className="form-field">
            <label>Scan strategy</label>
            <select className="pol-select" value={strategy} onChange={e => setStrategy(e.target.value)}>
              <option value="round_robin">Round robin</option>
              <option value="capacity_weighted">Capacity weighted</option>
              <option value="latency_aware">Latency aware</option>
            </select>
          </div>
          <div className="form-field">
            <label>Members</label>
            <div className="agent-checklist">
              {agents.map((a: any) => (
                <label key={a.id} className="agent-check-row">
                  <input type="checkbox" checked={selectedAgents.includes(a.id)}
                    onChange={() => toggle(a.id)} />
                  <span>{a.name}</span>
                  <span className={`fleet-agent-pill ${a.is_online ? 'online' : 'offline'}`}>
                    {a.is_online ? 'online' : 'offline'}
                  </span>
                </label>
              ))}
              {agents.length === 0 && (
                <p style={{ fontSize: 12, color: 'var(--text-tertiary)', margin: 0 }}>
                  No agents registered yet. Install the agent first.
                </p>
              )}
            </div>
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn btn-secondary btn-sm" onClick={onClose}>Cancel</button>
          <button
            className="btn btn-primary btn-sm"
            disabled={!name || selectedAgents.length < 2 || create.isPending}
            onClick={() => create.mutate()}
          >
            {create.isPending ? 'Creating…' : 'Create fleet'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function AgentsPage() {
  const [showCreate, setShowCreate] = useState(false)
  const qc = useQueryClient()

  const { data: agents = [],  isLoading: agentsLoading  } = useQuery({ queryKey: ['agents'],  queryFn: fetchAgents,  refetchInterval: 15_000 })
  const { data: fleets = [],  isLoading: fleetsLoading  } = useQuery({ queryKey: ['fleets'],  queryFn: fetchFleets  })

  const revoke = useMutation({
    mutationFn: (id: string) => apiFetch(`/api/agents/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['agents'] }),
  })

  const onlineCount = agents.filter((a: any) => a.is_online).length

  return (
    <div className="agents-page">
      <PageHeader
        title="Agents & Fleets"
        subtitle="Deploy agents, manage fleets, monitor health"
        actions={
          <button className="btn btn-primary btn-sm" onClick={() => setShowCreate(true)}>
            <Plus size={14} /> New fleet
          </button>
        }
      />

      {/* Summary banner */}
      <div className="agents-summary">
        <div className="agents-summary-stat">
          <Server size={16} />
          <strong>{agents.length}</strong>
          <span>total agents</span>
        </div>
        <div className="agents-summary-stat">
          <Wifi size={16} />
          <strong className={onlineCount > 0 ? 'text-green' : ''}>{onlineCount}</strong>
          <span>online</span>
        </div>
        <div className="agents-summary-stat">
          <Network size={16} />
          <strong>{fleets.length}</strong>
          <span>fleets</span>
        </div>
        <div className="agents-summary-stat">
          <HardDrive size={16} />
          <strong>{(agents as any[]).reduce((s, a) => s + (a.files_indexed || 0), 0).toLocaleString()}</strong>
          <span>files indexed</span>
        </div>
      </div>

      <div className="agents-layout">
        {/* Agents column */}
        <div className="agents-col">
          <div className="agents-col-header">
            <h2>Agents <span className="count-badge">{agents.length}</span></h2>
            <button className="btn btn-ghost btn-sm" onClick={() => qc.invalidateQueries({ queryKey: ['agents'] })}>
              <RefreshCw size={12} />
            </button>
          </div>
          {agentsLoading ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {[1,2].map(i => <Skeleton key={i} height={120} />)}
            </div>
          ) : agents.length === 0 ? (
            <EmptyState
              icon={<Server size={28} />}
              title="No agents yet"
              desc="Install the scanner agent to start indexing your data sources"
              action={{ label: 'View install guide', onClick: () => window.location.href = '/connectors' }}
            />
          ) : (
            <div className="agents-list">
              {(agents as any[]).map(a => (
                <AgentCard key={a.id} agent={a} onRevoke={id => revoke.mutate(id)} />
              ))}
            </div>
          )}
        </div>

        {/* Fleets column */}
        <div className="agents-col">
          <div className="agents-col-header">
            <h2>Fleets <span className="count-badge">{fleets.length}</span></h2>
          </div>
          {fleetsLoading ? (
            <Skeleton height={120} />
          ) : fleets.length === 0 ? (
            <EmptyState
              icon={<Network size={28} />}
              title="No fleets yet"
              desc="Group agents into fleets for load-balanced scanning of large NFS/SMB shares"
              action={{ label: 'Create fleet', onClick: () => setShowCreate(true) }}
            />
          ) : (
            <div className="fleets-list">
              {(fleets as any[]).map(f => (
                <FleetCard key={f.id} fleet={f} agents={agents as any[]} />
              ))}
            </div>
          )}

          {/* Fleet feature info */}
          <div className="fleet-info-card">
            <Shield size={14} />
            <div>
              <strong>Fleet scanning</strong>
              <p>Add 2+ agents to a fleet to enable load-balanced scanning. The platform assigns connectors to agents based on your chosen strategy: round-robin, capacity-weighted, or latency-aware (uses mesh probe results).</p>
            </div>
          </div>
        </div>
      </div>

      {showCreate && (
        <CreateFleetModal
          agents={agents}
          onClose={() => setShowCreate(false)}
          onCreated={() => {}}
        />
      )}
    </div>
  )
}
