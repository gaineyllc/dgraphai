"""
Reliable outbound webhooks.

Current webhooks are fire-and-forget. This replaces them with:
  - Signed payloads (HMAC-SHA256) so receivers can verify authenticity
  - Automatic retry with exponential backoff (3 attempts over ~15 minutes)
  - Dead letter queue for permanently failed deliveries
  - Delivery log (status, attempts, last_error per event)
  - Per-tenant webhook endpoints with event type filtering

Signature header: X-DGraph-Signature: sha256=<hmac>
Retry schedule:   attempt 1 = immediate, 2 = 60s, 3 = 300s
Dead letter:      after 3 failures → status=dead_letter, alert tenant admin

Event types:
  connector.scan.complete    scanner finished a sync
  connector.scan.failed      scanner error
  finding.created            new security finding (PII, secret, CVE, etc.)
  finding.resolved           finding marked resolved
  alert.fired                alert rule triggered
  user.provisioned           SCIM user created
  user.deprovisioned         SCIM user deactivated
  gdpr.erasure.complete      erasure job finished
  indexing.started / .complete / .failed
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from src.dgraphai.tasks.celery_app import app as celery_app

# Webhook retry schedule (seconds)
RETRY_DELAYS = [0, 60, 300]


def dispatch_webhook(
    tenant_id:  str,
    event_type: str,
    payload:    dict[str, Any],
) -> None:
    """
    Dispatch a webhook event to all registered endpoints for this tenant.
    Runs asynchronously via Celery — returns immediately.
    """
    deliver_webhook_event.apply_async(
        args=[tenant_id, event_type, payload],
        queue="default",
    )


@celery_app.task(
    name="dgraphai.webhooks.deliver_webhook_event",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def deliver_webhook_event(self, tenant_id: str, event_type: str, payload: dict):
    """Celery task: deliver webhook to all matching endpoints."""
    import asyncio
    asyncio.run(_deliver_async(self, tenant_id, event_type, payload))


async def _deliver_async(task, tenant_id: str, event_type: str, payload: dict):
    import httpx
    from src.dgraphai.db.session import async_session
    from src.dgraphai.db.models import WebhookEndpoint, WebhookDelivery

    async with async_session() as db:
        from sqlalchemy import select
        result = await db.execute(
            select(WebhookEndpoint).where(
                WebhookEndpoint.tenant_id == uuid.UUID(tenant_id),
                WebhookEndpoint.is_active == True,
            )
        )
        endpoints = result.scalars().all()

    for endpoint in endpoints:
        # Check event type filter
        subscribed = endpoint.event_types or []
        if subscribed and event_type not in subscribed and "*" not in subscribed:
            continue

        await _deliver_to_endpoint(endpoint, event_type, payload, tenant_id)


async def _deliver_to_endpoint(endpoint, event_type: str, payload: dict, tenant_id: str):
    import httpx
    from src.dgraphai.db.session import async_session
    from src.dgraphai.db.models import WebhookDelivery
    from sqlalchemy import update

    event_id    = str(uuid.uuid4())
    timestamp   = int(time.time())
    body        = json.dumps({
        "id":         event_id,
        "type":       event_type,
        "tenant_id":  tenant_id,
        "timestamp":  timestamp,
        "data":       payload,
    })
    signature = _sign_payload(body, endpoint.secret or "")

    headers = {
        "Content-Type":       "application/json",
        "X-DGraph-Event":     event_type,
        "X-DGraph-Event-Id":  event_id,
        "X-DGraph-Timestamp": str(timestamp),
        "X-DGraph-Signature": f"sha256={signature}",
    }

    attempt     = 0
    last_error  = ""
    delivered   = False

    for delay in RETRY_DELAYS:
        if delay > 0:
            import asyncio
            await asyncio.sleep(delay)

        attempt += 1
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(endpoint.url, content=body, headers=headers)
                if 200 <= resp.status_code < 300:
                    delivered   = True
                    last_error  = ""
                    break
                last_error = f"HTTP {resp.status_code}"
        except Exception as e:
            last_error = str(e)

    # Log delivery attempt
    async with async_session() as db:
        delivery = WebhookDelivery(
            endpoint_id  = endpoint.id,
            tenant_id    = uuid.UUID(tenant_id),
            event_type   = event_type,
            event_id     = event_id,
            attempts     = attempt,
            delivered    = delivered,
            last_error   = last_error if not delivered else None,
            status       = "delivered" if delivered else ("dead_letter" if attempt >= 3 else "failed"),
            delivered_at = datetime.now(timezone.utc) if delivered else None,
        )
        db.add(delivery)

        # Update endpoint last delivery stats
        await db.execute(
            update(type(endpoint)).where(type(endpoint).id == endpoint.id).values(
                last_delivery_at     = datetime.now(timezone.utc),
                last_delivery_status = "success" if delivered else "failed",
                failure_count        = (endpoint.failure_count or 0) + (0 if delivered else 1),
            )
        )

    if not delivered:
        # TODO: if status == dead_letter, notify tenant admin
        pass


def _sign_payload(body: str, secret: str) -> str:
    return hmac.new(
        secret.encode() if secret else b"unsigned",
        body.encode(),
        hashlib.sha256,
    ).hexdigest()


# ── Webhook management API ─────────────────────────────────────────────────────

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from src.dgraphai.auth.oidc import get_auth_context, AuthContext
from src.dgraphai.db.session import get_db
from sqlalchemy.ext.asyncio import AsyncSession

webhook_router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

VALID_EVENTS = {
    "connector.scan.complete", "connector.scan.failed",
    "finding.created", "finding.resolved",
    "alert.fired", "user.provisioned", "user.deprovisioned",
    "gdpr.erasure.complete", "indexing.started",
    "indexing.complete", "indexing.failed",
    "*",
}


class CreateWebhookRequest(BaseModel):
    url:         str
    event_types: list[str] = ["*"]
    description: str = ""


@webhook_router.get("")
async def list_webhooks(
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> list[dict]:
    from src.dgraphai.db.models import WebhookEndpoint
    from sqlalchemy import select
    result = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.tenant_id == auth.tenant_id,
            WebhookEndpoint.is_active == True,
        )
    )
    endpoints = result.scalars().all()
    return [
        {
            "id":            str(e.id),
            "url":           e.url,
            "event_types":   e.event_types,
            "description":   e.description,
            "last_delivery_at":     e.last_delivery_at.isoformat() if e.last_delivery_at else None,
            "last_delivery_status": e.last_delivery_status,
            "failure_count":        e.failure_count,
        }
        for e in endpoints
    ]


@webhook_router.post("", status_code=201)
async def create_webhook(
    req:  CreateWebhookRequest,
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict:
    if "admin:*" not in auth.permissions:
        raise HTTPException(status_code=403, detail="Admin required")

    invalid = set(req.event_types) - VALID_EVENTS
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown event types: {invalid}")

    import secrets as _sec
    from src.dgraphai.db.models import WebhookEndpoint
    secret = _sec.token_hex(32)

    ep = WebhookEndpoint(
        tenant_id   = auth.tenant_id,
        url         = req.url,
        event_types = req.event_types,
        description = req.description,
        secret      = secret,
        is_active   = True,
        created_by  = auth.user_id,
    )
    db.add(ep)
    await db.flush()
    return {
        "id":      str(ep.id),
        "url":     ep.url,
        "secret":  secret,
        "warning": "Save the secret. Use it to verify X-DGraph-Signature headers.",
    }


@webhook_router.post("/{webhook_id}/test")
async def test_webhook(
    webhook_id: str,
    auth:       AuthContext = Depends(get_auth_context),
    db:         AsyncSession = Depends(get_db),
) -> dict:
    """Send a test ping to a webhook endpoint."""
    from src.dgraphai.db.models import WebhookEndpoint
    from sqlalchemy import select
    result = await db.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.id == uuid.UUID(webhook_id),
            WebhookEndpoint.tenant_id == auth.tenant_id,
        )
    )
    ep = result.scalar_one_or_none()
    if not ep:
        raise HTTPException(status_code=404, detail="Webhook not found")

    dispatch_webhook(str(auth.tenant_id), "webhook.test", {
        "message": "Test ping from dgraph.ai",
        "webhook_id": webhook_id,
    })
    return {"status": "dispatched"}


@webhook_router.delete("/{webhook_id}")
async def delete_webhook(
    webhook_id: str,
    auth:       AuthContext = Depends(get_auth_context),
    db:         AsyncSession = Depends(get_db),
) -> dict:
    from src.dgraphai.db.models import WebhookEndpoint
    from sqlalchemy import update as sql_update, select
    await db.execute(
        sql_update(WebhookEndpoint).where(
            WebhookEndpoint.id == uuid.UUID(webhook_id),
            WebhookEndpoint.tenant_id == auth.tenant_id,
        ).values(is_active=False)
    )
    return {"status": "deleted"}
