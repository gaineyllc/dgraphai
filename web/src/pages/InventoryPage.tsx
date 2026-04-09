// @ts-nocheck
/**
 * InventoryPage — normalized data & technology taxonomy.
 *
 * Like Wiz "Technology" view: click a category → navigate to QueryWorkspace
 * with that query pre-loaded. Every navigation encodes the query in the URL.
 */
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Search, ChevronRight, Database } from 'lucide-react'
import { useState, useMemo } from 'react'
import './InventoryPage.css'

const api = {
  list: () => fetch('/api/inventory').then(r => r.json()),
}

export function InventoryPage() {
  const navigate   = useNavigate()
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
    // Navigate to QueryWorkspace with query pre-loaded in URL
    navigate(cat.query_url)
  }

  const totalCount = Object.values(groups).flat()
    .reduce((sum, c) => sum + (c.count ?? 0), 0)

  return (
    <div className="inventory-page">
      {/* Header */}
      <div className="inv-header">
        <div>
          <h1>Data Inventory</h1>
          <p>Browse all data categories — click any to explore in the graph</p>
        </div>
        <div className="inv-header-right">
          <div className="inv-total">
            <Database size={12} />
            {fmt(totalCount)} total objects
          </div>
        </div>
      </div>

      {/* Search */}
      <div className="inv-search-row">
        <div className="inv-search">
          <Search size={13} />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search data categories…"
          />
        </div>
      </div>

      {/* Groups */}
      {isLoading ? (
        <div className="inv-loading">Loading inventory…</div>
      ) : (
        <div className="inv-groups">
          {Object.entries(filtered).map(([group, cats]) => (
            <div key={group} className="inv-group">
              <div className="inv-group-title">{group}</div>
              <div className="inv-grid">
                {cats.map((cat, i) => (
                  <motion.button
                    key={cat.id}
                    className="inv-card"
                    style={{ '--c': cat.color } as any}
                    onClick={() => handleClick(cat)}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.03 }}
                    whileHover={{ y: -2 }}
                  >
                    <div className="inv-card-icon"
                      style={{ background: `${cat.color}18`, border: `1px solid ${cat.color}30` }}>
                      {cat.icon}
                    </div>
                    <div className="inv-card-body">
                      <div className="inv-card-name">{cat.name}</div>
                      <div className="inv-card-desc">{cat.description}</div>
                      {cat.tags?.length > 0 && (
                        <div className="inv-card-tags">
                          {cat.tags.map((t: string) => (
                            <span key={t} className="inv-tag">{t}</span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="inv-card-right">
                      <div className="inv-card-count" style={{ color: cat.color }}>
                        {cat.count === null || cat.count === undefined
                          ? '—'
                          : fmt(cat.count)}
                      </div>
                      <ChevronRight size={14} className="inv-card-arrow" />
                    </div>
                  </motion.button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function fmt(n: number) {
  if (!n && n !== 0) return '—'
  if (n >= 1e6) return `${(n/1e6).toFixed(1)}M`
  if (n >= 1e3) return `${(n/1e3).toFixed(1)}K`
  return String(n)
}
