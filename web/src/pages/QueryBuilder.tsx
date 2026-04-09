// @ts-nocheck
/**
 * QueryBuilder — visual drag-and-drop query construction.
 *
 * Build Cypher queries by composing node types, filters, and relationships.
 * Every state change updates the URL (shareable/bookmarkable).
 * Live results update as you build — JSON, YAML, or Graph view.
 *
 * URL encoding: /builder?state=<base64-encoded-builder-state>
 */
import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence, Reorder } from 'framer-motion'
import CodeMirror from '@uiw/react-codemirror'
import { sql } from '@codemirror/lang-sql'
import { oneDark } from '@codemirror/theme-one-dark'
import yaml from 'js-yaml'
import {
  Plus, Play, Copy, Download, Trash2, GripVertical,
  ChevronDown, ChevronRight, Code2, Braces, List, Network,
  ArrowRight, Filter, RefreshCw, Link2, AlertTriangle, X
} from 'lucide-react'
import './QueryBuilder.css'

// ── Constants (static fallbacks — overridden by live schema API) ──────────────

const FALLBACK_NODE_TYPES = [
  { id: 'File',          label: 'File',          icon: '📄', color: '#4f8ef7' },
  { id: 'Directory',     label: 'Directory',     icon: '📁', color: '#fbbf24' },
  { id: 'Person',        label: 'Person',        icon: '👤', color: '#f472b6' },
  { id: 'FaceCluster',   label: 'Face Cluster',  icon: '👥', color: '#ec4899' },
  { id: 'Application',   label: 'Application',   icon: '🖥️', color: '#8b5cf6' },
  { id: 'Location',      label: 'Location',      icon: '📍', color: '#34d399' },
  { id: 'Organization',  label: 'Organization',  icon: '🏢', color: '#fb923c' },
  { id: 'Topic',         label: 'Topic',         icon: '🏷️', color: '#a3e635' },
  { id: 'Vulnerability', label: 'Vulnerability', icon: '🛡️', color: '#f87171' },
  { id: 'MediaItem',     label: 'Media Item',    icon: '🎞️', color: '#818cf8' },
  { id: 'Certificate',   label: 'Certificate',   icon: '🏅', color: '#4ade80' },
  { id: 'Dependency',    label: 'Dependency',    icon: '🧩', color: '#67e8f9' },
  { id: 'License',       label: 'License',       icon: '📜', color: '#6ee7b7' },
  { id: 'Vendor',        label: 'Vendor',        icon: '🏭', color: '#a78bfa' },
  { id: 'Collection',    label: 'Collection',    icon: '📚', color: '#f59e0b' },
  { id: 'Event',         label: 'Event',         icon: '🎉', color: '#fb923c' },
]

const FALLBACK_RELS = [
  'CHILD_OF','DUPLICATE_OF','SIMILAR_TO','PART_OF','REFERENCES',
  'MENTIONS','TAGGED_WITH','LOCATED_AT','OCCURRED_DURING',
  'DEPICTS','CONTAINS_FACE','MATCHED_TO',
  'IS_APPLICATION','IS_BINARY','MADE_BY','IS_VERSION_OF','DEPENDS_ON',
  'LICENSED_UNDER','HAS_VULNERABILITY','SIGNED_BY',
  'WITHIN','SAME_PERSON_AS',
]

const FILTER_OPS = [
  { op: '=',           label: '='           },
  { op: '<>',          label: '≠'           },
  { op: '>',           label: '>'           },
  { op: '<',           label: '<'           },
  { op: '>=',          label: '>='          },
  { op: '<=',          label: '<='          },
  { op: 'CONTAINS',    label: 'contains'    },
  { op: 'STARTS WITH', label: 'starts with' },
  { op: 'IS NULL',     label: 'is not set'  },
  { op: 'IS NOT NULL', label: 'is set'      },
]

// ── Types ─────────────────────────────────────────────────────────────────────

interface NodeClause {
  id:     string   // e.g. "n0"
  type:   string   // e.g. "File"
  alias:  string   // user editable alias
  filters: FilterClause[]
}

interface FilterClause {
  id:    string
  field: string
  op:    string
  value: string
}

interface RelationshipClause {
  id:       string
  from:     string  // alias
  to:       string  // alias
  type:     string
  directed: boolean
}

interface BuilderState {
  nodes:         NodeClause[]
  relationships: RelationshipClause[]
  returnAll:     boolean
  limit:         number
}

