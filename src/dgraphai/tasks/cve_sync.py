"""
NVD CVE sync — pulls new and updated CVEs from the National Vulnerability Database.

Uses the NVD REST API v2 (free, no key required for basic use, 10 req/min).
Syncs to Neo4j as Vulnerability nodes linked to Application nodes
via HAS_VULNERABILITY relationships.

Schedule: daily via Celery Beat.
Also triggered manually via POST /api/admin/sync/cve.

Data sources:
  - NVD API v2: https://services.nvd.nist.gov/rest/json/cves/2.0
  - OSV (Open Source Vulnerabilities): https://api.osv.dev/v1/query
    Better for dependency CVEs (npm, PyPI, Go, Maven)

Matching strategy:
  1. CPE matching (Common Platform Enumeration) — exact product/version match
  2. Fuzzy name matching — application name contains CPE product name
"""
from __future__ import annotations
import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any

import httpx

from src.dgraphai.tasks.celery_app import app

log = logging.getLogger("dgraphai.tasks.cve_sync")

NVD_API_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
NVD_API_KEY = os.getenv("NVD_API_KEY", "")   # optional — raises rate limit to 50 req/30s
OSV_API_URL = "https://api.osv.dev/v1/query"


@app.task(
    name="dgraphai.tasks.cve_sync.sync_nvd_cves",
    queue="default",
    max_retries=3,
    default_retry_delay=300,
)
def sync_nvd_cves(days_back: int = 7):
    """
    Pull CVEs published/modified in the last N days from NVD.
    Updates Vulnerability nodes and links to affected Applications.
    """
    asyncio.run(_sync_nvd_async(days_back))


async def _sync_nvd_async(days_back: int):
    from src.dgraphai.db.session import async_session
    from src.dgraphai.db.models import Tenant
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(select(Tenant).where(Tenant.is_active == True))
        tenants = result.scalars().all()

    # Fetch CVEs from NVD (shared across all tenants — CVE data is global)
    cves = await _fetch_nvd_cves(days_back)
    log.info(f"Fetched {len(cves)} CVEs from NVD (last {days_back} days)")

    if not cves:
        return

    # For each tenant, link CVEs to their affected applications
    for tenant in tenants:
        await _link_cves_to_tenant(cves, tenant)


