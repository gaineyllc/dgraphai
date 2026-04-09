// @ts-nocheck
/**
 * Usage & Billing page.
 * Shows current usage by tier, estimated monthly cost, plan details,
 * and a tier breakdown explanation.
 */
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  Database, Zap, Brain, Users, GitBranch,
  TrendingUp, CheckCircle, AlertTriangle, XCircle,
  ArrowUpRight, Info
} from 'lucide-react'
import './UsagePage.css'

const api = {
  snapshot: () => apiFetch('/api/usage/snapshot').then(r => r.json()),
  plans:    () => apiFetch('/api/usage/plans').then(r => r.json()),
  rates:    () => apiFetch('/api/usage/rates').then(r => r.json()),
  limits:   () => apiFetch('/api/usage/limits').then(r => r.json()),
}

const TIER_META = {
  standard:    { icon: Database, color: '#6b7280', label: 'Standard nodes'    },
  enrichable:  { icon: Database, color: '#4f8ef7', label: 'Enrichable nodes'  },
  ai_enriched: { icon: Brain,    color: '#a855f7', label: 'AI-enriched nodes' },
  identity:    { icon: Users,    color: '#f472b6', label: 'Identified people' },
  graph_edges: { icon: GitBranch,color: '#34d399', label: 'Graph relationships'},
  platform:    { icon: Zap,      color: '#fbbf24', label: 'Platform fee'      },
}

