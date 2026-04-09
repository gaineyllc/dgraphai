/**
 * GraphPage — the main graph visualization view.
 * Left panel: search + node details
 * Center: interactive Cytoscape graph
 * Right panel: node properties (on selection)
 */
import { useState, useCallback, useEffect } from 'react'
import { AnimatePresence } from 'framer-motion'
import { NodeTooltip } from '../components/NodeTooltip'
import { InspectionPane } from '../components/InspectionPane'
import { NodeContextMenu } from '../components/NodeContextMenu'
import '../components/inspection.css'
import { useQuery } from '@tanstack/react-query'
import { Search, X, ChevronRight } from 'lucide-react'
import { GraphCanvas } from '../components/GraphCanvas'
import { graphApi, type GraphNode, type Subgraph, type SearchResult } from '../lib/api'

export function GraphPage() {
  const [subgraph, setSubgraph]         = useState<Subgraph>({ nodes: [], edges: [] })
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [tooltipNode, setTooltipNode]   = useState<GraphNode | null>(null)
  const [tooltipPos, setTooltipPos]     = useState({ x: 0, y: 0 })
  const [inspecting, setInspecting]     = useState<GraphNode | null>(null)
  const [contextNode, setContextNode]   = useState<GraphNode | null>(null)
  const [contextPos, setContextPos]     = useState({ x: 0, y: 0 })
  const [attackPathFrom, setAttackPathFrom] = useState<string | null>(null)
  const [searchTerm, setSearchTerm]     = useState('')
  const [searchResults, setSearchResults] = useState<SearchResult[]>([])
  const [searching, setSearching]       = useState(false)

  // Graph stats
  const { data: stats } = useQuery({
    queryKey: ['graph-stats'],
    queryFn: graphApi.stats,
    refetchInterval: 30_000,
  })

  // Search
  const runSearch = useCallback(async (term: string) => {
    if (!term.trim()) { setSearchResults([]); return }
    setSearching(true)
    try {
      const results = await graphApi.search(term, undefined, {}, 30)
      setSearchResults(results)
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
    const data = await graphApi.getNeighbors(id, 1, 80)
    setSubgraph(prev => ({
      nodes: mergeUnique(prev.nodes, data.nodes, 'id'),
      edges: mergeUnique(prev.edges, data.edges, 'id'),
    }))
    setSelectedNode(data.nodes.find(n => n.id === id) ?? null)
  }, [])

  const clearGraph = () => {
    setSubgraph({ nodes: [], edges: [] })
    setSelectedNode(null)
  }

  return (
    <div className="flex h-full">
      {/* ── Left panel ── */}
      <div className="w-72 flex flex-col border-r border-[#252535] bg-[#12121a] flex-shrink-0">
        {/* Search */}
        <div className="p-3 border-b border-[#252535]">
          <div className="relative">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#55557a]" />
            <input
              value={searchTerm}
              onChange={e => setSearchTerm(e.target.value)}
              placeholder="Search files, people, topics…"
              className="w-full pl-8 pr-3 py-2 text-sm bg-[#0a0a0f] border border-[#252535] rounded-lg text-[#e2e2f0] placeholder-[#55557a] focus:outline-none focus:border-[#4f8ef7]"
            />
            {searching && (
              <div className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3 h-3 border border-[#4f8ef7] border-t-transparent rounded-full animate-spin" />
            )}
          </div>
        </div>

        {/* Search results */}
        {searchResults.length > 0 && (
          <div className="flex-1 overflow-y-auto">
            {searchResults.map(r => (
              <button
                key={r.id}
                onClick={() => loadNode(r.id)}
                className="w-full px-3 py-2 text-left hover:bg-[#1a1a28] transition-colors border-b border-[#1a1a28]"
              >
                <div className="flex items-center gap-2">
                  <NodeDot label={r.label} />
                  <div className="min-w-0">
                    <div className="text-sm text-[#e2e2f0] truncate">{r.name}</div>
                    <div className="text-xs text-[#55557a]">{r.label} {r.category ? `· ${r.category}` : ''}</div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        )}

        {/* Stats when no search */}
        {searchResults.length === 0 && stats && (
          <div className="flex-1 overflow-y-auto p-3">
            <div className="text-xs text-[#55557a] uppercase tracking-wider mb-2">Graph overview</div>
            <div className="space-y-1">
              {Object.entries(stats)
                .filter(([k]) => k !== 'relationships')
                .map(([type, count]) => (
                  <div key={type} className="flex items-center justify-between py-1">
                    <div className="flex items-center gap-2">
                      <NodeDot label={type} />
                      <span className="text-sm text-[#8888aa]">{type}</span>
                    </div>
                    <span className="text-sm text-[#e2e2f0] font-mono">{count.toLocaleString()}</span>
                  </div>
                ))
              }
              <div className="flex items-center justify-between py-1 border-t border-[#252535] mt-1">
                <span className="text-sm text-[#8888aa]">Relationships</span>
                <span className="text-sm text-[#e2e2f0] font-mono">{stats.relationships?.toLocaleString()}</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── Graph canvas ── */}
      <div className="flex-1 relative">
        {subgraph.nodes.length === 0 ? (
          <EmptyState />
        ) : (
          <GraphCanvas
            data={subgraph}
            selectedId={selectedNode?.id}
            onNodeClick={(node) => {
              setSelectedNode(node)
              setContextNode(null)  // close context menu on left click
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

        {/* Controls overlay */}
        <div className="absolute bottom-4 right-4 flex flex-col gap-1">
          {subgraph.nodes.length > 0 && (
            <button
              onClick={clearGraph}
              title="Clear graph"
              className="w-8 h-8 bg-[#12121a] border border-[#252535] rounded-lg flex items-center justify-center text-[#55557a] hover:text-[#f87171] transition-colors"
            >
              <X size={14} />
            </button>
          )}
        </div>

        {/* Node count badge */}
        {subgraph.nodes.length > 0 && (
          <div className="absolute top-3 left-3 text-xs text-[#55557a] bg-[#12121a] border border-[#252535] px-2 py-1 rounded-full">
            {subgraph.nodes.length} nodes · {subgraph.edges.length} edges
          </div>
        )}
      </div>

      {/* Floating tooltip — shows on node click */}
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

      {/* Full inspection pane — slides in from right, draggable */}
      <AnimatePresence>
        {inspecting && (
          <InspectionPane
            node={inspecting}
            onClose={() => setInspecting(null)}
            onExpand={loadNode}
          />
        )}
      </AnimatePresence>

      {/* Right-click context menu */}
      <AnimatePresence>
        {contextNode && (
          <NodeContextMenu
            node={contextNode}
            position={contextPos}
            onClose={() => setContextNode(null)}
            onExpand={(nodeId, hops) => {
              loadNode(nodeId)
              setContextNode(null)
            }}
            onAttackPath={(fromId) => {
              setAttackPathFrom(fromId)
              setContextNode(null)
            }}
          />
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-4 text-[#55557a]">
      <div className="w-16 h-16 rounded-2xl bg-[#12121a] border border-[#252535] flex items-center justify-center">
        <Search size={24} />
      </div>
      <div className="text-center">
        <div className="text-[#8888aa] font-medium">Search to explore</div>
        <div className="text-sm mt-1">Find files, people, or topics<br />then double-click nodes to expand</div>
      </div>
    </div>
  )
}

function NodeDot({ label }: { label: string }) {
  const COLORS: Record<string, string> = {
    File: '#4f8ef7', Directory: '#8b5cf6', Person: '#f472b6',
    FaceCluster: '#ec4899', Location: '#34d399', Organization: '#fbbf24',
    Topic: '#22d3ee', Application: '#fb923c', Vendor: '#a78bfa',
    Vulnerability: '#f87171', Certificate: '#4ade80',
  }
  const color = COLORS[label] ?? '#6b7280'
  return <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: color }} />
}

function formatProp(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number' && v > 1e9) {
    return `${(v / 1e9).toFixed(2)} GB`
  }
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

function mergeUnique<T extends { id: unknown }>(a: T[], b: T[], key: keyof T): T[] {
  const seen = new Set(a.map(x => x[key]))
  return [...a, ...b.filter(x => !seen.has(x[key]))]
}