async def _fetch_nvd_cves(days_back: int) -> list[dict]:
    """Fetch CVEs from NVD API v2."""
    now       = datetime.now(timezone.utc)
    start     = now - timedelta(days=days_back)
    pub_start = start.strftime("%Y-%m-%dT%H:%M:%S.000")
    pub_end   = now.strftime("%Y-%m-%dT%H:%M:%S.000")

    headers = {}
    if NVD_API_KEY:
        headers["apiKey"] = NVD_API_KEY

    cves     = []
    start_idx= 0
    results_per_page = 2000

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            try:
                resp = await client.get(
                    NVD_API_URL,
                    headers=headers,
                    params={
                        "pubStartDate":   pub_start,
                        "pubEndDate":     pub_end,
                        "resultsPerPage": results_per_page,
                        "startIndex":     start_idx,
                    }
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                log.error(f"NVD API error: {e}")
                break

            vulnerabilities = data.get("vulnerabilities", [])
            for item in vulnerabilities:
                cve = item.get("cve", {})
                cve_id  = cve.get("id", "")
                metrics = cve.get("metrics", {})
                cvss_v3 = metrics.get("cvssMetricV31", metrics.get("cvssMetricV30", []))

                cvss_score    = None
                cvss_severity = "unknown"
                if cvss_v3:
                    score_data    = cvss_v3[0].get("cvssData", {})
                    cvss_score    = score_data.get("baseScore")
                    cvss_severity = score_data.get("baseSeverity", "").lower()

                descriptions = cve.get("descriptions", [])
                description  = next(
                    (d["value"] for d in descriptions if d.get("lang") == "en"), ""
                )

                # Extract affected CPE strings
                cpe_matches = []
                for config in cve.get("configurations", []):
                    for node in config.get("nodes", []):
                        for match in node.get("cpeMatch", []):
                            if match.get("vulnerable"):
                                cpe_matches.append(match.get("criteria", ""))

                published = cve.get("published", "")
                cves.append({
                    "cve_id":              cve_id,
                    "cvss_score":          cvss_score,
                    "cvss_severity":       cvss_severity,
                    "description":         description[:500],
                    "published_date":      published,
                    "cpe_matches":         cpe_matches,
                    "exploit_available":   False,   # TODO: check CISA KEV
                    "actively_exploited":  False,
                })

            total = data.get("totalResults", 0)
            start_idx += results_per_page
            if start_idx >= total:
                break

            # Rate limit: 10 req/min without key, 50/30s with key
            await asyncio.sleep(6 if not NVD_API_KEY else 0.6)

    return cves


async def _link_cves_to_tenant(cves: list[dict], tenant):
    """
    For each CVE, find matching Application nodes in the tenant's graph
    and create/update HAS_VULNERABILITY relationships.
    """
    from src.dgraphai.db.models import Tenant
    from src.dgraphai.graph.backends.factory import get_backend_for_tenant
    import uuid

    backend = get_backend_for_tenant(
        tenant.graph_backend or "neo4j",
        tenant.graph_config  or {},
    )
    tid = str(tenant.id)

    linked = 0
    async with backend:
        for cve in cves:
            cve_id = cve["cve_id"]

            # Create/update Vulnerability node
            merge_vuln = """
            MERGE (v:Vulnerability {cve_id: $cve_id, tenant_id: $tid})
            ON CREATE SET
              v.id                = $vid,
              v.cvss_score        = $cvss_score,
              v.cvss_severity     = $cvss_severity,
              v.description       = $description,
              v.published_date    = $published_date,
              v.exploit_available = $exploit_available,
              v.actively_exploited= $actively_exploited,
              v.tenant_id         = $tid
            ON MATCH SET
              v.cvss_score        = $cvss_score,
              v.cvss_severity     = $cvss_severity,
              v.description       = $description
            RETURN id(v) AS vuln_id
            """
            try:
                rows = await backend.query(merge_vuln, {
                    "cve_id":             cve_id,
                    "tid":                tid,
                    "vid":                str(uuid.uuid4()),
                    "cvss_score":         cve["cvss_score"],
                    "cvss_severity":      cve["cvss_severity"],
                    "description":        cve["description"],
                    "published_date":     cve["published_date"],
                    "exploit_available":  cve["exploit_available"],
                    "actively_exploited": cve["actively_exploited"],
                }, tenant.id)
            except Exception:
                continue

            # Match CPE strings to Application nodes by product name
            for cpe in cve["cpe_matches"][:10]:  # limit per CVE
                parts = cpe.split(":")
                if len(parts) < 5:
                    continue
                product = parts[4].replace("_", " ").lower()
                if not product or product == "*":
                    continue

                link_cypher = """
                MATCH (a:Application) WHERE a.tenant_id = $tid
                  AND toLower(a.name) CONTAINS $product
                MATCH (v:Vulnerability {cve_id: $cve_id, tenant_id: $tid})
                MERGE (a) -[:HAS_VULNERABILITY]-> (v)
                RETURN count(*) AS linked
                """
                try:
                    result = await backend.query(link_cypher, {
                        "tid": tid, "product": product, "cve_id": cve_id,
                    }, tenant.id)
                    if result:
                        linked += result[0].get("linked", 0)
                except Exception:
                    continue

    log.info(f"Tenant {tid}: linked {linked} CVE relationships")


@app.task(
    name="dgraphai.tasks.cve_sync.check_cisa_kev",
    queue="default",
    max_retries=2,
)
def check_cisa_kev():
    """
    Download CISA Known Exploited Vulnerabilities catalog and mark
    matching Vulnerability nodes as actively_exploited=True.
    """
    asyncio.run(_check_kev_async())


async def _check_kev_async():
    """CISA KEV catalog: https://www.cisa.gov/known-exploited-vulnerabilities-catalog"""
    CISA_KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(CISA_KEV_URL)
            resp.raise_for_status()
            kev_data = resp.json()
        except Exception as e:
            log.error(f"CISA KEV fetch failed: {e}")
            return

    kev_ids = {v["cveID"] for v in kev_data.get("vulnerabilities", [])}
    log.info(f"CISA KEV: {len(kev_ids)} actively exploited CVEs")

    from src.dgraphai.db.session import async_session
    from src.dgraphai.db.models import Tenant
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(select(Tenant).where(Tenant.is_active == True))
        tenants = result.scalars().all()

    for tenant in tenants:
        backend = get_backend_for_tenant(
            tenant.graph_backend or "neo4j", tenant.graph_config or {}
        )
        async with backend:
            for cve_id in kev_ids:
                try:
                    await backend.query(
                        "MATCH (v:Vulnerability {cve_id: $cve_id, tenant_id: $tid}) "
                        "SET v.actively_exploited = true, v.exploit_available = true",
                        {"cve_id": cve_id, "tid": str(tenant.id)},
                        tenant.id,
                    )
                except Exception:
                    pass
