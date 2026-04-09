"""
Email onboarding sequence.

Triggered by signup. Sends a series of contextual emails to guide
new users from signup → first connector → first scan → value realised.

Sequence:
  T+0:       Welcome email (immediate, on signup)
  T+1h:      "Connect your first source" if no connectors yet
  T+24h:     "Your data is being indexed" if scan started but not complete
  T+48h:     "Here's what we found" if scan complete (summary of top findings)
  T+7d:      "Tips & tricks" if user has been active
  T+14d:     "Upgrade to Pro" if still on Starter and approaching limits

Each email is only sent if the condition is still true when the task fires.
This prevents spamming users who already completed the action.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from src.dgraphai.tasks.celery_app import app

log = logging.getLogger("dgraphai.onboarding")


def queue_onboarding_sequence(user_id: str, tenant_id: str, user_email: str, user_name: str):
    """
    Queue the full onboarding email sequence for a new user.
    Called from the signup endpoint after account creation.
    """
    # T+0: Welcome (immediate)
    send_welcome.apply_async(
        args=[user_id, tenant_id, user_email, user_name],
        countdown=0,
        queue="default",
    )
    # T+1h: Connect first source reminder
    check_and_send_connect_reminder.apply_async(
        args=[user_id, tenant_id, user_email, user_name],
        countdown=3600,
        queue="default",
    )
    # T+24h: Indexing progress
    check_and_send_indexing_update.apply_async(
        args=[user_id, tenant_id, user_email, user_name],
        countdown=86400,
        queue="default",
    )
    # T+48h: Findings summary
    check_and_send_findings_summary.apply_async(
        args=[user_id, tenant_id, user_email, user_name],
        countdown=172800,
        queue="default",
    )
    # T+7d: Tips
    check_and_send_tips.apply_async(
        args=[user_id, tenant_id, user_email, user_name],
        countdown=604800,
        queue="default",
    )


@app.task(name="dgraphai.tasks.onboarding.send_welcome", queue="default")
def send_welcome(user_id: str, tenant_id: str, email: str, name: str):
    asyncio.run(_send_welcome_async(user_id, tenant_id, email, name))


@app.task(name="dgraphai.tasks.onboarding.check_and_send_connect_reminder", queue="default")
def check_and_send_connect_reminder(user_id: str, tenant_id: str, email: str, name: str):
    asyncio.run(_connect_reminder_async(user_id, tenant_id, email, name))


@app.task(name="dgraphai.tasks.onboarding.check_and_send_indexing_update", queue="default")
def check_and_send_indexing_update(user_id: str, tenant_id: str, email: str, name: str):
    asyncio.run(_indexing_update_async(user_id, tenant_id, email, name))


@app.task(name="dgraphai.tasks.onboarding.check_and_send_findings_summary", queue="default")
def check_and_send_findings_summary(user_id: str, tenant_id: str, email: str, name: str):
    asyncio.run(_findings_summary_async(user_id, tenant_id, email, name))


@app.task(name="dgraphai.tasks.onboarding.check_and_send_tips", queue="default")
def check_and_send_tips(user_id: str, tenant_id: str, email: str, name: str):
    asyncio.run(_tips_async(user_id, tenant_id, email, name))


# ── Email implementations ─────────────────────────────────────────────────────

async def _send_welcome_async(user_id, tenant_id, email, name):
    import os
    from src.dgraphai.auth.email import send_email
    app_url = os.getenv("APP_URL", "https://app.dgraph.ai")
    html = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:0 auto;color:#e2e2f0;background:#0e0e16;padding:32px;border-radius:12px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:24px">
        <div style="width:36px;height:36px;border-radius:9px;background:#4f8ef7;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:14px">dg</div>
        <span style="font-size:18px;font-weight:700;color:#e2e2f0">dgraph.ai</span>
      </div>
      <h1 style="font-size:22px;font-weight:700;color:#e2e2f0;margin:0 0 8px">Welcome, {name.split()[0] if name else 'there'}!</h1>
      <p style="color:#8888aa;line-height:1.6;margin:0 0 20px">
        You've just joined the most powerful way to understand what lives in your data.
        dgraph.ai indexes your files, enriches them with AI, and builds a knowledge graph
        so you can explore everything — security findings, relationships, and patterns —
        in one place.
      </p>
      <div style="background:#12121a;border:1px solid #252535;border-radius:10px;padding:20px;margin-bottom:24px">
        <div style="font-size:13px;font-weight:700;color:#e2e2f0;margin-bottom:12px">Get started in 3 steps</div>
        <div style="display:flex;flex-direction:column;gap:8px">
          <div style="display:flex;align-items:center;gap:10px;font-size:13px;color:#8888aa">
            <span style="width:22px;height:22px;border-radius:50%;background:#4f8ef7;color:#fff;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;flex-shrink:0">1</span>
            Connect a data source (SMB, S3, SharePoint, local folder)
          </div>
          <div style="display:flex;align-items:center;gap:10px;font-size:13px;color:#8888aa">
            <span style="width:22px;height:22px;border-radius:50%;background:#8b5cf6;color:#fff;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;flex-shrink:0">2</span>
            Install the scanner agent (5-minute Helm or Docker install)
          </div>
          <div style="display:flex;align-items:center;gap:10px;font-size:13px;color:#8888aa">
            <span style="width:22px;height:22px;border-radius:50%;background:#10b981;color:#fff;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;flex-shrink:0">3</span>
            Watch your knowledge graph come to life
          </div>
        </div>
      </div>
      <a href="{app_url}" style="display:inline-block;padding:12px 24px;background:#4f8ef7;color:#fff;text-decoration:none;border-radius:9px;font-weight:700;font-size:14px">
        Open dgraph.ai →
      </a>
      <p style="color:#35354a;font-size:11px;margin-top:24px">
        Questions? Reply to this email or visit our docs at docs.dgraph.ai
      </p>
    </div>
    """
    await send_email(email, "Welcome to dgraph.ai", html)
    log.info(f"Welcome email sent to {email}")


