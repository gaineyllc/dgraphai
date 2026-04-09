"""
dgraphai Scanner Agent
─────────────────────
On-prem component that indexes local filesystems and syncs graph deltas
to the dgraphai backend. Runs as a Kubernetes deployment or Docker container.

Security model:
  - Outbound connections only (no inbound except health UI on loopback)
  - API key authentication to backend (never exposes credentials)
  - Health UI shows operational status only — no file paths, no content
  - All sensitive config via environment variables or K8s secrets

Endpoints:
  GET  /health      Liveness probe (K8s)
  GET  /ready       Readiness probe (K8s)
  GET  /            Health UI (local only, binds to 127.0.0.1)
  GET  /api/status  JSON health status (local only)
"""
from __future__ import annotations

import asyncio
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# ── Configuration ─────────────────────────────────────────────────────────────

BACKEND_URL  = os.environ.get("dgraphai_BACKEND_URL", "")
API_KEY      = os.environ.get("dgraphai_AGENT_API_KEY", "")
AGENT_NAME   = os.environ.get("dgraphai_AGENT_NAME", platform.node())
HEALTH_PORT  = int(os.environ.get("dgraphai_HEALTH_PORT", "8080"))
HEALTH_HOST  = os.environ.get("dgraphai_HEALTH_HOST", "127.0.0.1")  # loopback only
SCAN_INTERVAL = int(os.environ.get("dgraphai_SCAN_INTERVAL_SECONDS", "3600"))

# ── State ─────────────────────────────────────────────────────────────────────

class AgentState:
    started_at:        datetime = datetime.now(timezone.utc)
    last_sync:         datetime | None = None
    last_sync_status:  str = "never"
    files_indexed:     int = 0
    errors:            int = 0
    backend_reachable: bool = False
    backend_version:   str = "unknown"
    current_scan:      str | None = None  # "running" | None
    connectors:        int = 0
    version:           str = "0.1.0"

state = AgentState()

# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="dgraphai Scanner Agent",
    docs_url=None,   # no Swagger UI
    redoc_url=None,  # no ReDoc
    openapi_url=None # no OpenAPI schema
)

# Only allow local connections to the health UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1", "http://localhost"],
    allow_methods=["GET"],
    allow_headers=[],
)


# ── Health probes (for K8s) ───────────────────────────────────────────────────

@app.get("/health")
async def liveness() -> dict:
    """K8s liveness probe — is the process alive?"""
    return {"status": "ok"}


@app.get("/ready")
async def readiness() -> dict:
    """K8s readiness probe — is the agent ready to scan?"""
    if not BACKEND_URL or not API_KEY:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "reason": "backend not configured"}
        )
    return {"status": "ready", "backend": state.backend_reachable}


# ── Status API (local only — no exploitable info) ─────────────────────────────

@app.get("/api/status")
async def status(request: Request) -> dict:
    """
    Operational status for the health UI.
    Returns only health/operational metrics — no file paths, no content,
    no network topology, no credentials, no error details.
    """
    uptime_secs = (datetime.now(timezone.utc) - state.started_at).total_seconds()

    return {
        "agent": {
            "name":       AGENT_NAME,
            "version":    state.version,
            "platform":   sys.platform,
            "uptime_secs": int(uptime_secs),
            "started_at": state.started_at.isoformat(),
        },
        "backend": {
            "reachable": state.backend_reachable,
            "version":   state.backend_version,
            # Never expose the backend URL or API key
        },
        "scanning": {
            "status":       state.current_scan or "idle",
            "files_indexed": state.files_indexed,
            "errors":        state.errors,
            "last_sync":     state.last_sync.isoformat() if state.last_sync else None,
            "last_status":   state.last_sync_status,
            "connectors":    state.connectors,
            "interval_secs": SCAN_INTERVAL,
        },
    }


# ── Health UI ─────────────────────────────────────────────────────────────────

