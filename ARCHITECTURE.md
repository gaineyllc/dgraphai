# dgraph.ai — Production Architecture

## Deployment Targets

| Target | Kubernetes | Graph DB | PostgreSQL | Redis | Object Storage | AI Enrichment |
|---|---|---|---|---|---|---|
| AWS SaaS | EKS | Neo4j Aura / Neptune | RDS Aurora | ElastiCache | S3 | Cloud workers |
| Azure SaaS | AKS | Neo4j Aura | Azure DB for PostgreSQL | Azure Cache | Blob Storage | Cloud workers |
| GCP SaaS | GKE | Neo4j Aura | Cloud SQL | Memorystore | GCS | Cloud workers |
| On-prem | Customer K8s | Neo4j Enterprise | PostgreSQL | Redis | MinIO | Optional GPU |
| Air-gapped | Customer K8s | Neo4j Enterprise | PostgreSQL | Redis | MinIO | Local Ollama |

## Service Architecture

```
                    ┌──────────────────────────────────────────┐
                    │           CONTROL PLANE (Go)             │
                    │                                          │
  Browser/API ───► │  dgraph-gateway    dgraph-api            │
  SDK clients       │  - JWT validation  - REST endpoints      │
                    │  - Rate limiting   - GraphQL             │
                    │  - TLS termination - Inventory/Search    │
                    │  - mTLS to agents  - Auth/SCIM/SAML      │
                    │  - DDoS protection - Compliance/Audit    │
                    │  30MB container    - Webhooks/Billing     │
                    │                    30MB container        │
                    │              dgraph-ingest               │
                    │              - Scanner delta ingestion   │
                    │              - 10K+ concurrent agents    │
                    │              - Offline queue flush       │
                    │              - Batch graph writes        │
                    │              30MB container              │
                    └──────────┬───────────────────────────────┘
                               │ gRPC (proto-defined contracts)
                    ┌──────────▼───────────────────────────────┐
                    │           DATA PLANE (Python)            │
                    │                                          │
                    │  dgraph-enrich     dgraph-vision         │
                    │  - LLM enrichment  - Face recognition    │
                    │  - Code analysis   - LLaVA vision        │
                    │  - Binary analysis - Scene detection     │
                    │  - Celery worker   - Celery worker       │
                    │  8GB container     12GB container (GPU)  │
                    │                                          │
                    │  dgraph-index                            │
                    │  - Search index sync                     │
                    │  - CVE sync (NVD)                        │
                    │  - Re-enrichment queue                   │
                    │  - GDPR erasure worker                   │
                    │  500MB container                         │
                    └──────────────────────────────────────────┘
                               │ abstracted storage interface
                    ┌──────────▼───────────────────────────────┐
                    │           STORAGE LAYER                  │
                    │                                          │
                    │  Graph:      Neo4j | Neptune | Cosmos | SQLite
                    │  Relational: PostgreSQL (Aurora/Flex/SQL)│
                    │  Cache/Queue:Redis (ElastiCache/Cache/Memorystore)
                    │  Search:     Meilisearch | OpenSearch    │
                    │  Objects:    S3 | Blob | GCS | MinIO     │
                    └──────────────────────────────────────────┘
                               │ outbound HTTPS (TLS 1.3 + mTLS)
                    ┌──────────▼───────────────────────────────┐
                    │           CUSTOMER PREMISES              │
                    │                                          │
                    │  dgraph-agent (Go binary)                │
                    │  - Single signed binary                  │
                    │  - SMB/NFS/local/S3/Azure connectors     │
                    │  - Zero inbound ports                    │
                    │  - Offline queue (SQLite)                │
                    │                                          │
                    │  dgraph-enricher (Rust binary, planned)  │
                    │  - Content scanning (secrets/PII/binary) │
                    │  - Runs before data leaves network       │
                    │  - 5s timeout, 256MB rlimit              │
                    └──────────────────────────────────────────┘
```

## Language Decisions

| Component | Language | Rationale |
|---|---|---|
| dgraph-gateway | Go | Hot path: JWT+rate-limit at 100K req/s. 30MB container. |
| dgraph-api | Go (Phase 1) / Python (current) | CRUD logic, not performance-critical now. Migrate in Phase 1. |
| dgraph-ingest | Go | 10K+ concurrent agent connections. Go goroutines = ~1KB/conn vs ~8MB/thread. |
| dgraph-enrich | Python | HuggingFace, Ollama, LangChain — no Go equivalent. |
| dgraph-vision | Python+GPU | InsightFace, LLaVA — GPU Python ecosystem only. |
| dgraph-index | Python | Celery workers. I/O bound. No reason to rewrite. |
| dgraph-agent | Go | On-premises. Single binary. No Python runtime on customer machines. |
| dgraph-enricher | Rust | Parses untrusted file content. Memory safety guarantees required. |
| Frontend | TypeScript | React/Vite. Existing. |
| SDK (Python) | Python | Customer integration. Matches ML ecosystem. |
| SDK (TypeScript) | TypeScript | Browser + Node.js integration. |

## Migration Phases

### Current (Phase 0)
- Python FastAPI handles all API routes
- Celery workers for async jobs (6 queues)
- Go agent for on-premises scanning
- In-process rate limiting (fixed → Redis)
- gRPC contracts defined (proto/)

### Phase 1 — Q3 2026 (Control Plane Go Rewrite)
- dgraph-gateway in Go: auth, rate limiting, routing
- dgraph-ingest in Go: agent delta ingestion
- dgraph-api skeleton in Go: CRUD routes, one by one
- Python API continues running in parallel
- Feature parity testing before cutover

### Phase 2 — Q4 2026 (Multi-Cloud Storage)
- GraphBackend interface complete (Neo4j/Neptune/Cosmos/SQLite)
- Per-cloud values.yaml tested and validated
- Automated test suite per backend
- Air-gapped bundle v1.0

### Phase 3 — Q1 2027 (Production Scale)
- dgraph-enricher Rust binary
- Service mesh (Linkerd or Istio) for mTLS
- KEDA autoscaling on queue depth
- Multi-region active/active for SaaS
- SOC 2 Type II certification complete

## API Contract Stability

All API routes versioned under /api/v1/ (currently unversioned = v1).
Breaking changes require a new version prefix.
SDKs pin to API version.
gRPC proto files are the source of truth for service contracts.

## Air-Gapped Bundle

Bundle contents (total ~25GB):
- Container images (OCI tarballs, pre-signed)
- Ollama models (GGUF format, q4_K_M quantization)
- Helm charts
- Binaries (dgraph-agent for Linux/Windows/macOS)
- Install scripts
- Bundle manifest (Ed25519-signed)

Install procedure:
1. Copy bundle to air-gapped host
2. Verify signature: `./scripts/verify-bundle.sh`
3. Install: `./scripts/install.sh`
4. Create admin: `kubectl exec ... python -m src.dgraphai.cli create-admin`