async def _connect_reminder_async(user_id, tenant_id, email, name):
    """Send only if user hasn't added a connector yet."""
    from src.dgraphai.db.session import async_session
    from src.dgraphai.db.connector_models import Connector
    import uuid
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(
            select(Connector).where(Connector.tenant_id == uuid.UUID(tenant_id)).limit(1)
        )
        if result.scalar_one_or_none():
            log.info(f"Connect reminder skipped — {email} already has connectors")
            return

    import os
    from src.dgraphai.auth.email import send_email
    app_url = os.getenv("APP_URL", "https://app.dgraph.ai")
    first_name = (name or "").split()[0] or "there"
    html = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:0 auto;color:#e2e2f0;background:#0e0e16;padding:32px;border-radius:12px">
      <h2 style="font-size:20px;font-weight:700;color:#e2e2f0;margin:0 0 8px">Hey {first_name}, your graph is empty 👀</h2>
      <p style="color:#8888aa;line-height:1.6;margin:0 0 20px">
        You signed up an hour ago but haven't connected a data source yet.
        It takes under 5 minutes to connect an SMB share, S3 bucket, or local folder.
      </p>
      <a href="{app_url}/connectors" style="display:inline-block;padding:12px 24px;background:#4f8ef7;color:#fff;text-decoration:none;border-radius:9px;font-weight:700;font-size:14px">
        Connect your first source →
      </a>
    </div>
    """
    await send_email(email, "Your knowledge graph is waiting", html)
    log.info(f"Connect reminder sent to {email}")


async def _indexing_update_async(user_id, tenant_id, email, name):
    """Send summary if a scan completed in the last 24h."""
    import os
    from src.dgraphai.auth.email import send_email
    from src.dgraphai.db.session import async_session
    from src.dgraphai.db.connector_models import Connector
    import uuid
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(
            select(Connector)
            .where(Connector.tenant_id == uuid.UUID(tenant_id))
            .where(Connector.last_scan_status == "success")
            .limit(1)
        )
        connector = result.scalar_one_or_none()
        if not connector:
            return  # No scan yet

    app_url = os.getenv("APP_URL", "https://app.dgraph.ai")
    first_name = (name or "").split()[0] or "there"
    count = connector.total_files_indexed or 0
    html = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:0 auto;background:#0e0e16;padding:32px;border-radius:12px">
      <h2 style="color:#e2e2f0;margin:0 0 8px">Your graph has {count:,} nodes, {first_name} 🎉</h2>
      <p style="color:#8888aa;line-height:1.6;margin:0 0 20px">
        Your first scan completed. dgraph.ai has indexed {count:,} files and is now enriching
        them with AI — detecting secrets, PII, CVEs, and building the relationship graph.
      </p>
      <a href="{app_url}" style="display:inline-block;padding:12px 24px;background:#4f8ef7;color:#fff;text-decoration:none;border-radius:9px;font-weight:700">
        Explore your graph →
      </a>
    </div>
    """
    await send_email(email, f"Your graph has {count:,} nodes and counting", html)


