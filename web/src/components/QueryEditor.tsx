/**
 * QueryEditor — Cypher query editor with syntax highlighting and results.
 * Built on a plain textarea with keyboard shortcuts for now.
 * Ready to swap in CodeMirror when needed.
 */
import { useState, useCallback } from 'react'
import { graphApi } from '../lib/api'
import { Play, RotateCcw } from 'lucide-react'

const EXAMPLE_QUERIES = [
  { label: 'All 4K videos',     cypher: "MATCH (f:File) WHERE f.resolution = '2160p' RETURN f.name, f.size_bytes ORDER BY f.size_bytes DESC LIMIT 20" },
  { label: 'Duplicate files',   cypher: "MATCH (f:File) WHERE f.sha256 IS NOT NULL WITH f.sha256 AS hash, collect(f.path) AS paths WHERE size(paths) > 1 RETURN hash, paths LIMIT 20" },
  { label: 'Files with secrets',cypher: "MATCH (f:File) WHERE f.contains_secrets = true RETURN f.path, f.secret_types LIMIT 20" },
  { label: 'EOL applications',  cypher: "MATCH (f:File) WHERE f.eol_status = 'eol' RETURN f.name, f.file_version, f.company_name LIMIT 20" },
  { label: 'Find by person',    cypher: "MATCH (f:File)-[:DEPICTS|MENTIONS]->(p:Person) WHERE p.name CONTAINS 'Neil' RETURN f.path, f.file_category LIMIT 20" },
]

interface Props {
  onResults?: (rows: Record<string, unknown>[]) => void
}

export function QueryEditor({ onResults }: Props) {
  const [cypher, setCypher] = useState(EXAMPLE_QUERIES[0].cypher)
  const [results, setResults] = useState<Record<string, unknown>[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [duration, setDuration] = useState<number | null>(null)

  const run = useCallback(async () => {
    if (!cypher.trim()) return
    setLoading(true)
    setError(null)
    const t0 = performance.now()
    try {
      const rows = await graphApi.query(cypher)
      setResults(rows)
      setDuration(performance.now() - t0)
      onResults?.(rows)
    } catch (e) {
      setError(String(e))
      setResults([])
    } finally {
      setLoading(false)
    }
  }, [cypher, onResults])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault()
      run()
    }
  }

  const columns = results.length > 0 ? Object.keys(results[0]) : []

  return (
    <div className="flex flex-col h-full gap-2">
      {/* Example query pills */}
      <div className="flex gap-1 flex-wrap px-3 pt-3">
        {EXAMPLE_QUERIES.map(q => (
          <button
            key={q.label}
            onClick={() => setCypher(q.cypher)}
            className="px-2 py-0.5 text-xs rounded-full border border-[#252535] text-[#8888aa] hover:text-[#e2e2f0] hover:border-[#4f8ef7] transition-colors"
          >
            {q.label}
          </button>
        ))}
      </div>

      {/* Editor */}
      <div className="relative mx-3">
        <textarea
          value={cypher}
          onChange={e => setCypher(e.target.value)}
          onKeyDown={handleKeyDown}
          spellCheck={false}
          rows={4}
          className="w-full font-mono text-sm bg-[#12121a] border border-[#252535] rounded-lg p-3 pr-20 text-[#e2e2f0] resize-none focus:outline-none focus:border-[#4f8ef7] placeholder-[#55557a]"
          placeholder="MATCH (n) RETURN n LIMIT 25"
        />
        <div className="absolute top-2 right-2 flex gap-1">
          <button
            onClick={() => { setResults([]); setError(null); setDuration(null) }}
            title="Clear results"
            className="p-1.5 text-[#55557a] hover:text-[#e2e2f0] transition-colors"
          >
            <RotateCcw size={14} />
          </button>
          <button
            onClick={run}
            disabled={loading}
            title="Run query (Ctrl+Enter)"
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#4f8ef7] text-white text-xs font-medium rounded-md hover:bg-[#3a7de6] disabled:opacity-50 transition-colors"
          >
            <Play size={12} />
            {loading ? 'Running…' : 'Run'}
          </button>
        </div>
      </div>

      {/* Status bar */}
      {(results.length > 0 || error) && (
        <div className="flex items-center gap-3 px-3 text-xs text-[#55557a]">
          {error
            ? <span className="text-[#f87171]">{error}</span>
            : <span>{results.length} rows · {duration?.toFixed(0)}ms</span>
          }
        </div>
      )}

      {/* Results table */}
      {results.length > 0 && (
        <div className="flex-1 overflow-auto mx-3 mb-3 border border-[#252535] rounded-lg">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-[#12121a] border-b border-[#252535]">
              <tr>
                {columns.map(col => (
                  <th key={col} className="px-3 py-2 text-left text-[#8888aa] font-medium whitespace-nowrap">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {results.map((row, i) => (
                <tr
                  key={i}
                  className="border-b border-[#1a1a28] hover:bg-[#12121a] transition-colors"
                >
                  {columns.map(col => (
                    <td key={col} className="px-3 py-2 text-[#e2e2f0] max-w-xs truncate">
                      {formatCell(row[col])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}
