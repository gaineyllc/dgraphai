// @ts-nocheck
/**
 * Data Inventory — hierarchical drill-down with paginated node table.
 *
 * Root view: category cards with counts.
 * Category view: subcategory cards + paginated node table with column schema.
 * URL: /inventory → /inventory?cat=video-media → /inventory?cat=video-4k
 */
import { useQuery, useInfiniteQuery } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useState, useMemo } from 'react'
import {
  Search, ChevronRight, Database, Layers,
  ChevronLeft, ExternalLink, ArrowUpRight,
  FileText, HardDrive, AlertTriangle, MoreHorizontal
} from 'lucide-react'
import './InventoryPage.css'

// ── API ────────────────────────────────────────────────────────────────────────

const api = {
  list:    () => fetch('/api/inventory').then(r => r.json()),
  detail:  (id: string, page: number, pageSize = 25) =>
    fetch(`/api/inventory/${id}?page=${page}&page_size=${pageSize}`).then(r => r.json()),
}

// ── Root view ──────────────────────────────────────────────────────────────────

export function InventoryPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const activeCat = searchParams.get('cat')

  if (activeCat) {
    return (
      <CategoryDrillDown
        categoryId={activeCat}
        onNavigate={id => setSearchParams(id ? { cat: id } : {})}
      />
    )
  }
  return <InventoryRoot onNavigate={id => setSearchParams({ cat: id })} />
}

// ── Root ───────────────────────────────────────────────────────────────────────

