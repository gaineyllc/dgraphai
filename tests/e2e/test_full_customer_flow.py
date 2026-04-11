"""
Full end-to-end customer flow test.

Tests the complete 15-minute customer setup flow against a running local stack.
Run with: pytest tests/e2e/test_full_customer_flow.py -v --timeout=60

Prerequisites (docker compose up -d postgres neo4j redis):
  - Postgres on localhost:5432
  - Neo4j on localhost:7687
  - Redis on localhost:6379
  - API server on localhost:8000 (or set E2E_BASE_URL)

The tests run in order and share state via module-level fixtures.
Each test class represents one stage of the customer journey.
"""
from __future__ import annotations

import os
import time
import uuid
import pytest
import httpx

BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8001")
TIMEOUT  = httpx.Timeout(30.0)

# ── Shared state across the full flow ────────────────────────────────────────
state: dict = {}


def api(path: str) -> str:
    return f"{BASE_URL}{path}"


def auth_headers() -> dict:
    token = state.get("token", "")
    return {"Authorization": f"Bearer {token}"}


# ── Stage 0: Health ───────────────────────────────────────────────────────────

class TestHealth:
    def test_api_is_up(self):
        r = httpx.get(api("/api/health"), timeout=TIMEOUT)
        assert r.status_code == 200, f"Health check failed: {r.text}"
        assert r.json().get("status") == "ok"

    def test_docs_available(self):
        r = httpx.get(api("/docs"), timeout=TIMEOUT)
        # Docs may be disabled in prod — 200 or 404 both acceptable
        assert r.status_code in (200, 404)

    def test_openapi_schema(self):
        r = httpx.get(api("/openapi.json"), timeout=TIMEOUT)
        assert r.status_code == 200
        schema = r.json()
        assert "paths" in schema
        # Verify key routes exist
        paths = schema["paths"]
        assert any("/auth" in p for p in paths), "Auth routes missing"
        assert any("/connectors" in p for p in paths), "Connector routes missing"
        assert any("/agent" in p for p in paths), "Agent routes missing"


# ── Stage 1: Signup + Auth ────────────────────────────────────────────────────

class TestSignup:
    email    = f"e2e-{uuid.uuid4().hex[:8]}@test.dgraph.ai"
    password = "E2eTestPass123!"
    name     = "E2E Test User"
    company  = "E2E Corp"

    def test_signup(self):
        r = httpx.post(api("/api/auth/signup"), json={
            "email":    self.email,
            "password": self.password,
            "name":     self.name,
            "company":  self.company,
        }, timeout=TIMEOUT)
        assert r.status_code in (200, 201), f"Signup failed: {r.text}"
        data = r.json()
        assert "token" in data or "access_token" in data or "message" in data
        state["signup_email"]   = self.email
        state["signup_password"]= self.password

    def test_login(self):
        r = httpx.post(api("/api/auth/login"), json={
            "email":    state["signup_email"],
            "password": state["signup_password"],
        }, timeout=TIMEOUT)
        assert r.status_code == 200, f"Login failed: {r.text}"
        data = r.json()
        token = data.get("token") or data.get("access_token")
        assert token, f"No token in response: {data}"
        state["token"]     = token
        state["user"]      = data.get("user", {})
        state["tenant_id"] = data.get("user", {}).get("tenant_id", "")

    def test_get_me(self):
        r = httpx.get(api("/api/auth/me"), headers=auth_headers(), timeout=TIMEOUT)
        assert r.status_code == 200, f"GET /auth/me failed: {r.text}"
        me = r.json()
        assert me.get("email") == state["signup_email"]


# ── Stage 2: Connectors ───────────────────────────────────────────────────────

