// @ts-nocheck
/**
 * InventoryDrillDown — the drill-down view for a single inventory category.
 *
 * Shows:
 *   - Breadcrumb trail
 *   - Category hero (name, count, View in Graph)
 *   - Subcategory cards → click to go deeper
 *   - Attribute filter bar (inline, shows fields relevant to this format type)
 *   - Paginated node table with columns from the category schema
 *   - Node drawer on row click
 *
 * The attribute filter bar adds WHERE clauses to the base category Cypher.
 * "View in Graph" exports the full query including any active filters.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ChevronRight, ArrowUpRight, X, Plus,
  SlidersHorizontal, Filter, ExternalLink
} from 'lucide-react'

const api = {
  detail:     (id, page, ps = 25) =>
    fetch(`/api/inventory/${id}?page=${page}&page_size=${ps}`).then(r => r.json()),
  filterAttrs:(id) =>
    fetch(`/api/inventory/${id}/filterable-attributes`).then(r => r.json()),
  filtered:   (id, filters, page, ps = 25) =>
    fetch(`/api/inventory/${id}/filtered?page=${page}&page_size=${ps}`, {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ filters }),
    }).then(r => r.json()),
}

const FILTER_OPS: Record<string, string[]> = {
  text:   ['=','<>','CONTAINS','STARTS WITH','IS NOT NULL','IS NULL'],
  badge:  ['=','<>','CONTAINS','IS NOT NULL','IS NULL'],
  bool:   ['= true','= false'],
  num:    ['=','>','>=','<','<=','IS NOT NULL','IS NULL'],
  size:   ['>','>=','<','<='],
  date:   ['>','>=','<','<=','IS NOT NULL','IS NULL'],
  path:   ['CONTAINS','STARTS WITH','IS NOT NULL','IS NULL'],
  mono:   ['=','CONTAINS'],
}

export function InventoryDrillDown({ categoryId, onNavigate }) {
  const navigate = useNavigate()
  const [page, setPage]              = useState(0)
  const [nodes, setNodes]            = useState<any[]>([])
  const [selected, setSelected]      = useState<any | null>(null)
  const [filters, setFilters]        = useState<any[]>([])   // draft filters
  const [active, setActive]          = useState<any[]>([])   // committed filters
  const [showFilterBar, setShowFB]   = useState(false)
  const [filtCypher, setFiltCypher]  = useState<string|null>(null)
  const [filtTotal, setFiltTotal]    = useState<number|null>(null)
  const [prevCat, setPrevCat]        = useState(categoryId)
  const PAGE = 25

  if (prevCat !== categoryId) {
    setPage(0); setNodes([]); setSelected(null)
    setFilters([]); setActive([]); setFiltCypher(null); setFiltTotal(null)
    setShowFB(false); setPrevCat(categoryId)
  }

  const hasActive = active.length > 0

  // Base query
  const { data, isLoading, isFetching: baseFetch } = useQuery({
    queryKey: ['inv-detail', categoryId, page],
    queryFn:  () => api.detail(categoryId, page, PAGE),
    enabled:  !hasActive,
    onSuccess: d => { if (!hasActive) setNodes(p => page === 0 ? (d.nodes ?? []) : [...p, ...(d.nodes ?? [])]) },
  })

  // Filtered query
  const { isFetching: filtFetch } = useQuery({
    queryKey: ['inv-filtered', categoryId, active, page],
    queryFn:  () => api.filtered(categoryId, active, page, PAGE),
    enabled:  hasActive,
    onSuccess: d => {
      setNodes(p => page === 0 ? (d.nodes ?? []) : [...p, ...(d.nodes ?? [])])
      setFiltCypher(d.cypher); setFiltTotal(d.pagination?.total ?? null)
    },
  })

  // Filterable attributes for this category
  const { data: attrData } = useQuery({
    queryKey: ['inv-attrs', categoryId],
    queryFn:  () => api.filterAttrs(categoryId),
    staleTime: 5 * 60_000,
  })
  const fields   = attrData?.fields ?? []
  const cat      = data?.category
  const subcats  = data?.subcategories ?? []
  const breadcrumb = data?.breadcrumb ?? []
  const cols     = data?.columns ?? []
  const isLeaf   = subcats.length === 0
  const isFetch  = hasActive ? filtFetch : baseFetch
  const total    = hasActive ? filtTotal : (data?.pagination?.total ?? 0)
  const hasMore  = hasActive
    ? (filtTotal != null && (page + 1) * PAGE < filtTotal)
    : (data?.pagination?.has_more ?? false)
  const baseCypher = data?.query_url?.split('?q=')[1]?.split('&')[0]

  const viewInGraph = () => {
    const q = filtCypher ?? baseCypher
    if (q) navigate(`/query?q=${q}`)
  }

  const applyFilters = () => {
    const valid = filters.filter(f => f.field && f.op)
    setActive(valid); setPage(0); setNodes([])
  }

  const clearFilters = () => {
    setFilters([]); setActive([]); setPage(0); setNodes([])
    setFiltCypher(null); setFiltTotal(null)
  }

  const addFilter = () => setFilters(f => [...f, { id: Date.now(), field: '', op: '=', value: '' }])
  const updFilter = (id, patch) => setFilters(f => f.map(x => x.id === id ? {...x,...patch} : x))
  const delFilter = (id) => setFilters(f => f.filter(x => x.id !== id))

  return (
    <div className="inventory-page inv-drilldown">

      {/* ── Breadcrumb ─────────────────────────────────────────── */}
      <nav className="inv-breadcrumb">
        {breadcrumb.map((crumb, i) => (
          <span key={i} className="inv-crumb-item">
            {i > 0 && <ChevronRight size={11} className="inv-crumb-sep" />}
            <button
              className={`inv-crumb-btn ${i === breadcrumb.length - 1 ? 'inv-crumb-current' : ''}`}
              onClick={() => i < breadcrumb.length - 1 && (crumb.id ? onNavigate(crumb.id) : onNavigate(null))}
              disabled={i === breadcrumb.length - 1}
            >
              <span>{crumb.icon}</span> {crumb.name}
            </button>
          </span>
        ))}
      </nav>

      {isLoading && page === 0 ? <DrillSkeleton /> : cat && (
        <motion.div className="inv-detail" key={categoryId}
          initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.14 }}>

          {/* ── Category hero ───────────────────────────────────── */}
          <div className="inv-cat-hero" style={{ '--c': cat.color } as any}>
            <div className="inv-cat-hero-icon"
              style={{ background: `${cat.color}15`, border: `1px solid ${cat.color}28` }}>
              {cat.icon}
            </div>
            <div className="inv-cat-hero-text">
              <h2>{cat.name}</h2>
              <p>{cat.description}</p>
            </div>
            <div className="inv-cat-hero-count">
              <div className="inv-cat-count-num" style={{ color: cat.color }}>
                {total != null ? fmt(total) : '—'}
              </div>
              <div className="inv-cat-count-label">
                {hasActive ? 'filtered' : 'nodes'}
              </div>
            </div>
            <button onClick={viewInGraph} className="inv-view-graph-btn">
              <ArrowUpRight size={13} /> View in Graph
            </button>
          </div>

          {/* ── Subcategory cards ───────────────────────────────── */}
          {subcats.length > 0 && (
            <div className="inv-subcats">
              <div className="inv-section-label">Format types</div>
              <div className="inv-subcat-grid">
                {subcats.map((sc, i) => (
                  <motion.button key={sc.id} className="inv-subcat-card"
                    style={{ '--c': sc.color } as any}
                    onClick={() => onNavigate(sc.id)}
                    initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.04 }} whileHover={{ y: -2 }}>
                    <span className="inv-subcat-icon">{sc.icon}</span>
                    <div className="inv-subcat-body">
                      <div className="inv-subcat-name">{sc.name}</div>
                      <div className="inv-subcat-desc">{sc.description}</div>
                    </div>
                    <div className="inv-subcat-right">
                      <div className="inv-subcat-num" style={{ color: sc.color }}>
                        {sc.count != null ? fmt(sc.count) : '—'}
                      </div>
                      <div className="inv-subcat-label">nodes</div>
                    </div>
                    <ChevronRight size={13} className="inv-subcat-caret" />
                  </motion.button>
                ))}
              </div>
            </div>
          )}

          {/* ── Node list (leaf) ────────────────────────────────── */}
          {isLeaf && (
            <div className="inv-nodes">

              {/* Section header with filter toggle */}
              <div className="inv-section-header">
                <div className="inv-section-label">Files</div>
                <div className="inv-section-actions">
                  {hasActive && (
                    <span className="inv-filter-active-badge">
                      <Filter size={10} /> {active.length} filter{active.length > 1 ? 's' : ''} active
                      <button onClick={clearFilters} className="inv-filter-clear-btn">
                        <X size={9} />
                      </button>
                    </span>
                  )}
                  {nodes.length > 0 && (
                    <span className="inv-showing">{nodes.length} of {fmt(total ?? 0)}</span>
                  )}
                  <button
                    className={`inv-filter-toggle ${showFilterBar ? 'inv-filter-toggle-on' : ''}`}
                    onClick={() => setShowFB(v => !v)}
                    title="Filter by attributes"
                  >
                    <SlidersHorizontal size={12} />
                    Filter
                    {active.length > 0 && <span className="inv-ftog-count">{active.length}</span>}
                  </button>
                </div>
              </div>

              {/* Attribute filter bar */}
              <AnimatePresence>
                {showFilterBar && (
                  <motion.div className="inv-filter-bar"
                    initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.15 }}>

                    <div className="inv-filter-rows">
                      {filters.map(f => {
                        const fieldMeta = fields.find(x => x.key === f.field)
                        const ops = FILTER_OPS[fieldMeta?.kind ?? 'text'] ?? FILTER_OPS.text
                        return (
                          <div key={f.id} className="inv-filter-row">
                            {/* Field selector */}
                            <select
                              value={f.field}
                              onChange={e => updFilter(f.id, { field: e.target.value, op: '=', value: '' })}
                              className="inv-filter-select inv-filter-field"
                            >
                              <option value="">— attribute —</option>
                              {fields.map(fl => (
                                <option key={fl.key} value={fl.key}>{fl.label}</option>
                              ))}
                            </select>
                            {/* Operator */}
                            <select
                              value={f.op}
                              onChange={e => updFilter(f.id, { op: e.target.value })}
                              className="inv-filter-select inv-filter-op"
                            >
                              {ops.map(o => <option key={o} value={o}>{o}</option>)}
                            </select>
                            {/* Value */}
                            {f.op !== 'IS NULL' && f.op !== 'IS NOT NULL' &&
                             !f.op.startsWith('=') || (f.op === '=' && fieldMeta?.kind !== 'bool') ? (
                              f.op !== 'IS NULL' && f.op !== 'IS NOT NULL' &&
                              !f.op.includes('true') && !f.op.includes('false') && (
                                <input
                                  value={f.value}
                                  onChange={e => updFilter(f.id, { value: e.target.value })}
                                  placeholder="value"
                                  className="inv-filter-value"
                                  onKeyDown={e => e.key === 'Enter' && applyFilters()}
                                />
                              )
                            ) : null}
                            <button onClick={() => delFilter(f.id)} className="inv-filter-del">
                              <X size={10} />
                            </button>
                          </div>
                        )
                      })}
                      {filters.length === 0 && (
                        <span className="inv-filter-empty">No filters — add one to narrow results</span>
                      )}
                    </div>

                    <div className="inv-filter-footer">
                      <button onClick={addFilter} className="inv-filter-add">
                        <Plus size={11} /> Add filter
                      </button>
                      <div style={{ flex: 1 }} />
                      {hasActive && (
                        <button onClick={clearFilters} className="inv-filter-clear">Clear all</button>
                      )}
                      <button
                        onClick={applyFilters}
                        disabled={!filters.some(f => f.field && f.op)}
                        className="inv-filter-apply"
                      >
                        Apply
                      </button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Node table */}
              {cols.length > 0 && nodes.length > 0 ? (
                <div className="inv-table-wrap">
                  <table className="inv-table">
                    <thead>
                      <tr>
                        {cols.map(c => (
                          <th key={c.key} style={{ minWidth: c.width }}>{c.label}</th>
                        ))}
                        <th className="inv-th-action" />
                      </tr>
                    </thead>
                    <tbody>
                      {nodes.map((node, i) => (
                        <motion.tr key={node.id ?? node.path ?? i}
                          className={`inv-tr ${selected === node ? 'inv-tr-selected' : ''}`}
                          onClick={() => setSelected(node === selected ? null : node)}
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          transition={{ delay: Math.min(i, 8) * 0.02 }}
                        >
                          {cols.map(col => (
                            <td key={col.key} className={`inv-td inv-td-${col.kind}`}>
                              <CellValue kind={col.kind} value={node[col.key]} />
                            </td>
                          ))}
                          <td className="inv-td-action">
                            <button
                              className="inv-node-link"
                              onClick={e => {
                                e.stopPropagation()
                                const id = node.id ?? node._id
                                const q = id
                                  ? encodeURIComponent(`MATCH (f) WHERE id(f) = '${id}' RETURN f`)
                                  : (filtCypher ?? baseCypher ?? '')
                                navigate(`/query?q=${q}`)
                              }}
                              title="View in Graph"
                            >
                              <ExternalLink size={11} />
                            </button>
                          </td>
                        </motion.tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                !isLoading && !isFetch && (
                  <div className="inv-empty-list">
                    {hasActive ? 'No nodes match the applied filters' : 'No nodes in this category'}
                  </div>
                )
              )}

              {/* Load more */}
              {hasMore && (
                <div className="inv-loadmore-row">
                  <button className="inv-loadmore-btn"
                    onClick={() => setPage(p => p + 1)} disabled={isFetch}>
                    {isFetch
                      ? <><span className="inv-spinner" /> Loading…</>
                      : <>Load more</>
                    }
                  </button>
                  <span className="inv-loadmore-meta">{nodes.length} / {fmt(total ?? 0)} loaded</span>
                </div>
              )}
              {!hasMore && nodes.length > 0 && (
                <div className="inv-all-done">All {fmt(total ?? 0)} nodes loaded</div>
              )}
            </div>
          )}
        </motion.div>
      )}

      {/* ── Node drawer ──────────────────────────────────────────── */}
      <AnimatePresence>
        {selected && cat && (
          <NodeDetailDrawer
            node={selected}
            cat={cat}
            onClose={() => setSelected(null)}
            onViewInGraph={() => {
              const id = selected.id ?? selected._id
              const q  = id
                ? encodeURIComponent(`MATCH (f) WHERE id(f) = '${id}' RETURN f`)
                : (filtCypher ?? baseCypher ?? '')
              navigate(`/query?q=${q}`)
            }}
          />
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Cell renderer ──────────────────────────────────────────────────────────────

function CellValue({ kind, value }) {
  if (value === null || value === undefined) return <span className="inv-cell-null">—</span>
  if (kind === 'bool')   return <span className={`inv-badge ${value ? 'inv-badge-green' : 'inv-badge-gray'}`}>{value ? 'Yes' : 'No'}</span>
  if (kind === 'badge')  return <span className="inv-badge inv-badge-blue">{String(value)}</span>
  if (kind === 'size')   return <span className="inv-cell-mono">{fmtSize(Number(value))}</span>
  if (kind === 'num')    return <span className="inv-cell-mono">{Number(value).toLocaleString()}</span>
  if (kind === 'date') {
    const d = new Date(value)
    return isNaN(d.getTime())
      ? <span className="inv-cell-mono">{String(value)}</span>
      : <span className="inv-cell-date" title={d.toISOString()}>{d.toLocaleDateString()}</span>
  }
  if (kind === 'path') {
    const s = String(value)
    const parts = s.split(/[/\\]/)
    return <span className="inv-cell-path" title={s}>
      {parts.length > 3 ? '…/' + parts.slice(-2).join('/') : s}
    </span>
  }
  const s = String(value)
  return <span className="inv-cell-text" title={s.length > 60 ? s : undefined}>
    {s.length > 60 ? s.slice(0, 60) + '…' : s}
  </span>
}

// ── Node detail drawer ─────────────────────────────────────────────────────────

function NodeDetailDrawer({ node, cat, onClose, onViewInGraph }) {
  const entries = Object.entries(node).filter(([k]) =>
    !k.startsWith('_') && k !== 'tenant_id' && k !== 'elementId'
  )
  return (
    <>
      <motion.div className="inv-drawer-backdrop"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        onClick={onClose} />
      <motion.aside className="inv-drawer"
        initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
        transition={{ type: 'spring', damping: 28, stiffness: 260 }}>

        <div className="inv-drawer-header">
          <div className="inv-drawer-cat">
            <span>{cat.icon}</span>
            <span className="inv-drawer-cat-name">{cat.name}</span>
          </div>
          <button onClick={onClose} className="inv-drawer-close"><X size={15} /></button>
        </div>

        <div className="inv-drawer-title">
          {node.name ?? node.path?.split(/[/\\]/).pop() ?? node.id ?? 'Node'}
        </div>
        {node.path && <div className="inv-drawer-path">{node.path}</div>}

        <button className="inv-drawer-graph-btn" style={{ '--c': cat.color } as any}
          onClick={onViewInGraph}>
          <ArrowUpRight size={14} /> View in Graph
        </button>

        <div className="inv-drawer-divider" />

        <div className="inv-drawer-props">
          {entries.map(([k, v]) => {
            if (v === null || v === undefined) return null
            return (
              <div key={k} className="inv-drawer-prop">
                <div className="inv-drawer-prop-key">{k.replace(/_/g, ' ')}</div>
                <div className="inv-drawer-prop-val"><DrawerVal k={k} v={v} /></div>
              </div>
            )
          })}
        </div>
      </motion.aside>
    </>
  )
}

function DrawerVal({ k, v }) {
  const s = String(v)
  if (typeof v === 'boolean')
    return <span className={`inv-prop-badge ${v ? 'inv-badge-yes' : 'inv-badge-no'}`}>{v ? 'Yes' : 'No'}</span>
  if (k.endsWith('_at') || k.endsWith('_date') || k === 'modified' || k === 'created')
    return <span className="inv-prop-date">{new Date(s).toLocaleString()}</span>
  if (k === 'size' || k.endsWith('_size') || k.endsWith('_bytes'))
    return <span className="inv-prop-mono">{fmtSize(Number(v))}</span>
  if (s.length > 80)
    return <span className="inv-prop-long" title={s}>{s.slice(0, 80)}…</span>
  return <span className="inv-prop-text">{s}</span>
}

// ── Skeleton ───────────────────────────────────────────────────────────────────

function DrillSkeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: 20 }}>
      <div className="inv-skel" style={{ width: 300, height: 14, borderRadius: 5 }} />
      <div className="inv-skel" style={{ height: 80, borderRadius: 12 }} />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
        {[1,2,3].map(i => <div key={i} className="inv-skel" style={{ height: 70, borderRadius: 10 }} />)}
      </div>
    </div>
  )
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmt(n: number) {
  if (!n && n !== 0) return '—'
  if (n >= 1_000_000) return `${(n/1_000_000).toFixed(1)}M`
  if (n >= 1_000)     return `${(n/1_000).toFixed(n >= 10_000 ? 0 : 1)}K`
  return n.toLocaleString()
}
function fmtSize(b: number) {
  if (!b) return '—'
  if (b >= 1e9) return `${(b/1e9).toFixed(1)} GB`
  if (b >= 1e6) return `${(b/1e6).toFixed(1)} MB`
  if (b >= 1e3) return `${(b/1e3).toFixed(0)} KB`
  return `${b} B`
}