function InventoryRoot({ onNavigate }) {
  const [search, setSearch] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['inventory'],
    queryFn:  api.list,
    refetchInterval: 60_000,
  })

  const groups: Record<string, any[]> = data?.groups ?? {}

  const filtered = useMemo(() => {
    if (!search.trim()) return groups
    const q = search.toLowerCase()
    const out: Record<string, any[]> = {}
    for (const [g, cats] of Object.entries(groups)) {
      const matching = cats.filter(c =>
        c.name.toLowerCase().includes(q) ||
        c.description.toLowerCase().includes(q) ||
        c.tags?.some((t: string) => t.includes(q))
      )
      if (matching.length) out[g] = matching
    }
    return out
  }, [groups, search])

  const allCats    = Object.values(groups).flat()
  const totalNodes = allCats.reduce((s, c) => s + (c.count ?? 0), 0)

  return (
    <div className="inventory-page">
      <div className="inv-header">
        <div className="inv-header-left">
          <h1>Data Inventory</h1>
          <p>Every data category indexed across your connected sources</p>
        </div>
        <div className="inv-header-stats">
          <div className="inv-stat-pill">
            <Database size={12} />
            <span className="inv-stat-num">{fmt(totalNodes)}</span>
            <span className="inv-stat-label">total nodes</span>
          </div>
          <div className="inv-stat-pill">
            <Layers size={12} />
            <span className="inv-stat-num">{allCats.length}</span>
            <span className="inv-stat-label">categories</span>
          </div>
        </div>
      </div>

      <div className="inv-search-row">
        <div className="inv-search">
          <Search size={13} />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Filter categories…"
          />
          {search && <button className="inv-search-clear" onClick={() => setSearch('')}>✕</button>}
        </div>
      </div>

      {isLoading ? (
        <LoadingSkeleton />
      ) : (
        <div className="inv-groups">
          {Object.entries(filtered).map(([group, cats]) => {
            const groupTotal = cats.reduce((s, c) => s + (c.count ?? 0), 0)
            return (
              <div key={group} className="inv-group">
                <div className="inv-group-header">
                  <span className="inv-group-title">{group}</span>
                  <span className="inv-group-count">{fmt(groupTotal)} nodes · {cats.length} categories</span>
                </div>
                <div className="inv-grid">
                  {cats.map((cat, i) => (
                    <CategoryCard key={cat.id} cat={cat} index={i} onClick={() => onNavigate(cat.id)} />
                  ))}
                </div>
              </div>
            )
          })}
          {Object.keys(filtered).length === 0 && search && (
            <div className="inv-no-results">No categories match <strong>"{search}"</strong></div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Drill-down view ────────────────────────────────────────────────────────────

function CategoryDrillDown({ categoryId, onNavigate }) {
  const navigate = useNavigate()
  const [page, setPage]       = useState(0)
  const [loadedNodes, setLoaded] = useState<any[]>([])
  const PAGE_SIZE = 25

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['inventory-detail', categoryId, page],
    queryFn:  () => api.detail(categoryId, page, PAGE_SIZE),
    keepPreviousData: true,
    onSuccess: (d) => {
      if (page === 0) {
        setLoaded(d.nodes ?? [])
      } else {
        setLoaded(prev => [...prev, ...(d.nodes ?? [])])
      }
    },
  })

  // Reset when category changes
  const prevCatRef = { current: categoryId }
  if (prevCatRef.current !== categoryId) {
    setPage(0)
    setLoaded([])
  }

  const loadMore = () => setPage(p => p + 1)

  const cat         = data?.category
  const subcats     = data?.subcategories ?? []
  const cols        = data?.columns ?? []
  const pagination  = data?.pagination
  const breadcrumb  = data?.breadcrumb ?? []
  const hasMore     = pagination?.has_more ?? false
  const total       = pagination?.total ?? 0

  const openInGraph = () => {
    if (data?.query_url) navigate(data.query_url)
  }

  return (
    <div className="inventory-page">
      {/* Breadcrumb */}
      <div className="inv-breadcrumb">
        {breadcrumb.map((crumb, i) => (
          <span key={i} className="inv-crumb">
            {i > 0 && <ChevronRight size={11} className="inv-crumb-sep" />}
            <button
              className={`inv-crumb-btn ${i === breadcrumb.length - 1 ? 'inv-crumb-active' : ''}`}
              onClick={() => {
                if (crumb.id === null) onNavigate(null)
                else if (i < breadcrumb.length - 1) onNavigate(crumb.id)
              }}
            >
              {crumb.icon} {crumb.name}
            </button>
          </span>
        ))}
      </div>

      {isLoading && page === 0 ? (
        <LoadingSkeleton />
      ) : (
        <AnimatePresence mode="wait">
          <motion.div
            key={categoryId}
            initial={{ opacity: 0, x: 10 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -10 }}
            transition={{ duration: 0.15 }}
            className="inv-detail"
          >
            {/* Category header */}
            {cat && (
              <div className="inv-detail-header" style={{ '--c': cat.color } as any}>
                <div className="inv-detail-icon"
                  style={{ background: `${cat.color}18`, border: `1px solid ${cat.color}30` }}>
                  {cat.icon}
                </div>
                <div className="inv-detail-title-block">
                  <h2>{cat.name}</h2>
                  <p>{cat.description}</p>
                </div>
                <div className="inv-detail-count-block">
                  <div className="inv-detail-count" style={{ color: cat.color }}>
                    {total !== null ? fmt(total) : '—'}
                  </div>
                  <div className="inv-detail-count-label">nodes</div>
                </div>
                <button onClick={openInGraph} className="inv-open-graph" title="Open in graph explorer">
                  <ArrowUpRight size={13} /> View in graph
                </button>
              </div>
            )}

            {/* Subcategories */}
            {subcats.length > 0 && (
              <div className="inv-subcats-section">
                <div className="inv-section-title">Subcategories</div>
                <div className="inv-subcat-grid">
                  {subcats.map((sc, i) => (
                    <motion.button
                      key={sc.id}
                      className="inv-subcat-card"
                      style={{ '--c': sc.color } as any}
                      onClick={() => { setPage(0); setLoaded([]); onNavigate(sc.id) }}
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.04 }}
                      whileHover={{ y: -1 }}
                    >
                      <span className="inv-subcat-icon">{sc.icon}</span>
                      <div className="inv-subcat-body">
                        <div className="inv-subcat-name">{sc.name}</div>
                        <div className="inv-subcat-desc">{sc.description}</div>
                      </div>
                      <div className="inv-subcat-count-block">
                        <div className="inv-subcat-count" style={{ color: sc.color }}>
                          {sc.count !== null && sc.count !== undefined ? fmt(sc.count) : '—'}
                        </div>
                        <div className="inv-subcat-count-label">nodes</div>
                      </div>
                      <ChevronRight size={13} className="inv-subcat-arrow" />
                    </motion.button>
                  ))}
                </div>
              </div>
            )}

            {/* Node table */}
            <div className="inv-nodes-section">
              <div className="inv-section-header">
                <div className="inv-section-title">
                  {subcats.length > 0 ? 'All nodes in this category' : 'Nodes'}
                </div>
                <div className="inv-section-meta">
                  {loadedNodes.length > 0 && (
                    <span className="inv-showing">
                      Showing {loadedNodes.length} of {total !== null ? fmt(total) : '?'}
                    </span>
                  )}
                </div>
              </div>

              {cols.length > 0 && loadedNodes.length > 0 ? (
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
                      {loadedNodes.map((node, i) => (
                        <motion.tr
                          key={node.id ?? node.path ?? i}
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          transition={{ delay: Math.min(i, 10) * 0.02 }}
                          className="inv-tr"
                        >
                          {cols.map(col => (
                            <td key={col.key} className={`inv-td inv-td-${col.kind}`}>
                              <CellValue kind={col.kind} value={node[col.key]} />
                            </td>
                          ))}
                          <td className="inv-td-action">
                            <button
                              className="inv-node-link"
                              onClick={() => navigate(`/query?q=${encodeURIComponent(`MATCH (f) WHERE id(f) = '${node.id}' RETURN f`)}`)}
                              title="View in graph"
                            >
                              <ExternalLink size={11} />
                            </button>
                          </td>
                        </motion.tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : isLoading ? null : (
                <div className="inv-empty-table">No nodes found in this category</div>
              )}

              {/* Load more */}
              {hasMore && (
                <div className="inv-load-more-wrap">
                  <button
                    className="inv-load-more"
                    onClick={loadMore}
                    disabled={isFetching}
                  >
                    {isFetching
                      ? <><span className="inv-spinner" /> Loading…</>
                      : <>Load {Math.min(PAGE_SIZE, total - loadedNodes.length)} more nodes</>
                    }
                  </button>
                  <span className="inv-load-progress">
                    {loadedNodes.length} / {fmt(total)} loaded
                  </span>
                </div>
              )}

              {!hasMore && loadedNodes.length > 0 && (
                <div className="inv-all-loaded">
                  All {fmt(total)} nodes loaded
                </div>
              )}
            </div>
          </motion.div>
        </AnimatePresence>
      )}
    </div>
  )
}

// ── Cell renderer ──────────────────────────────────────────────────────────────

function CellValue({ kind, value }) {
  if (value === null || value === undefined) return <span className="inv-cell-null">—</span>

  if (kind === 'bool') {
    return value
      ? <span className="inv-badge inv-badge-green">Yes</span>
      : <span className="inv-badge inv-badge-gray">No</span>
  }
  if (kind === 'badge') {
    return <span className="inv-badge inv-badge-blue">{String(value)}</span>
  }
  if (kind === 'size') {
    return <span className="inv-cell-mono">{fmtSize(Number(value))}</span>
  }
  if (kind === 'date') {
    const d = new Date(value)
    return isNaN(d.getTime())
      ? <span className="inv-cell-mono">{String(value)}</span>
      : <span className="inv-cell-date" title={d.toISOString()}>{d.toLocaleDateString()}</span>
  }
  if (kind === 'path') {
    const s = String(value)
    const parts = s.split(/[/\\]/)
    const short = parts.length > 3
      ? '…/' + parts.slice(-2).join('/')
      : s
    return <span className="inv-cell-path" title={s}>{short}</span>
  }
  // text default
  const s = String(value)
  return <span className="inv-cell-text" title={s.length > 60 ? s : undefined}>
    {s.length > 60 ? s.slice(0, 60) + '…' : s}
  </span>
}

// ── Category card (root) ───────────────────────────────────────────────────────

function CategoryCard({ cat, index, onClick }) {
  return (
    <motion.button
      className="inv-card"
      style={{ '--c': cat.color } as any}
      onClick={onClick}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.025, duration: 0.18 }}
      whileHover={{ y: -2 }}
    >
      <div className="inv-card-icon-wrap"
        style={{ background: `${cat.color}14`, border: `1px solid ${cat.color}25` }}>
        <span className="inv-card-icon">{cat.icon}</span>
      </div>
      <div className="inv-card-body">
        <div className="inv-card-name">{cat.name}</div>
        <div className="inv-card-desc">{cat.description}</div>
        {cat.has_children && <div className="inv-card-drill">subcategories available</div>}
      </div>
      <div className="inv-card-count-block">
        <div className="inv-card-count" style={{ color: cat.count != null ? cat.color : '#35354a' }}>
          {cat.count != null ? fmt(cat.count) : '—'}
        </div>
        <div className="inv-card-count-label">nodes</div>
        <ChevronRight size={12} className="inv-card-arrow" />
      </div>
    </motion.button>
  )
}

// ── Skeleton ───────────────────────────────────────────────────────────────────

function LoadingSkeleton() {
  return (
    <div className="inv-groups">
      {[5, 3, 4].map((n, gi) => (
        <div key={gi} className="inv-group">
          <div className="inv-group-header">
            <div className="inv-skel inv-skel-title" />
            <div className="inv-skel inv-skel-badge" />
          </div>
          <div className="inv-grid">
            {Array.from({ length: n }).map((_, i) => (
              <div key={i} className="inv-card inv-card-skel">
                <div className="inv-skel inv-skel-icon" />
                <div className="inv-card-body">
                  <div className="inv-skel inv-skel-name" />
                  <div className="inv-skel inv-skel-desc" />
                </div>
                <div className="inv-skel inv-skel-count" />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function fmt(n: number) {
  if (!n && n !== 0) return '—'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000)     return `${(n / 1_000).toFixed(n >= 10_000 ? 0 : 1)}K`
  return n.toLocaleString()
}

function fmtSize(bytes: number) {
  if (!bytes) return '—'
  if (bytes >= 1e9) return `${(bytes / 1e9).toFixed(1)} GB`
  if (bytes >= 1e6) return `${(bytes / 1e6).toFixed(1)} MB`
  if (bytes >= 1e3) return `${(bytes / 1e3).toFixed(0)} KB`
  return `${bytes} B`
}
