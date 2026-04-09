// @ts-nocheck
/**
 * Global search — Cmd/Ctrl+K opens full-screen search over all node types.
 * Falls back to graph query when no search index is configured.
 * Uses /api/search endpoint; backend routes to Meilisearch/OpenSearch if available,
 * otherwise runs a graph full-text query.
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Search, X, FileText, User, Shield, Code, Archive, Loader2 } from 'lucide-react'
import './GlobalSearch.css'

const TYPE_ICONS: Record<string, any> = {
  File:          FileText,
  Person:        User,
  Vulnerability: Shield,
  Application:   Code,
  Certificate:   Archive,
}

const api = {
  search: (q: string, limit = 20) =>
    apiFetch(`/api/search?q=${encodeURIComponent(q)}&limit=${limit}`, {
      headers: { Authorization: `Bearer ${localStorage.getItem('dgraphai_token')}` },
    }).then(r => r.json()),
}

interface SearchResult {
  id:          string
  node_type:   string
  name:        string
  path?:       string
  summary?:    string
  highlight?:  string
  score?:      number
}

export function GlobalSearch() {
  const navigate  = useNavigate()
  const [open,    setOpen]    = useState(false)
  const [query,   setQuery]   = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [selected,setSelected]= useState(0)
  const inputRef  = useRef<HTMLInputElement>(null)
  const debounce  = useRef<any>(null)

  // Cmd+K / Ctrl+K to open
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setOpen(v => !v)
      }
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  // Focus input when opened
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50)
    else { setQuery(''); setResults([]) }
  }, [open])

  // Debounced search
  useEffect(() => {
    clearTimeout(debounce.current)
    if (!query.trim() || query.length < 2) { setResults([]); return }
    debounce.current = setTimeout(async () => {
      setLoading(true)
      try {
        const data = await api.search(query)
        setResults(data.results || [])
        setSelected(0)
      } catch { setResults([]) }
      finally { setLoading(false) }
    }, 200)
  }, [query])

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSelected(s => Math.min(s + 1, results.length - 1)) }
    if (e.key === 'ArrowUp')   { e.preventDefault(); setSelected(s => Math.max(s - 1, 0)) }
    if (e.key === 'Enter'   )  { e.preventDefault(); openResult(results[selected]) }
  }

  const openResult = (r: SearchResult) => {
    if (!r) {
      // Fall back to graph query
      navigate(`/query?q=${encodeURIComponent(`MATCH (n) WHERE toLower(n.name) CONTAINS toLower('${query}') RETURN n LIMIT 50`)}`)
    } else {
      navigate(`/query?q=${encodeURIComponent(`MATCH (n:${r.node_type}) WHERE id(n) = '${r.id}' RETURN n`)}`)
    }
    setOpen(false)
  }

  return (
    <>
      {/* Trigger button in sidebar/header */}
      <button className="gs-trigger" onClick={() => setOpen(true)} title="Search (⌘K)">
        <Search size={13} />
        <span>Search…</span>
        <kbd>⌘K</kbd>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div className="gs-overlay"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={() => setOpen(false)}>
            <motion.div className="gs-panel"
              initial={{ opacity: 0, y: -20, scale: .97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.15 }}
              onClick={e => e.stopPropagation()}>

              {/* Search input */}
              <div className="gs-input-wrap">
                <Search size={16} className="gs-search-icon" />
                <input
                  ref={inputRef}
                  value={query}
                  onChange={e => setQuery(e.target.value)}
                  onKeyDown={onKey}
                  placeholder="Search files, people, findings, applications…"
                  className="gs-input"
                  spellCheck={false}
                />
                {loading && <Loader2 size={14} className="gs-loading" />}
                {query && !loading && (
                  <button onClick={() => setQuery('')} className="gs-clear"><X size={13} /></button>
                )}
              </div>

              {/* Results */}
              {results.length > 0 ? (
                <div className="gs-results">
                  {results.map((r, i) => {
                    const Icon = TYPE_ICONS[r.node_type] || FileText
                    return (
                      <button key={r.id}
                        className={`gs-result ${i === selected ? 'gs-selected' : ''}`}
                        onClick={() => openResult(r)}
                        onMouseEnter={() => setSelected(i)}>
                        <div className="gs-result-icon"><Icon size={14} /></div>
                        <div className="gs-result-body">
                          <div className="gs-result-name"
                            dangerouslySetInnerHTML={{ __html: r.highlight || r.name }} />
                          <div className="gs-result-meta">
                            <span className="gs-result-type">{r.node_type}</span>
                            {r.path && <span className="gs-result-path">{r.path.split(/[/\\]/).slice(-2).join('/')}</span>}
                          </div>
                        </div>
                      </button>
                    )
                  })}
                </div>
              ) : query.length >= 2 && !loading ? (
                <div className="gs-empty">
                  <p>No results for <strong>"{query}"</strong></p>
                  <button onClick={() => openResult(null)} className="gs-fallback-btn">
                    Search graph for "{query}" →
                  </button>
                </div>
              ) : null}

              {/* Footer hints */}
              <div className="gs-footer">
                <span><kbd>↑↓</kbd> navigate</span>
                <span><kbd>↵</kbd> open in graph</span>
                <span><kbd>Esc</kbd> close</span>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}



