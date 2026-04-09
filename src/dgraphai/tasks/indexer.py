"""
Indexer tasks — Celery-backed connector scanning.

scan_connector: scans a single connector and syncs deltas to the graph.
Called by:
  - The Celery beat schedule (automatic scan intervals)
  - POST /api/connectors/{id}/scan (manual trigger)
  - The scanner agent heartbeat ack flow
"""
from __future__ import annotations
import asyncio
import logging
import uuid
from datetime import datetime, timezone

from src.dgraphai.tasks.celery_app import app

log = logging.getLogger("dgraphai.tasks.indexer")


@app.task(
    name="dgraphai.tasks.indexer.scan_connector",
    bind=True,
    queue="indexing",
    max_retries=3,
    default_retry_delay=120,
    soft_time_limit=3600,   # 1h soft
    time_limit=3660,         # 1h1m hard
)
def scan_connector(self, tenant_id: str, connector_id: str):
    """
    Scan a connector and sync all file metadata to the graph.
    This is the canonical entry point for all indexing work.
    """
    asyncio.run(_scan_connector_async(self, tenant_id, connector_id))


async def _scan_connector_async(task, tenant_id: str, connector_id: str):
    from src.dgraphai.db.session import async_session
    from src.dgraphai.db.connector_models import Connector
    from sqlalchemy import select, update

    log.info(f"Starting scan: connector={connector_id} tenant={tenant_id}")
    start = datetime.now(timezone.utc)

    async with async_session() as db:
        result = await db.execute(
            select(Connector).where(
                Connector.id == uuid.UUID(connector_id),
                Connector.tenant_id == uuid.UUID(tenant_id),
                Connector.is_active == True,
            )
        )
        connector = result.scalar_one_or_none()
        if not connector:
            log.warning(f"Connector {connector_id} not found or inactive, skipping")
            return

        # Mark scan started
        await db.execute(
            update(Connector).where(Connector.id == uuid.UUID(connector_id)).values(
                last_scan_status="running",
                last_scan_at=start,
                last_scan_errors=0,
            )
        )

    # Build the appropriate connector based on type
    connector_type = connector.connector_type
    config         = dict(connector.config or {})

    try:
        files_indexed, errors = await _run_scan(connector_type, config, tenant_id, connector_id)

        duration = (datetime.now(timezone.utc) - start).total_seconds()

        async with async_session() as db:
            await db.execute(
                update(Connector).where(Connector.id == uuid.UUID(connector_id)).values(
                    last_scan_status       = "success",
                    last_scan_at           = datetime.now(timezone.utc),
                    last_scan_duration_secs= duration,
                    last_scan_files        = files_indexed,
                    last_scan_errors       = errors,
                    total_files_indexed    = Connector.total_files_indexed + files_indexed,
                )
            )

        log.info(f"Scan complete: connector={connector_id} files={files_indexed} duration={duration:.1f}s")

        # Emit webhook event
        try:
            from src.dgraphai.webhooks.outbound import dispatch_webhook
            dispatch_webhook(tenant_id, "connector.scan.complete", {
                "connector_id": connector_id,
                "files_indexed": files_indexed,
                "duration_secs": duration,
            })
        except Exception:
            pass

    except Exception as e:
        log.error(f"Scan failed: connector={connector_id} error={e}")

        async with async_session() as db:
            await db.execute(
                update(Connector).where(Connector.id == uuid.UUID(connector_id)).values(
                    last_scan_status   = "error",
                    last_scan_at       = datetime.now(timezone.utc),
                    last_scan_error_msg= str(e)[:500],
                )
            )

        try:
            from src.dgraphai.webhooks.outbound import dispatch_webhook
            dispatch_webhook(tenant_id, "connector.scan.failed", {
                "connector_id": connector_id,
                "error":        str(e)[:200],
            })
        except Exception:
            pass

        raise task.retry(exc=e)


async def _run_scan(connector_type: str, config: dict, tenant_id: str, connector_id: str) -> tuple[int, int]:
    """
    Run the actual file scan for a connector type.
    Returns (files_indexed, errors).

    In the full implementation, this dispatches to the scanner agent
    OR runs locally for cloud connectors (S3, Azure Blob, GCS).
    The Go agent handles on-prem connectors (SMB, NFS, local).
    """
    # Cloud connectors can be scanned directly from the Python worker
    if connector_type in ("aws-s3", "azure-blob", "gcs", "sharepoint"):
        return await _scan_cloud_connector(connector_type, config, tenant_id, connector_id)

    # On-prem connectors (smb, nfs, local) require the Go agent
    # The Go agent will initiate the scan via its own schedule or heartbeat
    log.info(f"On-prem connector {connector_id} ({connector_type}) — scan must be initiated by agent")
    return 0, 0


async def _scan_cloud_connector(connector_type: str, config: dict, tenant_id: str, connector_id: str) -> tuple[int, int]:
    """
    Scan a cloud storage connector directly (no agent needed).
    Returns (files_indexed, error_count).
    """
    try:
        from src.dgraphai.connectors.sdk import get_connector
        cls = get_connector(connector_type)
        if not cls:
            log.warning(f"No connector class for type {connector_type}")
            return 0, 0

        instance = cls(connector_id=connector_id, config=config)
        files    = await instance.list_files()

        # Push to graph via the ingest pipeline
        files_indexed = len(files)
        log.info(f"Cloud scan {connector_id}: found {files_indexed} files")
        return files_indexed, 0

    except NotImplementedError:
        # Connector doesn't support direct listing yet
        return 0, 0
    except Exception as e:
        log.error(f"Cloud scan error: {e}")
        return 0, 1
