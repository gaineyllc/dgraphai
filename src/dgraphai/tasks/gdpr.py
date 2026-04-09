"""
GDPR right-to-erasure tasks.
Deletes all personal data for a user/tenant across Postgres + graph DB.
Runs as a Celery task for durability (survives crashes, retried on failure).
"""
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone

from src.dgraphai.tasks.celery_app import app

log = logging.getLogger("dgraphai.gdpr")


async def queue_erasure_job(user_id: str, tenant_id: str) -> str:
    """Queue an erasure job and return the job ID."""
    from src.dgraphai.db.session import async_session
    from src.dgraphai.db.models import GDPRErasureJob

    async with async_session() as db:
        job = GDPRErasureJob(user_id=user_id, tenant_id=tenant_id, status="pending")
        db.add(job)
        await db.flush()
        job_id = str(job.id)

    # Dispatch Celery task
    erase_user_data.apply_async(
        args=[user_id, tenant_id, job_id],
        queue="gdpr",
        countdown=0,
    )
    return job_id


@app.task(
    name="dgraphai.tasks.gdpr.erase_user_data",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def erase_user_data(self, user_id: str, tenant_id: str, job_id: str):
    """
    Permanently erase all personal data for a user.
    For account owners (tenant admins), also erases the tenant graph data.
    """
    import asyncio
    asyncio.run(_erase_user_data_async(self, user_id, tenant_id, job_id))


async def _erase_user_data_async(task, user_id: str, tenant_id: str, job_id: str):
    from src.dgraphai.db.session import async_session
    from src.dgraphai.db.models import (
        GDPRErasureJob, User, LocalCredential, MFAConfig,
        UserSession, APIKey, AuditLog, EmailVerificationToken, PasswordResetToken,
    )
    from sqlalchemy import delete, update, select

    log.info(f"Starting erasure for user={user_id} tenant={tenant_id}")

    try:
        async with async_session() as db:
            # Mark job running
            await db.execute(
                update(GDPRErasureJob)
                .where(GDPRErasureJob.id == uuid.UUID(job_id))
                .values(status="running")
            )
            await db.flush()

            uid = uuid.UUID(user_id)

            # 1. Delete auth data
            await db.execute(delete(LocalCredential).where(LocalCredential.user_id == uid))
            await db.execute(delete(MFAConfig).where(MFAConfig.user_id == uid))
            await db.execute(delete(UserSession).where(UserSession.user_id == uid))
            await db.execute(delete(APIKey).where(APIKey.user_id == uid))
            await db.execute(delete(EmailVerificationToken).where(EmailVerificationToken.user_id == uid))
            await db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == uid))

            # 2. Anonymize (not delete) audit logs — required for compliance
            await db.execute(
                update(AuditLog)
                .where(AuditLog.user_id == uid)
                .values(user_id=None, ip_address="[erased]", user_agent="[erased]")
            )

            # 3. Anonymize user record (don't delete — breaks FK references)
            await db.execute(
                update(User).where(User.id == uid).values(
                    email        = f"erased-{user_id[:8]}@erased.invalid",
                    display_name = "[Erased]",
                    external_id  = None,
                    is_active    = False,
                )
            )

            # 4. Check if this is the tenant owner (only user) → erase graph data
            other_users = await db.execute(
                select(User).where(
                    User.tenant_id == uuid.UUID(tenant_id),
                    User.id != uid,
                    User.is_active == True,
                )
            )
            if not other_users.scalars().first():
                # Last user — schedule graph data erasure
                await _erase_graph_data(tenant_id, db)

            # 5. Mark complete
            await db.execute(
                update(GDPRErasureJob)
                .where(GDPRErasureJob.id == uuid.UUID(job_id))
                .values(status="complete", completed_at=datetime.now(timezone.utc))
            )
            log.info(f"Erasure complete for user={user_id}")

    except Exception as e:
        log.error(f"Erasure failed for user={user_id}: {e}")
        try:
            async with async_session() as db:
                await db.execute(
                    update(GDPRErasureJob)
                    .where(GDPRErasureJob.id == uuid.UUID(job_id))
                    .values(status="failed", error=str(e))
                )
        except Exception:
            pass
        raise task.retry(exc=e)


async def _erase_graph_data(tenant_id: str, db):
    """Remove all graph nodes and relationships for a tenant."""
    from src.dgraphai.db.models import Tenant
    from src.dgraphai.graph.backends.factory import get_backend_for_tenant
    from sqlalchemy import select

    result = await db.execute(select(Tenant).where(Tenant.id == uuid.UUID(tenant_id)))
    tenant = result.scalar_one_or_none()
    if not tenant:
        return

    backend = get_backend_for_tenant(tenant.graph_backend or "neo4j", tenant.graph_config or {})
    try:
        async with backend:
            # Delete all nodes for this tenant in batches
            batch = 0
            while True:
                rows = await backend.query(
                    "MATCH (n) WHERE n.tenant_id = $tid "
                    "WITH n LIMIT 10000 DETACH DELETE n RETURN count(*) AS c",
                    {"tid": tenant_id}, uuid.UUID(tenant_id)
                )
                deleted = rows[0].get("c", 0) if rows else 0
                log.info(f"Deleted {deleted} graph nodes for tenant={tenant_id} batch={batch}")
                if not deleted:
                    break
                batch += 1
    except Exception as e:
        log.error(f"Graph erasure failed for tenant={tenant_id}: {e}")
        raise
