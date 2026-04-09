// @ts-nocheck
/**
 * Data Inventory — normalized taxonomy of every data category in the graph.
 * Each category shows a node count. Click → QueryWorkspace filtered to those nodes.
 * URL encodes the Cypher query so every view is shareable.
 */
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Search, ChevronRight, Database, Layers } from 'lucide-react'
import { useState, useMemo } from 'react'
import './InventoryPage.css'

const api = {
  list: () => fetch('/api/inventory').then(r => r.json()),
}

export function InventoryPage() {
  const navigate        = useNavigate()
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

  const handleClick = (cat: any) => {
    navigate(cat.query_url)
  }

  // Summary stats
  const allCats     = Object.values(groups).flat()
  const totalNodes  = allCats.reduce((s, c) => s + (c.count ?? 0), 0)
  const totalGroups = Object.keys(groups).length

  return (
    <div className="inventory-page">

      {/* ── Header ── */}
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

      {/* ── Search ── */}
      <div className="inv-search-row">
        <div className="inv-search">
          <Search size={13} />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Filter categories…"
          />
          {search && (
            <button className="inv-search-clear" onClick={() => setSearch('')}>✕</button>
          )}
        </div>
      </div>

      {/* ── Groups ── */}
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
                  <span className="inv-group-count">
                    {fmt(groupTotal)} nodes · {cats.length} categories
                  </span>
                </div>
                <div className="inv-grid">
                  {cats.map((cat, i) => (
                    <CategoryCard
                      key={cat.id}
                      cat={cat}
                      index={i}
                      onClick={() => handleClick(cat)}
                    />
                  ))}
                </div>
              </div>
            )
          })}
          {Object.keys(filtered).length === 0 && search && (
            <div className="inv-no-results">
              No categories match <strong>"{search}"</strong>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Category card ──────────────────────────────────────────────────────────────

function CategoryCard({ cat, index, onClick }) {
  const hasCount = cat.count !== null && cat.count !== undefined

  return (
    <motion.button
      className={`inv-card ${!hasCount ? 'inv-card-unknown' : ''}`}
      style={{ '--c': cat.color } as any}
      onClick={onClick}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.025, duration: 0.18 }}
      whileHover={{ y: -2 }}
    >
      {/* Left: icon */}
      <div className="inv-card-icon-wrap"
        style={{ background: `${cat.color}14`, border: `1px solid ${cat.color}25` }}>
        <span className="inv-card-icon">{cat.icon}</span>
      </div>

      {/* Center: name + description */}
      <div className="inv-card-body">
        <div className="inv-card-name">{cat.name}</div>
        <div className="inv-card-desc">{cat.description}</div>
      </div>

      {/* Right: node count — the prominent number */}
      <div className="inv-card-count-block">
        <div className="inv-card-count" style={{ color: hasCount ? cat.color : '#35354a' }}>
          {hasCount ? fmt(cat.count) : '—'}
        </div>
        <div className="inv-card-count-label">nodes</div>
        <ChevronRight size={12} className="inv-card-arrow" />
      </div>
    </motion.button>
  )
}

// ── Loading skeleton ───────────────────────────────────────────────────────────

function LoadingSkeleton() {
  return (
    <div className="inv-groups">
      {[6, 4, 5].map((n, gi) => (
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