const DEFAULT_STATE: BuilderState = {
  nodes:         [],
  relationships: [],
  returnAll:     true,
  limit:         50,
}

// ── Cypher builder ────────────────────────────────────────────────────────────

function buildCypher(state: BuilderState): string {
  if (!state.nodes.length) return ''

  const matchClauses = state.nodes.map(n => {
    const alias = n.alias || n.id
    return `(${alias}:${n.type})`
  })

  const relClauses = state.relationships.map(r => {
    const arrow = r.directed ? `-[:${r.type}]->` : `-[:${r.type}]-`
    return `(${r.from})${arrow}(${r.to})`
  })

  const allMatch = [...matchClauses, ...relClauses]
  const matchLine = `MATCH ${allMatch.join(', ')}`

  const whereClauses: string[] = []
  // Always scope to tenant
  const firstAlias = state.nodes[0].alias || state.nodes[0].id
  whereClauses.push(`${firstAlias}.tenant_id = $tid`)

  for (const node of state.nodes) {
    const alias = node.alias || node.id
    for (const f of node.filters) {
      if (!f.field) continue
      if (f.op === 'IS NULL' || f.op === 'IS NOT NULL') {
        whereClauses.push(`${alias}.${f.field} ${f.op}`)
      } else if (f.op === 'CONTAINS' || f.op === 'STARTS WITH') {
        whereClauses.push(`${alias}.${f.field} ${f.op} '${f.value}'`)
      } else if (f.value === 'true' || f.value === 'false' || !isNaN(Number(f.value))) {
        whereClauses.push(`${alias}.${f.field} ${f.op} ${f.value}`)
      } else {
        whereClauses.push(`${alias}.${f.field} ${f.op} '${f.value}'`)
      }
    }
  }

  const whereLine = whereClauses.length ? `\nWHERE ${whereClauses.join('\n  AND ')}` : ''

  const returnVars = state.nodes.map(n => n.alias || n.id).join(', ')
  const returnLine = `\nRETURN ${returnVars}`
  const limitLine  = state.limit ? `\nLIMIT ${state.limit}` : ''

  return matchLine + whereLine + returnLine + limitLine
}

// ── URL state encoding ────────────────────────────────────────────────────────

function encodeState(state: BuilderState): string {
  return btoa(JSON.stringify(state))
}

function decodeState(encoded: string): BuilderState {
  try { return JSON.parse(atob(encoded)) } catch { return DEFAULT_STATE }
}

// ── Main component ─────────────────────────────────────────────────────────────

// ── Live schema hook ───────────────────────────────────────────────────────────────

function useGraphSchema() {
  const { data: schema } = useQuery({
    queryKey: ['graph-schema'],
    queryFn:  () => fetch('/api/schema').then(r => r.json()),
    staleTime: 5 * 60_000,
  })
  const { data: stats } = useQuery({
    queryKey: ['graph-schema-stats'],
    queryFn:  () => fetch('/api/schema/stats').then(r => r.json()),
    staleTime: 60_000,
  })
  const nodeTypes      = schema?.node_types      ?? FALLBACK_NODE_TYPES
  const relTypes       = schema?.relationship_types?.map(r => r.id) ?? FALLBACK_RELS
  const relTypeFull    = schema?.relationship_types ?? []
  return { nodeTypes, relTypes, relTypeFull, stats: stats ?? {} }
}