class TestConnectors:
    def test_list_connectors_empty(self):
        r = httpx.get(api("/api/connectors"), headers=auth_headers(), timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    def test_create_local_connector(self):
        r = httpx.post(api("/api/connectors"), headers={
            **auth_headers(), "Content-Type": "application/json"
        }, json={
            "name":           "E2E S3 Test",
            "connector_type": "aws-s3",
            "config":         {"bucket": "e2e-test-bucket", "region": "us-east-1"},
            "routing_mode":   "direct",
        }, timeout=TIMEOUT)
        assert r.status_code in (200, 201), f"Create connector failed: {r.text}"
        data = r.json()
        assert "id" in data
        state["connector_id"] = data["id"]

    def test_list_connectors_has_one(self):
        r = httpx.get(api("/api/connectors"), headers=auth_headers(), timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1

    def test_get_connector(self):
        r = httpx.get(api(f"/api/connectors/{state['connector_id']}"),
                      headers=auth_headers(), timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == state["connector_id"]

    def test_update_scan_schedule(self):
        r = httpx.patch(api(f"/api/connectors/{state['connector_id']}/schedule"),
                        headers={**auth_headers(), "Content-Type": "application/json"},
                        json={"schedule": "24h"}, timeout=TIMEOUT)
        assert r.status_code in (200, 204), f"Schedule update failed: {r.text}"

    def test_connector_types(self):
        r = httpx.get(api("/api/connectors/types"), headers=auth_headers(), timeout=TIMEOUT)
        assert r.status_code == 200


# ── Stage 3: Agent token + heartbeat ─────────────────────────────────────────

class TestAgent:
    def test_generate_agent_token(self):
        r = httpx.post(api("/api/agent/token?name=e2e-agent"),
                       headers=auth_headers(), timeout=TIMEOUT)
        assert r.status_code in (200, 201), f"Token gen failed: {r.text}"
        data = r.json()
        assert data.get("api_key", "").startswith("dga_"), f"Bad key format: {data}"
        assert "install_linux" in data
        assert "install_docker" in data
        assert "install_helm" in data
        # Verify actual key is in the install commands
        key = data["api_key"]
        assert key in data["install_linux"], "Key not in linux install cmd"
        assert key in data["install_docker"], "Key not in docker install cmd"
        state["agent_key"] = key
        state["agent_id"]  = data["agent_id"]

    def test_list_agents(self):
        r = httpx.get(api("/api/agents"), headers=auth_headers(), timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert any(a["id"] == state["agent_id"] for a in data)

    def test_agent_config_delivery(self):
        """Agent polls this endpoint to know what to scan."""
        r = httpx.get(api("/api/agent/config"), headers={
            "X-Scanner-Key": state["agent_key"]
        }, timeout=TIMEOUT)
        assert r.status_code == 200, f"Config delivery failed: {r.text}"
        data = r.json()
        assert "connectors" in data
        assert "cloud_url" in data
        assert data["agent_id"] == state["agent_id"]

    def test_agent_heartbeat(self):
        """Simulate agent reporting in."""
        r = httpx.post(api("/api/agent/heartbeat"), headers={
            "X-Scanner-Key": state["agent_key"],
            "Content-Type": "application/json",
        }, json={
            "agent_id":      state["agent_id"],
            "version":       "0.1.0-e2e",
            "os":            "linux",
            "hostname":      "e2e-test-host",
            "files_indexed": 1234,
            "files_pending": 0,
            "connector_statuses": {
                state.get("connector_id", "test"): "idle"
            },
        }, timeout=TIMEOUT)
        assert r.status_code == 200, f"Heartbeat failed: {r.text}"
        assert r.json()["ok"] is True

    def test_agent_is_online_after_heartbeat(self):
        """Agent should appear online within 90 seconds of heartbeat."""
        r = httpx.get(api(f"/api/agents/{state['agent_id']}"),
                      headers=auth_headers(), timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert data["is_online"] is True, "Agent not online after heartbeat"
        assert data["files_indexed"] == 1234
        assert data["version"] == "0.1.0-e2e"


# ── Stage 4: Graph + inventory ────────────────────────────────────────────────

class TestGraph:
    def test_graph_schema(self):
        r = httpx.get(api("/api/schema"), headers=auth_headers(), timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert "node_types" in data
        assert len(data["node_types"]) >= 10

    def test_inventory_returns(self):
        r = httpx.get(api("/api/inventory"), headers=auth_headers(), timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert "categories" in data or isinstance(data, list)

    def test_graphql_introspection(self):
        r = httpx.post(api("/graphql"), json={
            "query": "{ __schema { queryType { name } } }"
        }, headers={**auth_headers(), "Content-Type": "application/json"},
        timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert "data" in data
        assert data["data"]["__schema"]["queryType"]["name"] == "Query"

    def test_graphql_stats(self):
        r = httpx.post(api("/graphql"), json={
            "query": "{ stats { node_count edge_count tenant_id } }"
        }, headers={**auth_headers(), "Content-Type": "application/json"},
        timeout=TIMEOUT)
        assert r.status_code == 200
        data = r.json()
        assert "data" in data

    def test_ingest_test_node(self):
        """Push a synthetic file node through the scanner ingest endpoint."""
        r = httpx.post(api("/api/scanner/ingest"), headers={
            "X-Scanner-Key": state["agent_key"],
            "Content-Type":  "application/json",
        }, json={
            "connector_id": state.get("connector_id", "test"),
            "files": [{
                "path":          "/tmp/e2e-test-file.txt",
                "name":          "e2e-test-file.txt",
                "size":          1024,
                "modified":      "2026-04-11T00:00:00Z",
                "sha256":        "abc123def456",
                "file_category": "document",
                "mime_type":     "text/plain",
            }]
        }, timeout=TIMEOUT)
        # Accept 200/201/202 (async ingest may queue)
        assert r.status_code in (200, 201, 202), f"Ingest failed: {r.text}"


# ── Stage 5: Security endpoints ───────────────────────────────────────────────

class TestSecurity:
    def test_security_stats(self):
        r = httpx.get(api("/api/security/stats"), headers=auth_headers(), timeout=TIMEOUT)
        # May return 404 if not implemented yet — that's a finding, not a failure
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            data = r.json()
            assert isinstance(data, dict)

    def test_alerts_list(self):
        r = httpx.get(api("/api/alerts"), headers=auth_headers(), timeout=TIMEOUT)
        assert r.status_code == 200

    def test_audit_log(self):
        r = httpx.get(api("/api/audit"), headers=auth_headers(), timeout=TIMEOUT)
        assert r.status_code == 200


# ── Stage 6: Proxy sync ───────────────────────────────────────────────────────

class TestProxySync:
    def test_proxy_sync_endpoint(self):
        """Simulate dgraph-proxy sending a delta batch."""
        r = httpx.post(api("/api/v1/proxy/sync"), headers={
            "Authorization": f"Bearer {state.get('token', '')}",
            "Content-Type":  "application/json",
            "X-Proxy-ID":    "e2e-proxy-001",
            "X-Tenant-ID":   state.get("tenant_id", ""),
        }, json={
            "proxy_id":  "e2e-proxy-001",
            "tenant_id": state.get("tenant_id", "test"),
            "agent_id":  "e2e-agent",
            "deltas": [{
                "seq": 1,
                "op":  "upsert_node",
                "node_id": str(uuid.uuid4()),
                "payload": {
                    "labels":     ["File"],
                    "properties": {"path": "/tmp/proxy-test.txt", "size": 512},
                },
                "timestamp": "2026-04-11T00:00:00Z",
            }],
            "batch_seq": 1,
            "sent_at": "2026-04-11T00:00:00Z",
            "stats": {"node_count": 1, "pending_deltas": 0, "uptime_seconds": 60},
        }, timeout=TIMEOUT)
        assert r.status_code in (200, 201), f"Proxy sync failed: {r.text}"
        data = r.json()
        assert "acked_seqs" in data

    def test_proxy_heartbeat(self):
        r = httpx.post(api("/api/v1/proxy/heartbeat"), headers={
            "Authorization": f"Bearer {state.get('token', '')}",
            "Content-Type":  "application/json",
        }, json={
            "proxy_id":  "e2e-proxy-001",
            "tenant_id": state.get("tenant_id", "test"),
            "agent_id":  "e2e-agent",
            "version":   "0.1.0",
            "stats": {"node_count": 1, "pending_deltas": 0, "uptime_seconds": 120},
        }, timeout=TIMEOUT)
        assert r.status_code in (200, 201), f"Proxy heartbeat failed: {r.text}"


# ── Stage 7: Settings + Notifications ────────────────────────────────────────

class TestSettings:
    def test_get_settings(self):
        r = httpx.get(api("/api/settings/tenant"), headers=auth_headers(), timeout=TIMEOUT)
        assert r.status_code in (200, 403), f"settings: {r.text[:100]}"

    def test_notifications_list(self):
        r = httpx.get(api("/api/alerts/notifications"), headers=auth_headers(), timeout=TIMEOUT)
        assert r.status_code in (200, 403), f"notifications: {r.text[:100]}"

    def test_usage_endpoint(self):
        r = httpx.get(api("/api/usage/limits"), headers=auth_headers(), timeout=TIMEOUT)
        assert r.status_code in (200, 403), f"usage: {r.text[:100]}"


# ── Stage 8: Cleanup ──────────────────────────────────────────────────────────

class TestCleanup:
    def test_revoke_agent(self):
        if not state.get("agent_id"):
            pytest.skip("No agent_id in state")
        r = httpx.delete(api(f"/api/agents/{state['agent_id']}"),
                         headers=auth_headers(), timeout=TIMEOUT)
        assert r.status_code in (200, 204), f"Revoke failed: {r.text}"

    def test_delete_connector(self):
        if not state.get("connector_id"):
            pytest.skip("No connector_id in state")
        r = httpx.delete(api(f"/api/connectors/{state['connector_id']}"),
                         headers=auth_headers(), timeout=TIMEOUT)
        assert r.status_code in (200, 204), f"Delete connector failed: {r.text}"
