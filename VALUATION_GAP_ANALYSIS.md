# dgraph.ai — Gap Analysis: Current State vs $1B Production Platform
_April 2026_

A $1B SaaS valuation requires ~$80-150M ARR (7-12x multiple) or a compelling
growth story with >$20M ARR and clear path to $100M+. This document maps every
gap between what's built and what that requires.

---

## What a $1B Platform Actually Means

At that valuation level, investors expect:
- **Defensible enterprise deals** — Fortune 500 procurement can close
- **No single points of failure** — platform survives any individual component outage
- **SOC 2 Type II certification** — most enterprise deals require it
- **99.9%+ uptime SLA** — with monitoring and remediation to back it
- **Customer trust** — every data touchpoint is auditable, reversible, secure
- **Self-service growth** — product-led growth driving SMB → mid-market → enterprise
- **Partner ecosystem** — resellers, ISV integrations, marketplace listings

---

## 🔴 BLOCKER — Platform Cannot Ship Without These

### 1. Authentication & Identity
| Gap | Risk | Effort |
|---|---|---|
| No login/signup UI | Can't acquire any customer | 2 weeks |
| No password reset | Legal liability, support cost | 3 days |
| No MFA (TOTP/WebAuthn) | Blocked from every enterprise deal | 1 week |
| No email verification | Spam/abuse vector | 2 days |
| No session management | Users can't revoke access after breach | 3 days |
| No account lockout policy | Brute force vulnerability | 1 day |

**Current state:** Auth backend (JWT/OIDC) exists but zero frontend flows. No user can actually sign up, log in, reset a password, or enable MFA without custom engineering.

### 2. Data Security & Isolation
| Gap | Risk | Effort |
|---|---|---|
| Graph data not encrypted at rest | SOC 2 blocker, GDPR blocker | 1 week |
| No field-level encryption for PII nodes | GDPR/HIPAA violation | 2 weeks |
| No secrets management (vault) | Credentials in env vars | 1 week |
| No network policy enforcement | K8s egress unrestricted | 3 days |
| No data masking for non-admin roles | PII leak via graph queries | 1 week |
| Scanner agent has no auth rotation | Compromised agent = full access | 3 days |

### 3. Billing & Revenue Collection
| Gap | Risk | Effort |
|---|---|---|
| No Stripe integration | Zero revenue | 1 week |
| No dunning management | Failed payments = silent churn | 1 week |
| No subscription lifecycle | Can't upgrade/downgrade/cancel | 1 week |
| No invoice generation | Illegal in many jurisdictions for B2B | 3 days |
| No tax handling (VAT, sales tax) | Regulatory violation in EU/US states | 1 week |
| Usage metering not persisted | Can't bill retroactively if DB goes down | 2 days |

### 4. Operational Reliability
| Gap | Risk | Effort |
|---|---|---|
| No database migrations (Alembic) | Schema change = downtime | 1 week |
| asyncio tasks for indexing | Single worker failure loses all jobs | 2 weeks |
| No circuit breakers on graph queries | Slow query hangs all requests | 3 days |
| No rate limiting on API | Single tenant can DoS others | 2 days |
| No request validation/sanitization beyond Pydantic | Cypher injection possible | 1 week |
| Neo4j single node | Zero fault tolerance | 2 weeks (infra) |
| No backup strategy | Data loss = churn | 1 week |
| No health checks for scanner agents | Silent failures undetected | 2 days |

### 5. Legal & Compliance
| Gap | Risk | Effort |
|---|---|---|
| No Terms of Service enforcement | Legal exposure | 3 days |
| No Privacy Policy flow | GDPR violation | 3 days |
| No GDPR right to erasure endpoint | €20M fine risk | 1 week |
| No data processing agreement (DPA) generation | EU customer blocker | 1 day (legal) |
| No SOC 2 controls documented | Enterprise sales blocker | 3 months |
| No penetration test | Enterprise security questionnaire blocker | 2 weeks (third party) |

---

## 🟠 SERIOUS — Blocks Enterprise Sales

### 6. Enterprise Auth
| Gap | Notes |
|---|---|
| SCIM provisioning | Every Fortune 500 requires auto-provision/deprovision |
| SAML 2.0 support | ~30% of enterprises use SAML, not OIDC |
| Directory sync (AD/LDAP) | On-prem customers can't use cloud IdP |
| Group-based access control | Role sync from IdP groups |
| Just-in-time provisioning | Auto-create accounts on first SSO login |
| Break-glass emergency access | Required by most security teams |

### 7. Audit & Compliance
| Gap | Notes |
|---|---|
| Complete audit log (who queried what data, when) | Required for HIPAA, SOC 2 |
| Immutable audit trail | Log tampering must be impossible |
| SIEM export (Splunk, Datadog, Elastic, Sentinel) | Security team requirement |
| Data lineage tracking | Who accessed which file nodes |
| Export controls | Prevent bulk data exfiltration |
| Compliance report automation | Manual report generation → scheduled |
| Evidence collection for auditors | Artifact bundles for SOC 2 auditors |

