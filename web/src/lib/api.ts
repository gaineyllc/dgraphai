/**
 * fsgraph API client.
 * Typed wrappers around every backend endpoint.
 */

const BASE = '/api'

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const token = localStorage.getItem('dgraphai_token') || ''
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (res.status === 401) {
    localStorage.removeItem('dgraphai_token')
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? res.statusText)
  }
  return res.json()
}

const get  = <T>(path: string)             => request<T>('GET',    path)
const post = <T>(path: string, body: unknown) => request<T>('POST',   path, body)
const del  = <T>(path: string)             => request<T>('DELETE', path)

// ── Types ──────────────────────────────────────────────────────────────────────

export interface GraphStats {
  File: number
  Directory: number
  Person: number
  FaceCluster: number
  Location: number
  Organization: number
  Topic: number
  Application: number
  Vendor: number
  Vulnerability: number
  Certificate: number
  relationships: number
}

export interface GraphNode {
  id: string
  label: string
  name: string
  props?: Record<string, unknown>
}

export interface GraphEdge {
  id: string | number
  source: string
  target: string
  type: string
}

export interface Subgraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface SearchResult {
  id: string
  label: string
  name: string
  summary?: string
  category?: string
  size_bytes?: number
}

export interface Mount {
  id: string
  name: string
  uri: string
  protocol: string
  host: string
  auto_index: boolean
  created_at: string
  last_indexed: string | null
  index_status: string
  file_count: number
  reachable: boolean
}

export interface IndexJob {
  id: string
  mount_id: string
  mount_name: string
  source: string
  status: 'running' | 'complete' | 'error'
  files_scanned: number
  files_indexed: number
  files_skipped: number
  errors: number
  current_file: string
  dry_run: boolean
  started_at: number
  duration_secs?: number
}

export interface AuditEntry {
  id: string
  type: 'move' | 'delete' | 'rename'
  timestamp: string
  status: string
  dry_run: boolean
  source?: string
  destination?: string
  path?: string
}

// ── Graph API ─────────────────────────────────────────────────────────────────

export const graphApi = {
  stats: () =>
    get<GraphStats>('/graph/stats'),

  query: (cypher: string, params: Record<string, unknown> = {}) =>
    post<Record<string, unknown>[]>('/graph/query', { cypher, params }),

  getNode: (id: string) =>
    get<GraphNode>(`/graph/node/${encodeURIComponent(id)}`),

  getNeighbors: (id: string, depth = 1, limit = 100) =>
    get<Subgraph>(`/graph/node/${encodeURIComponent(id)}/neighbors?depth=${depth}&limit=${limit}`),

  search: (term?: string, node_type?: string, filters: Record<string, unknown> = {}, limit = 50) =>
    post<SearchResult[]>('/graph/search', { term, node_type, filters, limit }),
}

// ── Mounts API ────────────────────────────────────────────────────────────────

export const mountsApi = {
  list: () =>
    get<Mount[]>('/mounts'),

  add: (name: string, uri: string, auto_index = true) =>
    post<Mount>('/mounts', { name, uri, auto_index }),

  remove: (id: string) =>
    del<{ status: string }>(`/mounts/${id}`),

  get: (id: string) =>
    get<Mount>(`/mounts/${id}`),
}

// ── Indexer API ───────────────────────────────────────────────────────────────

export const indexerApi = {
  listJobs: () =>
    get<IndexJob[]>('/indexer/jobs'),

  getJob: (id: string) =>
    get<IndexJob>(`/indexer/jobs/${id}`),

  start: (mount_id: string, options: {
    enrich_llm?: boolean
    enrich_vision?: boolean
    enrich_faces?: boolean
    dry_run?: boolean
  } = {}) =>
    post<{ job_id: string; status: string }>('/indexer/start', {
      mount_id,
      enrich_llm:    options.enrich_llm    ?? true,
      enrich_vision: options.enrich_vision ?? true,
      enrich_faces:  options.enrich_faces  ?? true,
      dry_run:       options.dry_run       ?? false,
    }),
}

// ── Actions API ───────────────────────────────────────────────────────────────

export const actionsApi = {
  auditLog: (limit = 100) =>
    get<AuditEntry[]>(`/actions/audit?limit=${limit}`),

  move: (source: string, destination: string, dry_run = true) =>
    post<AuditEntry>('/actions/move', { source, destination, dry_run }),

  delete: (path: string, dry_run = true) =>
    post<AuditEntry>('/actions/delete', { path, dry_run }),

  rename: (path: string, new_name: string, dry_run = true) =>
    post<AuditEntry>('/actions/rename', { path, new_name, dry_run }),
}

// ── WebSocket helper ──────────────────────────────────────────────────────────

export function connectIndexerWs(
  jobId: string,
  onMessage: (event: string, data: unknown) => void,
): WebSocket {
  const ws = new WebSocket(`ws://${window.location.host}/api/indexer/ws/${jobId}`)
  ws.onmessage = (e) => {
    const { event, data } = JSON.parse(e.data)
    onMessage(event, data)
  }
  return ws
}