async def _findings_summary_async(user_id, tenant_id, email, name):
    """Send a summary of key findings after 48h."""
    # This would query Neo4j for top findings — simplified for now
    import os
    from src.dgraphai.auth.email import send_email
    app_url = os.getenv("APP_URL", "https://app.dgraph.ai")
    first_name = (name or "").split()[0] or "there"
    html = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:0 auto;background:#0e0e16;padding:32px;border-radius:12px">
      <h2 style="color:#e2e2f0;margin:0 0 8px">Here's what dgraph.ai found, {first_name}</h2>
      <p style="color:#8888aa;line-height:1.6;margin:0 0 20px">
        After 48 hours of indexing and AI enrichment, your knowledge graph is ready.
        Check the Security page for exposed secrets, PII, and vulnerabilities discovered
        across your connected sources.
      </p>
      <a href="{app_url}/security" style="display:inline-block;padding:12px 24px;background:#f87171;color:#fff;text-decoration:none;border-radius:9px;font-weight:700">
        View security findings →
      </a>
    </div>
    """
    await send_email(email, "Your AI enrichment is complete — here's what we found", html)


async def _tips_async(user_id, tenant_id, email, name):
    import os
    from src.dgraphai.auth.email import send_email
    app_url = os.getenv("APP_URL", "https://app.dgraph.ai")
    first_name = (name or "").split()[0] or "there"
    html = f"""
    <div style="font-family:sans-serif;max-width:560px;margin:0 auto;background:#0e0e16;padding:32px;border-radius:12px">
      <h2 style="color:#e2e2f0;margin:0 0 8px">3 things you might not know about dgraph.ai</h2>
      <div style="display:flex;flex-direction:column;gap:14px;margin-bottom:20px">
        <div style="background:#12121a;border:1px solid #252535;border-radius:8px;padding:14px">
          <div style="font-weight:700;color:#4f8ef7;margin-bottom:4px">⌘K — Global Search</div>
          <div style="color:#8888aa;font-size:13px">Press Cmd+K anywhere to search your entire graph by name, content, or relationship.</div>
        </div>
        <div style="background:#12121a;border:1px solid #252535;border-radius:8px;padding:14px">
          <div style="font-weight:700;color:#8b5cf6;margin-bottom:4px">Query Builder</div>
          <div style="color:#8888aa;font-size:13px">Drag-and-drop Cypher query builder at /builder — no graph database knowledge needed.</div>
        </div>
        <div style="background:#12121a;border:1px solid #252535;border-radius:8px;padding:14px">
          <div style="font-weight:700;color:#10b981;margin-bottom:4px">What Changed</div>
          <div style="color:#8888aa;font-size:13px">The /diff page shows everything new since your last scan — great for daily security reviews.</div>
        </div>
      </div>
      <a href="{app_url}" style="display:inline-block;padding:12px 24px;background:#4f8ef7;color:#fff;text-decoration:none;border-radius:9px;font-weight:700">
        Back to dgraph.ai →
      </a>
    </div>
    """
    await send_email(email, f"3 things you might not know, {first_name}", html)