export function QueryBuilder() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()

  // Restore state from URL
  const initState = useMemo(() => {
    const s = searchParams.get('state')
    return s ? decodeState(s) : DEFAULT_STATE
  }, [])

  const [state, setState_]       = useState<BuilderState>(initState)
  const [cypher, setCypher]      = useState('')
  const [results, setResults]    = useState<any[] | null>(null)
  const [running, setRunning]    = useState(false)
  const [error, setError]        = useState('')
  const [outputMode, setOutput]  = useState<'json' | 'yaml' | 'graph'>('json')
  const [showCypher, setShowCypher] = useState(true)
  const [copied, setCopied]      = useState(false)
  const nodeIdRef = useRef(0)
  const relIdRef  = useRef(0)
  const filterIdRef = useRef(0)
  const { nodeTypes, relTypes, relTypeFull, stats } = useGraphSchema()

  // Update URL whenever state changes
  const setState = useCallback((updater: any) => {
    setState_(prev => {
      const next = typeof updater === 'function' ? updater(prev) : updater
      const cyp  = buildCypher(next)
      setCypher(cyp)
      // Encode state in URL
      const params: any = { state: encodeState(next) }
      if (cyp) params.q = cyp
      setSearchParams(params, { replace: true })
      return next
    })
  }, [setSearchParams])

  // Init cypher on mount
  useEffect(() => {
    setCypher(buildCypher(state))
  }, [])

  const addNode = (type: string) => {
    const id    = `n${nodeIdRef.current++}`
    const alias = `${type.toLowerCase()[0]}${nodeIdRef.current}`
    setState(s => ({
      ...s,
      nodes: [...s.nodes, { id, type, alias, filters: [] }],
    }))
  }

  const removeNode = (id: string) => {
    setState(s => ({
      ...s,
      nodes:         s.nodes.filter(n => n.id !== id),
      relationships: s.relationships.filter(r => r.from !== (s.nodes.find(n => n.id === id)?.alias) && r.to !== (s.nodes.find(n => n.id === id)?.alias)),
    }))
  }

  const updateNodeAlias = (id: string, alias: string) => {
    setState(s => ({ ...s, nodes: s.nodes.map(n => n.id === id ? { ...n, alias } : n) }))
  }

  const addFilter = (nodeId: string) => {
    const fid = `f${filterIdRef.current++}`
    setState(s => ({
      ...s,
      nodes: s.nodes.map(n =>
        n.id === nodeId
          ? { ...n, filters: [...n.filters, { id: fid, field: '', op: '=', value: '' }] }
          : n
      ),
    }))
  }

  const updateFilter = (nodeId: string, filterId: string, patch: Partial<FilterClause>) => {
    setState(s => ({
      ...s,
      nodes: s.nodes.map(n =>
        n.id === nodeId
          ? { ...n, filters: n.filters.map(f => f.id === filterId ? { ...f, ...patch } : f) }
          : n
      ),
    }))
  }

  const removeFilter = (nodeId: string, filterId: string) => {
    setState(s => ({
      ...s,
      nodes: s.nodes.map(n =>
        n.id === nodeId ? { ...n, filters: n.filters.filter(f => f.id !== filterId) } : n
      ),
    }))
  }

  const addRelationship = () => {
    if (state.nodes.length < 2) return
    const id = `r${relIdRef.current++}`
    setState(s => ({
      ...s,
      relationships: [...s.relationships, {
        id, type: 'CONTAINS',
        from: (s.nodes[0].alias || s.nodes[0].id),
        to:   (s.nodes[1].alias || s.nodes[1].id),
        directed: true,
      }],
    }))
  }

  const removeRelationship = (id: string) => {
    setState(s => ({ ...s, relationships: s.relationships.filter(r => r.id !== id) }))
  }

  const runQuery = async () => {
    if (!cypher.trim()) return
    setRunning(true); setError(''); setResults(null)
    try {
      const r = await fetch('/api/graph/query', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ cypher, params: {} }),
      })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || 'Query failed')
      setResults(d.rows ?? d.nodes ?? d)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setRunning(false)
    }
  }

  const viewInGraph = () => {
    navigate(`/query?q=${encodeURIComponent(cypher)}`)
  }

  const copyUrl = () => {
    navigator.clipboard.writeText(window.location.href)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const downloadResults = () => {
    if (!results) return
    let content: string
    let ext: string
    if (outputMode === 'yaml') {
      content = yaml.dump(results)
      ext = 'yaml'
    } else {
      content = JSON.stringify(results, null, 2)
      ext = 'json'
    }
    const blob = new Blob([content], { type: 'text/plain' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href = url; a.download = `query-results.${ext}`; a.click()
  }

  const outputText = useMemo(() => {
    if (!results) return ''
    if (outputMode === 'yaml') return yaml.dump(results)
    return JSON.stringify(results, null, 2)
  }, [results, outputMode])

  const aliases = state.nodes.map(n => n.alias || n.id)

  return (
    <div className="qb-page">
      {/* Header */}
      <div className="qb-header">
        <div>
          <h1>Query Builder</h1>
          <p>Drag-and-drop Cypher construction — every state is URL-shareable</p>
        </div>
        <div className="qb-header-actions">
          <button onClick={copyUrl} className="qb-btn-ghost" title="Copy shareable URL">
            {copied ? '✓ Copied' : <><Copy size={12} /> Share URL</>}
          </button>
          {cypher && (
            <button onClick={viewInGraph} className="qb-btn-ghost">
              <Network size={12} /> View in graph
            </button>
          )}
          <button onClick={runQuery} disabled={!cypher || running} className="qb-btn-run">
            {running ? <RefreshCw size={13} className="qb-spin" /> : <Play size={13} />}
            Run
          </button>
        </div>
      </div>

      <div className="qb-layout">

        {/* Left: node type palette */}
        <div className="qb-palette">
          <div className="qb-palette-title">Node types</div>
          {nodeTypes.map(nt => (
            <button
              key={nt.id}
              className="qb-palette-item"
              style={{ '--nc': nt.color } as any}
              onClick={() => addNode(nt.id)}
              title={nt.description ?? nt.label}
            >
              <span>{nt.icon}</span>
              <span>{nt.label}</span>
              {stats[nt.id] != null && (
                <span className="qb-palette-count">{fmtCount(stats[nt.id])}</span>
              )}
              <Plus size={10} className="qb-palette-plus" />
            </button>
          ))}

          <div className="qb-palette-title" style={{ marginTop: 16 }}>Relationships</div>
          <button
            className="qb-palette-rel"
            onClick={addRelationship}
            disabled={state.nodes.length < 2}
            title={state.nodes.length < 2 ? 'Add at least 2 nodes first' : 'Add relationship'}
          >
            <Link2 size={12} /> Add relationship
          </button>
        </div>

        {/* Center: builder canvas */}
        <div className="qb-canvas">

          {state.nodes.length === 0 ? (
            <div className="qb-empty">
              <div className="qb-empty-icon">🔍</div>
              <div className="qb-empty-title">Click a node type to start building</div>
              <div className="qb-empty-sub">Each node becomes a MATCH clause</div>
            </div>
          ) : (
            <div className="qb-clauses">
              <Reorder.Group
                axis="y"
                values={state.nodes}
                onReorder={nodes => setState(s => ({ ...s, nodes }))}
              >
                {state.nodes.map(node => (
                  <Reorder.Item key={node.id} value={node}>
                    <NodeClauseCard
                      node={node}
                      onAliasChange={a => updateNodeAlias(node.id, a)}
                      onAddFilter={() => addFilter(node.id)}
                      onUpdateFilter={(fid, patch) => updateFilter(node.id, fid, patch)}
                      onRemoveFilter={fid => removeFilter(node.id, fid)}
                      onRemove={() => removeNode(node.id)}
                    />
                  </Reorder.Item>
                ))}
              </Reorder.Group>

              {/* Relationship clauses */}
              {state.relationships.map(rel => (
                <RelationshipCard
                  key={rel.id}
                  rel={rel}
                  aliases={aliases}
                  onChange={patch => setState(s => ({
                    ...s,
                    relationships: s.relationships.map(r => r.id === rel.id ? { ...r, ...patch } : r),
                  }))}
                  onRemove={() => removeRelationship(rel.id)}
                />
              ))}

              {/* Limit row */}
              <div className="qb-limit-row">
                <span>LIMIT</span>
                <input
                  type="number"
                  value={state.limit}
                  onChange={e => setState(s => ({ ...s, limit: Number(e.target.value) }))}
                  min={1} max={10000}
                />
                <span>rows</span>
              </div>
            </div>
          )}

          {/* Generated Cypher */}
          {cypher && (
            <div className="qb-cypher-block">
              <div className="qb-cypher-header" onClick={() => setShowCypher(v => !v)}>
                <Code2 size={12} />
                <span>Generated Cypher</span>
                {showCypher ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              </div>
              {showCypher && (
                <CodeMirror
                  value={cypher}
                  extensions={[sql()]}
                  theme={oneDark}
                  onChange={setCypher}
                  className="qb-codemirror"
                  basicSetup={{ lineNumbers: false, foldGutter: false }}
                />
              )}
            </div>
          )}
        </div>

        {/* Right: results */}
        <div className="qb-results">
          <div className="qb-results-header">
            <span>Results</span>
            <div className="qb-output-tabs">
              {(['json', 'yaml'] as const).map(m => (
                <button
                  key={m}
                  className={`qb-tab ${outputMode === m ? 'qb-tab-active' : ''}`}
                  onClick={() => setOutput(m)}
                >
                  {m === 'json' ? <Braces size={11} /> : <List size={11} />}
                  {m.toUpperCase()}
                </button>
              ))}
            </div>
            {results && (
              <button onClick={downloadResults} className="qb-btn-ghost qb-dl-btn" title="Download">
                <Download size={11} />
              </button>
            )}
          </div>

          {error && (
            <div className="qb-error">
              <AlertTriangle size={12} /> {error}
            </div>
          )}

          {running && (
            <div className="qb-running">
              <RefreshCw size={14} className="qb-spin" /> Running query…
            </div>
          )}

          {!running && !error && results !== null && (
            <div className="qb-results-count">
              {results.length} row{results.length !== 1 ? 's' : ''}
            </div>
          )}

          {!running && !error && results !== null && (
            <pre className="qb-output">{outputText}</pre>
          )}

          {!running && !error && results === null && (
            <div className="qb-results-empty">
              Build a query and press Run
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function NodeClauseCard({ node, onAliasChange, onAddFilter, onUpdateFilter, onRemoveFilter, onRemove }) {
  const { nodeTypes } = useGraphSchema()
  const nt = nodeTypes.find(t => t.id === node.type)
  const { data: propData } = useQuery({
    queryKey: ['schema-props', node.type],
    queryFn:  () => fetch(`/api/schema/properties/${node.type}?live=true`).then(r => r.json()),
    staleTime: 5 * 60_000,
  })
  const fields = (propData?.properties ?? []).map(p => p.key)

  return (
    <motion.div
      layout
      className="qb-node-card"
      style={{ '--nc': nt?.color ?? '#4f8ef7' } as any}
    >
      <div className="qb-node-header">
        <GripVertical size={12} className="qb-grip" />
        <span className="qb-node-icon">{nt?.icon}</span>
        <span className="qb-node-label">MATCH</span>
        <span className="qb-node-type">{node.type}</span>
        <span className="qb-node-as">AS</span>
        <input
          className="qb-alias-input"
          value={node.alias}
          onChange={e => onAliasChange(e.target.value)}
        />
        <button onClick={onRemove} className="qb-node-remove"><X size={11} /></button>
      </div>

      {/* Filters */}
      {node.filters.map(f => (
        <div key={f.id} className="qb-filter-row">
          <Filter size={10} className="qb-filter-icon" />
          <span className="qb-filter-where">WHERE</span>
          <span className="qb-filter-alias">{node.alias}.</span>
          <select
            value={f.field}
            onChange={e => onUpdateFilter(f.id, { field: e.target.value })}
          >
            <option value="">field</option>
            {fields.map(ff => <option key={ff} value={ff}>{ff}</option>)}
          </select>
          <select
            value={f.op}
            onChange={e => onUpdateFilter(f.id, { op: e.target.value })}
          >
            {FILTER_OPS.map(o => <option key={o.op} value={o.op}>{o.label}</option>)}
          </select>
          {f.op !== 'IS NULL' && f.op !== 'IS NOT NULL' && (
            <input
              value={f.value}
              onChange={e => onUpdateFilter(f.id, { value: e.target.value })}
              placeholder="value"
              className="qb-filter-value"
            />
          )}
          <button onClick={() => onRemoveFilter(f.id)} className="qb-filter-remove"><X size={10} /></button>
        </div>
      ))}

      <button onClick={onAddFilter} className="qb-add-filter">
        <Plus size={10} /> Add filter
      </button>
    </motion.div>
  )
}

function RelationshipCard({ rel, aliases, onChange, onRemove }) {
  const { relTypes, relTypeFull } = useGraphSchema()
  const relInfo = relTypeFull.find(r => r.id === rel.type)
  return (
    <motion.div layout className="qb-rel-card" title={relInfo?.description}>
      <ArrowRight size={12} className="qb-rel-icon" />
      <select value={rel.from} onChange={e => onChange({ from: e.target.value })}>
        {aliases.map(a => <option key={a} value={a}>{a}</option>)}
      </select>
      <select value={rel.type} onChange={e => onChange({ type: e.target.value })}>
        {relTypes.map(t => <option key={t} value={t}>{t}</option>)}
      </select>
      <ArrowRight size={12} />
      <select value={rel.to} onChange={e => onChange({ to: e.target.value })}>
        {aliases.map(a => <option key={a} value={a}>{a}</option>)}
      </select>
      <label className="qb-rel-directed">
        <input
          type="checkbox"
          checked={rel.directed}
          onChange={e => onChange({ directed: e.target.checked })}
        />
        directed
      </label>
      <button onClick={onRemove} className="qb-filter-remove"><X size={11} /></button>
    </motion.div>
  )
}

function fmtCount(n: number) {
  if (n == null) return ''
  if (n >= 1_000_000) return `${(n/1_000_000).toFixed(1)}M`
  if (n >= 1_000)     return `${(n/1_000).toFixed(0)}K`
  return String(n)
}


