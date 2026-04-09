// @ts-nocheck
/**
 * QueryWorkspace — the primary data exploration surface.
 *
 * Layout:
 *   ┌──────────────────────────────────────────────────────┐
 *   │  Query bar (always visible, full width)              │
 *   ├──────────┬───────────────────────────────────────────┤
 *   │ Filter   │  Graph Canvas  ──── or ────  Table View   │
 *   │ Sidebar  │  (infinite zoom/pan, lasso selection)     │
 *   │ (left)   │                                           │
 *   └──────────┴───────────────────────────────────────────┘
 *
 * Features:
 *   - Infinite zoom/pan graph canvas with minimap
 *   - Table view toggle
 *   - Lasso/circle selection → creates new saved query from selection
 *   - Left filter sidebar: auto-detected attributes, live node recoloring
 *   - Zoom controls + fit-to-screen
 *   - Query results count + execution time
 */
import { useState, useRef, useEffect } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  Play, RotateCcw, Table2, Network, ZoomIn, ZoomOut,
  Maximize2, Save, Lasso, Clock, Database
} from 'lucide-react'
import { FilterSidebar } from '../components/FilterSidebar'
import { ResultsTable } from '../components/ResultsTable'
import { NodeTooltip } from '../components/NodeTooltip'
import { InspectionPane } from '../components/InspectionPane'
import { AnimatePresence } from 'framer-motion'
import { graphApi, type GraphNode, type Subgraph } from '../lib/api'
import {
  getNodeColor,
  getNodeOpacity,
  type FilterState,
} from '../lib/colorScale'
import '../components/inspection.css'
import './QueryWorkspace.css'

// ── Cytoscape setup ────────────────────────────────────────────────────────────
import cytoscape from 'cytoscape'
// @ts-ignore — no types for cytoscape-fcose
import fcose from 'cytoscape-fcose'
cytoscape.use(fcose)

const EXAMPLE_QUERIES = [
  { label: 'All 4K videos',       q: "MATCH (f:File) WHERE f.resolution = '2160p' RETURN f LIMIT 200" },
  { label: 'PII files',           q: "MATCH (f:File) WHERE f.pii_detected = true RETURN f LIMIT 200" },
  { label: 'EOL applications',    q: "MATCH (f:File) WHERE f.eol_status = 'eol' RETURN f LIMIT 200" },
  { label: 'Exposed secrets',     q: "MATCH (f:File) WHERE f.contains_secrets = true RETURN f LIMIT 100" },
  { label: 'Duplicate files',     q: "MATCH (f:File) WHERE f.sha256 IS NOT NULL WITH f.sha256 AS h, collect(f) AS files WHERE size(files) > 1 UNWIND files AS f RETURN f LIMIT 200" },
  { label: 'Critical CVEs',       q: "MATCH (a:Application)-[:HAS_VULNERABILITY]->(v:Vulnerability) WHERE v.cvss_severity='critical' RETURN a, v LIMIT 100" },
]