### 8. Enterprise Operations
| Gap | Notes |
|---|---|
| Multi-region deployment | Data residency: EU customers can't have data in US |
| Dedicated instances (single-tenant SaaS) | Large enterprises demand isolation |
| Private cloud deployment (air-gapped) | Defense/government sector |
| Custom SLA tiers | 99.9% vs 99.95% vs 99.99% |
| SLA credits/remediation | Required by procurement |
| Disaster recovery with tested RTO/RPO | DR runbook + quarterly tests |
| Change management process | Documented deploy/rollback procedures |

### 9. Integrations (Revenue Blockers)
| Gap | Notes |
|---|---|
| Slack / Teams notifications | Alerts land nowhere useful today |
| Jira / ServiceNow ticketing | Security findings → tickets |
| PagerDuty / OpsGenie | Critical findings → on-call |
| Splunk / QRadar SIEM | Security operations workflow |
| Salesforce (for licensing/billing data) | Sales team needs it |
| Webhook reliability (retries, dead letter queue) | Current webhooks are fire-and-forget |
| Partner API with rate limits and docs | ISVs can't build on an undocumented API |

---

## 🟡 GROWTH — Required for Product-Led Growth Engine

### 10. Onboarding & Activation
| Gap | Notes |
|---|---|
| First-run wizard | Without this, 90%+ of signups never activate |
| Time-to-value < 5 minutes | Must see graph within first session |
| Empty state guidance | Every page currently shows nothing for new users |
| Interactive product tour | Replaces sales demo for SMB |
| Sample/demo tenant | Sales can't demo without running infra |
| In-app onboarding checklist | Drives activation milestones |
| Email onboarding sequence | Triggered by activation events |

### 11. Self-Service Growth
| Gap | Notes |
|---|---|
| In-app plan upgrade | Users can't upgrade without contacting sales |
| Trial management | Free trial → paid conversion flow |
| Usage alerts | "You're at 80% of your limit" drives upgrades |
| Feature previews / upgrade gates | Locked features visible to drive upgrades |
| Referral program | Product-led growth multiplier |
| In-app help/docs | Reduce support burden |
| Changelog / "what's new" | Drives re-engagement |

### 12. Collaboration & Sharing
| Gap | Notes |
|---|---|
| Shared workspaces | Multiple analysts working simultaneously |
| Comments on nodes/findings | Async investigation workflow |
| @mentions | Tag teammate on a suspicious finding |
| Query sharing / permalinks | Already have URL state, but no sharing UI |
| Notification preferences | Users choose how they want to be reached |
| Team management (invite, remove, roles) | Currently only admin can do anything |

---

## 🔵 SCALE — Infrastructure for $100M ARR

### 13. Performance at Scale
| Gap | Notes |
|---|---|
| Graph query optimization | No query planner, no index hints, no cost analysis |
| Async job queue (Celery/Temporal) | asyncio breaks at >1000 concurrent jobs |
| Graph partitioning | Single Neo4j can't handle 10B+ nodes |
| CDN for static assets | Currently serving direct, no caching |
| Database connection pooling (PgBouncer) | Postgres will hit connection limits |
| Search index (Meilisearch/Elasticsearch) | Full-text search needs a dedicated index |
| Caching layer (Redis) | Repeated graph queries hit Neo4j every time |
| GraphQL query depth limiting | Infinite recursion possible |
| Pagination on all endpoints | Some endpoints return unbounded results |

### 14. Multi-Tenancy Hardening
| Gap | Notes |
|---|---|
| Tenant isolation at graph level is property-based | A bug could expose cross-tenant data |
| No tenant-level resource quotas enforced at infra layer | One tenant can starve others |
| No per-tenant graph namespacing (true isolation) | vs. property-scoping |
| Scanner agent authentication tied to tenant | Currently uses static tokens |
| Cross-tenant data leakage audit | Has never been tested |

### 15. Observability
| Gap | Notes |
|---|---|
| No Prometheus metrics | Can't SLA without metrics |
| No distributed tracing (OpenTelemetry) | Can't debug latency in production |
| No structured logging with correlation IDs | Support debugging is impossible |
| No real-time dashboard (Grafana) | Engineering flying blind |
| No alerting on infra metrics | Don't know when things break |
| No error budget tracking | Can't manage SLOs |
| No synthetic monitoring | Don't know if product is up from customer POV |

### 16. Developer Ecosystem
| Gap | Notes |
|---|---|
| No public API docs | Partners can't build on the platform |
| No Python SDK | Data science customers can't integrate |
| No TypeScript/JS SDK | Web developers can't integrate |
| No CLI | Power users have no programmatic access |
| No sandbox/dev environment | Testing against production is dangerous |
| No API versioning strategy | Breaking changes will break integrations |
| No rate limiting with clear headers | Partners can't build reliable integrations |
| No webhook signature verification | Security risk for all integrations |

---

