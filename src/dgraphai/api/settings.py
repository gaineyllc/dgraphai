"""
Settings API — tenant settings, user preferences, danger zone, Stripe billing.
"""
from __future__ import annotations
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.dgraphai.auth.oidc import get_auth_context, AuthContext
from src.dgraphai.db.models import Tenant, User
from src.dgraphai.db.session import get_db

router = APIRouter(prefix="/api/settings", tags=["settings"])

STRIPE_SECRET = os.getenv("STRIPE_SECRET_KEY", "")
APP_URL       = os.getenv("APP_URL", "https://app.dgraph.ai")


class TenantSettingsRequest(BaseModel):
    name:     str | None = None
    timezone: str | None = None
    logo_url: str | None = None


class NotificationSettingsRequest(BaseModel):
    email_alerts:   bool = True
    slack_webhook:  str | None = None
    teams_webhook:  str | None = None
    pagerduty_key:  str | None = None
    alert_severity_threshold: str = "high"   # critical | high | medium | low


# ── Tenant settings ────────────────────────────────────────────────────────────

@router.get("/tenant")
async def get_tenant_settings(
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(select(Tenant).where(Tenant.id == auth.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return {
        "id":       str(tenant.id),
        "name":     tenant.name,
        "slug":     tenant.slug,
        "plan":     tenant.plan,
        "timezone": getattr(tenant, "timezone", "UTC"),
        "logo_url": getattr(tenant, "logo_url", None),
        "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
    }


@router.patch("/tenant")
async def update_tenant_settings(
    req:  TenantSettingsRequest,
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if "admin:*" not in auth.permissions:
        raise HTTPException(status_code=403, detail="Admin required")

    updates = {}
    if req.name:     updates["name"]     = req.name
    if req.timezone: updates["timezone"] = req.timezone
    if req.logo_url is not None: updates["logo_url"] = req.logo_url

    if updates:
        await db.execute(update(Tenant).where(Tenant.id == auth.tenant_id).values(**updates))

    return {"status": "updated"}


# ── Notification settings ──────────────────────────────────────────────────────

@router.get("/notifications")
async def get_notification_settings(
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(select(Tenant).where(Tenant.id == auth.tenant_id))
    tenant = result.scalar_one_or_none()
    cfg    = getattr(tenant, "notification_config", {}) or {}
    return {
        "email_alerts":               cfg.get("email_alerts", True),
        "slack_webhook":              cfg.get("slack_webhook"),
        "teams_webhook":              cfg.get("teams_webhook"),
        "pagerduty_key_set":          bool(cfg.get("pagerduty_key")),
        "alert_severity_threshold":   cfg.get("alert_severity_threshold", "high"),
    }


@router.patch("/notifications")
async def update_notification_settings(
    req:  NotificationSettingsRequest,
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict:
    if "admin:*" not in auth.permissions:
        raise HTTPException(status_code=403, detail="Admin required")

    result = await db.execute(select(Tenant).where(Tenant.id == auth.tenant_id))
    tenant = result.scalar_one_or_none()
    existing = dict(getattr(tenant, "notification_config", {}) or {})
    existing.update({
        "email_alerts":               req.email_alerts,
        "alert_severity_threshold":   req.alert_severity_threshold,
    })
    if req.slack_webhook  is not None: existing["slack_webhook"]  = req.slack_webhook
    if req.teams_webhook  is not None: existing["teams_webhook"]  = req.teams_webhook
    if req.pagerduty_key  is not None: existing["pagerduty_key"]  = req.pagerduty_key

    await db.execute(
        update(Tenant).where(Tenant.id == auth.tenant_id)
        .values(notification_config=existing)
    )
    return {"status": "updated"}


# ── Stripe billing ─────────────────────────────────────────────────────────────

@router.get("/billing")
async def get_billing_info(
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get current billing status, plan, and Stripe customer portal link."""
    result = await db.execute(select(Tenant).where(Tenant.id == auth.tenant_id))
    tenant = result.scalar_one_or_none()

    billing: dict[str, Any] = {
        "plan":              tenant.plan,
        "stripe_customer_id":getattr(tenant, "stripe_customer_id", None),
        "subscription_status": getattr(tenant, "subscription_status", "none"),
        "current_period_end":  getattr(tenant, "current_period_end", None),
        "cancel_at_period_end":getattr(tenant, "cancel_at_period_end", False),
    }

    # Generate Stripe customer portal session if customer exists
    if STRIPE_SECRET and billing["stripe_customer_id"]:
        try:
            import stripe
            stripe.api_key = STRIPE_SECRET
            session = stripe.billing_portal.Session.create(
                customer  = billing["stripe_customer_id"],
                return_url= f"{APP_URL}/settings/billing",
            )
            billing["portal_url"] = session.url
        except Exception:
            pass

    return billing


@router.post("/billing/checkout")
async def create_checkout_session(
    body: dict,
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Create a Stripe Checkout session for plan upgrade.
    body: { plan: "pro" | "business" | "enterprise" }
    """
    if not STRIPE_SECRET:
        raise HTTPException(status_code=501, detail="Stripe not configured")

    plan = body.get("plan", "pro")
    PRICE_IDS = {
        "pro":      os.getenv("STRIPE_PRICE_PRO",      ""),
        "business": os.getenv("STRIPE_PRICE_BUSINESS",  ""),
        "enterprise": None,  # Sales contact
    }

    price_id = PRICE_IDS.get(plan)
    if not price_id:
        if plan == "enterprise":
            return {"redirect_url": f"{APP_URL}/contact-sales"}
        raise HTTPException(status_code=400, detail=f"Unknown plan: {plan}")

    result = await db.execute(select(Tenant).where(Tenant.id == auth.tenant_id))
    tenant = result.scalar_one_or_none()
    user_r = await db.execute(select(User).where(User.id == auth.user_id))
    user   = user_r.scalar_one_or_none()

    try:
        import stripe
        stripe.api_key = STRIPE_SECRET

        # Create or retrieve Stripe customer
        customer_id = getattr(tenant, "stripe_customer_id", None)
        if not customer_id:
            customer = stripe.Customer.create(
                email    = user.email if user else None,
                name     = tenant.name,
                metadata = {"tenant_id": str(auth.tenant_id)},
            )
            customer_id = customer.id
            await db.execute(
                update(Tenant).where(Tenant.id == auth.tenant_id)
                .values(stripe_customer_id=customer_id)
            )

        session = stripe.checkout.Session.create(
            customer    = customer_id,
            mode        = "subscription",
            line_items  = [{"price": price_id, "quantity": 1}],
            success_url = f"{APP_URL}/settings/billing?upgraded=true",
            cancel_url  = f"{APP_URL}/settings/billing",
            metadata    = {"tenant_id": str(auth.tenant_id), "plan": plan},
            subscription_data = {
                "metadata": {"tenant_id": str(auth.tenant_id), "plan": plan}
            },
        )
        return {"checkout_url": session.url, "session_id": session.id}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe error: {e}")


@router.post("/billing/webhook")
async def stripe_webhook(
    request: __import__("fastapi").Request,
    db:      AsyncSession = Depends(get_db),
) -> dict:
    """
    Stripe webhook handler — updates subscription status on plan changes.
    Verify signature with STRIPE_WEBHOOK_SECRET.
    """
    if not STRIPE_SECRET:
        raise HTTPException(status_code=501, detail="Stripe not configured")

    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    payload        = await request.body()
    sig_header     = request.headers.get("Stripe-Signature", "")

    try:
        import stripe
        stripe.api_key = STRIPE_SECRET
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook signature failed: {e}")

    if event["type"] in ("customer.subscription.created",
                          "customer.subscription.updated",
                          "customer.subscription.deleted"):
        sub   = event["data"]["object"]
        tid   = sub.get("metadata", {}).get("tenant_id")
        plan  = sub.get("metadata", {}).get("plan", "starter")
        if tid:
            updates = {
                "subscription_status": sub["status"],
                "plan":                plan if sub["status"] == "active" else "starter",
                "current_period_end":  sub.get("current_period_end"),
                "cancel_at_period_end":sub.get("cancel_at_period_end", False),
            }
            await db.execute(
                update(Tenant).where(Tenant.id == __import__("uuid").UUID(tid))
                .values(**updates)
            )

    elif event["type"] == "invoice.payment_failed":
        inv = event["data"]["object"]
        tid = inv.get("subscription_details", {}).get("metadata", {}).get("tenant_id")
        if tid:
            # Send usage alert email to admin
            pass  # TODO: fetch admin email and send dunning email

    return {"received": True}


# ── Danger zone ────────────────────────────────────────────────────────────────

@router.post("/danger/delete-tenant")
async def delete_tenant(
    body: dict,
    auth: AuthContext = Depends(get_auth_context),
    db:   AsyncSession = Depends(get_db),
) -> dict:
    """
    Permanently delete the tenant and all data.
    Requires password confirmation and 'DELETE' typed in the body.
    """
    if "admin:*" not in auth.permissions:
        raise HTTPException(status_code=403, detail="Admin required")

    confirm = body.get("confirm", "")
    if confirm != "DELETE":
        raise HTTPException(status_code=400, detail="Type 'DELETE' to confirm")

    password = body.get("password", "")
    from src.dgraphai.db.models import LocalCredential
    from src.dgraphai.auth.local import pwd_ctx
    cr = await db.execute(
        select(LocalCredential).where(LocalCredential.user_id == auth.user_id)
    )
    cred = cr.scalar_one_or_none()
    if cred and not pwd_ctx.verify(password, cred.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect password")

    # Queue GDPR erasure for all tenant users
    from src.dgraphai.tasks.gdpr import queue_erasure_job
    result = await db.execute(
        select(User).where(User.tenant_id == auth.tenant_id, User.is_active == True)
    )
    users = result.scalars().all()
    for user in users:
        await queue_erasure_job(str(user.id), str(auth.tenant_id))

    # Mark tenant inactive immediately
    await db.execute(
        update(Tenant).where(Tenant.id == auth.tenant_id).values(is_active=False)
    )

    return {
        "status":  "queued",
        "message": "Tenant deletion queued. All data will be erased within 72 hours.",
    }
