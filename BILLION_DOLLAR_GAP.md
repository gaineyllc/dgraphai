# dgraph.ai — $1B Valuation Gap Analysis
_April 9, 2026 — Honest assessment_

---

## The Math

A $1B valuation in 2026 enterprise SaaS requires one of:
- **$80–120M ARR** at 8–12x revenue multiple (mature growth)
- **$20–40M ARR** with >150% net revenue retention and clear $100M+ path (Series B/C)
- **Strategic acquisition premium** — being the only platform in a category (Wiz sold to Google for $32B at ~$500M ARR)

The Wiz comparable is instructive: they got to $100M ARR in 18 months post-launch by being first in cloud security graph. dgraph.ai's thesis is the same play in filesystem/data intelligence. The category is real. The timing window is 18–24 months before a well-funded competitor locks it down.

---

## Current State (What's Actually Built)

**38,421 lines across 216 files.** That's not vapor.

### ✅ Built and Production-Ready
| Layer | Status |
|---|---|
| Core graph schema (20 node types, 26 rel types, 216 props) | Done |
| Multi-tenant Postgres + Neo4j with RBAC/ABAC | Done |
| Local auth (signup/login/MFA/sessions/API keys/password reset/email verify) | Done |
| SCIM 2.0 + SAML 2.0 | Done |
| Stripe billing + webhook + dunning | Done |
| Alembic migrations (3, all tables present) | Done |
| Celery queue (6 queues, 7 beat tasks) | Done |
| Redis rate limiting (sliding window) | Done |
| Prometheus metrics | Done |
| Audit log (append-only, SIEM webhook) | Done |
| Go agent (SMB/local/S3/MinIO, streaming hash, offline queue) | Done |
| Go gateway (JWT validation, rate limiting, proxy) | Done |
| Go ingest (write batcher, Neo4j UNWIND) | Done |
| Rust enricher (20 secret patterns, 10 PII patterns, binary analysis) | Done |
| GDPR erasure endpoint | Done |
| Reliable webhooks (HMAC-signed, retry + DLQ) | Done |
| Helm charts (AWS/Azure/GCP/on-prem/air-gapped) | Done |
| Python SDK + TypeScript SDK | Done |
| Circuit breakers on graph queries | Done |
| GraphQL depth limiting | Done |
| JWT_SECRET validation at startup | Done |
| 307 passing tests (280 Python + 27 Go) | Done |
| Material 3 Expressive design system (HCT-derived palette) | Done |
| Severity badge system (C/H/M/L) | Done |
| First-run wizard | Done |
| Global search (⌘K) | Done |
| Notification center | Done |
| Connector scan scheduling | Done |
| Graph diff ("What Changed") | Done |
| Onboarding email sequence | Done |
| Terraform (Stripe/Okta/AWS/Neo4j modules) | Done |

---

## Gap Categories: What Actually Separates This From $1B

### 🔴 TIER 1 — Deal Killers (No Revenue Without These)

**1. Zero real customers**
This is the only gap that actually matters at the $1B threshold. Everything else is solvable with money. You can't buy customer trust or ARR.

- **What's missing:** Paying customers, usage data, NPS, churn numbers, expansion revenue
- **What's needed for $1B path:** 10 design partners → 3 paying logos → $1M ARR → Series A
- **Timeline:** 6–9 months of real selling
- **This cannot be code-solved**

**2. No production deployment**
The code works in dev. It has never run in production serving real traffic.

- **Missing:** Production Neo4j cluster (causal cluster, 3 nodes minimum)
- **Missing:** Production Postgres with PgBouncer connection pooling
- **Missing:** Production Redis cluster (not single instance)
- **Missing:** Real SSL certificates, real domain routing, real monitoring
- **Missing:** Incident response runbook — what happens at 3am when it breaks?
- **Effort:** 2–3 weeks of infrastructure work once Docker is running

**3. dgraph-proxy not built**
The air-gapped on-prem story requires a local graph store that doesn't phone home. This is called out in the architecture but doesn't exist.

- **What it is:** Go binary, local graph store (embedded Kuzu or BadgerDB), syncs delta to cloud when connected, fully offline-capable
- **Why it matters:** Government, defense, heavily regulated enterprises (banks, healthcare) require this. It's also the moat — once an agent is embedded on-prem, churn is near-zero.
- **Effort:** 4–6 weeks
- **Revenue unlocked:** Federal/defense contracts ($500K–$5M ACV each)

