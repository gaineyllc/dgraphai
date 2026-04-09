"""
Alert evaluation engine.
Runs alert rules on schedule, fires alerts, delivers via configured channels.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import httpx
from jinja2 import Environment

from src.dgraphai.db.alert_models import Alert, AlertRule

log = logging.getLogger("dgraphai.alerts")
jinja = Environment(autoescape=False)

# ── Built-in alert rule templates ─────────────────────────────────────────────

BUILTIN_RULES = [
    {
        "name":        "PII files accessible to all",
        "description": "Files containing PII with no access restrictions",
        "severity":    "high",
        "cypher": """
            MATCH (f:File)
            WHERE f.pii_detected = true
              AND f.tenant_id = $__tid
            RETURN f.path AS path, f.pii_types AS pii_types,
                   f.size_bytes AS size_bytes
            LIMIT 100
        """,
        "message_template": "⚠️ {{row_count}} file(s) contain PII: {{summary}}",
        "eval_schedule": "0 9 * * 1",  # Monday 9am
        "cooldown_minutes": 1440,
    },
    {
        "name":        "Files with exposed secrets",
        "description": "Source code or config files containing credentials",
        "severity":    "critical",
        "cypher": """
            MATCH (f:File)
            WHERE f.contains_secrets = true
              AND f.tenant_id = $__tid
            RETURN f.path AS path, f.secret_types AS secret_types
            LIMIT 50
        """,
        "message_template": "🚨 {{row_count}} file(s) contain exposed secrets: {{summary}}",
        "eval_schedule": "0 */4 * * *",  # every 4 hours
        "cooldown_minutes": 240,
    },
    {
        "name":        "EOL software detected",
        "description": "Executables running past end-of-life date",
        "severity":    "high",
        "cypher": """
            MATCH (f:File)
            WHERE f.eol_status = 'eol'
              AND f.tenant_id = $__tid
            RETURN f.name AS name, f.file_version AS version,
                   f.company_name AS vendor
            LIMIT 100
        """,
        "message_template": "{{row_count}} EOL application(s) found: {{summary}}",
        "eval_schedule": "0 8 * * *",  # daily 8am
        "cooldown_minutes": 1440,
    },
    {
        "name":        "Certificates expiring within 30 days",
        "description": "TLS/code signing certificates about to expire",
        "severity":    "medium",
        "cypher": """
            MATCH (f:File)
            WHERE f.file_category = 'certificate'
              AND f.days_until_expiry < 30
              AND f.days_until_expiry >= 0
              AND f.tenant_id = $__tid
            RETURN f.path AS path, f.cert_subject AS subject,
                   f.days_until_expiry AS days_left
            ORDER BY f.days_until_expiry
            LIMIT 50
        """,
        "message_template": "{{row_count}} certificate(s) expiring soon: {{summary}}",
        "eval_schedule": "0 8 * * *",
        "cooldown_minutes": 1440,
    },
    {
        "name":        "Critical CVE vulnerabilities",
        "description": "Applications with actively exploited CVEs",
        "severity":    "critical",
        "cypher": """
            MATCH (f:File)-[:HAS_VULNERABILITY]->(v:Vulnerability)
            WHERE v.cvss_severity = 'critical'
              AND v.actively_exploited = true
              AND f.tenant_id = $__tid
            RETURN f.name AS app, v.cve_id AS cve,
                   v.cvss_score AS score
            LIMIT 50
        """,
        "message_template": "🚨 {{row_count}} critical CVE(s) in actively exploited state: {{summary}}",
        "eval_schedule": "0 */2 * * *",
        "cooldown_minutes": 120,
    },
]


class AlertEngine:
    """Evaluates alert rules and dispatches notifications."""

    async def evaluate_rule(
        self,
        rule: AlertRule,
        backend: Any,
        tenant_id: UUID,
    ) -> Alert | None:
        """
        Evaluate a single alert rule.
        Returns a new Alert if the rule fires, None otherwise.
        """
        # Check cooldown
        if rule.last_fired_at:
            cooldown = timedelta(minutes=rule.cooldown_minutes or 60)
            if datetime.now(timezone.utc) - rule.last_fired_at < cooldown:
                return None

        # Check suppression
        if rule.suppress_until and rule.suppress_until > datetime.now(timezone.utc):
            return None

        try:
            async with backend:
                rows = await backend.query(rule.cypher, rule.cypher_params or {}, tenant_id)
        except Exception as e:
            log.error(f"Alert rule {rule.name!r} query failed: {e}")
            return None

        if len(rows) < (rule.threshold_count or 1):
            return None

        # Rule fired — create alert
        summary = _build_summary(rows[:5])
        message = _render_template(
            rule.message_template or "{{row_count}} item(s) found",
            {"row_count": len(rows), "summary": summary, "rows": rows[:10]},
        )

        alert = Alert(
            rule_id   = rule.id,
            tenant_id = tenant_id,
            severity  = rule.severity,
            title     = rule.name,
            message   = message,
            context   = {"rows": rows[:50], "total": len(rows)},
            row_count = len(rows),
        )
        return alert

    async def deliver(self, alert: Alert, rule: AlertRule) -> None:
        """Deliver an alert via all configured channels."""
        for channel in (rule.channels or []):
            try:
                await self._deliver_channel(alert, channel)
            except Exception as e:
                log.error(f"Alert delivery failed ({channel.get('type')}): {e}")

    async def _deliver_channel(self, alert: Alert, channel: dict) -> None:
        ch_type = channel.get("type")

        if ch_type == "webhook":
            await _deliver_webhook(alert, channel)
        elif ch_type == "slack":
            await _deliver_slack(alert, channel)
        elif ch_type == "email":
            await _deliver_email(alert, channel)
        elif ch_type == "pagerduty":
            await _deliver_pagerduty(alert, channel)
        elif ch_type == "siem":
            await _deliver_siem(alert, channel)


async def _deliver_webhook(alert: Alert, config: dict) -> None:
    payload = {
        "alert_id": str(alert.id),
        "severity": alert.severity,
        "title":    alert.title,
        "message":  alert.message,
        "fired_at": alert.fired_at.isoformat() if alert.fired_at else None,
        "row_count": alert.row_count,
        "context":  alert.context,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(
            config["url"],
            json=payload,
            headers=config.get("headers", {}),
        )


async def _deliver_slack(alert: Alert, config: dict) -> None:
    emoji = {"critical": "🚨", "high": "⚠️", "medium": "⚡", "low": "ℹ️", "info": "💡"}
    color = {"critical": "#FF0000", "high": "#FF6600", "medium": "#FFCC00",
             "low": "#00CC00", "info": "#0099FF"}
    icon  = emoji.get(alert.severity, "⚡")
    clr   = color.get(alert.severity, "#888888")

    payload = {
        "channel": config.get("channel", "#alerts"),
        "attachments": [{
            "color": clr,
            "title": f"{icon} {alert.title}",
            "text":  alert.message,
            "fields": [
                {"title": "Severity",   "value": alert.severity.upper(), "short": True},
                {"title": "Findings",   "value": str(alert.row_count),   "short": True},
            ],
            "footer": "dgraph.ai",
            "ts": int(alert.fired_at.timestamp()) if alert.fired_at else None,
        }],
    }
    async with httpx.AsyncClient(timeout=10) as client:
        webhook_url = config.get("webhook_url", "")
        if webhook_url:
            await client.post(webhook_url, json=payload)


async def _deliver_email(alert: Alert, config: dict) -> None:
    """Email delivery via SMTP (aiosmtplib)."""
    try:
        import aiosmtplib
        from email.mime.text import MIMEText
        import os

        msg          = MIMEText(f"{alert.title}\n\n{alert.message}\n\nFindings: {alert.row_count}")
        msg["Subject"] = f"[dgraph.ai] {alert.severity.upper()}: {alert.title}"
        msg["From"]    = os.getenv("SMTP_FROM", "alerts@dgraph.ai")
        msg["To"]      = config.get("to", "")

        await aiosmtplib.send(
            msg,
            hostname = os.getenv("SMTP_HOST", "localhost"),
            port     = int(os.getenv("SMTP_PORT", "587")),
            username = os.getenv("SMTP_USER"),
            password = os.getenv("SMTP_PASS"),
            use_tls  = os.getenv("SMTP_TLS", "true").lower() == "true",
        )
    except ImportError:
        log.warning("aiosmtplib not available — email delivery skipped")


async def _deliver_pagerduty(alert: Alert, config: dict) -> None:
    severity_map = {"critical": "critical", "high": "error",
                    "medium": "warning", "low": "info", "info": "info"}
    payload = {
        "routing_key": config.get("routing_key", ""),
        "event_action": "trigger",
        "payload": {
            "summary":   alert.title,
            "severity":  severity_map.get(alert.severity, "warning"),
            "source":    "dgraph.ai",
            "custom_details": {"message": alert.message, "findings": alert.row_count},
        },
    }
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post("https://events.pagerduty.com/v2/enqueue", json=payload)


async def _deliver_siem(alert: Alert, config: dict) -> None:
    """Forward alert to SIEM as a structured log entry (CEF or JSON)."""
    import json as _json
    entry = {
        "timestamp":  alert.fired_at.isoformat() if alert.fired_at else None,
        "source":     "dgraph.ai",
        "event_type": "SECURITY_ALERT",
        "severity":   alert.severity,
        "title":      alert.title,
        "message":    alert.message,
        "findings":   alert.row_count,
        "context":    alert.context,
    }
    siem_url = config.get("url", "")
    if siem_url:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(siem_url, json=entry,
                             headers={"Content-Type": "application/json"})


def _build_summary(rows: list[dict]) -> str:
    if not rows:
        return "no details available"
    first = rows[0]
    parts = []
    for k, v in list(first.items())[:3]:
        if v is not None:
            parts.append(f"{k}={v!r}")
    summary = ", ".join(parts)
    if len(rows) > 1:
        summary += f" (+{len(rows)-1} more)"
    return summary


def _render_template(template: str, context: dict) -> str:
    try:
        return jinja.from_string(template).render(**context)
    except Exception:
        return template
