// @ts-nocheck
/**
 * ExplorePage — redesigned graph exploration with filter panel.
 * Route: /explore
 *
 * Layout:
 *   Left 280px filter panel → builds Cypher query → POST /api/graph/query
 *   Center canvas → Cytoscape graph
 *   Right slide-in panel → node properties on click
 */
import { useState, useCallback, useRef } from 'react'
import { useMutation } from '@tanstack/react-query'
import { apiFetch } from '../lib/apiFetch'
import { NodeTooltipCard } from '../components/NodeTooltipCard'
import { NodeDrawer } from '../components/NodeDrawer'
import { GraphCanvas } from '../components/GraphCanvas'
import {
  Network, ChevronDown, ChevronRight,
  Play, X, Code2, Filter,
  FileCode2, FolderOpen, Users, Shield,
  Copy, Check
} from 'lucide-react'
import './ExplorePage.css'

// ─── Types ─────────────────────────────────────────────────────────────────────
interface NodeType { id: string; label: string; icon: any; color: string }
interface FilterState {
  nodeTypes:   string[]
  category:    string
  extension:   string
  depth:       number
  sizeMin:     string
  sizeMax:     string
}

// ─── Available node types ──────────────────────────────────────────────────────
const NODE_TYPES: NodeType[] = [
  { id: 'File',          label: 'File',          icon: FileCode2,  color: 'var(--color-primary)' },
  { id: 'Directory',     label: 'Directory',     icon: FolderOpen, color: '#8b5cf6' },
  { id: 'Person',        label: 'Person',        icon: Users,      color: '#f472b6' },
  { id: 'Vulnerability', label: 'Vulnerability', icon: Shield,     color: 'var(--color-critical)' },
]

const FILE_CATEGORIES = [
  'Code', 'Image', 'Text', 'Data', 'Config', 'Binary',
  'Archive', 'Markup', 'Document', 'Executable', 'Unknown',
]

const COMMON_EXTENSIONS = ['.py', '.js', '.ts', '.go', '.rs', '.java', '.cpp', '.json', '.yaml', '.md']

// ─── Cypher builder ────────────────────────────────────────────────────────────
function buildCypher(filters: FilterState): string {
  const { nodeTypes, category, extension, depth, sizeMin, sizeMax } = filters

  if (nodeTypes.length === 0) return ''

  // Single type: simple query
  if (nodeTypes.length === 1) {
    const t = nodeTypes[0]
    const conditions: string[] = []

    if (t === 'File') {
      if (category)             conditions.push(`f.file_category = '${category}'`)
      if (extension)            conditions.push(`f.extension = '${extension}'`)
      if (sizeMin)              conditions.push(`f.size >= ${Number(sizeMin) * 1024}`)
      if (sizeMax)              conditions.push(`f.size <= ${Number(sizeMax) * 1024}`)
    }

    const where = conditions.length ? `\nWHERE ${conditions.join('\n  AND ')}` : ''

    if (depth > 0 && t === 'File') {
      return `MATCH (f:${t})${where}\nWITH f LIMIT 100\nMATCH path = (f)-[*1..${depth}]-(neighbor)\nRETURN f, path LIMIT 200`
    }
    return `MATCH (f:${t})${where}\nRETURN f LIMIT 100`
  }

  // Multiple types: UNION
  const parts = nodeTypes.map(t =>
    `MATCH (f:${t})\nRETURN f LIMIT 50`
  )
  return parts.join('\nUNION\n')
}

