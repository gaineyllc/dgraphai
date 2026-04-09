# dgraph.ai — Platform Gap Audit
_Generated 2026-04-09. What's built, what's missing, what's next._

---

## ✅ Built

### Core Platform
- Multi-tenant DB (Postgres/SQLAlchemy) with RBAC + ABAC
- OIDC/JWT auth (Okta, Azure AD, Keycloak, Auth0)
- Custom roles + permissions per tenant
- Neo4j/Neptune/AuraDB graph backends
- K8s manifests + Keycloak SSO deployment

### Data Ingestion
- Scanner agent (outbound-only, SMB/local/S3/Azure connectors)
- Delta sync protocol (GraphDelta chunks)
- Offline queue for disconnected agents
- Connector SDK (S3, Azure Blob, SharePoint, GCS)
- Resumable indexing with state persistence

### AI Enrichment (local Ollama only)
- LLM: summary, document_type, sentiment, language, entities, action items
- Vision (LLaVA): scene_type, objects, people_count, text_visible, mood
- Code (qwen2.5-coder): framework, quality, tests, security_concerns
- Binary (deepseek-r1): risk_assessment, ai_category
- Face recognition (InsightFace): detection, clustering (DBSCAN), identity resolution

### Graph Schema
- 20 node types, 26 relationship types, 216+ properties
- Complete Kuzu DDL (also works as Neo4j schema spec)

### Frontend (React + Vite)
- Graph Explorer (Cytoscape, infinite zoom, lasso select)
- Query Workspace (Cypher editor, graph/table view, filter sidebar)
- Data Inventory (149 categories, 3-level drill-down, node drawer, "View in Graph")
- Query Builder (drag-and-drop Cypher, live JSON/YAML results, URL state)
- Security page (EOL/CVE/PII/secrets/certs panels)
- Workflow Builder (React Flow, 7 step types)
- Indexer Dashboard (WebSocket live progress)
- Connectors page (health cards, scanner routing, add/edit modal)
- Usage & Billing page (tier breakdown, cost estimate, plan comparison)
- Sources/Mounts page

### APIs
- REST: graph, mounts, indexer, connectors, inventory, schema, usage, alerts,
        compliance, queries, workflows, license, scanner, stream, tenants, auth
- GraphQL: strawberry-graphql schema with GraphiQL IDE at /graphql
- HuggingFace-compatible streaming endpoint (Arrow/Parquet/JSONL/WebDataset)

### Compliance & Security
- 5 built-in alert rules, 5 delivery channels
- 6 compliance report types (GDPR/HIPAA/SOC2/PCI-DSS/ISO-27001/NIST)
- Ed25519 cryptographic licensing (air-gapped, hardware-bound)

### Licensing
- 5 node types billed by tier (standard/enrichable/AI-enriched/identity/graph-edges)
- 4 plans: Starter (free), Pro ($299), Business ($999), Enterprise (custom)
- Volume discounts, grace period, hardware fingerprinting
- Developer fallback license for local dev

---

## 🔴 Missing — Critical Path (P0)

### Auth & Access Control
- [ ] **User invitation flow** — email invite → account creation UI
- [ ] **Password reset** — forgot password flow
- [ ] **Session management UI** — view/revoke active sessions
- [ ] **MFA (TOTP)** — required for enterprise customers
- [ ] **IP allowlist** per tenant — common enterprise requirement
- [ ] **API key management** — create/revoke personal access tokens for API use

### Onboarding
- [ ] **First-run wizard** — connect first source, run first scan, see first graph
- [ ] **Empty state guidance** — every page needs a meaningful empty state
- [ ] **Sample data mode** — demo tenant with pre-populated graph for sales

### Billing & Payments
- [ ] **Stripe integration** — actual payment processing
- [ ] **Invoice generation** — PDF invoices with line items
- [ ] **Usage alerts** — notify when approaching plan limits
- [ ] **Overage handling** — block vs charge vs warn
- [ ] **Trial → paid upgrade flow** — in-app upgrade
- [ ] **Billing history** — past invoices, payment methods
- [ ] **Annual billing discount** — standard SaaS pricing

### Settings Page
- [ ] **Tenant settings** — name, slug, logo, timezone
- [ ] **User profile** — name, email, avatar, notification preferences
- [ ] **Notification settings** — which alerts go where
- [ ] **Danger zone** — delete tenant, export all data (GDPR right to erasure)

---

## 🟡 Missing — High Priority (P1)

### Search
- [ ] **Global search bar** — search by filename, content summary, entity name
  across all node types — needs a search index (Meilisearch or OpenSearch)
- [ ] **Saved searches** — pin frequently used searches
- [ ] **Search result snippets** — show context around matching text

