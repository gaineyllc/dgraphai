// @ts-nocheck
/**
 * IndexerDashboard — real-time indexing progress and source management.
 *
 * Shows:
 *   - All configured filesystem sources (mounts) with status
 *   - Active indexing jobs with live WebSocket progress
 *   - Graph stats per source
 *   - One-click scan trigger per source
 */
import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Activity, HardDrive, Plus, RefreshCw, CheckCircle,
  XCircle, Clock, AlertCircle, Wifi, WifiOff,
  FileText, Database, Zap, BarChart3
} from 'lucide-react'
import { mountsApi, indexerApi, type Mount, type IndexJob } from '../lib/api'
import './IndexerDashboard.css'

export function IndexerDashboard() {
  const qc    = useQueryClient()
  const [activeJobId, setActiveJobId] = useState(null)
  const [progress, setProgress]       = useState({})
  const wsRef = useRef(null)

  const { data: mounts = [], isLoading: mountsLoading } = useQuery({
    queryKey: ['mounts'],
    queryFn:  mountsApi.list,
    refetchInterval: 15_000,
  })

  const { data: jobs = [] } = useQuery({
    queryKey: ['indexer-jobs'],
    queryFn:  indexerApi.listJobs,
    refetchInterval: 5_000,
  })

  const startIndex = useMutation({
    mutationFn: (mount_id) => indexerApi.start(mount_id, { enrich_llm: false, enrich_vision: false }),
    onSuccess: (data) => {
      setActiveJobId(data.job_id)
      qc.invalidateQueries({ queryKey: ['indexer-jobs'] })
      // Connect WebSocket for live progress
      connectWs(data.job_id)
    },
  })

  const connectWs = (jobId) => {
    if (wsRef.current) wsRef.current.close()
    const ws = new WebSocket(`ws://${window.location.host}/api/indexer/ws/${jobId}`)
    ws.onmessage = (e) => {
      const { event, data } = JSON.parse(e.data)
      if (event === 'progress' || event === 'state') {
        setProgress(prev => ({ ...prev, [jobId]: data }))
      }
      if (event === 'complete') {
        qc.invalidateQueries({ queryKey: ['indexer-jobs'] })
        qc.invalidateQueries({ queryKey: ['mounts'] })
      }
    }
    wsRef.current = ws
  }

  useEffect(() => () => wsRef.current?.close(), [])

  const activeJob = jobs.find(j => j.status === 'running') ?? null
  const liveProgress = activeJob ? (progress[activeJob.id] ?? activeJob) : null

  return (
    <div className="indexer-dashboard">

      {/* Header stats */}
      <div className="id-stats-row">
        <StatCard icon={HardDrive} label="Sources"    value={mounts.length}                   color="#4f8ef7" />
        <StatCard icon={CheckCircle} label="Online"   value={mounts.filter(m => m.reachable).length} color="#10b981" />
        <StatCard icon={Activity}   label="Running"   value={jobs.filter(j => j.status === 'running').length} color="#f59e0b" />
        <StatCard icon={Database}   label="Completed" value={jobs.filter(j => j.status === 'complete').length} color="#8b5cf6" />
      </div>

      {/* Active job progress */}
      {liveProgress && (
        <div className="id-active-job">
          <div className="id-aj-header">
            <div className="id-aj-spinner" />
            <div>
              <div className="id-aj-title">Indexing: {liveProgress.mount_name ?? liveProgress.source}</div>
              <div className="id-aj-sub">Job {liveProgress.id?.slice(0, 8)}…</div>
            </div>
            <div className="id-aj-stats">
              <span><FileText size={11} /> {(liveProgress.files_indexed ?? 0).toLocaleString()} files</span>
              {liveProgress.errors > 0 && <span className="id-aj-err"><AlertCircle size={11} /> {liveProgress.errors} errors</span>}
            </div>
          </div>
          {liveProgress.current_file && (
            <div className="id-aj-file">
              <span className="id-aj-file-label">Current:</span>
              <span className="id-aj-file-path">{truncatePath(liveProgress.current_file)}</span>
            </div>
          )}
          <div className="id-progress-bar">
            <div className="id-progress-fill" style={{ width: `${Math.min(100, (liveProgress.files_indexed ?? 0) / Math.max(liveProgress.files_scanned ?? 1, 1) * 100)}%` }} />
          </div>
        </div>
      )}

      {/* Source list */}
      <div className="id-section">
        <div className="id-section-header">
          <h2>Filesystem Sources</h2>
          <div className="id-section-actions">
            <button
              onClick={() => qc.invalidateQueries({ queryKey: ['mounts'] })}
              className="id-btn id-btn-ghost"
            >
              <RefreshCw size={12} /> Refresh
            </button>
          </div>
        </div>

        {mountsLoading ? (
          <div className="id-loading">Loading sources…</div>
        ) : mounts.length === 0 ? (
          <div className="id-empty">
            <HardDrive size={32} />
            <div>No sources configured</div>
            <div className="id-empty-sub">Add filesystem sources in the Mounts section</div>
          </div>
        ) : (
          <div className="id-mount-grid">
            {mounts.map(mount => (
              <MountCard
                key={mount.id}
                mount={mount}
                isRunning={activeJob?.mount_id === mount.id}
                onIndex={() => startIndex.mutate(mount.id)}
                progress={activeJob?.mount_id === mount.id ? liveProgress : null}
              />
            ))}
          </div>
        )}
      </div>

      {/* Job history */}
      {jobs.length > 0 && (
        <div className="id-section">
          <div className="id-section-header">
            <h2>Recent Jobs</h2>
          </div>
          <div className="id-job-list">
            {jobs.slice(0, 10).map(job => (
              <JobRow key={job.id} job={job} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function MountCard({ mount, isRunning, onIndex, progress }) {
  const statusColor = mount.reachable ? '#10b981' : '#f87171'
  const indexStatus = {
    never:    { color: '#35354a', label: 'Never indexed' },
    complete: { color: '#10b981', label: `${mount.file_count?.toLocaleString() ?? 0} files` },
    running:  { color: '#f59e0b', label: 'Indexing…' },
    error:    { color: '#f87171', label: 'Error' },
  }[mount.index_status] ?? { color: '#35354a', label: mount.index_status }

  return (
    <div className={`id-mount-card ${isRunning ? 'id-mount-running' : ''}`}>
      <div className="id-mc-header">
        <div className="id-mc-icon">
          {mount.reachable
            ? <Wifi size={16} style={{ color: statusColor }} />
            : <WifiOff size={16} style={{ color: statusColor }} />
          }
        </div>
        <div className="id-mc-info">
          <div className="id-mc-name">{mount.name}</div>
          <div className="id-mc-uri">{truncatePath(mount.uri, 36)}</div>
        </div>
        <span className="id-mc-protocol">{mount.protocol}</span>
      </div>

      <div className="id-mc-stats">
        <div className="id-mc-stat">
          <span className="id-mc-stat-label">Status</span>
          <span style={{ color: indexStatus.color }} className="id-mc-stat-value">{indexStatus.label}</span>
        </div>
        {mount.last_indexed && (
          <div className="id-mc-stat">
            <span className="id-mc-stat-label">Last scan</span>
            <span className="id-mc-stat-value">{new Date(mount.last_indexed).toLocaleDateString()}</span>
          </div>
        )}
      </div>

      {isRunning && progress && (
        <div className="id-mc-progress">
          <div className="id-mc-progress-bar">
            <div className="id-mc-progress-fill id-mc-progress-anim" />
          </div>
          <span>{(progress.files_indexed ?? 0).toLocaleString()} files indexed</span>
        </div>
      )}

      <button
        onClick={onIndex}
        disabled={isRunning || !mount.reachable}
        className={`id-mc-scan-btn ${isRunning ? 'id-mc-scan-running' : ''}`}
      >
        {isRunning
          ? <><RefreshCw size={12} className="id-spin" /> Scanning…</>
          : <><Zap size={12} /> Scan now</>
        }
      </button>
    </div>
  )
}

function JobRow({ job }) {
  const statusConfig = {
    running:  { color: '#f59e0b', icon: RefreshCw, spin: true  },
    complete: { color: '#10b981', icon: CheckCircle, spin: false },
    error:    { color: '#f87171', icon: XCircle, spin: false   },
    pending:  { color: '#55557a', icon: Clock, spin: false     },
  }[job.status] ?? { color: '#55557a', icon: Clock, spin: false }

  const Icon = statusConfig.icon

  return (
    <div className="id-job-row">
      <Icon size={14} style={{ color: statusConfig.color, flexShrink: 0 }}
           className={statusConfig.spin ? 'id-spin' : ''} />
      <div className="id-job-source">{job.mount_name ?? job.source}</div>
      <div className="id-job-files">
        {job.files_indexed?.toLocaleString() ?? 0} files
        {job.errors > 0 && <span className="id-job-errors"> · {job.errors} errors</span>}
      </div>
      <div className="id-job-time">
        {job.started_at ? new Date(job.started_at * 1000).toLocaleTimeString() : ''}
      </div>
      {job.duration_secs && (
        <div className="id-job-duration">{job.duration_secs.toFixed(1)}s</div>
      )}
    </div>
  )
}

function StatCard({ icon: Icon, label, value, color }) {
  return (
    <div className="id-stat-card">
      <div className="id-sc-icon" style={{ background: `${color}15`, color }}>
        <Icon size={18} />
      </div>
      <div>
        <div className="id-sc-value">{value}</div>
        <div className="id-sc-label">{label}</div>
      </div>
    </div>
  )
}

function truncatePath(path, n = 50) {
  if (!path || path.length <= n) return path
  return '…' + path.slice(-(n - 1))
}