HEALTH_UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="30">
<title>dgraphai Scanner Agent</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace, sans-serif;
    background: #0a0a0f; color: #e2e2f0;
    min-height: 100vh; padding: 32px 24px;
  }
  .header { display: flex; align-items: center; gap: 12px; margin-bottom: 32px; }
  .logo { width: 36px; height: 36px; background: linear-gradient(135deg, #4f8ef7, #8b5cf6);
    border-radius: 8px; display: flex; align-items: center; justify-content: center;
    font-size: 18px; }
  h1 { font-size: 18px; font-weight: 600; }
  .subtitle { font-size: 12px; color: #55557a; margin-top: 2px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
  .card { background: #12121a; border: 1px solid #252535; border-radius: 12px; padding: 20px; }
  .card-title { font-size: 11px; text-transform: uppercase; letter-spacing: .08em;
    color: #55557a; margin-bottom: 12px; }
  .stat { display: flex; justify-content: space-between; align-items: center;
    padding: 6px 0; border-bottom: 1px solid #1a1a28; }
  .stat:last-child { border-bottom: none; }
  .stat-label { font-size: 13px; color: #8888aa; }
  .stat-value { font-size: 13px; font-weight: 500; font-family: monospace; }
  .badge { display: inline-flex; align-items: center; gap: 5px; padding: 3px 8px;
    border-radius: 20px; font-size: 11px; font-weight: 600; }
  .badge-green  { background: rgba(52,211,153,.12); color: #34d399; border: 1px solid rgba(52,211,153,.2); }
  .badge-yellow { background: rgba(251,191,36,.12);  color: #fbbf24; border: 1px solid rgba(251,191,36,.2); }
  .badge-red    { background: rgba(248,113,113,.12); color: #f87171; border: 1px solid rgba(248,113,113,.2); }
  .badge-gray   { background: rgba(107,114,128,.12); color: #9ca3af; border: 1px solid rgba(107,114,128,.2); }
  .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
  .footer { margin-top: 24px; font-size: 11px; color: #252535; text-align: center; }
</style>
</head>
<body>
<div class="header">
  <div class="logo">⬡</div>
  <div>
    <h1>dgraphai Scanner Agent</h1>
    <div class="subtitle" id="agent-name">Loading…</div>
  </div>
</div>

<div class="grid" id="content">
  <div class="card"><div class="card-title">Loading…</div></div>
</div>

<div class="footer">
  Health information only · Refreshes every 30s ·
  <span id="last-updated"></span>
</div>

<script>
async function load() {
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    render(d);
    document.getElementById('last-updated').textContent =
      'Updated ' + new Date().toLocaleTimeString();
  } catch(e) {
    document.getElementById('content').innerHTML =
      '<div class="card"><div class="card-title" style="color:#f87171">Cannot reach agent API</div></div>';
  }
}

function badge(value, map) {
  for (const [match, cls, label] of map) {
    if (value === match || value === true && match === true || value === false && match === false)
      return `<span class="badge badge-${cls}"><span class="dot"></span>${label ?? value}</span>`;
  }
  return `<span class="badge badge-gray">${value ?? '—'}</span>`;
}

function stat(label, value) {
  return `<div class="stat"><span class="stat-label">${label}</span><span class="stat-value">${value}</span></div>`;
}

function fmtUptime(s) {
  const h = Math.floor(s/3600), m = Math.floor((s%3600)/60);
  return h > 0 ? h+'h '+m+'m' : m+'m';
}

function render(d) {
  document.getElementById('agent-name').textContent = d.agent.name + ' · v' + d.agent.version;
  document.getElementById('content').innerHTML = `
    <div class="card">
      <div class="card-title">Backend Connection</div>
      ${stat('Status', badge(d.backend.reachable, [[true,'green','Connected'],[false,'red','Unreachable']]))}
      ${stat('Version', d.backend.version || '—')}
    </div>
    <div class="card">
      <div class="card-title">Scanning</div>
      ${stat('Status', badge(d.scanning.status, [
        ['idle','green','Idle'],['running','yellow','Running'],['error','red','Error'],['never','gray','Never run']
      ]))}
      ${stat('Last sync', d.scanning.last_sync ? new Date(d.scanning.last_sync).toLocaleString() : '—')}
      ${stat('Last result', badge(d.scanning.last_status, [
        ['success','green','Success'],['error','red','Error'],['never','gray','Never']
      ]))}
      ${stat('Files indexed', d.scanning.files_indexed.toLocaleString())}
      ${stat('Errors', d.scanning.errors > 0
        ? `<span style="color:#f87171">${d.scanning.errors}</span>`
        : '0')}
      ${stat('Connectors', d.scanning.connectors)}
      ${stat('Interval', Math.floor(d.scanning.interval_secs/60)+'m')}
    </div>
    <div class="card">
      <div class="card-title">Agent</div>
      ${stat('Platform', d.agent.platform)}
      ${stat('Uptime', fmtUptime(d.agent.uptime_secs))}
      ${stat('Started', new Date(d.agent.started_at).toLocaleString())}
      ${stat('Version', d.agent.version)}
    </div>
  `;
}

load();
</script>
</body>
</html>"""


@app.get("/", response_class=HTMLResponse)
async def health_ui() -> str:
    """
    Local health UI — operational status only.
    Binds to loopback interface — not accessible over network.
    """
    return HEALTH_UI_HTML


# ── Backend sync loop ─────────────────────────────────────────────────────────

async def sync_loop() -> None:
    """Heartbeat, job polling, and offline queue flushing."""
    from src.sync.client import SyncClient

    client = SyncClient(
        backend_url = BACKEND_URL,
        api_key     = API_KEY,
        scanner_id  = os.environ.get("DGRAPHAI_SCANNER_ID", ""),
        tenant_id   = os.environ.get("DGRAPHAI_TENANT_ID", ""),
    )

    while True:
        # 1. Heartbeat
        if BACKEND_URL and API_KEY:
            health = {
                "version":      state.version,
                "platform":     sys.platform,
                "uptime_secs":  int((datetime.now(timezone.utc) - state.started_at).total_seconds()),
                "files_indexed": state.files_indexed,
                "errors":       state.errors,
                "connectors":   state.connectors,
                "scanning":     state.current_scan == "running",
            }
            ok = await client.heartbeat(health)
            state.backend_reachable = ok
            if ok:
                # Try to get backend version
                try:
                    async with httpx.AsyncClient(timeout=5) as hc:
                        r = await hc.get(
                            f"{BACKEND_URL}/api/health",
                            headers={"X-Scanner-Key": API_KEY},
                        )
                        state.backend_version = r.json().get("version", "unknown")
                except Exception:
                    pass

        # 2. Flush offline queue if backend reachable
        if state.backend_reachable:
            flushed = await client.flush_queue()
            if flushed:
                pass  # already logged in flush_queue

        # 3. Poll for jobs (simple polling — upgrade to WebSocket later)
        if state.backend_reachable and state.current_scan != "running":
            jobs = await client.poll_jobs()
            for job in jobs:
                asyncio.create_task(_run_job(job, client))

        await asyncio.sleep(60)


async def _run_job(job: dict, client) -> None:
    """Execute a scan job dispatched from the backend."""
    from src.connectors.local import LocalConnector
    from src.connectors.smb   import SMBConnector

    state.current_scan = "running"
    uri = job.get("source_uri", "")
    connector_id = job.get("connector_id", "unknown")
    job_id = job.get("job_id", str(uuid.uuid4()) if True else "")

    try:
        if uri.startswith("smb://"):
            connector = SMBConnector(connector_id, uri, job.get("options", {}))
        else:
            connector = LocalConnector(connector_id, uri, job.get("options", {}))

        stats = await connector.scan_and_sync(client, job_id)
        state.files_indexed += stats.get("total_files", 0)
        state.errors        += stats.get("total_errors", 0)
        state.last_sync        = datetime.now(timezone.utc)
        state.last_sync_status = "success"
    except Exception as e:
        state.errors       += 1
        state.last_sync_status = "error"
    finally:
        state.current_scan = None


async def startup() -> None:
    asyncio.create_task(sync_loop())


app.add_event_handler("startup", startup)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=HEALTH_HOST,
        port=HEALTH_PORT,
        log_level="warning",
        access_log=False,
    )