export function UsagePage() {
  const { data: snap, isLoading: snapLoading } = useQuery({
    queryKey: ['usage-snapshot'],
    queryFn:  api.snapshot,
    refetchInterval: 60_000,
  })
  const { data: plans = [] } = useQuery({ queryKey: ['usage-plans'], queryFn: api.plans })
  const { data: rates }      = useQuery({ queryKey: ['usage-rates'], queryFn: api.rates })
  const { data: limits }     = useQuery({ queryKey: ['usage-limits'], queryFn: api.limits, refetchInterval: 60_000 })

  const snapshot  = snap?.snapshot
  const cost      = snap?.cost
  const plan      = snap?.plan
  const limitsData = snap?.limits

  return (
    <div className="usage-page">
      <div className="usage-header">
        <div>
          <h1>Usage & Billing</h1>
          <p>Live usage across your knowledge graph — priced by data type and enrichment level</p>
        </div>
        {plan && (
          <div className="usage-plan-badge">
            <Zap size={12} />
            <span>{plan.name} plan</span>
          </div>
        )}
      </div>

      {/* Usage limit bar */}
      {limitsData && <LimitBar limits={limitsData} />}

      {/* Tier breakdown cards */}
      <div className="usage-section-title">Current usage</div>
      {snapLoading ? (
        <div className="usage-loading">Querying graph…</div>
      ) : snapshot ? (
        <div className="usage-tiers">
          <TierCard
            tier="standard"
            count={snapshot.standard_nodes}
            cost={cost?.line_items?.find(l => l.tier === 'standard')?.amount ?? 0}
            description="Directories, tags, collections, topics — structural metadata"
          />
          <TierCard
            tier="enrichable"
            count={snapshot.enrichable_nodes}
            cost={cost?.line_items?.find(l => l.tier === 'enrichable')?.amount ?? 0}
            description="Files and applications with metadata extracted, AI pending"
          />
          <TierCard
            tier="ai_enriched"
            count={snapshot.ai_enriched_nodes}
            cost={cost?.line_items?.find(l => l.tier === 'ai_enriched')?.amount ?? 0}
            description="Files with AI summary, vision analysis, or code review"
          />
          <TierCard
            tier="identity"
            count={snapshot.identified_people}
            cost={cost?.line_items?.find(l => l.tier === 'identity')?.amount ?? 0}
            description="People identified via face recognition"
          />
          <TierCard
            tier="graph_edges"
            count={snapshot.billed_relationships}
            cost={cost?.line_items?.find(l => l.tier === 'graph_edges')?.amount ?? 0}
            description="AI-computed graph relationships (MENTIONS, SIMILAR_TO, etc.)"
            unit="relationships"
          />
        </div>
      ) : null}

      {/* Enrichment breakdown */}
      {snapshot && (
        <div className="usage-enrichment">
          <div className="usage-section-title">AI enrichment breakdown</div>
          <div className="usage-enrich-grid">
            <EnrichStat label="Raw files (pending)"   value={snapshot.enrichment_detail?.files_raw}     color="#4f8ef7" />
            <EnrichStat label="LLM summarized"        value={snapshot.enrichment_detail?.files_enriched} color="#a855f7" />
            <EnrichStat label="Vision analyzed"       value={snapshot.enrichment_detail?.files_vision}   color="#ec4899" />
            <EnrichStat label="Code reviewed"         value={snapshot.enrichment_detail?.files_code}     color="#22d3ee" />
            <EnrichStat label="Binary assessed"       value={snapshot.enrichment_detail?.files_binary}   color="#f59e0b" />
            <EnrichStat label="Identified people"     value={snapshot.identified_people}                  color="#f472b6" />
          </div>
        </div>
      )}

      {/* Cost summary */}
      {cost && (
        <div className="usage-cost-block">
          <div className="usage-section-title">Estimated monthly cost</div>
          <div className="usage-cost-card">
            <div className="usage-cost-items">
              {cost.line_items?.map(item => {
                const meta = TIER_META[item.tier] ?? TIER_META.platform
                const Icon = meta.icon
                return item.amount > 0 ? (
                  <div key={item.tier} className="usage-cost-row">
                    <Icon size={13} style={{ color: meta.color }} />
                    <span className="usage-cost-label">{item.label}</span>
                    <span className="usage-cost-amount">${item.amount.toFixed(2)}</span>
                  </div>
                ) : null
              })}
            </div>
            <div className="usage-cost-divider" />
            {cost.discount_pct > 0 && (
              <div className="usage-cost-discount">
                <TrendingUp size={12} />
                {cost.discount_reason} — {cost.discount_pct}% off
              </div>
            )}
            <div className="usage-cost-total">
              <span>Estimated total</span>
              <span className="usage-cost-total-num">${cost.total?.toFixed(2)}<span>/mo</span></span>
            </div>
          </div>
        </div>
      )}

      {/* Tier rate card */}
      {rates && (
        <div className="usage-rates-block">
          <div className="usage-section-title">Pricing tiers</div>
          <div className="usage-rate-cards">
            {rates.tiers?.map(tier => {
              const meta = TIER_META[tier.id] ?? TIER_META.platform
              const Icon = meta.icon
              return (
                <div key={tier.id} className="usage-rate-card" style={{ '--tc': meta.color } as any}>
                  <div className="usage-rate-icon"><Icon size={16} /></div>
                  <div className="usage-rate-body">
                    <div className="usage-rate-name">{tier.name}</div>
                    <div className="usage-rate-desc">{tier.description}</div>
                    <div className="usage-rate-examples">
                      {tier.examples?.slice(0, 3).map(e => (
                        <span key={e} className="usage-rate-ex">{e}</span>
                      ))}
                      {tier.examples?.length > 3 && (
                        <span className="usage-rate-ex">+{tier.examples.length - 3} more</span>
                      )}
                    </div>
                  </div>
                  <div className="usage-rate-price">
                    <div className="usage-rate-amount">${tier.rate_per_1k.toFixed(2)}</div>
                    <div className="usage-rate-unit">{tier.unit ?? 'per 1,000 nodes'}</div>
                  </div>
                </div>
              )
            })}
          </div>

          {rates.free_relationships?.length > 0 && (
            <div className="usage-free-rels">
              <Info size={12} />
              <span>Free structural relationships (not billed):</span>
              <div className="usage-free-list">
                {rates.free_relationships.map(r => (
                  <span key={r} className="usage-rel-badge">{r}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Plans comparison */}
      {plans.length > 0 && (
        <div className="usage-plans-block">
          <div className="usage-section-title">Available plans</div>
          <div className="usage-plans-grid">
            {plans.map(p => (
              <PlanCard key={p.id} plan={p} current={plan?.id === p.id} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function TierCard({ tier, count, cost, description, unit = 'nodes' }) {
  const meta = TIER_META[tier]
  if (!meta) return null
  const Icon = meta.icon
  return (
    <motion.div className="usage-tier-card" style={{ '--tc': meta.color } as any}
      initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
      <div className="usage-tier-icon"><Icon size={18} /></div>
      <div className="usage-tier-body">
        <div className="usage-tier-name">{meta.label}</div>
        <div className="usage-tier-desc">{description}</div>
      </div>
      <div className="usage-tier-right">
        <div className="usage-tier-count">{fmt(count)}</div>
        <div className="usage-tier-unit">{unit}</div>
        {cost > 0 && <div className="usage-tier-cost">${cost.toFixed(2)}/mo</div>}
      </div>
    </motion.div>
  )
}

function EnrichStat({ label, value, color }) {
  return (
    <div className="usage-enrich-stat">
      <div className="usage-enrich-dot" style={{ background: color }} />
      <span className="usage-enrich-label">{label}</span>
      <span className="usage-enrich-val">{fmt(value ?? 0)}</span>
    </div>
  )
}

function LimitBar({ limits }) {
  const nodes = limits.nodes
  const status = nodes?.status ?? 'ok'
  const pct    = nodes?.pct ?? 0
  const StatusIcon = status === 'ok' ? CheckCircle : status === 'warning' ? AlertTriangle : XCircle
  const statusColor = { ok: '#10b981', warning: '#f59e0b', critical: '#fb923c', exceeded: '#f87171' }[status] ?? '#10b981'

  return (
    <div className="usage-limit-bar">
      <StatusIcon size={13} style={{ color: statusColor }} />
      <span className="usage-limit-label">Node usage</span>
      {nodes?.limit > 0 ? (
        <>
          <div className="usage-limit-track">
            <div
              className="usage-limit-fill"
              style={{ width: `${Math.min(100, pct ?? 0)}%`, background: statusColor }}
            />
          </div>
          <span className="usage-limit-num">{fmt(nodes.used)} / {fmt(nodes.limit)} included</span>
          {pct != null && <span className="usage-limit-pct" style={{ color: statusColor }}>{pct}%</span>}
        </>
      ) : (
        <span className="usage-limit-num">{fmt(nodes?.used ?? 0)} nodes (metered)</span>
      )}
    </div>
  )
}

function PlanCard({ plan, current }) {
  const included = (
    (plan.included?.standard_nodes ?? 0) +
    (plan.included?.enrichable_nodes ?? 0) +
    (plan.included?.ai_enriched_nodes ?? 0)
  )
  return (
    <div className={`usage-plan-card ${current ? 'usage-plan-current' : ''}`}>
      {current && <div className="usage-plan-current-badge">Current plan</div>}
      <div className="usage-plan-name">{plan.name}</div>
      <div className="usage-plan-fee">
        {plan.base_monthly_fee > 0
          ? <><span className="usage-plan-price">${plan.base_monthly_fee}</span><span>/mo</span></>
          : plan.id === 'starter' ? <span className="usage-plan-price-free">Free</span>
          : <span className="usage-plan-price-custom">Custom</span>
        }
      </div>
      <div className="usage-plan-included">
        {included > 0
          ? <span>{fmt(included)} nodes included</span>
          : <span>Unlimited</span>
        }
      </div>
      <div className="usage-plan-features">
        {Object.entries(plan.features ?? {}).slice(0, 6).map(([k, v]) => (
          <div key={k} className="usage-plan-feat">
            {v && v !== false
              ? <CheckCircle size={11} className="usage-feat-yes" />
              : <XCircle    size={11} className="usage-feat-no" />
            }
            <span>{k.replace(/_/g, ' ')}</span>
            {typeof v === 'number' && v > 0 && <span className="usage-feat-val">{v === -1 ? '∞' : v}</span>}
          </div>
        ))}
      </div>
      {!current && (
        <button className="usage-plan-upgrade">
          Upgrade <ArrowUpRight size={11} />
        </button>
      )}
    </div>
  )
}

function fmt(n: number) {
  if (!n && n !== 0) return '—'
  if (n >= 1_000_000) return `${(n/1_000_000).toFixed(1)}M`
  if (n >= 1_000)     return `${(n/1_000).toFixed(1)}K`
  return n.toLocaleString()
}



