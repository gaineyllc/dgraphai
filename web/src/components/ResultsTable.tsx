/**
 * ResultsTable — tabular view of graph query results.
 * Switchable with the graph canvas view.
 * Sortable columns, filterable rows, export to CSV/JSON.
 */
import { useState, useMemo } from 'react'
import { ArrowUpDown, ArrowUp, ArrowDown, Download } from 'lucide-react'
import type { FilterState } from '../lib/colorScale'

interface Props {
  rows:          Record<string, unknown>[]
  activeFilters: FilterState[]
  onRowClick?:   (row: Record<string, unknown>) => void
}

export function ResultsTable({ rows, activeFilters, onRowClick }: Props) {
  const [sortKey, setSortKey]   = useState<string | null>(null)
  const [sortDir, setSortDir]   = useState<'asc' | 'desc'>('asc')
  const [search, setSearch]     = useState('')

  const columns = useMemo(() => {
    if (rows.length === 0) return []
    return Object.keys(rows[0])
  }, [rows])

  const filtered = useMemo(() => {
    let result = rows
    // Apply active filters
    if (activeFilters.length > 0) {
      result = result.filter(row => {
        return activeFilters.some(f => {
          const val = row[f.attribute]
          return val !== undefined && f.values.has(val as string)
        })
      })
    }
    // Text search
    if (search) {
      const q = search.toLowerCase()
      result = result.filter(row =>
        Object.values(row).some(v => String(v ?? '').toLowerCase().includes(q))
      )
    }
    return result
  }, [rows, activeFilters, search])

  const sorted = useMemo(() => {
    if (!sortKey) return filtered
    return [...filtered].sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey]
      const cmp = String(av ?? '') < String(bv ?? '') ? -1 : String(av ?? '') > String(bv ?? '') ? 1 : 0
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [filtered, sortKey, sortDir])

  const handleSort = (col: string) => {
    if (sortKey === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortKey(col); setSortDir('asc') }
  }

  const exportCSV = () => {
    const header = columns.join(',')
    const body   = sorted.map(r => columns.map(c => JSON.stringify(r[c] ?? '')).join(',')).join('\n')
    const blob   = new Blob([header + '\n' + body], { type: 'text/csv' })
    const url    = URL.createObjectURL(blob)
    const a      = document.createElement('a'); a.href = url; a.download = 'results.csv'; a.click()
  }

  if (rows.length === 0) {
    return <div className="rt-empty">No results. Run a query to see data.</div>
  }

  return (
    <div className="results-table-wrap">
      <div className="rt-toolbar">
        <input
          value={search} onChange={e => setSearch(e.target.value)}
          placeholder="Search results…"
          className="rt-search"
        />
        <div className="rt-info">
          {sorted.length !== rows.length
            ? `${sorted.length} of ${rows.length} rows`
            : `${rows.length} rows`}
        </div>
        <button onClick={exportCSV} className="rt-export" title="Export CSV">
          <Download size={13} /> CSV
        </button>
      </div>

      <div className="rt-scroll">
        <table className="rt-table">
          <thead>
            <tr>
              {columns.map(col => (
                <th key={col} onClick={() => handleSort(col)} className="rt-th">
                  <span>{col.replace(/_/g, ' ')}</span>
                  {sortKey === col
                    ? sortDir === 'asc' ? <ArrowUp size={11} /> : <ArrowDown size={11} />
                    : <ArrowUpDown size={11} className="rt-sort-icon" />
                  }
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, i) => {
              const isHighlighted = activeFilters.length > 0 && activeFilters.some(f => {
                const val = row[f.attribute]
                return val !== undefined && f.values.has(val as string)
              })
              return (
                <tr
                  key={i}
                  onClick={() => onRowClick?.(row)}
                  className={`rt-row ${isHighlighted ? 'rt-row-highlight' : ''} ${activeFilters.length > 0 && !isHighlighted ? 'rt-row-dim' : ''}`}
                >
                  {columns.map(col => (
                    <td key={col} className="rt-td">
                      <CellValue col={col} value={row[col]} />
                    </td>
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function CellValue({ col, value }: { col: string; value: unknown }) {
  if (value === null || value === undefined) return <span className="rt-null">—</span>

  if (col === 'size_bytes') {
    const n = Number(value)
    if (n > 1e9) return <span>{(n/1e9).toFixed(2)} GB</span>
    if (n > 1e6) return <span>{(n/1e6).toFixed(1)} MB</span>
    return <span>{(n/1e3).toFixed(0)} KB</span>
  }

  if (col === 'eol_status') {
    if (value === 'eol') return <span className="badge badge-red">EOL</span>
    if (value === 'supported') return <span className="badge badge-green">Supported</span>
  }

  if (col === 'cvss_severity') {
    const c: Record<string,string> = {critical:'badge-red',high:'badge-orange',medium:'badge-yellow',low:'badge-green'}
    return <span className={`badge ${c[String(value)]??'badge-gray'}`}>{String(value).toUpperCase()}</span>
  }

  if (typeof value === 'boolean') {
    if (col === 'pii_detected' || col === 'contains_secrets' || col === 'actively_exploited') {
      return value ? <span className="badge badge-red">Yes</span> : <span className="rt-null">No</span>
    }
    return <span>{value ? 'Yes' : 'No'}</span>
  }

  const s = String(value)
  if (s.length > 60) {
    return <span title={s} className="rt-truncate">{s.slice(0, 58)}…</span>
  }
  return <span>{s}</span>
}
