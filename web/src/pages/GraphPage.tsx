// @ts-nocheck
/**
 * GraphPage — main graph visualization.
 *
 * Layout:
 *   Top toolbar: search, query actions, node count, clear
 *   Left panel: search results / graph stats (collapsible)
 *   Center: Cytoscape canvas
 *   Right: inspection pane (slides in on node select)
 */
import { useState, useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import {
  Search, X, ChevronRight, Terminal, Wrench,
  Network, Loader2, BarChart3, ZoomIn, RefreshCw,
  Filter, GitCompare
} from 'lucide-react'
import { GraphCanvas } from '../components/GraphCanvas'
import { NodeTooltip } from '../components/NodeTooltip'
import { InspectionPane } from '../components/InspectionPane'
import { NodeContextMenu } from '../components/NodeContextMenu'
import { graphApi, type GraphNode, type Subgraph, type SearchResult } from '../lib/api'
import { apiFetch } from '../lib/apiFetch'
import '../components/inspection.css'
import './GraphPage.css'

// ── Helpers ───────────────────────────────────────────────────────────────────

function mergeUnique<T extends { id: string }>(a: T[], b: T[], key: keyof T): T[] {
  const seen = new Set(a.map(x => x[key]))
  return [...a, ...b.filter(x => !seen.has(x[key]))]
}

// ── Empty state ───────────────────────────────────────────────────────────────

function GraphEmptyState({ onLoadSample }: { onLoadSample: () => void }) {
  const navigate = useNavigate()
  return (
    <div className="graph-empty">
      <div className="graph-empty-icon">
        <Network size={36} />
      </div>
      <h2 className="graph-empty-title">Your graph is empty</h2>
      <p className="graph-empty-desc">
        Connect a data source to start building your knowledge graph.
        Once indexed, search for any file, person, or topic above.
      </p>
      <div className="graph-empty-actions">
        <button className="btn btn-primary" onClick={() => navigate('/connectors')}>
          Connect a data source
        </button>
        <button className="btn btn-secondary" onClick={onLoadSample}>
          Load sample data
        </button>
      </div>
      <div className="graph-empty-hints">
        <div className="graph-empty-hint" onClick={() => navigate('/query')}>
          <Terminal size={14} /> Write a Cypher query
        </div>
        <div className="graph-empty-hint" onClick={() => navigate('/builder')}>
          <Wrench size={14} /> Use the query builder
        </div>
        <div className="graph-empty-hint" onClick={() => navigate('/inventory')}>
          <BarChart3 size={14} /> Browse the inventory
        </div>
      </div>
    </div>
  )
}

// ── Node type dot ─────────────────────────────────────────────────────────────

const NODE_COLORS: Record<string, string> = {
  File: '#4f8ef7', Directory: '#8b5cf6', Person: '#f59e0b',
  Application: '#10b981', Device: '#6366f1', Network: '#ec4899',
  Certificate: '#f97316', Secret: '#ef4444', CVE: '#dc2626',
}

function NodeDot({ label }: { label: string }) {
  const color = NODE_COLORS[label] ?? '#55557a'
  return <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, display: 'inline-block', flexShrink: 0 }} />
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function GraphPage() {
  const navigate = useNavigate()
  const [subgraph, setSubgraph]             = useState<Subgraph>({ nodes: [], edges: [] })
  const [selectedNode, setSelectedNode]     = useState<GraphNode | null>(null)
  const [tooltipNode, setTooltipNode]       = useState<GraphNode | null>(null)
  const [tooltipPos, setTooltipPos]         = useState({ x: 0, y: 0 })
  const [inspecting, setInspecting]         = useState<GraphNode | null>(null)
  const [contextNode, setContextNode]       = useState<GraphNode | null>(null)
  const [contextPos, setContextPos]         = useState({ x: 0, y: 0 })
  const [searchTerm, setSearchTerm]         = useState('')
  const [searchResults, setSearchResults]   = useState<SearchResult[]>([])
  const [searching, setSearching]           = useState(false)
  const [leftOpen, setLeftOpen]             = useState(true)

  // Graph stats
  const { data: stats, refetch: refetchStats } = useQuery({
    queryKey: ['graph-stats'],
    queryFn:  graphApi.stats,
    refetchInterval: 30_000,
    retry: 1,
  })

  const totalNodes = Object.entries(stats ?? {})
    .filter(([k]) => k !== 'relationships')
    .reduce((s, [, v]) => s + (Number(v) || 0), 0)

  // Search
  const runSearch = useCallback(async (term: string) => {
    if (!term.trim()) { setSearchResults([]); return }
    setSearching(true)
    try {
      const results = await graphApi.search(term, undefined, {}, 30)
      setSearchResults(results)
    } catch {
      setSearchResults([])
    } finally {
      setSearching(false)
    }
  }, [])

  useEffect(() => {
    const id = setTimeout(() => runSearch(searchTerm), 300)
    return () => clearTimeout(id)
  }, [searchTerm, runSearch])

  // Load node into graph
  const loadNode = useCallback(async (id: string) => {
    try {
      const data = await graphApi.getNeighbors(id, 1, 80)
      setSubgraph(prev => ({
        nodes: mergeUnique(prev.nodes, data.nodes, 'id'),
        edges: mergeUnique(prev.edges, data.edges, 'id'),
      }))
      setSelectedNode(data.nodes.find(n => n.id === id) ?? null)
    } catch (e) {
      console.error('Failed to load node:', e)
    }
  }, [])

  // Load sample data (first 50 nodes)
  const loadSample = useCallback(async () => {
    try {
      const data = await graphApi.query(
        'MATCH (n) RETURN n LIMIT 50',
        {}
      )
      if (data?.nodes?.length) {
        setSubgraph({ nodes: data.nodes, edges: data.edges ?? [] })
      }
    } catch (e) {
      console.error('Failed to load sample:', e)
    }
  }, [])

  const clearGraph = () => {
    setSubgraph({ nodes: [], edges: [] })
    setSelectedNode(null)
    setSearchTerm('')
    setSearchResults([])
  }

  return (
    <div className="graph-page">

      {/* ── Top toolbar ── */}
      <div className="graph-toolbar">
        {/* Search */}
        <div className="graph-search-wrap">
          <Search size={14} className="graph-search-icon" />
          <input
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            placeholder="Search nodes, files, people…"
            className="graph-search-input"
          />
          {searching && <Loader2 size={13} className="graph-search-spinner" />}
          {searchTerm && !searching && (
            <button className="graph-search-clear" onClick={() => { setSearchTerm(''); setSearchResults([]) }}>
              <X size={12} />
            </button>
          )}
        </div>

        {/* Toolbar actions */}
        <div className="graph-toolbar-actions">
          <button className="graph-tool-btn" onClick={() => navigate('/query')} title="Query workspace">
            <Terminal size={15} /> Query
          </button>
          <button className="graph-tool-btn" onClick={() => navigate('/builder')} title="Visual query builder">
            <Wrench size={15} /> Builder
          </button>
          <button className="graph-tool-btn" onClick={() => navigate('/diff')} title="What changed">
            <GitCompare size={15} /> Diff
          </button>
          {subgraph.nodes.length > 0 && (
            <button className="graph-tool-btn graph-tool-btn-danger" onClick={clearGraph} title="Clear graph">
              <X size={15} /> Clear
            </button>
          )}
        </div>

        {/* Node/edge count */}
        {subgraph.nodes.length > 0 && (
          <div className="graph-count-badge">
            {subgraph.nodes.length} nodes · {subgraph.edges.length} edges
          </div>
        )}
      </div>

      {/* ── Search results dropdown ── */}
      {searchResults.length > 0 && (
        <div className="graph-search-results">
          {searchResults.map(r => (
            <button key={r.id} className="graph-result-item" onClick={() => {
              loadNode(r.id)
              setSearchTerm('')
              setSearchResults([])
            }}>
              <NodeDot label={r.label} />
              <div className="graph-result-text">
                <span className="graph-result-name">{r.name}</span>
                <span className="graph-result-meta">{r.label}{r.category ? ` · ${r.category}` : ''}</span>
              </div>
              <ChevronRight size={12} className="graph-result-arrow" />
            </button>
          ))}
        </div>
      )}

      {/* ── Body: left panel + canvas ── */}
      <div className="graph-body">

        {/* Left panel: stats */}
        {leftOpen && (
          <div className="graph-left-panel">
            <div className="graph-panel-header">
              <span className="text-label">Graph overview</span>
              <button className="graph-panel-close" onClick={() => setLeftOpen(false)}>
                <X size={12} />
              </button>
            </div>

            {totalNodes === 0 ? (
              <div className="graph-panel-empty">
                <p>No data indexed yet.</p>
                <button className="btn btn-ghost btn-sm" onClick={() => navigate('/connectors')}>
                  Connect a source →
                </button>
              </div>
            ) : (
              <div className="graph-stats-list">
                {Object.entries(stats ?? {})
                  .filter(([k]) => k !== 'relationships')
                  .sort(([, a], [, b]) => Number(b) - Number(a))
                  .map(([type, count]) => (
                    <button key={type} className="graph-stat-row" onClick={() => {
                      // Load this node type into graph
                      graphApi.query(`MATCH (n:${type}) RETURN n LIMIT 50`, {})
                        .then(d => d?.nodes?.length && setSubgraph({ nodes: d.nodes, edges: d.edges ?? [] }))
                        .catch(() => {})
                    }}>
                      <NodeDot label={type} />
                      <span className="graph-stat-type">{type}</span>
                      <span className="graph-stat-count">{Number(count).toLocaleString()}</span>
                    </button>
                  ))
                }
                <div className="graph-stat-row graph-stat-total">
                  <span className="graph-stat-type">Relationships</span>
                  <span className="graph-stat-count">{Number(stats?.relationships ?? 0).toLocaleString()}</span>
                </div>
              </div>
            )}

            <div className="graph-panel-actions">
              <button className="btn btn-ghost btn-sm" onClick={refetchStats}>
                <RefreshCw size={12} /> Refresh
              </button>
            </div>
          </div>
        )}

        {/* Toggle left panel when closed */}
        {!leftOpen && (
          <button className="graph-panel-toggle" onClick={() => setLeftOpen(true)} title="Show graph overview">
            <BarChart3 size={15} />
          </button>
        )}

        {/* Canvas */}
        <div className="graph-canvas-wrap">
          {subgraph.nodes.length === 0 ? (
            <GraphEmptyState onLoadSample={loadSample} />
          ) : (
            <GraphCanvas
              data={subgraph}
              selectedId={selectedNode?.id}
              onNodeClick={(node) => {
                setSelectedNode(node)
                setContextNode(null)
                setTooltipNode(node)
              }}
              onNodeExpand={loadNode}
              onNodeClickPos={(node, pos) => {
                setSelectedNode(node)
                setTooltipNode(node)
                setTooltipPos(pos)
              }}
              onNodeRightClick={(node, pos) => {
                setContextNode(node)
                setContextPos(pos)
                setTooltipNode(null)
              }}
              className="w-full h-full"
            />
          )}
        </div>
      </div>

      {/* Floating tooltip */}
      <AnimatePresence>
        {tooltipNode && (
          <NodeTooltip
            node={tooltipNode}
            position={tooltipPos}
            onClose={() => setTooltipNode(null)}
            onDetails={() => { setInspecting(tooltipNode); setTooltipNode(null) }}
          />
        )}
      </AnimatePresence>

      {/* Inspection pane */}
      <AnimatePresence>
        {inspecting && (
          <InspectionPane
            node={inspecting}
            onClose={() => setInspecting(null)}
            onViewInGraph={(id) => { loadNode(id); setInspecting(null) }}
          />
        )}
      </AnimatePresence>

      {/* Context menu */}
      <AnimatePresence>
        {contextNode && (
          <NodeContextMenu
            node={contextNode}
            position={contextPos}
            onClose={() => setContextNode(null)}
            onExpand={() => { loadNode(contextNode.id); setContextNode(null) }}
            onInspect={() => { setInspecting(contextNode); setContextNode(null) }}
            onAttackPath={() => setContextNode(null)}
          />
        )}
      </AnimatePresence>
    </div>
  )
}