**4. No working demo environment**
Sales can't close without showing the product. The platform requires Docker + Neo4j + Redis running to demo anything.

- **Missing:** One-click demo instance (read-only, sample data pre-loaded)
- **Missing:** Public demo at demo.dgraph.ai (like Wiz's demo.wiz.io)
- **Missing:** Guided demo script / interactive tour
- **Effort:** 1 week (spin up with archon-indexed sample data, make read-only)

---

### 🟠 TIER 2 — Enterprise Sales Blockers ($100K+ deals need these)

**5. SOC 2 Type I certification**
Every Fortune 500 procurement checklist requires it. You can start the process now — it takes 3 months minimum.

- **What's built:** Controls are implemented (audit log, RBAC, encryption, MFA, SCIM)
- **What's missing:** Formal evidence collection, auditor engagement, policy documentation
- **Cost:** ~$15–30K for a mid-tier auditor (Vanta/Drata can automate much of it)
- **Timeline:** 3 months minimum
- **Start this now — it's on the critical path**

**6. Penetration test**
Security questionnaires at enterprise (especially finance, healthcare) require a recent pentest report.

- **Missing:** External pentest by qualified firm (Cobalt, HackerOne, NetSPI)
- **Cost:** $8–20K
- **Timeline:** 2–4 weeks
- **Start after production deployment**

**7. Data residency / multi-region**
EU enterprise customers cannot have their data processed in US datacenters (GDPR Article 44–46).

- **What's built:** Helm charts for EU deployment, GDPR erasure
- **What's missing:** Actual EU region deployment + data residency controls in the UI
- **Missing:** Data processing agreement (DPA) template
- **Effort:** 1 week infra + 1 day legal (DPA template is standard)

**8. Dedicated/single-tenant SaaS tier**
Large enterprises ($250K+ ACV) will require their own instance. "We share infrastructure with other companies" kills deals.

- **What's built:** Air-gapped Helm values, on-prem deployment scripts
- **What's missing:** Automated provisioning of dedicated instances (a control plane to spin them up)
- **Effort:** 3–4 weeks (Terraform-driven instance provisioning API)

**9. Security questionnaire automation**
Every enterprise deal involves a 200-question security questionnaire. You need pre-filled answers, preferably in a tool like Vanta or SafeBase.

- **Missing entirely**
- **Effort:** 1 week to set up Vanta + populate answers from existing controls
- **Multiplier:** Halves the sales cycle on security reviews

**10. CVE/vulnerability database integration**
The security page shows "Critical CVEs" but there's no live CVE feed. It's showing zeros.

- **What's built:** `cve_sync` Celery task exists
- **What's missing:** Actual NVD API integration, CVE-to-software matching against graph, real exploit data
- **Effort:** 2 weeks
- **This is a demo killer** — the flagship security page shows no data

---

### 🟡 TIER 3 — Product-Led Growth Engine (Required for $10M+ ARR)

**11. SDK publishing**
Both SDKs are built but not published.

- **Missing:** `pip install dgraphai` (PyPI)
- **Missing:** `npm install @dgraphai/sdk` (npm)
- **Missing:** SDK documentation site
- **Effort:** 2 days (PyPI/npm accounts, CI/CD publish job in release.yml)
- **Why it matters:** Developers who use the SDK become internal champions who push procurement

**12. Integration ecosystem**
Wiz grew rapidly by being in every customer's existing toolchain. dgraph.ai is currently isolated.

| Integration | Why | Effort |
|---|---|---|
| Splunk app | SIEM customers want findings in Splunk | 2 weeks |
| Microsoft Sentinel connector | Azure shops | 1 week |
| Jira integration (findings → tickets) | Workflow closure | 1 week |
| Slack/Teams (already in notifications) | ✅ Exists | Done |
| VS Code extension | Devs can query graph from editor | 3 weeks |
| GitHub Action (scan on push) | DevSecOps workflow | 1 week |

**13. Graph visualization — competitive gap**
The graph is the core product. Currently using Cytoscape with basic rendering. Wiz's security graph is a significant competitive advantage.

- **Missing:** Force-directed layouts with physics (already have fcose but needs tuning)
- **Missing:** Node clustering/grouping (hundreds of nodes → group by type)
- **Missing:** Path highlighting (attack path visualization — critical for security)
- **Missing:** Timeline playback (graph state at time T vs time T+7d)
- **Missing:** Geographic map overlay (nodes grouped by datacenter/region)
- **Effort:** 3–4 weeks of graph engineering

**14. AI query assistant**
The platform has Ollama integration but it's only in the enrichment pipeline. There's no natural language → Cypher for the query interface.

- **What's built:** NL search for inventory (resolves to categories)
- **What's missing:** NL → Cypher synthesis for the query workspace ("show me all files modified in the last 7 days that contain PII")
- **Effort:** 2 weeks (Ollama + schema-aware prompt → Cypher)
- **This is the WOW demo moment** that closes SMB deals

**15. Mobile-responsive UI**
Current UI is desktop-only. CISOs and security managers check dashboards on mobile/tablet.

- **Missing:** Responsive breakpoints on all pages
- **Effort:** 1 week

---

### ⚪ TIER 4 — Scale Infrastructure (Required at $10M+ ARR)

These don't matter until you have the customers. Don't work on them now.

| Gap | Needed When | Effort |
|---|---|---|
| Graph partitioning (10B+ nodes) | ~$5M ARR | 3 months |
| Multi-region active-active | ~$10M ARR | 2 months |
| Zero-downtime deploys (blue/green) | First enterprise SLA | 2 weeks |
| PgBouncer connection pooling | >500 concurrent users | 3 days |
| Search index (Meilisearch) already have NL search | ~$2M ARR | 1 week |
| Synthetic monitoring (Playwright + uptime) | Before SOC 2 | 1 week |
| Error budget / SLO tracking | Before SOC 2 | 1 week |
| Distributed tracing (OpenTelemetry) | >10 services running | 2 weeks |
| True graph-level tenant isolation (Neo4j databases per tenant) | Regulated verticals | 3 weeks |

---

## The Honest Priority Stack

**Right now (April–June 2026):**
1. **Get Docker running → spin up production** (week 1)
2. **Index real data with archon → seed the demo** (week 1–2)
3. **Ship demo.dgraph.ai** — public, read-only, impressive sample data (week 2)
4. **Fix CVE feed** — the security page can't show zeros in a demo (week 2–3)
5. **Publish SDKs to PyPI + npm** (2 days, do it this week)
6. **Start SOC 2 with Vanta** — longest lead time item, start now (ongoing)
7. **Build dgraph-proxy** — the air-gapped moat (week 3–6)
8. **Get 3 design partners** — offer free until SOC 2 (ongoing)
9. **NL → Cypher in query workspace** — the demo moment (week 4–5)
10. **Pentest after first design partner** (week 6–8)

**July–September 2026 (Series A prep):**
- 3 paying logos, ~$150K ARR minimum
- SOC 2 Type I in hand
- 2 enterprise integrations shipped (Splunk + Jira)
- EU region live
- Dedicated instance provisioning working

**At Series A ($3–8M raised):**
- Hire: 1 enterprise AE, 1 solutions engineer, 1 security-focused backend engineer
- Scale to 10 customers, $1M ARR
- Start SOC 2 Type II (6 month observation period)

**Series B (~$20–40M ARR):**
- That's the $1B valuation conversation

---

## Competitive Moat Assessment

| Moat | Current Strength | Risk |
|---|---|---|
| **On-prem agent** (Go, trust boundary) | Strong — exists, hard to replicate | Medium — Wiz could add on-prem |
| **Rust enricher** (memory-safe, air-gapped) | Strong — unique for air-gapped | Low — nobody else targeting this |
| **Format-based inventory** (149 categories) | Medium — differentiated taxonomy | Medium — Wiz Inventory is close |
| **Graph + NL search** | Medium — built, not demo'd | High — several competitors doing this |
| **M3 design system** | Weak moat — UI is table stakes | N/A |
| **Multi-cloud Helm** | Medium — turnkey deploy story | Medium — every K8s app does this |

**The real moat is the on-prem agent + air-gapped enrichment.** That's the wedge that government/defense/financial services will pay for. No cloud-native competitor can serve that market. That's where the $1B story lives.

---

## Summary Score

| Dimension | Score | Notes |
|---|---|---|
| Product completeness | 7/10 | Core built, gaps in CVE/demo/proxy |
| Enterprise readiness | 5/10 | Auth/SCIM/SAML done; SOC 2 missing |
| Design & UX | 7/10 | M3 system done; needs page-by-page migration |
| Distribution | 1/10 | Zero customers, zero SDKs published |
| Moat | 6/10 | On-prem story is real; needs to be proven |
| Infrastructure | 4/10 | Never run in production |
| **Overall** | **5/10** | Strong foundation, zero distribution |

**The code is not the bottleneck. Distribution is.**