### Graph UX
- [ ] **Node context menu** — right-click: "Find related", "Add to collection",
  "View connections", "Open in new tab"
- [ ] **Path finder** — shortest path between two nodes
- [ ] **Neighborhood expansion** — click "+" on a node to expand its connections
- [ ] **Graph diff** — compare two snapshots (what changed since last scan)
- [ ] **Subgraph export** — export visible graph as PNG/SVG or JSON

### Audit Log
- [ ] **Audit log table** — who did what, when (query, export, modify)
- [ ] **Audit log stream** — forward to SIEM (Splunk/Datadog/Elastic)
- [ ] **Data access log** — which files were viewed/exported

### Notifications
- [ ] **In-app notification center** — bell icon with unread alerts
- [ ] **Email digest** — daily/weekly summary of new findings
- [ ] **Webhook outbound** — push events to external systems (Slack, Teams, PagerDuty)

### Collaboration
- [ ] **Shared saved queries** — share query with teammates
- [ ] **Comments on nodes** — annotation layer on graph nodes
- [ ] **@mention in queries** — notify a colleague about a finding
- [ ] **Query history** — per-user history of queries run

### Data Quality
- [ ] **Re-enrichment queue** — queue stale nodes for re-processing
- [ ] **Enrichment status dashboard** — per-source enrichment progress
- [ ] **Failed enrichment log** — files that couldn't be processed
- [ ] **Manual node properties** — let analysts add custom attributes

---

## 🟢 Missing — Nice to Have (P2)

### Graph Intelligence
- [ ] **Anomaly detection** — flag unusual patterns (access time, entropy spike)
- [ ] **Similarity search** — "find files similar to this one" 
- [ ] **Entity deduplication** — merge duplicate Person/Organization nodes
- [ ] **Graph summary** — LLM-generated "your graph contains…" narrative

### Connectors
- [ ] **Google Drive** connector
- [ ] **Dropbox** connector
- [ ] **OneDrive (personal)** connector
- [ ] **SFTP** connector
- [ ] **Email (IMAP)** connector — index email attachments
- [ ] **Slack** connector — index shared files
- [ ] **Notion** connector
- [ ] **Connector health history** — sparkline of scan success over time
- [ ] **Scan schedule config** — per-connector schedule UI

### AI Training Export
- [ ] **Dataset versioning** — tag export snapshots
- [ ] **Export pipeline UI** — configure format, filters, destination
- [ ] **HuggingFace push** — push directly to HF dataset repo

### Enterprise
- [ ] **SCIM provisioning** — auto-provision users from IdP
- [ ] **Custom domain** — tenant.yourdomain.com
- [ ] **Data residency** — choose region for graph data
- [ ] **Encryption key management** — BYOK (bring your own key)
- [ ] **SLA dashboard** — uptime, response time, scan success rate
- [ ] **Dedicated graph instance** — per-enterprise Neo4j namespace

### Developer Experience
- [ ] **API documentation site** — interactive Redoc/SwaggerUI
- [ ] **Python SDK** — dgraphai-python client
- [ ] **TypeScript SDK** — dgraphai-js client
- [ ] **CLI tool** — dgraph query / dgraph export / dgraph status
- [ ] **Webhook events catalog** — document all event types
- [ ] **OpenAPI spec export** — /api/openapi.json

### Observability
- [ ] **Backend metrics** — Prometheus endpoint (/metrics)
- [ ] **Tracing** — OpenTelemetry spans
- [ ] **Health endpoint detail** — per-component health (graph, db, queue)
- [ ] **Celery job queue** — replace asyncio tasks for production scale

---

## 🔵 Backlog (Enricher-dependent, from BACKLOG.md)

See `src/dgraphai/inventory/BACKLOG.md` for the full list.
Top items:
- AcousticID fingerprinting + MusicBrainz lookup
- Scene change detection for video
- OCR enricher (Tesseract)
- Object detection (YOLO/OWL-ViT)
- Dependency manifest parser (package.json, requirements.txt)
- Hash reputation (VirusTotal / NSRL)
- NVD/OSV CVE sync job
- TMDB/IMDB media matching enricher
- License scanner (SPDX header detection)

---

## Priority Order for Next Sessions

1. **Settings page** (P0 — referenced everywhere, currently placeholder)
2. **API key management** (P0 — required for API access plan feature)
3. **Usage alerts** + **Stripe integration** (P0 — monetization)
4. **Global search** (P1 — most-requested enterprise feature)
5. **Audit log** (P1 — required for compliance customers)
6. **Node context menu** + **neighborhood expansion** (P1 — core graph UX)
7. **Webhook outbound** (P1 — integration requirement)
8. **In-app notifications** (P1)
9. **Re-enrichment queue** (P2)
10. **NVD CVE sync job** (P2 — security page needs live data)
