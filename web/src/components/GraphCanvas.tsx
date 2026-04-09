// @ts-nocheck
/**
 * GraphCanvas — interactive Cytoscape.js graph visualization.
 *
 * Features:
 *   - Force-directed physics layout (fcose)
 *   - Node type → color + shape mapping
 *   - Click to expand neighbors
 *   - Hover tooltips
 *   - Zoom/pan with mouse
 *   - Minimap (coming)
 */
import { useEffect, useRef, useCallback } from 'react'
import cytoscape from 'cytoscape'
import fcose from 'cytoscape-fcose'
import type { Subgraph, GraphNode, GraphEdge } from '../lib/api'

cytoscape.use(fcose)

// ── Node type styling ─────────────────────────────────────────────────────────

const NODE_STYLES: Record<string, { color: string; shape: string }> = {
  File:          { color: '#4f8ef7', shape: 'ellipse' },
  Directory:     { color: '#8b5cf6', shape: 'round-rectangle' },
  Person:        { color: '#f472b6', shape: 'ellipse' },
  FaceCluster:   { color: '#ec4899', shape: 'ellipse' },
  Location:      { color: '#34d399', shape: 'diamond' },
  Organization:  { color: '#fbbf24', shape: 'hexagon' },
  Topic:         { color: '#22d3ee', shape: 'ellipse' },
  Application:   { color: '#fb923c', shape: 'round-rectangle' },
  Vendor:        { color: '#a78bfa', shape: 'hexagon' },
  Vulnerability: { color: '#f87171', shape: 'star' },
  Certificate:   { color: '#4ade80', shape: 'diamond' },
  Default:       { color: '#6b7280', shape: 'ellipse' },
}

const EDGE_COLORS: Record<string, string> = {
  CHILD_OF:          '#252535',
  DUPLICATE_OF:      '#f87171',
  SIMILAR_TO:        '#4f8ef7',
  MENTIONS:          '#22d3ee',
  DEPICTS:           '#f472b6',
  CONTAINS_FACE:     '#ec4899',
  HAS_VULNERABILITY: '#f87171',
  MADE_BY:           '#fbbf24',
  Default:           '#252535',
}

function nodeStyle(label: string) {
  return NODE_STYLES[label] ?? NODE_STYLES.Default
}

function edgeColor(type: string) {
  return EDGE_COLORS[type] ?? EDGE_COLORS.Default
}

// ── Component ──────────────────────────────────────────────────────────────────

interface Props {
  data: Subgraph
  selectedId?: string
  onNodeClick?: (node: GraphNode) => void
  onNodeClickPos?: (node: GraphNode, pos: { x: number; y: number }) => void
  onNodeExpand?: (id: string) => void
  className?: string
}

