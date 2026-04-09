/**
 * Color scale utilities for dynamic node coloring based on filter state.
 * Maps attribute values → colors, updates live as filters change.
 */

// Base node colors by label
export const LABEL_COLORS: Record<string, string> = {
  File:          '#4f8ef7',
  Directory:     '#8b5cf6',
  Person:        '#f472b6',
  FaceCluster:   '#ec4899',
  Location:      '#34d399',
  Organization:  '#fbbf24',
  Topic:         '#22d3ee',
  Application:   '#fb923c',
  Vendor:        '#a78bfa',
  Vulnerability: '#f87171',
  Certificate:   '#4ade80',
  Default:       '#6b7280',
}

// Filter-driven color palettes — each active filter gets a hue shift
export const FILTER_HUES = [
  '#f87171', // red
  '#fb923c', // orange
  '#fbbf24', // yellow
  '#34d399', // green
  '#22d3ee', // cyan
  '#818cf8', // indigo
  '#e879f9', // pink
  '#a3e635', // lime
]

export interface FilterState {
  attribute: string
  values:    Set<string | number | boolean>
  colorIndex: number
}

export function getNodeColor(
  nodeProps: Record<string, unknown>,
  nodeLabel: string,
  activeFilters: FilterState[],
  dimmedIds: Set<string>,
  nodeId: string,
): string {
  if (dimmedIds.has(nodeId)) return '#1e1e2e'  // dimmed — almost invisible

  // If any active filter matches, use filter color
  for (const filter of activeFilters) {
    const val = nodeProps[filter.attribute]
    if (val !== undefined && filter.values.has(val as string)) {
      return FILTER_HUES[filter.colorIndex % FILTER_HUES.length]
    }
  }

  // Default label color
  return LABEL_COLORS[nodeLabel] ?? LABEL_COLORS.Default
}

export function getNodeOpacity(
  nodeProps: Record<string, unknown>,
  activeFilters: FilterState[],
  nodeId: string,
  dimmedIds: Set<string>,
): number {
  if (dimmedIds.has(nodeId)) return 0.12
  if (activeFilters.length === 0) return 1.0

  // Dim nodes that don't match any active filter
  for (const filter of activeFilters) {
    const val = nodeProps[filter.attribute]
    if (val !== undefined && filter.values.has(val as string)) return 1.0
  }
  return 0.2  // not matching any filter
}

/**
 * Extract common filterable attributes from query result nodes.
 * Returns attributes that have fewer than ~20 distinct values (categorical).
 */
export function extractFilterableAttributes(
  nodes: Array<{ props?: Record<string, unknown>; label?: string }>,
): Array<{
  attribute:    string
  type:         'categorical' | 'boolean' | 'numeric_range'
  values:       Array<{ value: string | number | boolean; count: number }>
  min?:         number
  max?:         number
}> {
  const counts: Record<string, Map<string, number>> = {}
  const types:  Record<string, Set<string>> = {}

  for (const node of nodes) {
    for (const [k, v] of Object.entries(node.props ?? {})) {
      if (v === null || v === undefined) continue
      if (k === 'id' || k === 'path' || k === 'sha256' || k.endsWith('_at')) continue

      if (!counts[k]) counts[k] = new Map()
      if (!types[k])  types[k]  = new Set()

      const vStr = String(v)
      counts[k].set(vStr, (counts[k].get(vStr) ?? 0) + 1)
      types[k].add(typeof v)
    }
  }

  const result = []

  for (const [attr, valueCounts] of Object.entries(counts)) {
    const uniqueCount = valueCounts.size
    if (uniqueCount < 2 || uniqueCount > 25) continue  // skip trivial or too-many-values

    const typeSet = types[attr]
    const isNumeric = typeSet.size === 1 && typeSet.has('number')
    const isBoolean = typeSet.size === 1 && typeSet.has('boolean')

    const values = Array.from(valueCounts.entries())
      .map(([v, count]) => ({ value: isNumeric ? Number(v) : isBoolean ? v === 'true' : v, count }))
      .sort((a, b) => b.count - a.count)

    if (isBoolean) {
      result.push({ attribute: attr, type: 'boolean' as const, values })
    } else if (isNumeric && uniqueCount > 5) {
      const nums = values.map(v => v.value as number)
      result.push({ attribute: attr, type: 'numeric_range' as const, values,
                    min: Math.min(...nums), max: Math.max(...nums) })
    } else {
      result.push({ attribute: attr, type: 'categorical' as const, values })
    }
  }

  // Sort by relevance — security/status fields first
  const PRIORITY = ['file_category','eol_status','sensitivity_level','pii_detected',
                    'contains_secrets','cvss_severity','signed','protocol','resolution']
  result.sort((a, b) => {
    const ai = PRIORITY.indexOf(a.attribute)
    const bi = PRIORITY.indexOf(b.attribute)
    if (ai >= 0 && bi >= 0) return ai - bi
    if (ai >= 0) return -1
    if (bi >= 0) return 1
    return b.values.length - a.values.length
  })

  return result.slice(0, 12)  // max 12 filter dimensions
}