export function QueryWorkspace() {
  const [cypher,       setCypher]       = useState(EXAMPLE_QUERIES[0].q)
  const [viewMode,     setViewMode]     = useState<'graph' | 'table'>('graph')
  const [activeFilters,setActiveFilters]= useState<FilterState[]>([])
  const [subgraph,     setSubgraph]     = useState<Subgraph>({ nodes: [], edges: [] })
  const [tableRows,    setTableRows]    = useState<Record<string, unknown>[]>([])
  const [execTime,     setExecTime]     = useState<number | null>(null)
  const [isLasso,      setIsLasso]      = useState(false)
  const [selection,    setSelection]    = useState<GraphNode[]>([])
  const [tooltipNode,  setTooltipNode]  = useState<GraphNode | null>(null)
  const [tooltipPos,   setTooltipPos]   = useState({ x: 0, y: 0 })
  const [inspecting,   setInspecting]   = useState<GraphNode | null>(null)
  const [showSaveDialog, setShowSaveDialog] = useState(false)

  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef        = useRef<Core | null>(null)

  // ── Run query ────────────────────────────────────────────────────────────────

  const { mutate: runQuery, isPending } = useMutation({
    mutationFn: async (q: string) => {
      const t0  = performance.now()
      const rows = await graphApi.query(q)
      const dt  = performance.now() - t0
      return { rows, dt }
    },
    onSuccess: ({ rows, dt }) => {
      setExecTime(dt)
      setTableRows(rows)
      setActiveFilters([])

      // Build subgraph from rows — look for node-shaped objects
      const nodes: GraphNode[] = []
      const seen = new Set<string>()
      for (const row of rows) {
        for (const val of Object.values(row)) {
          const v = val as any
          if (v && typeof v === 'object' && v.id && !seen.has(v.id)) {
            seen.add(v.id)
            nodes.push({
              id:    v.id,
              label: v.labels?.[0] ?? 'Unknown',
              name:  v.name ?? v.path ?? v.title ?? v.id,
              props: v,
            })
          }
        }
      }
      setSubgraph({ nodes, edges: [] })
    },
  })

  // ── Cytoscape init ────────────────────────────────────────────────────────────

  useEffect(() => {
    if (!containerRef.current || viewMode !== 'graph') return
    if (cyRef.current) return  // already initialized

    const cy = cytoscape({
      container: containerRef.current,
      elements:  [],
      style: [
        {
          selector: 'node',
          style: {
            'background-color': 'data(color)' as string, 'opacity': 'data(opacity)' as any,
            'border-color':      'data(color)',
            'border-width':      2,
            'border-opacity':    0.5,
            'shape':             'ellipse',
            'width':             'data(size)',
            'height':            'data(size)',
            'label':             'data(label)',
            'color':             '#e2e2f0',
            // font-size set via CSS class
            'text-valign':       'bottom',
            'text-margin-y':     4,
            'text-outline-width': 2,
            'text-outline-color': '#0a0a0f',
            'text-max-width':    100,
            'text-wrap':         'ellipsis',
            'overlay-opacity':   0,
          },
        },
        {
          selector: 'node:selected',
          style: {
            'border-width':   3,
            'border-color':   '#ffffff',
            'border-opacity': 1,
            'overlay-color':  '#ffffff',
            'overlay-padding': 4,
            'overlay-opacity': 0.08,
          },
        },
        {
          selector: 'edge',
          style: {
            'line-color':         '#1e1e2e',
            'width':              1,
            'curve-style':        'bezier',
            'overlay-opacity':    0,
          },
        },
      ],
      layout:          { name: 'preset' },
      wheelSensitivity: 0.25,
      minZoom:          0.02,   // extremely zoomed out
      maxZoom:          20,     // very close zoom
    })

    // Click → tooltip
    cy.on('tap', 'node', (e) => {
      const n  = e.target as NodeSingular
      const raw = n.data()
      const node: GraphNode = {
        id:    raw.id,
        label: raw._nodeLabel ?? 'Unknown',
        name:  raw._nodeName  ?? raw.id,
        props: raw._nodeProps ? JSON.parse(raw._nodeProps) : {},
      }
      const bb = containerRef.current!.getBoundingClientRect()
      const rp = (e as any).renderedPosition ?? { x: 0, y: 0 }
      setTooltipNode(node)
      setTooltipPos({ x: bb.left + rp.x, y: bb.top + rp.y })
    })

    // Double-click → inspect
    cy.on('dblclick', 'node', (e) => {
      const n   = e.target as NodeSingular
      const raw = n.data()
      const node: GraphNode = {
        id:    raw.id,
        label: raw._nodeLabel ?? 'Unknown',
        name:  raw._nodeName  ?? raw.id,
        props: raw._nodeProps ? JSON.parse(raw._nodeProps) : {},
      }
      setInspecting(node)
    })

    // Box selection tracking
    cy.on('select', 'node', () => {
      setSelection(cy.nodes(':selected').map(n => n.data() as GraphNode))
    })
    cy.on('unselect', 'node', () => {
      setSelection(cy.nodes(':selected').map(n => n.data() as GraphNode))
    })

    cyRef.current = cy
    return () => { cy.destroy(); cyRef.current = null }
  }, [viewMode])

  // ── Sync nodes to Cytoscape ────────────────────────────────────────────────

  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return

    cy.batch(() => {
      // Add new nodes
      for (const node of subgraph.nodes) {
        if (cy.getElementById(node.id).length) continue
        const color   = getNodeColor(node.props ?? {}, node.label, activeFilters, new Set(), node.id)
        const opacity = getNodeOpacity(node.props ?? {}, activeFilters, node.id, new Set())
        cy.add({
          data: {
            id:           node.id,
            label:        truncate(node.name, 18),
            color:        color as string,
            opacity:      String(opacity),
            size:         '28',
            _nodeLabel:   node.label,
            _nodeName:    node.name,
            _nodeProps:   JSON.stringify(node.props ?? {}),
          },
        })
      }

      // Re-run layout when nodes added
      cy.layout({
        name:              'fcose',
        animate:           true,
        animationDuration: 500,
        randomize:         false,
        nodeRepulsion:     () => 3500,
        idealEdgeLength:   () => 80,
        gravity:           0.3,
        numIter:           1500,
        tile:              true,
      } as any).run()
    })
  }, [subgraph.nodes])

  // ── Live filter recoloring ────────────────────────────────────────────────

  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return

    cy.batch(() => {
      cy.nodes().forEach(n => {
        const node = n.data() as GraphNode
        const color   = getNodeColor(node.props ?? {}, node.label, activeFilters, new Set(), node.id)
        const opacity = getNodeOpacity(node.props ?? {}, activeFilters, node.id, new Set())
        n.data('color', color)
        n.data('opacity', opacity)
      })
    })
  }, [activeFilters])

  // ── Zoom controls ─────────────────────────────────────────────────────────

  const zoomIn  = () => cyRef.current?.zoom({ level: (cyRef.current.zoom() * 1.3), renderedPosition: { x: containerRef.current!.offsetWidth/2, y: containerRef.current!.offsetHeight/2 } })
  const zoomOut = () => cyRef.current?.zoom({ level: (cyRef.current.zoom() * 0.75), renderedPosition: { x: containerRef.current!.offsetWidth/2, y: containerRef.current!.offsetHeight/2 } })
  const fitAll  = () => cyRef.current?.fit(undefined, 40)

  // ── Lasso mode ────────────────────────────────────────────────────────────

  const toggleLasso = () => {
    const cy = cyRef.current
    if (!cy) return
    if (!isLasso) {
      // Enable box selection
      cy.userPanningEnabled(false)
      cy.boxSelectionEnabled(true)
      setIsLasso(true)
    } else {
      cy.userPanningEnabled(true)
      cy.boxSelectionEnabled(false)
      setIsLasso(false)
    }
  }

  const saveSelectionAsQuery = () => {
    if (selection.length === 0) return
    setShowSaveDialog(true)
  }

  return (
    <div className="query-workspace">

      {/* ── Query bar ─────────────────────────────────────────────────── */}
      <div className="qw-querybar">
        <div className="qw-examples">
          {EXAMPLE_QUERIES.map(eq => (
            <button key={eq.label} onClick={() => setCypher(eq.q)} className="qw-example-pill">
              {eq.label}
            </button>
          ))}
        </div>
        <div className="qw-editor-row">
          <textarea
            value={cypher}
            onChange={e => setCypher(e.target.value)}
            onKeyDown={e => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') runQuery(cypher) }}
            className="qw-editor"
            placeholder="MATCH (n) RETURN n LIMIT 100"
            rows={2}
            spellCheck={false}
          />
          <div className="qw-editor-actions">
            <button
              onClick={() => runQuery(cypher)}
              disabled={isPending}
              className="qw-run-btn"
            >
              {isPending ? <div className="qw-spinner" /> : <Play size={13} />}
              {isPending ? 'Running…' : 'Run'}
            </button>
            <button onClick={() => { setSubgraph({ nodes:[], edges:[] }); setTableRows([]); setActiveFilters([]) }} className="qw-clear-btn" title="Clear results">
              <RotateCcw size={13} />
            </button>
          </div>
        </div>
        {(execTime !== null || subgraph.nodes.length > 0) && (
          <div className="qw-stats">
            {subgraph.nodes.length > 0 && <span><Database size={11} /> {subgraph.nodes.length} nodes</span>}
            {tableRows.length > 0 && <span><Table2 size={11} /> {tableRows.length} rows</span>}
            {execTime !== null && <span><Clock size={11} /> {execTime.toFixed(0)}ms</span>}
            {activeFilters.length > 0 && <span className="qw-filter-badge">{activeFilters.length} filter{activeFilters.length > 1 ? 's' : ''} active</span>}
          </div>
        )}
      </div>

      {/* ── Main area ─────────────────────────────────────────────────── */}
      <div className="qw-main">

        {/* Filter sidebar */}
        <FilterSidebar
          nodes={subgraph.nodes}
          activeFilters={activeFilters}
          onFiltersChange={setActiveFilters}
        />

        {/* Canvas / table area */}
        <div className="qw-canvas-area">

          {/* View toggle + zoom controls toolbar */}
          <div className="qw-toolbar">
            <div className="qw-view-toggle">
              <button
                onClick={() => setViewMode('graph')}
                className={`qw-toggle-btn ${viewMode === 'graph' ? 'active' : ''}`}
              >
                <Network size={13} /> Graph
              </button>
              <button
                onClick={() => setViewMode('table')}
                className={`qw-toggle-btn ${viewMode === 'table' ? 'active' : ''}`}
              >
                <Table2 size={13} /> Table
              </button>
            </div>

            {viewMode === 'graph' && (
              <div className="qw-zoom-controls">
                <button onClick={zoomIn}  className="qw-zoom-btn" title="Zoom in"><ZoomIn  size={13} /></button>
                <button onClick={zoomOut} className="qw-zoom-btn" title="Zoom out"><ZoomOut size={13} /></button>
                <button onClick={fitAll}  className="qw-zoom-btn" title="Fit all"><Maximize2 size={13} /></button>
                <button
                  onClick={toggleLasso}
                  className={`qw-zoom-btn ${isLasso ? 'qw-zoom-btn-active' : ''}`}
                  title={isLasso ? 'Exit selection mode' : 'Box select nodes'}
                >
                  <Lasso size={13} />
                </button>
                {selection.length > 0 && (
                  <button onClick={saveSelectionAsQuery} className="qw-save-sel-btn">
                    <Save size={13} /> Save {selection.length} nodes as query
                  </button>
                )}
              </div>
            )}
          </div>

          {viewMode === 'graph' ? (
            <div
              ref={containerRef}
              className={`qw-graph-canvas ${isLasso ? 'qw-lasso-mode' : ''}`}
            />
          ) : (
            <ResultsTable
              rows={tableRows}
              activeFilters={activeFilters}
              onRowClick={row => {
                // Try to find matching node and inspect it
                const nodeId = row.id as string
                if (nodeId) {
                  const node = subgraph.nodes.find(n => n.id === nodeId)
                  if (node) setInspecting(node)
                }
              }}
            />
          )}

          {/* Lasso mode overlay hint */}
          {isLasso && (
            <div className="qw-lasso-hint">
              Draw a box to select nodes → save as a new query
            </div>
          )}
        </div>
      </div>

      {/* Tooltip */}
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
          />
        )}
      </AnimatePresence>

      {/* Save selection dialog */}
      {showSaveDialog && (
        <SaveSelectionDialog
          nodes={selection}
          onSave={(name, q) => {
            // POST to saved queries API
            fetch('/api/queries', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ name, cypher: q, tags: ['from-selection'] }),
            })
            setShowSaveDialog(false)
            setSelection([])
            cyRef.current?.nodes(':selected').unselect()
          }}
          onClose={() => setShowSaveDialog(false)}
        />
      )}
    </div>
  )
}