export function GraphCanvas({
  data,
  selectedId,
  onNodeClick,
  onNodeExpand,
  className = '',
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const cyRef         = useRef<Core | null>(null)
  const props         = { onNodeClickPos }   // capture for closure

  // Initialise Cytoscape once
  useEffect(() => {
    if (!containerRef.current) return

    const cy = cytoscape({
      container: containerRef.current,
      elements: [],
      style: [
        {
          selector: 'node',
          style: {
            'background-color':  'data(color)',
            'border-color':      'data(color)',
            'border-width':      2,
            'border-opacity':    0.6,
            'shape':             'data(shape)',
            'width':             'data(size)',
            'height':            'data(size)',
            'label':             'data(label)',
            'color':             '#e2e2f0',
            'font-size':         11,
            'text-valign':       'bottom',
            'text-margin-y':     4,
            'text-outline-width':2,
            'text-outline-color':'#0a0a0f',
            'text-max-width':    120,
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
          },
        },
        {
          selector: 'node.dimmed',
          style: { opacity: 0.25 },
        },
        {
          selector: 'edge',
          style: {
            'line-color':          'data(color)',
            'target-arrow-color':  'data(color)',
            'target-arrow-shape':  'triangle',
            'arrow-scale':         0.8,
            'width':               1.5,
            'curve-style':         'bezier',
            'label':               'data(type)',
            'font-size':           9,
            'color':               '#55557a',
            'text-rotation':       'autorotate',
            'text-outline-width':  1,
            'text-outline-color':  '#0a0a0f',
            'overlay-opacity':     0,
          },
        },
        {
          selector: 'edge.dimmed',
          style: { opacity: 0.1 },
        },
      ],
      layout: { name: 'preset' },
      wheelSensitivity: 0.3,
      minZoom: 0.1,
      maxZoom: 5,
    })

    // Double-click to expand neighbors
    cy.on('dblclick', 'node', (e) => {
      const node = e.target as NodeSingular
      onNodeExpand?.(node.id())
    })

    // Single click to select — also emit screen position for tooltip
    cy.on('tap', 'node', (e) => {
      const node      = e.target as NodeSingular
      const data      = node.data() as GraphNode
      const renderedPos = e.renderedPosition ?? { x: 0, y: 0 }
      const container = containerRef.current?.getBoundingClientRect()
      const screenPos = {
        x: (container?.left ?? 0) + renderedPos.x,
        y: (container?.top  ?? 0) + renderedPos.y,
      }
      onNodeClick?.(data)
      ;(props as any).onNodeClickPos?.(data, screenPos)
    })

    // Hover highlight
    cy.on('mouseover', 'node', (e) => {
      const node = e.target as NodeSingular
      cy.elements().not(node.neighborhood().add(node)).addClass('dimmed')
    })
    cy.on('mouseout', 'node', () => {
      cy.elements().removeClass('dimmed')
    })

    cyRef.current = cy
    return () => { cy.destroy(); cyRef.current = null }
  }, [])  // eslint-disable-line

  // Update data when it changes
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return

    const existingIds = new Set(cy.nodes().map(n => n.id()))
    const newNodes: cytoscape.ElementDefinition[] = []
    const newEdges: cytoscape.ElementDefinition[] = []

    for (const node of data.nodes) {
      if (existingIds.has(node.id)) continue
      const style = nodeStyle(node.label)
      newNodes.push({
        data: {
          id:    node.id,
          label: truncate(node.name, 24),
          color: style.color,
          shape: style.shape,
          size:  node.label === 'Directory' ? 32 : 24,
          ...node,
        },
      })
    }

    const existingEdgeIds = new Set(cy.edges().map(e => String(e.id())))
    for (const edge of data.edges) {
      const eid = String(edge.id)
      if (existingEdgeIds.has(eid)) continue
      newEdges.push({
        data: {
          id:     eid,
          source: edge.source,
          target: edge.target,
          type:   edge.type,
          color:  edgeColor(edge.type),
        },
      })
    }

    if (newNodes.length === 0 && newEdges.length === 0) return

    cy.add([...newNodes, ...newEdges])

    // Re-run layout only on new nodes
    if (newNodes.length > 0) {
      cy.layout({
        name:               'fcose',
        animate:            true,
        animationDuration:  600,
        randomize:          false,
        nodeRepulsion:      () => 4500,
        idealEdgeLength:    () => 80,
        edgeElasticity:     () => 0.45,
        gravity:            0.25,
        numIter:            2500,
        tile:               true,
      } as cytoscape.LayoutOptions).run()
    }
  }, [data])

  // Highlight selected node
  useEffect(() => {
    const cy = cyRef.current
    if (!cy || !selectedId) return
    cy.nodes().unselect()
    cy.getElementById(selectedId).select()
  }, [selectedId])

  return (
    <div
      ref={containerRef}
      className={`w-full h-full bg-[#0a0a0f] ${className}`}
    />
  )
}

function truncate(s: string, n: number) {
  return s.length > n ? s.slice(0, n) + '…' : s
}
