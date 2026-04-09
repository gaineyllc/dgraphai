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
import { useState, useRef, useEffect, useMemo } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  Play, RotateCcw, Table2, Network, ZoomIn, ZoomOut,
  Maximize2, Save, Lasso, Clock, Database,
  SlidersHorizontal, Plus, X, ChevronDown
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
  const [showFilterBuilder, setShowFilterBuilder] = useState(false)
  const [attrFilters, setAttrFilters]             = useState<AttrFilter[]>([])

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
      <div className="qw-querybar" onClick={() => !showFilterBuilder && setShowFilterBuilder(true)}>
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
        {/* Attribute filter builder — appears when query bar is clicked */}
        {showFilterBuilder && (
          <AttributeFilterBuilder
            nodes={subgraph.nodes}
            filters={attrFilters}
            onChange={setAttrFilters}
            onClose={() => setShowFilterBuilder(false)}
            onApply={(filters) => {
              // Append WHERE clauses to cypher and re-run
              const extra = filters
                .filter(f => f.field && f.op)
                .map(f => {
                  const alias = f.alias || 'n'
                  const val = f.op === 'IS NULL' || f.op === 'IS NOT NULL' ? '' :
                    (f.value === 'true' || f.value === 'false' || !isNaN(Number(f.value)))
                      ? ` ${f.value}` : ` '${f.value}'`
                  return `${alias}.${f.field} ${f.op}${val}`
                })
                .join(' AND ')
              if (!extra) return
              const base = cypher.replace(/\s+WHERE\s+/i, ' WHERE ').replace(/\s+RETURN\s+/i, ' RETURN ')
              const hasWhere = /WHERE/i.test(base)
              const newQ = hasWhere
                ? base.replace(/(WHERE\s+)(.+?)(\s+RETURN)/is, `$1$2 AND ${extra}$3`)
                : base.replace(/(RETURN)/i, `WHERE ${extra} RETURN`)
              setCypher(newQ)
              runQuery(newQ)
              setShowFilterBuilder(false)
            }}
          />
        )}

        {(execTime !== null || subgraph.nodes.length > 0) && (
          <div className="qw-stats">
            {subgraph.nodes.length > 0 && <span><Database size={11} /> {subgraph.nodes.length} nodes</span>}
            {tableRows.length > 0 && <span><Table2 size={11} /> {tableRows.length} rows</span>}
            {execTime !== null && <span><Clock size={11} /> {execTime.toFixed(0)}ms</span>}
            {activeFilters.length > 0 && <span className="qw-filter-badge">{activeFilters.length} filter{activeFilters.length > 1 ? 's' : ''} active</span>}
            {attrFilters.length > 0 && <span className="qw-filter-badge">{attrFilters.length} attr filter{attrFilters.length > 1 ? 's' : ''}</span>}
            <button className="qw-filter-toggle" onClick={e => { e.stopPropagation(); setShowFilterBuilder(v => !v) }}>
              <SlidersHorizontal size={11} /> Filters
            </button>
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

// ── Attribute filter builder ───────────────────────────────────────────────────

interface AttrFilter {
  id:     string
  alias:  string
  field:  string
  op:     string
  value:  string
}

const ATTR_OPS = [
  { op: '=',           label: '= equals'          },
  { op: '<>',          label: '≠ not equals'       },
  { op: '>',           label: '> greater than'     },
  { op: '<',           label: '< less than'        },
  { op: 'CONTAINS',    label: 'contains'           },
  { op: 'STARTS WITH', label: 'starts with'        },
  { op: 'IS NULL',     label: 'is not set'         },
  { op: 'IS NOT NULL', label: 'is set'             },
]

function AttributeFilterBuilder({ nodes, filters, onChange, onClose, onApply }) {
  const idRef = useRef(0)

  // Collect all property keys seen in current result nodes
  const knownFields = useMemo(() => {
    const keys = new Set<string>()
    for (const node of nodes) {
      for (const k of Object.keys(node.props ?? {})) {
        if (!k.startsWith('_') && k !== 'tenant_id') keys.add(k)
      }
    }
    return Array.from(keys).sort()
  }, [nodes])

  // Collect aliases (node variable names) from current nodes
  const aliases = useMemo(() => {
    const s = new Set<string>()
    for (const node of nodes) s.add(node.label?.toLowerCase()[0] ?? 'n')
    s.add('f'); s.add('n'); s.add('a')
    return Array.from(s)
  }, [nodes])

  const addFilter = () => {
    onChange(prev => [...prev, { id: String(idRef.current++), alias: aliases[0] ?? 'f', field: '', op: '=', value: '' }])
  }

  const updateFilter = (id: string, patch: Partial<AttrFilter>) => {
    onChange(prev => prev.map(f => f.id === id ? { ...f, ...patch } : f))
  }

  const removeFilter = (id: string) => {
    onChange(prev => prev.filter(f => f.id !== id))
  }

  return (
    <div className="qw-attr-builder" onClick={e => e.stopPropagation()}>
      <div className="qw-attr-header">
        <SlidersHorizontal size={12} />
        <span>Add filters</span>
        <span className="qw-attr-hint">Appended to query as WHERE clauses</span>
        <button onClick={onClose} className="qw-attr-close"><X size={12} /></button>
      </div>

      <div className="qw-attr-rows">
        {filters.map(f => (
          <div key={f.id} className="qw-attr-row">
            {/* Alias selector */}
            <select
              value={f.alias}
              onChange={e => updateFilter(f.id, { alias: e.target.value })}
              className="qw-attr-select qw-attr-alias"
            >
              {aliases.map(a => <option key={a} value={a}>{a}</option>)}
            </select>
            <span className="qw-attr-dot">.</span>
            {/* Field */}
            <select
              value={f.field}
              onChange={e => updateFilter(f.id, { field: e.target.value })}
              className="qw-attr-select qw-attr-field"
            >
              <option value="">— field —</option>
              {knownFields.map(k => <option key={k} value={k}>{k}</option>)}
            </select>
            {/* Operator */}
            <select
              value={f.op}
              onChange={e => updateFilter(f.id, { op: e.target.value })}
              className="qw-attr-select qw-attr-op"
            >
              {ATTR_OPS.map(o => <option key={o.op} value={o.op}>{o.label}</option>)}
            </select>
            {/* Value */}
            {f.op !== 'IS NULL' && f.op !== 'IS NOT NULL' && (
              <input
                value={f.value}
                onChange={e => updateFilter(f.id, { value: e.target.value })}
                placeholder="value"
                className="qw-attr-value"
              />
            )}
            <button onClick={() => removeFilter(f.id)} className="qw-attr-remove"><X size={10} /></button>
          </div>
        ))}

        {filters.length === 0 && (
          <div className="qw-attr-empty">No filters yet — add one to narrow results</div>
        )}
      </div>

      <div className="qw-attr-footer">
        <button onClick={addFilter} className="qw-attr-add">
          <Plus size={11} /> Add filter
        </button>
        <button
          onClick={() => onApply(filters)}
          disabled={!filters.some(f => f.field && f.op)}
          className="qw-attr-apply"
        >
          Apply & re-run
        </button>
      </div>
    </div>
  )
}
