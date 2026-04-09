// @ts-nocheck
/**
 * Data Inventory — Wiz-style hierarchical drill-down.
 *
 * Flow:
 *   Root: group → top-level categories (with counts)
 *   Drill: category → subcategories (with counts) until leaf
 *   Leaf:  paginated node list — click node → right drawer
 *   Drawer: node details + "View in Graph" → navigates to /query with cypher
 *
 * URL: /inventory?cat=<id>  (bookmarkable, each level has its own URL)
 */
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useState, useMemo, useRef, useEffect } from 'react'
import {
  Search, ChevronRight, Database, Layers,
  X, ExternalLink, ArrowUpRight, Sparkles,
  AlertCircle, Loader2, CornerDownLeft
} from 'lucide-react'
import './InventoryPage.css'

// ── API ────────────────────────────────────────────────────────────────────────

const api = {
  list:    ()                              => fetch('/api/inventory').then(r => r.json()),
  detail:  (id: string, page: number, ps = 25) =>
    fetch(`/api/inventory/${id}?page=${page}&page_size=${ps}`).then(r => r.json()),
  search:  (q: string)                    => fetch(`/api/inventory/search?q=${encodeURIComponent(q)}`).then(r => r.json()),
  suggest: (q: string)                    => fetch(`/api/inventory/search/suggest?q=${encodeURIComponent(q)}&limit=8`).then(r => r.json()),
}

// ── Entry point ────────────────────────────────────────────────────────────────

export function InventoryPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const activeCat = searchParams.get('cat')

  const navigateTo = (id: string | null) =>
    id ? setSearchParams({ cat: id }) : setSearchParams({})

  return activeCat
    ? <DrillDown categoryId={activeCat} onNavigate={navigateTo} />
    : <InventoryRoot onNavigate={navigateTo} />
}

// ── Root ───────────────────────────────────────────────────────────────────────

function InventoryRoot({ onNavigate }) {
  const navigate = useNavigate()

  const { data, isLoading } = useQuery({
    queryKey: ['inventory'],
    queryFn:  api.list,
    refetchInterval: 60_000,
  })

  const groups: Record<string, any[]> = data?.groups ?? {}
  const allCats    = Object.values(groups).flat()
  const totalNodes = allCats.reduce((s, c) => s + (c.count ?? 0), 0)

  const handleNLResult = (result: any) => {
    if (result.matched_category) {
      onNavigate(result.matched_category)
    } else if (result.query_url?.startsWith('/query')) {
      navigate(result.query_url)
    }
  }

  return (
    <div className="inventory-page">
      <div className="inv-header">
        <div className="inv-header-left">
          <h1>Data Inventory</h1>
          <p>Every data category indexed across your connected sources</p>
        </div>
        <div className="inv-header-stats">
          <div className="inv-stat-pill"><Database size={12} />
            <span className="inv-stat-num">{fmt(totalNodes)}</span>
            <span className="inv-stat-label">total nodes</span>
          </div>
          <div className="inv-stat-pill"><Layers size={12} />
            <span className="inv-stat-num">{allCats.length}</span>
            <span className="inv-stat-label">categories</span>
          </div>
        </div>
      </div>

      {/* Natural language search */}
      <NLSearchBar onResult={handleNLResult} onNavigate={onNavigate} />

      {isLoading ? <LoadingSkeleton /> : (
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

        </div>
      )}
    </div>
  )
}

// ── Drill-down ─────────────────────────────────────────────────────────────────

