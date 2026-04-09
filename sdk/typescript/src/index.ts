/**
 * dgraph.ai TypeScript/JavaScript SDK
 * Official client library for the dgraph.ai API.
 *
 * Install: npm install @dgraphai/sdk
 *
 * Usage:
 *   import { DGraphAI } from '@dgraphai/sdk'
 *
 *   const client = new DGraphAI({ apiKey: 'dg_...', tenantId: '...' })
 *
 *   const results = await client.graph.query('MATCH (f:File) WHERE f.pii_detected = true RETURN f')
 *   const categories = await client.inventory.list()
 *   const search = await client.search('4K videos with HDR')
 */

export interface DGraphAIConfig {
  apiKey:    string
  tenantId:  string
  baseUrl?:  string   // default: https://api.dgraph.ai
  timeout?:  number   // ms, default: 30000
}

export interface GraphQueryResult { rows: Record<string, unknown>[] }
export interface InventoryCategory {
  id: string; name: string; description: string; icon: string; color: string
  count: number | null; has_children: boolean; parent_id: string | null
}
export interface SearchResult {
  id: string; node_type: string; name: string
  path?: string; summary?: string; highlight?: string; score?: number
}
export interface UsageSnapshot {
  snapshot: { total_nodes: number; standard_nodes: number; enrichable_nodes: number; ai_enriched_nodes: number }
  cost: { total: number; line_items: Array<{label: string; amount: number; tier: string}> }
  plan: { id: string; name: string }
}
export interface AttackPath {
  found: boolean
  paths: Array<{ nodes: unknown[]; edges: unknown[]; hops: number; risk_score: number; risk_label: string }>
  summary?: string
}
export interface ExposureScore {
  node_id: string; name: string; score: number; label: string
  factors: Array<{factor: string; weight: number; severity: string}>
}

class BaseClient {
  protected headers: Record<string, string>
  protected baseUrl: string
  protected timeout: number

  constructor(config: Required<DGraphAIConfig>) {
    this.baseUrl = config.baseUrl
    this.timeout = config.timeout
    this.headers = {
      'Authorization': `Bearer ${config.apiKey}`,
      'X-Tenant-ID':   config.tenantId,
      'Content-Type':  'application/json',
      'User-Agent':    'dgraphai-ts/0.1.0',
    }
  }

  protected async get<T>(path: string, params?: Record<string, string | number>): Promise<T> {
    const url = new URL(this.baseUrl + path)
    if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, String(v)))
    const resp = await fetch(url.toString(), { headers: this.headers,
      signal: AbortSignal.timeout(this.timeout) })
    if (!resp.ok) throw new Error(`GET ${path}: HTTP ${resp.status} ${await resp.text()}`)
    return resp.json()
  }

  protected async post<T>(path: string, body?: unknown, params?: Record<string, string | number>): Promise<T> {
    const url = new URL(this.baseUrl + path)
    if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, String(v)))
    const resp = await fetch(url.toString(), {
      method: 'POST', headers: this.headers,
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(this.timeout),
    })
    if (!resp.ok) throw new Error(`POST ${path}: HTTP ${resp.status} ${await resp.text()}`)
    return resp.json()
  }
}

class GraphClient extends BaseClient {
  async query(cypher: string, params?: Record<string, unknown>, limit = 100): Promise<Record<string, unknown>[]> {
    const r = await this.post<GraphQueryResult>('/api/graph/query', { cypher, params: params ?? {}, limit })
    return r.rows
  }
  async attackPath(fromId: string, toId: string, maxHops = 6): Promise<AttackPath> {
    return this.get('/api/graph/intel/attack-path', { from_id: fromId, to_id: toId, max_hops: maxHops })
  }
  async neighborhood(nodeId: string, hops = 1): Promise<unknown> {
    return this.get('/api/graph/intel/neighborhood', { node_id: nodeId, hops })
  }
  async exposureScore(nodeId: string): Promise<ExposureScore> {
    return this.get(`/api/graph/intel/exposure-score/${nodeId}`)
  }
  async diff(sinceHours = 24): Promise<unknown> {
    return this.get('/api/graph/intel/diff', { since_hours: sinceHours })
  }
}

class InventoryClient extends BaseClient {
  async list(): Promise<{ groups: Record<string, InventoryCategory[]>; total_categories: number }> {
    return this.get('/api/inventory')
  }
  async category(categoryId: string, page = 0, pageSize = 25): Promise<unknown> {
    return this.get(`/api/inventory/${categoryId}`, { page, page_size: pageSize })
  }
  async search(query: string): Promise<unknown> {
    return this.get('/api/inventory/search', { q: query })
  }
  async filteredNodes(categoryId: string, filters: Array<{field: string; op: string; value?: string}>, page = 0): Promise<unknown> {
    return this.post(`/api/inventory/${categoryId}/filtered`, { filters }, { page })
  }
}

class ConnectorsClient extends BaseClient {
  async list(): Promise<unknown[]> { return this.get('/api/connectors') }
  async create(name: string, type: string, config: Record<string, string>, routingMode = 'auto'): Promise<unknown> {
    return this.post('/api/connectors', { name, connector_type: type, config, routing_mode: routingMode })
  }
  async test(connectorId: string): Promise<unknown> {
    return this.post(`/api/connectors/${connectorId}/test`)
  }
}

class UsageClient extends BaseClient {
  async snapshot(): Promise<UsageSnapshot> { return this.get('/api/usage/snapshot') }
  async limits(): Promise<unknown>          { return this.get('/api/usage/limits') }
  async plans(): Promise<unknown[]>         { return this.get('/api/usage/plans') }
}

export class DGraphAI {
  readonly graph:      GraphClient
  readonly inventory:  InventoryClient
  readonly connectors: ConnectorsClient
  readonly usage:      UsageClient
  private  _base:      BaseClient
  private  _cfg:       Required<DGraphAIConfig>

  constructor(config: DGraphAIConfig) {
    if (!config.apiKey)   throw new Error('apiKey is required')
    if (!config.tenantId) throw new Error('tenantId is required')

    this._cfg = {
      apiKey:   config.apiKey,
      tenantId: config.tenantId,
      baseUrl:  config.baseUrl  ?? 'https://api.dgraph.ai',
      timeout:  config.timeout  ?? 30_000,
    }

    this.graph      = new GraphClient(this._cfg)
    this.inventory  = new InventoryClient(this._cfg)
    this.connectors = new ConnectorsClient(this._cfg)
    this.usage      = new UsageClient(this._cfg)
    this._base      = new BaseClient(this._cfg)
  }

  async search(query: string, limit = 20): Promise<SearchResult[]> {
    const r = await this._base['get']<{results: SearchResult[]}>('/api/search', { q: query, limit })
    return r.results
  }

  async healthCheck(): Promise<{ status: string; version: string }> {
    return this._base['get']('/api/health')
  }
}

export default DGraphAI