// ── Save selection dialog ──────────────────────────────────────────────────────

function SaveSelectionDialog({ nodes, onSave, onClose }: {
  nodes:   GraphNode[]
  onSave:  (name: string, cypher: string) => void
  onClose: () => void
}) {
  const [name, setName] = useState(`Selection — ${nodes.length} nodes`)
  const ids = nodes.map(n => `'${n.id}'`).join(', ')
  const q   = `MATCH (n) WHERE n.id IN [${ids}] RETURN n`

  return (
    <div className="qw-dialog-overlay" onClick={onClose}>
      <div className="qw-dialog" onClick={e => e.stopPropagation()}>
        <h3>Save selection as query</h3>
        <p className="qw-dialog-sub">{nodes.length} nodes selected</p>
        <input value={name} onChange={e => setName(e.target.value)} className="qw-dialog-input" placeholder="Query name" />
        <textarea value={q} readOnly className="qw-dialog-cypher" rows={3} />
        <div className="qw-dialog-actions">
          <button onClick={onClose} className="qw-dialog-cancel">Cancel</button>
          <button onClick={() => onSave(name, q)} className="qw-dialog-save">Save query</button>
        </div>
      </div>
    </div>
  )
}

function truncate(s: string, n: number) {
  return s.length > n ? s.slice(0, n) + '…' : s
}