function DrillDown({ categoryId, onNavigate }) {
  const navigate = useNavigate()
  const [page, setPage]           = useState(0)
  const [nodes, setNodes]         = useState<any[]>([])
  const [selectedNode, setSelected] = useState<any | null>(null)
  const PAGE_SIZE = 25

  // Reset when category changes
  const [prevId, setPrevId] = useState(categoryId)
  if (prevId !== categoryId) {
    setPage(0)
    setNodes([])
    setSelected(null)
    setPrevId(categoryId)
  }

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['inv-detail', categoryId, page],
    queryFn:  () => api.detail(categoryId, page, PAGE_SIZE),
    onSuccess: d => {
      setNodes(prev => page === 0 ? (d.nodes ?? []) : [...prev, ...(d.nodes ?? [])])
    },
  })

  const cat        = data?.category
  const subcats    = data?.subcategories ?? []
  const pagination = data?.pagination
  const breadcrumb = data?.breadcrumb ?? []
  const hasMore    = pagination?.has_more ?? false
  const total      = pagination?.total ?? 0

  // If this category has subcategories and no leaf nodes yet — show subcategory grid only
  const isLeaf = subcats.length === 0

  const openInGraph = (cypher?: string) => {
    const q = cypher ?? data?.query_url?.split('?q=')[1]?.split('&')[0]
    if (q) navigate(`/query?q=${q}`)
  }

  return (
    <div className="inventory-page inv-drilldown">

      {/* Breadcrumb */}
      <nav className="inv-breadcrumb">
        {breadcrumb.map((crumb, i) => (
          <span key={i} className="inv-crumb-item">
            {i > 0 && <ChevronRight size={11} className="inv-crumb-sep" />}
            <button
              className={`inv-crumb-btn ${i === breadcrumb.length - 1 ? 'inv-crumb-current' : ''}`}
              onClick={() => i < breadcrumb.length - 1
                ? (crumb.id ? onNavigate(crumb.id) : onNavigate(null))
                : undefined
              }
              disabled={i === breadcrumb.length - 1}
            >
              <span>{crumb.icon}</span> {crumb.name}
            </button>
          </span>
        ))}
      </nav>

      {isLoading && page === 0 ? <LoadingSkeleton /> : cat && (
        <AnimatePresence mode="wait">
          <motion.div
            key={categoryId}
            className="inv-detail"
            initial={{ opacity: 0, x: 12 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.14 }}
          >
            {/* Category hero */}
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
                <div className="inv-cat-count-label">nodes</div>
              </div>
              <button onClick={() => openInGraph()} className="inv-view-graph-btn">
                <ArrowUpRight size={13} /> View in Graph
              </button>
            </div>

            {/* Subcategories — shown at every non-leaf level */}
            {subcats.length > 0 && (
              <div className="inv-subcats">
                <div className="inv-section-label">Subcategories</div>
                <div className="inv-subcat-grid">
                  {subcats.map((sc, i) => (
                    <motion.button
                      key={sc.id}
                      className="inv-subcat-card"
                      style={{ '--c': sc.color } as any}
                      onClick={() => onNavigate(sc.id)}
                      initial={{ opacity: 0, y: 5 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.04 }}
                      whileHover={{ y: -2 }}
                    >
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

            {/* Node list — shown at leaf categories (no subcats) */}
            {isLeaf && (
              <div className="inv-nodes">
                <div className="inv-section-header">
                  <div className="inv-section-label">Nodes</div>
                  {nodes.length > 0 && (
                    <span className="inv-showing">
                      {nodes.length} of {fmt(total)}
                    </span>
                  )}
                </div>

                <div className="inv-node-list">
                  {nodes.map((node, i) => (
                    <motion.div
                      key={node.id ?? node.path ?? i}
                      className={`inv-node-row ${selectedNode === node ? 'inv-node-selected' : ''}`}
                      style={{ '--c': cat.color } as any}
                      onClick={() => setSelected(node === selectedNode ? null : node)}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: Math.min(i, 15) * 0.015 }}
                    >
                      <div className="inv-node-icon">{cat.icon}</div>
                      <div className="inv-node-primary">
                        <div className="inv-node-name">
                          {node.name ?? node.path?.split(/[/\\]/).pop() ?? node.id ?? 'Unknown'}
                        </div>
                        <div className="inv-node-path">
                          {node.path ?? node.source_connector ?? ''}
                        </div>
                      </div>
                      <ChevronRight size={13} className="inv-node-caret" />
                    </motion.div>
                  ))}

                  {!nodes.length && !isLoading && (
                    <div className="inv-empty-list">No nodes found in this category</div>
                  )}
                </div>

                {/* Load more */}
                {hasMore && (
                  <div className="inv-loadmore-row">
                    <button
                      className="inv-loadmore-btn"
                      onClick={() => setPage(p => p + 1)}
                      disabled={isFetching}
                    >
                      {isFetching
                        ? <><span className="inv-spinner" /> Loading…</>
                        : <>Load {Math.min(PAGE_SIZE, total - nodes.length)} more</>
                      }
                    </button>
                    <span className="inv-loadmore-meta">{nodes.length} / {fmt(total)} loaded</span>
                  </div>
                )}
                {!hasMore && nodes.length > 0 && (
                  <div className="inv-all-done">All {fmt(total)} nodes loaded</div>
                )}
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      )}

      {/* Node detail drawer */}
      <AnimatePresence>
        {selectedNode && (
          <NodeDrawer
            node={selectedNode}
            categoryColor={cat?.color}
            categoryIcon={cat?.icon}
            categoryName={cat?.name}
            onClose={() => setSelected(null)}
            onViewInGraph={() => {
              const id = selectedNode.id ?? selectedNode._id
              const nodeType = cat?.id?.includes('people') ? 'Person' : 'File'
              const q = id
                ? `MATCH (f:${nodeType}) WHERE id(f) = '${id}' RETURN f`
                : data?.category?.cypher?.replace('RETURN f', 'RETURN f LIMIT 100')
              openInGraph(encodeURIComponent(q ?? ''))
            }}
          />
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Node drawer ────────────────────────────────────────────────────────────────

function NodeDrawer({ node, categoryColor, categoryIcon, categoryName, onClose, onViewInGraph }) {
  const entries = Object.entries(node).filter(([k]) =>
    !k.startsWith('_') && k !== 'tenant_id' && k !== 'elementId'
  )

  return (
    <>
      {/* Backdrop */}
      <motion.div
        className="inv-drawer-backdrop"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        onClick={onClose}
      />
      {/* Drawer */}
      <motion.aside
        className="inv-drawer"
        initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
        transition={{ type: 'spring', damping: 28, stiffness: 260 }}
      >
        <div className="inv-drawer-header">
          <div className="inv-drawer-cat">
            <span>{categoryIcon}</span>
            <span className="inv-drawer-cat-name">{categoryName}</span>
          </div>
          <button onClick={onClose} className="inv-drawer-close"><X size={15} /></button>
        </div>

        <div className="inv-drawer-title">
          {node.name ?? node.path?.split(/[/\\]/).pop() ?? node.id ?? 'Node'}
        </div>
        {node.path && (
          <div className="inv-drawer-path">{node.path}</div>
        )}

        <button
          className="inv-drawer-graph-btn"
          style={{ '--c': categoryColor } as any}
          onClick={onViewInGraph}
        >
          <ArrowUpRight size={14} /> View in Security Graph
        </button>

        <div className="inv-drawer-divider" />

        <div className="inv-drawer-props">
          {entries.map(([k, v]) => {
            if (v === null || v === undefined) return null
            return (
              <div key={k} className="inv-drawer-prop">
                <div className="inv-drawer-prop-key">{k.replace(/_/g, ' ')}</div>
                <div className="inv-drawer-prop-val">
                  <PropValue k={k} v={v} />
                </div>
              </div>
            )
          })}
        </div>
      </motion.aside>
    </>
  )
}

function PropValue({ k, v }) {
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

// ── NL Search bar ─────────────────────────────────────────────────────────────

function NLSearchBar({ onResult, onNavigate }) {
  const navigate    = useNavigate()
  const [value,       setValue]       = useState('')
  const [suggestions, setSuggestions] = useState<any[]>([])
  const [result,      setResult]      = useState<any | null>(null)
  const [loading,     setLoading]     = useState(false)
  const [open,        setOpen]        = useState(false)
  const inputRef    = useRef<HTMLInputElement>(null)
  const debounceRef = useRef<any>(null)

  // Typeahead: fetch suggestions as user types
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (!value.trim() || value.length < 2) {
      setSuggestions([])
      setOpen(false)
      return
    }
    debounceRef.current = setTimeout(async () => {
      try {
        const s = await api.suggest(value)
        setSuggestions(s)
        setOpen(s.length > 0)
      } catch { setSuggestions([]) }
    }, 180)
  }, [value])

  const runSearch = async (q = value) => {
    if (!q.trim()) return
    setLoading(true)
    setOpen(false)
    try {
      const r = await api.search(q)
      if (r.matched_category) {
        // Any category match: navigate immediately
        onNavigate(r.matched_category)
        setValue('')
        setResult(null)
      } else {
        // No category match: show no-match card with suggestions
        setResult(r)
      }
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }

  const pickSuggestion = (s: any) => {
    setValue(s.name)
    setSuggestions([])
    setOpen(false)
    onNavigate(s.id)
  }

  const clear = () => {
    setValue('')
    setResult(null)
    setSuggestions([])
    setOpen(false)
    inputRef.current?.focus()
  }

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter')  runSearch()
    if (e.key === 'Escape') clear()
  }

  return (
    <div className="nl-search-wrap">
      {/* Search input */}
      <div className={`nl-search-bar ${open || result ? 'nl-bar-active' : ''}`}>
        <Sparkles size={14} className="nl-bar-icon" />
        <input
          ref={inputRef}
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={onKey}
          onFocus={() => suggestions.length && setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          placeholder='Search your data — try “4K HDR movies”, “exposed passwords”, “photos with faces”…'
          className="nl-search-input"
          autoComplete="off"
          spellCheck={false}
        />
        {loading && <Loader2 size={13} className="nl-bar-loading" />}
        {value && !loading && (
          <button onClick={clear} className="nl-bar-clear"><X size={12} /></button>
        )}
        <div className="nl-bar-hint">
          <CornerDownLeft size={11} /> Search
        </div>
      </div>

      {/* Typeahead dropdown */}
      <AnimatePresence>
        {open && suggestions.length > 0 && (
          <motion.div
            className="nl-suggestions"
            initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.12 }}
          >
            {suggestions.map(s => (
              <button key={s.id} className="nl-suggestion-item" onMouseDown={() => pickSuggestion(s)}>
                <span className="nl-sug-icon">{s.icon}</span>
                <span className="nl-sug-name">{s.name}</span>
                <span className="nl-sug-desc">{s.description}</span>
                <ChevronRight size={11} className="nl-sug-arrow" />
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* No-match card — category not found, offer suggestions + Graph escape */}
      <AnimatePresence>
        {result && !result.matched_category && (
          <motion.div
            className="nl-result-card"
            initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
          >
            <div className="nl-result-header">
              <AlertCircle size={13} className="nl-result-icon" />
              <span>No data category found for <strong>“{value}”</strong></span>
              {result.no_match_query_url && (
                <button
                  onClick={() => { navigate(result.no_match_query_url); clear() }}
                  className="nl-result-run"
                  title="Search the graph for this term"
                >
                  Search Graph <ArrowUpRight size={11} />
                </button>
              )}
              <button onClick={clear} className="nl-result-close"><X size={12} /></button>
            </div>
            {result.suggestions?.length > 0 && (
              <div className="nl-result-suggestions">
                <span className="nl-result-label">Did you mean:</span>
                {result.suggestions.slice(0, 5).map(s => (
                  <button key={s.id} className="nl-result-sug"
                    style={{ '--c': s.color } as any}
                    onMouseDown={() => { onNavigate(s.id); clear() }}>
                    {s.icon} {s.name}
                  </button>
                ))}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Category card ──────────────────────────────────────────────────────────────

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
        {cat.has_children && <span className="inv-card-drill-hint">drill down →</span>}
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

function fmt(n) {
  if (!n && n !== 0) return '—'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000)     return `${(n / 1_000).toFixed(n >= 10_000 ? 0 : 1)}K`
  return n.toLocaleString()
}
function fmtSize(b) {
  if (!b) return '—'
  if (b >= 1e9) return `${(b/1e9).toFixed(1)} GB`
  if (b >= 1e6) return `${(b/1e6).toFixed(1)} MB`
  if (b >= 1e3) return `${(b/1e3).toFixed(0)} KB`
  return `${b} B`
}
