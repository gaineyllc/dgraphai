// @ts-nocheck
/**
 * PageShell — shared page scaffolding.
 *
 * Provides:
 *   <PageShell>          — wraps a page with consistent padding + max-width
 *   <PageHeader>         — title, subtitle, optional actions
 *   <Skeleton>           — animated loading placeholder
 *   <SkeletonCard>       — card-shaped skeleton
 *   <SkeletonTable>      — table skeleton with header + rows
 *   <EmptyState>         — zero-data state with icon, title, description, CTA
 *   <ErrorState>         — error state with retry button
 *   <PageErrorBoundary>  — React error boundary that shows ErrorState instead of white screen
 */
import React, { Component, type ReactNode } from 'react'
import { AlertCircle, RefreshCw, Inbox } from 'lucide-react'
import './PageShell.css'

// ── Skeleton primitives ────────────────────────────────────────────────────────

interface SkeletonProps {
  width?:   string | number
  height?:  string | number
  rounded?: boolean
  className?: string
}

export function Skeleton({ width = '100%', height = 16, rounded = false, className = '' }: SkeletonProps) {
  return (
    <div
      className={`skeleton ${className}`}
      style={{
        width:        typeof width  === 'number' ? `${width}px`  : width,
        height:       typeof height === 'number' ? `${height}px` : height,
        borderRadius: rounded ? '9999px' : 'var(--radius-xs)',
      }}
    />
  )
}

export function SkeletonText({ lines = 3, lastWidth = '60%' }: { lines?: number; lastWidth?: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} height={13} width={i === lines - 1 ? lastWidth : '100%'} />
      ))}
    </div>
  )
}

export function SkeletonCard({ height = 120 }: { height?: number }) {
  return (
    <div className="skeleton-card" style={{ height }}>
      <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
        <Skeleton width={36} height={36} rounded />
        <div style={{ flex: 1 }}>
          <Skeleton height={13} width="40%" style={{ marginBottom: 6 }} />
          <Skeleton height={11} width="60%" />
        </div>
      </div>
      <Skeleton height={11} />
    </div>
  )
}

export function SkeletonTable({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="skeleton-table">
      {/* Header */}
      <div className="skeleton-table-header">
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} height={11} width={`${60 + Math.random() * 40}%`} />
        ))}
      </div>
      {/* Rows */}
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="skeleton-table-row">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} height={13} width={`${40 + Math.random() * 50}%`} />
          ))}
        </div>
      ))}
    </div>
  )
}

export function SkeletonGrid({ count = 6, minWidth = 200 }: { count?: number; minWidth?: number }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(auto-fill, minmax(${minWidth}px, 1fr))`, gap: 12 }}>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  )
}

// ── Empty state ────────────────────────────────────────────────────────────────

interface EmptyStateProps {
  icon?:    ReactNode
  title:    string
  desc?:    string
  action?:  { label: string; onClick: () => void }
  compact?: boolean
}

export function EmptyState({ icon, title, desc, action, compact = false }: EmptyStateProps) {
  return (
    <div className={`empty-state-wrap ${compact ? 'compact' : ''}`}>
      {icon && (
        <div className="empty-state-icon-wrap">
          {icon}
        </div>
      )}
      {!icon && (
        <div className="empty-state-icon-wrap">
          <Inbox size={28} />
        </div>
      )}
      <div className="empty-state-title">{title}</div>
      {desc && <div className="empty-state-desc">{desc}</div>}
      {action && (
        <button className="btn btn-primary btn-sm" onClick={action.onClick}>
          {action.label}
        </button>
      )}
    </div>
  )
}

// ── Error state ────────────────────────────────────────────────────────────────

interface ErrorStateProps {
  title?:   string
  message?: string
  onRetry?: () => void
  compact?: boolean
}

export function ErrorState({ title = 'Something went wrong', message, onRetry, compact = false }: ErrorStateProps) {
  return (
    <div className={`error-state-wrap ${compact ? 'compact' : ''}`}>
      <div className="error-state-icon">
        <AlertCircle size={28} />
      </div>
      <div className="error-state-title">{title}</div>
      {message && <div className="error-state-desc">{message}</div>}
      {onRetry && (
        <button className="btn btn-secondary btn-sm" onClick={onRetry}>
          <RefreshCw size={13} /> Try again
        </button>
      )}
    </div>
  )
}

// ── Page error boundary ────────────────────────────────────────────────────────

interface ErrorBoundaryState { error: Error | null }

export class PageErrorBoundary extends Component<
  { children: ReactNode; name?: string },
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[PageErrorBoundary]', error, info)
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <ErrorState
            title={`${this.props.name ?? 'Page'} failed to load`}
            message={this.state.error.message}
            onRetry={() => this.setState({ error: null })}
          />
        </div>
      )
    }
    return this.props.children
  }
}

// ── Page header ────────────────────────────────────────────────────────────────

interface PageHeaderProps {
  title:     string
  subtitle?: string
  actions?:  ReactNode
  badge?:    string
}

export function PageHeader({ title, subtitle, actions, badge }: PageHeaderProps) {
  return (
    <div className="page-header">
      <div className="page-header-left">
        <div className="page-header-title-row">
          <h1 className="page-header-title">{title}</h1>
          {badge && <span className="page-header-badge">{badge}</span>}
        </div>
        {subtitle && <p className="page-header-sub">{subtitle}</p>}
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </div>
  )
}

// ── Page shell ─────────────────────────────────────────────────────────────────

export function PageShell({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <PageErrorBoundary name="Page">
      <div className={`page-shell ${className}`}>
        {children}
      </div>
    </PageErrorBoundary>
  )
}
