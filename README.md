# dgraph.ai

**Enterprise Filesystem Knowledge Graph** — index everything across your connected data sources, enrich it with AI, and explore it as a unified graph.

> Connect SMB shares, S3 buckets, SharePoint, Azure Blob, and local filesystems.  
> AI enrichment finds secrets, PII, CVEs, faces, and semantic relationships.  
> Browse 149 data categories, run Cypher queries, or use natural language search.

---

## Quick Start (Local Dev)

```bash
# 1. Clone
git clone https://github.com/gaineyllc/dgraphai && cd dgraphai

# 2. Copy env
cp .env.example .env
# Edit .env — set JWT_SECRET at minimum

# 3. Start services
docker compose up -d

# 4. Run migrations
uv run alembic upgrade head

# 5. Create first admin
uv run python -m src.dgraphai.cli create-admin --email admin@example.com

# 6. Start frontend
cd web && npm install && npm run dev

# Open: http://localhost:5173
```

## Deployment

| Target | Command |
|---|---|
| AWS (EKS) | `helm install dgraphai oci://ghcr.io/gaineyllc/charts/dgraphai -f deploy/aws/values-aws.yaml` |
| Azure (AKS) | `helm install dgraphai oci://ghcr.io/gaineyllc/charts/dgraphai -f deploy/azure/values-azure.yaml` |
| GCP (GKE) | `helm install dgraphai oci://ghcr.io/gaineyllc/charts/dgraphai -f deploy/gcp/values-gcp.yaml` |
| On-prem | `helm install dgraphai oci://ghcr.io/gaineyllc/charts/dgraphai -f deploy/onprem/values-onprem.yaml` |
| Air-gapped | `./deploy/airgapped/scripts/install.sh` |

## Install the scanner agent

```bash
# Helm
helm install dgraph-agent oci://ghcr.io/gaineyllc/charts/dgraph-agent \
  --set config.tenantId=YOUR_TENANT_ID \
  --set credentials.apiKey=YOUR_API_KEY

# Binary
curl -L https://github.com/gaineyllc/dgraphai/releases/latest/download/dgraph-agent-linux-amd64 \
  -o dgraph-agent && chmod +x dgraph-agent
./dgraph-agent --config config.yaml
```

## Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the full architecture reference.

**Service split:**
- `dgraph-api` — FastAPI (Python), REST + GraphQL, auth, inventory, compliance
- `dgraph-enrich` — Celery workers (Python), LLM/vision/code/binary AI enrichment  
- `dgraph-agent` — Go binary, on-premises filesystem scanner (no Python needed)
- Frontend — React + Vite, 17 pages

## SDK

```python
# Python
pip install dgraphai

from dgraphai import DGraphAI
client = DGraphAI(api_key="dg_...", tenant_id="...")
results = client.graph.query("MATCH (f:File) WHERE f.pii_detected = true RETURN f")
```

```typescript
// TypeScript
npm install @dgraphai/sdk

import { DGraphAI } from '@dgraphai/sdk'
const client = new DGraphAI({ apiKey: 'dg_...', tenantId: '...' })
const categories = await client.inventory.list()
```

## Development

```bash
# Backend tests
uv run pytest tests/unit -v           # 280 unit tests
uv run pytest tests/e2e               # API tests (needs running services)

# Frontend
cd web && npm run dev                  # dev server on :5173
cd web && npm run build                # production build

# Database
uv run alembic upgrade head           # run migrations
uv run alembic revision --autogenerate -m "add X"  # create migration

# CLI
uv run python -m src.dgraphai.cli --help
uv run python -m src.dgraphai.cli health
uv run python -m src.dgraphai.cli generate-key --type jwt
```

## Environment variables

See [.env.example](./.env.example) for all configuration options.

## License

Commercial license — see [LICENSE](./LICENSE).  
dgraph.ai scanner agent (agent-go/) is MIT licensed.