// ─── Filter panel ──────────────────────────────────────────────────────────────
function FilterPanel({
  filters, onChange, onExplore, isLoading, resultCount,
}: {
  filters: FilterState
  onChange: (f: FilterState) => void
  onExplore: () => void
  isLoading: boolean
  resultCount: number | null
}) {
  const [showCypher, setShowCypher] = useState(false)
  const [copied,     setCopied]     = useState(false)
  const cypher = buildCypher(filters)

  const toggleType = (id: string) => {
    const next = filters.nodeTypes.includes(id)
      ? filters.nodeTypes.filter(t => t !== id)
      : [...filters.nodeTypes, id]
    onChange({ ...filters, nodeTypes: next })
  }

  const set = (k: keyof FilterState, v: any) => onChange({ ...filters, [k]: v })

  const copyCypher = async () => {
    if (!cypher) return
    await navigator.clipboard.writeText(cypher)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <aside className="explore-filter-panel">
      <div className="efp-header">
        <Filter size={15} />
        <span>Explore</span>
      </div>

      {/* Node type pills */}
      <section className="efp-section">
        <div className="efp-section-label">Node Types</div>
        <div className="efp-pills">
          {NODE_TYPES.map(nt => (
            <button
              key={nt.id}
              className={`efp-pill ${filters.nodeTypes.includes(nt.id) ? 'efp-pill-active' : ''}`}
              style={{ '--pill-c': nt.color } as any}
              onClick={() => toggleType(nt.id)}
            >
              <nt.icon size={12} />
              {nt.label}
            </button>
          ))}
        </div>
      </section>

      {/* File-specific filters — only show when File is selected */}
      {filters.nodeTypes.includes('File') && (
        <>
          <section className="efp-section">
            <div className="efp-section-label">Category</div>
            <select
              className="efp-select"
              value={filters.category}
              onChange={e => set('category', e.target.value)}
            >
              <option value="">All categories</option>
              {FILE_CATEGORIES.map(c => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </section>

          <section className="efp-section">
            <div className="efp-section-label">Extension</div>
            <select
              className="efp-select"
              value={filters.extension}
              onChange={e => set('extension', e.target.value)}
            >
              <option value="">Any extension</option>
              {COMMON_EXTENSIONS.map(ext => (
                <option key={ext} value={ext}>{ext}</option>
              ))}
            </select>
          </section>

          <section className="efp-section">
            <div className="efp-section-label">Size (KB)</div>
            <div className="efp-range-row">
              <input
                type="number"
                className="efp-input"
                placeholder="Min"
                value={filters.sizeMin}
                onChange={e => set('sizeMin', e.target.value)}
                min={0}
              />
              <span className="efp-range-sep">–</span>
              <input
                type="number"
                className="efp-input"
                placeholder="Max"
                value={filters.sizeMax}
                onChange={e => set('sizeMax', e.target.value)}
                min={0}
              />
            </div>
          </section>

          <section className="efp-section">
            <div className="efp-section-label">Relationship Depth</div>
            <div className="efp-depth-row">
              {[0, 1, 2, 3].map(d => (
                <button
                  key={d}
                  className={`efp-depth-btn ${filters.depth === d ? 'active' : ''}`}
                  onClick={() => set('depth', d)}
                >
                  {d === 0 ? 'None' : `${d}×`}
                </button>
              ))}
            </div>
          </section>
        </>
      )}

      {/* Explore button */}
      <button
        className="efp-explore-btn"
        onClick={onExplore}
        disabled={filters.nodeTypes.length === 0 || isLoading}
      >
        {isLoading
          ? <><span className="efp-spinner" /> Exploring…</>
          : <><Play size={14} fill="currentColor" /> Explore</>
        }
      </button>

      {resultCount !== null && (
        <div className="efp-result-count">
          {resultCount} {resultCount === 1 ? 'node' : 'nodes'} returned
        </div>
      )}

      {/* Collapsible Cypher display */}
      <div className="efp-cypher-wrap">
        <button
          className="efp-cypher-toggle"
          onClick={() => setShowCypher(s => !s)}
        >
          <Code2 size={12} />
          <span>Cypher query</span>
          {showCypher ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
        </button>

        {showCypher && cypher && (
          <div className="efp-cypher-block">
            <button
              className="efp-cypher-copy"
              onClick={copyCypher}
              title="Copy query"
            >
              {copied ? <Check size={11} /> : <Copy size={11} />}
            </button>
            <pre className="efp-cypher-pre">{cypher}</pre>
          </div>
        )}
        {showCypher && !cypher && (
          <p className="efp-cypher-empty">Select node types to generate a query</p>
        )}
      </div>
    </aside>
  )
}

// ─── Node detail panel ─────────────────────────────────────────────────────────
function NodeDetailPanel({
  node, onClose,
}: {
  node: any; onClose: () => void
}) {
  if (!node) return null

  const data   = node.data?.() ?? node
  const props  = data.properties ?? data
  const label  = data.label ?? data.id ?? 'Node'
  const type   = data.type ?? data.nodeType ?? 'Unknown'

  const entries = Object.entries(props).filter(([k]) =>
    !['id', 'elementId', 'tenant_id', 'type', 'nodeType'].includes(k)
  )

  return (
    <>
      <div className="explore-drawer-backdrop" onClick={onClose} />
      <aside className="explore-drawer">
        <div className="exd-header">
          <div className="exd-type-badge">{type}</div>
          <button className="exd-close" onClick={onClose}><X size={15} /></button>
        </div>

        <div className="exd-title">{
          props.name
            ?? props.path?.split(/[/\\]/).pop()
            ?? label
            ?? 'Node'
        }</div>

        {props.path && (
          <div className="exd-path" title={props.path}>{props.path}</div>
        )}

        <div className="exd-divider" />

        <div className="exd-props">
          {entries.map(([k, v]) => {
            if (v == null) return null
            const val = String(v)
            return (
              <div key={k} className="exd-prop">
                <div className="exd-prop-key">{k.replace(/_/g, ' ')}</div>
                <div className="exd-prop-val" title={val}>
                  {val.length > 60 ? val.slice(0, 60) + '…' : val}
                </div>
              </div>
            )
          })}
          {entries.length === 0 && (
            <p className="exd-empty">No properties available.</p>
          )}
        </div>
      </aside>
    </>
  )
}

// ─── Main export ───────────────────────────────────────────────────────────────
export function ExplorePage() {
  const [filters, setFilters] = useState<FilterState>({
    nodeTypes:  [],
    category:   '',
    extension:  '',
    depth:      0,
    sizeMin:    '',
    sizeMax:    '',
  })
  const [graphData,   setGraphData]   = useState<any>(null)
  const [selectedNode, setSelected]   = useState<any>(null)
  const [tooltipPos,   setTooltipPos]  = useState<{ x: number; y: number } | null>(null)
  const [drawerOpen,   setDrawerOpen]  = useState(false)
  const [resultCount,  setResultCount] = useState<number | null>(null)

  const exploreMutation = useMutation({
    mutationFn: (cypher: string) =>
      apiFetch('/api/graph/query', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ cypher }),
      }).then(r => r.json()),
    onSuccess: (rawRows: any[]) => {
      // Transform flat row objects into Cytoscape node/edge format
      const rows = Array.isArray(rawRows) ? rawRows : []
      const nodeMap = new Map<string, any>()
      const edges: any[] = []

      rows.forEach((row, idx) => {
        // Each row may have one or more node properties
        Object.entries(row).forEach(([key, val]: [string, any]) => {
          if (val && typeof val === 'object' && (val.id || val.path)) {
            const nodeId = String(val.id ?? val.path ?? `node-${idx}`)
            if (!nodeMap.has(nodeId)) {
              nodeMap.set(nodeId, {
                id:    nodeId,
                label: key.replace(/^[a-z]\./, '').replace(/_/g, ' '),
                name:  val.name ?? val.id ?? nodeId,
                props: val,
              })
            }
          }
        })
      })

      const nodes = Array.from(nodeMap.values())
      setGraphData({ nodes, edges })
      setResultCount(nodes.length)
    },
  })

  const handleExplore = useCallback(() => {
    const cypher = buildCypher(filters)
    if (!cypher) return
    setSelected(null)
    exploreMutation.mutate(cypher)
  }, [filters, exploreMutation])

  const handleNodeClick = useCallback((node: any, pos?: { x: number; y: number }) => {
    setSelected(node)
    setTooltipPos(pos ?? null)
    setDrawerOpen(false)
  }, [])

  const isEmpty = !graphData && !exploreMutation.isLoading

  return (
    <div className="explore-page">
      <FilterPanel
        filters={filters}
        onChange={setFilters}
        onExplore={handleExplore}
        isLoading={exploreMutation.isPending}
        resultCount={resultCount}
      />

      <div className="explore-canvas-wrap">
        {isEmpty ? (
          <div className="explore-empty-state">
            <Network size={48} className="explore-empty-icon" />
            <h2 className="explore-empty-title">Select node types above to start exploring</h2>
            <p className="explore-empty-sub">
              Use the filter panel to choose what to visualize, then hit <strong>Explore</strong>.
            </p>
          </div>
        ) : exploreMutation.isError ? (
          <div className="explore-empty-state">
            <Shield size={40} className="explore-error-icon" />
            <h2 className="explore-empty-title">Query failed</h2>
            <p className="explore-empty-sub">{String(exploreMutation.error)}</p>
            <button className="efp-explore-btn" style={{ marginTop: 12 }} onClick={handleExplore}>
              <Play size={14} /> Retry
            </button>
          </div>
        ) : graphData ? (
          <GraphCanvas
            data={graphData}
            onNodeClick={handleNodeClick}
            onNodeClickPos={(node, pos) => handleNodeClick(node, pos)}
          />
        ) : null}

        {exploreMutation.isPending && (
          <div className="explore-loading-overlay">
            <span className="efp-spinner explore-spinner-lg" />
            <span>Running query…</span>
          </div>
        )}
      </div>

      {/* Anchored tooltip — click outside to dismiss */}
      <AnimatePresence>
        {selectedNode && tooltipPos && !drawerOpen && (
          <NodeTooltipCard
            node={selectedNode}
            position={tooltipPos}
            onClose={() => { setSelected(null); setTooltipPos(null) }}
            onDetails={() => setDrawerOpen(true)}
            onExpand={() => {
              // TODO: load 1-hop neighbors
              setSelected(null); setTooltipPos(null)
            }}
          />
        )}
      </AnimatePresence>

      {/* Full property drawer — resizable, slides in from right */}
      <AnimatePresence>
        {selectedNode && drawerOpen && (
          <NodeDrawer
            node={selectedNode}
            onClose={() => { setDrawerOpen(false); setSelected(null); setTooltipPos(null) }}
            onExplore={() => { setDrawerOpen(false) }}
            onFindSimilar={(node) => {
              const cat = (node.props ?? node).file_category
              const ext = (node.props ?? node).extension
              const newFilters = { ...filters, category: cat ?? '', extension: ext ?? '' }
              setFilters(newFilters)
              setDrawerOpen(false)
              setSelected(null)
              setTooltipPos(null)
              // Auto-run explore with these filters
              setTimeout(() => {
                const cypher = buildCypher(newFilters)
                if (cypher) exploreMutation.mutate(cypher)
              }, 100)
            }}
          />
        )}
      </AnimatePresence>
    </div>
  )
}

export default ExplorePage

