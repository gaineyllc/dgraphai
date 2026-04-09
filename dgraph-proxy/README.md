# dgraph-proxy

Local air-gappable graph store and sync agent for dgraph.ai.

## What It Does

dgraph-proxy runs on-premises next to `dgraph-agent` (the filesystem scanner). It:

- **Stores graph data locally** in [BadgerDB](https://github.com/dgraph-io/badger) — pure Go, no external dependencies
- **Exposes a local HTTP API** compatible with the dgraph.ai cloud API (subset)
- **Syncs deltas to cloud** when network is available — outbound HTTPS only, no inbound connections
- **Works fully offline** in air-gapped mode — data never leaves the machine

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  On-Premises                                              │
│                                                          │
│  ┌─────────────┐    nodes/edges    ┌──────────────────┐  │
│  │ dgraph-agent│ ────────────────► │  dgraph-proxy    │  │
│  │ (scanner)   │                   │  :7433 (local)   │  │
│  └─────────────┘                   │                  │  │
│                                    │  BadgerDB        │  │
│  ┌─────────────┐    query API      │  (local graph)   │  │
│  │ dgraph.ai   │ ◄──────────────── │                  │  │
│  │ frontend    │                   └──────┬───────────┘  │
│  └─────────────┘                         │ sync deltas   │
└─────────────────────────────────────────-│───────────────┘
                                           │ (when connected)
                                           ▼
                                   dgraph.ai cloud
                                   /api/v1/proxy/sync
```

## Quick Start

```bash
# Minimal — local only, no cloud sync
DGPROXY_TENANT_ID=acme \
DGPROXY_DATA_DIR=/var/lib/dgraph-proxy \
  dgraph-proxy

# With cloud sync
DGPROXY_TENANT_ID=acme \
DGPROXY_CLOUD_URL=https://api.dgraph.ai \
DGPROXY_CLOUD_TOKEN=<token> \
DGPROXY_DATA_DIR=/var/lib/dgraph-proxy \
  dgraph-proxy

# Air-gapped (never phones home, no network required)
DGPROXY_AIR_GAPPED=true \
DGPROXY_TENANT_ID=acme \
DGPROXY_DATA_DIR=/var/lib/dgraph-proxy \
  dgraph-proxy
```

## Configuration

All configuration via environment variables:

| Variable | Default | Description |
|---|---|---|
| `DGPROXY_TENANT_ID` | **required** | Your dgraph.ai tenant ID |
| `DGPROXY_AGENT_ID` | `default` | Agent identifier |
| `DGPROXY_PROXY_ID` | hostname | Unique ID for this proxy instance |
| `DGPROXY_DATA_DIR` | `./data` | Path to BadgerDB data directory |
| `DGPROXY_STORE_MODE` | `badger` | Storage backend (`badger` \| `bolt`) |
| `DGPROXY_CLOUD_URL` | _(empty)_ | Cloud API URL (empty = local-only) |
| `DGPROXY_CLOUD_TOKEN` | _(empty)_ | Bearer token for cloud API |
| `DGPROXY_SYNC_INTERVAL` | `5m` | How often to push deltas to cloud |
| `DGPROXY_SYNC_BATCH_SIZE` | `500` | Max nodes per sync batch |
| `DGPROXY_LISTEN_ADDR` | `127.0.0.1:7433` | Local API listen address |
| `DGPROXY_TLS_CERT` | _(empty)_ | TLS cert file (enables HTTPS) |
| `DGPROXY_TLS_KEY` | _(empty)_ | TLS key file |
| `DGPROXY_JWT_SECRET` | _(empty)_ | JWT secret for local API auth |
| `DGPROXY_METRICS_ADDR` | `:9091` | Prometheus metrics address |
| `DGPROXY_LOG_LEVEL` | `info` | Log level (debug\|info\|warn\|error) |
| `DGPROXY_LOG_FORMAT` | `json` | Log format (json\|text) |
| `DGPROXY_AIR_GAPPED` | `false` | Disable all outbound network calls |

## Local API

dgraph-proxy exposes a local HTTP API that dgraph-agent uses to write data and that the dgraph.ai frontend can query directly in air-gapped mode:

```
GET  /health                         Liveness probe
GET  /ready                          Readiness probe
GET  /api/v1/stats                   Node/edge counts, sync status
GET  /api/v1/nodes?label=File&limit=100  List nodes by label
GET  /api/v1/nodes/{id}              Get node by ID
POST /api/v1/nodes                   Upsert a node
DELETE /api/v1/nodes/{id}            Delete a node
POST /api/v1/edges                   Upsert an edge
GET  /api/v1/query?key=name&op=contains&value=secret  Property query
GET  /api/v1/inventory               Label counts (for inventory page)
POST /api/v1/sync/force              Trigger immediate cloud sync
```

## Cloud Sync Protocol

The sync protocol is outbound-only HTTPS (no inbound connections from cloud):

1. Proxy POSTs `DeltaBatch` to `DGPROXY_CLOUD_URL/api/v1/proxy/sync`
2. Cloud responds with `SyncResponse` (acked seq numbers + optional commands)
3. Proxy removes acked deltas from local queue
4. Cloud can push commands: `reindex`, `flush_deltas`, `update_config`

On network failure: exponential backoff (up to 30 minutes). All changes are buffered locally — nothing is lost.

## Building

```bash
cd dgraph-proxy
go mod tidy
go build -o dgraph-proxy ./cmd/dgraph-proxy
```

## Running with Docker

```dockerfile
FROM gcr.io/distroless/base-debian12
COPY dgraph-proxy /usr/local/bin/
VOLUME /data
ENV DGPROXY_DATA_DIR=/data
ENTRYPOINT ["dgraph-proxy"]
```

## Security Model

- Local API listens on `127.0.0.1` by default (loopback only)
- Enable TLS + JWT for network-exposed deployments
- Cloud sync uses Bearer token over HTTPS
- Air-gapped mode: zero network I/O, fully auditable
- BadgerDB data encrypted at rest when OS-level encryption is in use
  (recommend LUKS on Linux, BitLocker on Windows, FileVault on macOS)
