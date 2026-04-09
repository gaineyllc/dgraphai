/**
 * FilterSidebar — dynamic attribute filter panel.
 *
 * Auto-discovers filterable attributes from query results.
 * Each filter changes the color of matching nodes live.
 * Multiple filters can be active simultaneously — each gets a different color.
 *
 * Filter types:
 *   Categorical: colored pill buttons for each value (click to highlight)
 *   Boolean:     toggle switch
 *   Numeric:     range slider (min/max)
 */
import { useState, useCallback } from 'react'
import { Filter, X, RotateCcw } from 'lucide-react'
import { extractFilterableAttributes, FILTER_HUES, type FilterState } from '../lib/colorScale'
import type { GraphNode } from '../lib/api'

interface Props {
  nodes:          GraphNode[]
  activeFilters:  FilterState[]
  onFiltersChange:(filters: FilterState[]) => void
}

export function FilterSidebar({ nodes, activeFilters, onFiltersChange }: Props) {
  const attributes = extractFilterableAttributes(
    nodes.map(n => ({ props: n.props, label: n.label }))
  )

  const toggleValue = useCallback((
    attribute: string,
    value:     string | number | boolean,
  ) => {
    const existing  = activeFilters.find(f => f.attribute === attribute)
    const colorIndex = activeFilters.length

    if (existing) {
      const newValues = new Set(existing.values)
      if (newValues.has(value)) {
        newValues.delete(value)
        if (newValues.size === 0) {
          onFiltersChange(activeFilters.filter(f => f.attribute !== attribute))
        } else {
          onFiltersChange(activeFilters.map(f =>
            f.attribute === attribute ? { ...f, values: newValues } : f
          ))
        }
      } else {
        newValues.add(value)
        onFiltersChange(activeFilters.map(f =>
          f.attribute === attribute ? { ...f, values: newValues } : f
        ))
      }
    } else {
      onFiltersChange([...activeFilters, {
        attribute,
        values:     new Set([value]),
        colorIndex,
      }])
    }
  }, [activeFilters, onFiltersChange])

  const clearAll = () => onFiltersChange([])

  const isActive = (attribute: string, value: unknown) => {
    const f = activeFilters.find(f => f.attribute === attribute)
    return f ? f.values.has(value as string) : false
  }

  const filterColor = (attribute: string) => {
    const f = activeFilters.find(f => f.attribute === attribute)
    return f ? FILTER_HUES[f.colorIndex % FILTER_HUES.length] : undefined
  }

  if (attributes.length === 0) {
    return (
      <div className="filter-sidebar filter-sidebar-empty">
        <div className="fs-header">
          <Filter size={14} />
          <span>Filters</span>
        </div>
        <div className="fs-empty">Run a query to see filters</div>
      </div>
    )
  }

  return (
    <div className="filter-sidebar">
      <div className="fs-header">
        <Filter size={14} />
        <span>Filters</span>
        {activeFilters.length > 0 && (
          <button onClick={clearAll} className="fs-clear" title="Clear all filters">
            <RotateCcw size={12} />
            <span>{activeFilters.length}</span>
          </button>
        )}
      </div>

      <div className="fs-body">
        {attributes.map(attr => {
          const accentColor = filterColor(attr.attribute)
          const label       = attr.attribute.replace(/_/g, ' ')

          return (
            <div key={attr.attribute} className="fs-group" style={{
              borderLeftColor: accentColor ?? 'transparent',
            }}>
              <div className="fs-attr-name">{label}</div>

              {attr.type === 'categorical' && (
                <div className="fs-pills">
                  {attr.values.slice(0, 10).map(({ value, count }) => {
                    const active = isActive(attr.attribute, value)
                    return (
                      <button
                        key={String(value)}
                        onClick={() => toggleValue(attr.attribute, value)}
                        className={`fs-pill ${active ? 'fs-pill-active' : ''}`}
                        style={active ? { background: `${accentColor}20`, borderColor: accentColor, color: accentColor } : {}}
                        title={`${value} (${count})`}
                      >
                        <span className="fs-pill-val">{formatFilterValue(String(value))}</span>
                        <span className="fs-pill-count">{count}</span>
                      </button>
                    )
                  })}
                </div>
              )}

              {attr.type === 'boolean' && (
                <div className="fs-bools">
                  {attr.values.map(({ value, count }) => {
                    const active = isActive(attr.attribute, value)
                    return (
                      <button
                        key={String(value)}
                        onClick={() => toggleValue(attr.attribute, value)}
                        className={`fs-bool-btn ${active ? 'fs-bool-active' : ''}`}
                        style={active ? { borderColor: accentColor, color: accentColor } : {}}
                      >
                        {value === true || value === 'true' ? '✓ Yes' : '✗ No'}
                        <span className="fs-pill-count">{count}</span>
                      </button>
                    )
                  })}
                </div>
              )}

              {attr.type === 'numeric_range' && attr.min !== undefined && attr.max !== undefined && (
                <NumericRangeFilter
                  attribute={attr.attribute}
                  min={attr.min}
                  max={attr.max}
                  accentColor={accentColor}
                  onRangeChange={(min, max) => {
                    // For numeric ranges, encode as "min:max" value
                    const rangeKey = `${min}:${max}`
                    toggleValue(attr.attribute, rangeKey)
                  }}
                />
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function NumericRangeFilter({ attribute, min, max, accentColor, onRangeChange }: {
  attribute:     string
  min:           number
  max:           number
  accentColor:   string | undefined
  onRangeChange: (min: number, max: number) => void
}) {
  const [lo, setLo] = useState(min)
  const [hi, setHi] = useState(max)

  const fmt = (v: number) => v > 1e9 ? `${(v/1e9).toFixed(1)}G`
    : v > 1e6 ? `${(v/1e6).toFixed(1)}M`
    : v > 1e3 ? `${(v/1e3).toFixed(0)}K`
    : String(v)

  return (
    <div className="fs-range">
      <div className="fs-range-labels">
        <span style={{ color: accentColor ?? '#8888aa' }}>{fmt(lo)}</span>
        <span style={{ color: accentColor ?? '#8888aa' }}>{fmt(hi)}</span>
      </div>
      <input
        type="range" min={min} max={max} value={lo}
        onChange={e => { setLo(Number(e.target.value)); onRangeChange(Number(e.target.value), hi) }}
        className="fs-slider"
        style={{ accentColor: accentColor ?? '#4f8ef7' }}
      />
      <input
        type="range" min={min} max={max} value={hi}
        onChange={e => { setHi(Number(e.target.value)); onRangeChange(lo, Number(e.target.value)) }}
        className="fs-slider"
        style={{ accentColor: accentColor ?? '#4f8ef7' }}
      />
    </div>
  )
}

function formatFilterValue(v: string): string {
  if (v.length > 14) return v.slice(0, 12) + '…'
  return v
}