## 🟣 COMPETITIVE — Required to Win Against Wiz, Varonis, Rubrik

### 17. Security Differentiation
| Gap | Notes |
|---|---|
| No real-time threat detection | Just batch enrichment; Wiz does real-time |
| No attack path analysis | "How would an attacker move through this graph?" |
| No exposure scoring per asset | Single risk score per node |
| No lateral movement detection | Graph traversal for suspicious patterns |
| No compliance posture score | % compliant vs. GDPR/HIPAA/SOC2 |
| No remediation playbooks | Finding → action → ticket → resolution |
| No SaaS security posture (SSPM) | SaaS apps connected but not assessed |

### 18. AI Differentiation
| Gap | Notes |
|---|---|
| Local Ollama only — no cloud AI fallback | Quality ceiling vs. competitors using GPT-4 |
| No fine-tuned models on customer data | The moat comes from proprietary models |
| No natural language querying of graph | "Show me files accessed by former employees" |
| No anomaly detection models | Just rule-based alerts |
| No entity resolution AI | Duplicate Person/Org nodes not automatically merged |
| No data discovery AI | Currently needs a human to interpret findings |

### 19. Platform Network Effects
| Gap | Notes |
|---|---|
| No marketplace / extension gallery | Community connectors, enrichers |
| No partner program | VARs, MSSPs, system integrators |
| No threat intelligence feeds | Enrich findings with external context |
| No community / forum | Customer success requires human touch at scale |
| No benchmark data | "You have 3x more PII than similar companies" |

---

## 📊 Summary Scorecard

| Dimension | Current | $1B Threshold | Gap |
|---|---|---|---|
| Authentication | 30% | 100% | Login UI, MFA, SCIM, SAML |
| Data Security | 40% | 100% | Encryption at rest, field masking, vault |
| Billing/Revenue | 10% | 100% | No Stripe, no invoices, no dunning |
| Reliability/SRE | 20% | 100% | No migrations, asyncio jobs, no backups |
| Observability | 5% | 100% | No metrics, no tracing, no alerting |
| Enterprise Auth | 20% | 100% | No SCIM, no SAML, no directory sync |
| Compliance/Audit | 25% | 100% | No SOC 2, no audit log, no DPA |
| Onboarding | 10% | 100% | No signup flow, no wizard, no tour |
| Self-Service Growth | 5% | 100% | No upgrades, no trials, no email |
| Integrations | 15% | 100% | No Slack, Jira, PagerDuty, SIEM |
| Performance/Scale | 25% | 100% | asyncio, no queue, no caching |
| API/SDK/Ecosystem | 10% | 100% | No docs, no SDK, no versioning |
| AI Moat | 30% | 80% | Local models only, no fine-tuning |
| Security Product | 40% | 80% | No attack paths, no posture score |
| **Overall** | **~22%** | **100%** | **~78% gap** |

---

## 🛣️ Path to $1B

### Phase 1 — Launch-Ready (3-4 months, ~$2-5M ARR possible)
1. Auth UI complete (signup, login, MFA, invite, reset)
2. Stripe billing live with working upgrade/downgrade
3. First-run wizard + demo tenant
4. Basic audit log
5. SOC 2 Type I started
6. Celery job queue replacing asyncio
7. Database backups automated
8. Prometheus + basic Grafana

### Phase 2 — Enterprise-Ready (6-9 months, ~$10-20M ARR)
1. SCIM + SAML 2.0
2. Multi-region deployment (US + EU)
3. SOC 2 Type II certification
4. SIEM integrations (Splunk, Datadog)
5. Audit log immutable + exportable
6. Python SDK + public API docs
7. Slack/Teams/Jira/PagerDuty integrations
8. GDPR right to erasure + DPA generation
9. Attack path analysis (graph traversal security queries)

### Phase 3 — Scale & Moat (12-18 months, ~$50-100M ARR)
1. Fine-tuned AI models on anonymized customer graph data
2. Natural language graph querying
3. Real-time threat detection (streaming enrichment vs. batch)
4. Partner marketplace + connector SDK public
5. Compliance posture scoring + remediation playbooks
6. Benchmark/peer comparison data
7. Platform network effects (shared threat intelligence)

---

## 🔑 The Honest Answer

**What's built is an exceptional technical foundation.** The graph schema,
scanner architecture, multi-tenant RBAC, AI enrichment pipeline, and
inventory taxonomy are genuinely differentiated and would take 18-24 months
to replicate from scratch.

**What's missing is everything a customer touches.** Auth, billing, onboarding,
notifications, audit, integrations — the "software" layer that makes the
technology into a product. Every dollar of ARR requires that layer.

**The gap is ~6-9 months of focused engineering** with a team of 5-8, targeting
Phase 1 + Phase 2. Phase 3 is a funding event story, not a pre-revenue story.

**Fastest path to $1B:** Close 2-3 anchor enterprise deals ($500K-1M ACV) with
the existing foundation under a services wrapper while Phase 1/2 ships. That
buys the runway and de-risks the valuation story.
