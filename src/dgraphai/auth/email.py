"""
Transactional email — dgraph.ai

Provider priority (checked at startup):
  1. Resend   — RESEND_API_KEY env var   (recommended, simplest)
  2. SendGrid — SENDGRID_API_KEY env var
  3. SMTP     — SMTP_HOST env var        (fallback, self-hosted)
  4. Console  — dev fallback (prints to log, never fails)

All functions return bool (True = delivered, False = failed).
HTML templates use dgraph.ai M3 design system colors.
"""
from __future__ import annotations

import logging
import os
from typing import Literal

log = logging.getLogger("dgraphai.email")

# ── Provider config ──────────────────────────────────────────────────────────
RESEND_API_KEY    = os.getenv("RESEND_API_KEY", "")
SENDGRID_API_KEY  = os.getenv("SENDGRID_API_KEY", "")
SMTP_HOST         = os.getenv("SMTP_HOST", "")
SMTP_PORT         = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER         = os.getenv("SMTP_USER", "")
SMTP_PASS         = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM         = os.getenv("SMTP_FROM", "dgraph.ai <noreply@dgraph.ai>")
APP_URL           = os.getenv("APP_URL", "https://app.dgraph.ai")
EMAIL_FROM        = os.getenv("EMAIL_FROM", SMTP_FROM)

def _provider() -> Literal["resend", "sendgrid", "smtp", "console"]:
    if RESEND_API_KEY:   return "resend"
    if SENDGRID_API_KEY: return "sendgrid"
    if SMTP_HOST:        return "smtp"
    return "console"


async def send_email(to: str, subject: str, html: str, text: str = "") -> bool:
    """Send a transactional email via the configured provider."""
    provider = _provider()

    try:
        if provider == "resend":
            return await _send_resend(to, subject, html, text)
        elif provider == "sendgrid":
            return await _send_sendgrid(to, subject, html, text)
        elif provider == "smtp":
            return await _send_smtp(to, subject, html, text)
        else:
            log.info("[DEV EMAIL] To: %s | Subject: %s\n%s", to, subject, text or html[:300])
            return True
    except Exception as e:
        log.error("send_email failed (provider=%s, to=%s): %s", provider, to, e)
        return False


# ── Provider implementations ─────────────────────────────────────────────────

async def _send_resend(to: str, subject: str, html: str, text: str) -> bool:
    import httpx
    payload = {
        "from":    EMAIL_FROM,
        "to":      [to],
        "subject": subject,
        "html":    html,
    }
    if text:
        payload["text"] = text

    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json=payload,
            timeout=10,
        )
        if r.status_code >= 400:
            log.error("Resend error %d: %s", r.status_code, r.text)
            return False
        return True


async def _send_sendgrid(to: str, subject: str, html: str, text: str) -> bool:
    import httpx
    payload = {
        "personalizations": [{"to": [{"email": to}]}],
        "from": {"email": EMAIL_FROM},
        "subject": subject,
        "content": [{"type": "text/html", "value": html}],
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {SENDGRID_API_KEY}", "Content-Type": "application/json"},
            json=payload,
            timeout=10,
        )
        return r.status_code < 400


async def _send_smtp(to: str, subject: str, html: str, text: str) -> bool:
    import aiosmtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = to
    if text:
        msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    await aiosmtplib.send(
        msg,
        hostname=SMTP_HOST,
        port=SMTP_PORT,
        username=SMTP_USER or None,
        password=SMTP_PASS or None,
        use_tls=SMTP_PORT == 465,
        start_tls=SMTP_PORT == 587,
    )
    return True


# ── HTML template base ────────────────────────────────────────────────────────

def _base(content: str, preheader: str = "") -> str:
    """Wrap content in the dgraph.ai branded email shell."""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>dgraph.ai</title>
</head>
<body style="margin:0;padding:0;background:#09080c;font-family:'Segoe UI',Inter,sans-serif;">
{"" if not preheader else f'<span style="display:none;max-height:0;overflow:hidden;">{preheader}</span>'}
<table width="100%" cellpadding="0" cellspacing="0" style="background:#09080c;padding:32px 0;">
  <tr><td align="center">
    <table width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;">

      <!-- Header -->
      <tr><td style="padding:0 0 24px 0;">
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td>
              <div style="display:inline-flex;align-items:center;gap:10px;">
                <div style="width:32px;height:32px;border-radius:8px;
                  background:linear-gradient(135deg,#7c5cfc 0%,#2dd4bf 100%);
                  display:inline-block;vertical-align:middle;"></div>
                <span style="color:#eaeaf8;font-size:16px;font-weight:700;
                  vertical-align:middle;margin-left:10px;">dgraph.ai</span>
              </div>
            </td>
          </tr>
        </table>
      </td></tr>

      <!-- Body card -->
      <tr><td style="background:#0f0f1a;border:1px solid rgba(255,255,255,0.10);
        border-radius:12px;padding:32px;">
        {content}
      </td></tr>

      <!-- Footer -->
      <tr><td style="padding:24px 0 0 0;text-align:center;">
        <p style="color:#55557a;font-size:12px;margin:0;">
          dgraph.ai · <a href="{APP_URL}/settings" style="color:#55557a;">Unsubscribe</a>
        </p>
      </td></tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""


def _btn(url: str, label: str) -> str:
    return f"""<a href="{url}" style="display:inline-block;padding:12px 24px;
      background:#7c5cfc;color:#ffffff;text-decoration:none;border-radius:20px;
      font-weight:600;font-size:14px;margin:16px 0;">{label}</a>"""


def _h1(text: str) -> str:
    return f'<h1 style="color:#eaeaf8;font-size:22px;font-weight:700;margin:0 0 16px 0;">{text}</h1>'


def _p(text: str) -> str:
    return f'<p style="color:#cac4cf;font-size:14px;line-height:1.6;margin:0 0 12px 0;">{text}</p>'


def _code(text: str) -> str:
    return f"""<div style="background:#141424;border:1px solid rgba(255,255,255,0.08);
      border-radius:8px;padding:12px 16px;margin:12px 0;">
      <code style="color:#947dff;font-family:monospace;font-size:13px;word-break:break-all;">{text}</code>
    </div>"""


# ── Transactional templates ───────────────────────────────────────────────────

async def send_verification_email(to: str, name: str, token: str) -> bool:
    url = f"{APP_URL}/verify-email?token={token}"
    html = _base(
        _h1("Verify your email") +
        _p(f"Hi {name or 'there'}, thanks for signing up for dgraph.ai.") +
        _p("Click the button below to verify your email address and activate your account.") +
        _btn(url, "Verify email") +
        _p(f'Or copy this link: <a href="{url}" style="color:#947dff;">{url}</a>') +
        _p("This link expires in 24 hours. If you didn't create an account, you can ignore this email."),
        preheader="Verify your dgraph.ai account"
    )
    return await send_email(to, "Verify your dgraph.ai email", html)


async def send_password_reset_email(to: str, name: str, token: str) -> bool:
    url = f"{APP_URL}/reset-password?token={token}"
    html = _base(
        _h1("Reset your password") +
        _p(f"Hi {name or 'there'},") +
        _p("We received a request to reset your password. Click below to set a new one.") +
        _btn(url, "Reset password") +
        _p("This link expires in 1 hour.") +
        _p("If you didn't request a password reset, you can safely ignore this email. Your password won't change."),
        preheader="Reset your dgraph.ai password"
    )
    return await send_email(to, "Reset your dgraph.ai password", html)


async def send_invite_email(to: str, inviter_name: str, team_name: str, token: str) -> bool:
    url = f"{APP_URL}/accept-invite?token={token}"
    html = _base(
        _h1(f"You're invited to {team_name}") +
        _p(f"{inviter_name} has invited you to join their dgraph.ai workspace.") +
        _p("dgraph.ai maps your entire filesystem into a security knowledge graph — finding exposed secrets, PII, CVEs, and access patterns in minutes.") +
        _btn(url, "Accept invitation") +
        _p("This invitation expires in 7 days."),
        preheader=f"{inviter_name} invited you to dgraph.ai"
    )
    return await send_email(to, f"You're invited to {team_name} on dgraph.ai", html)


async def send_agent_connected_email(to: str, name: str, agent_name: str, connector_name: str) -> bool:
    html = _base(
        _h1("Agent connected 🎉") +
        _p(f"Hi {name or 'there'},") +
        _p(f"Your scanner agent <strong style='color:#eaeaf8;'>{agent_name}</strong> just connected and is indexing <strong style='color:#eaeaf8;'>{connector_name}</strong>.") +
        _p("You'll see your first findings in the graph within a few minutes.") +
        _btn(f"{APP_URL}/", "View graph") +
        _p("We'll send you a summary once the initial scan completes."),
        preheader="Your dgraph.ai agent is live"
    )
    return await send_email(to, "Your agent is connected and scanning", html)


async def send_findings_summary_email(
    to: str, name: str,
    secrets: int, pii: int, cves: int, total_files: int
) -> bool:
    items = ""
    if secrets: items += f'<tr><td style="color:#f04545;padding:8px 0;font-weight:700;">⚠ {secrets}</td><td style="color:#cac4cf;padding:8px 12px;">Exposed secrets found</td></tr>'
    if pii:     items += f'<tr><td style="color:#f97316;padding:8px 0;font-weight:700;">⚠ {pii}</td><td style="color:#cac4cf;padding:8px 12px;">Files containing PII</td></tr>'
    if cves:    items += f'<tr><td style="color:#f0c030;padding:8px 0;font-weight:700;">⚠ {cves}</td><td style="color:#cac4cf;padding:8px 12px;">Critical CVEs detected</td></tr>'
    if not items:
        items = '<tr><td colspan="2" style="color:#34d399;padding:8px 0;">✓ No critical findings — looking good!</td></tr>'

    html = _base(
        _h1("Your scan is complete") +
        _p(f"Hi {name or 'there'}, here's what dgraph.ai found across {total_files:,} files:") +
        f'<table cellpadding="0" cellspacing="0" style="margin:16px 0;">{items}</table>' +
        _btn(f"{APP_URL}/security", "View security findings") +
        _p("Your graph is live. You can explore all findings, query relationships, and set up alerts."),
        preheader=f"Scan complete: {total_files:,} files indexed"
    )
    return await send_email(to, f"Scan complete: {total_files:,} files indexed", html)


async def send_alert_email(to: str, name: str, alert_title: str, severity: str, detail: str) -> bool:
    color = {"critical": "#f04545", "high": "#f97316", "medium": "#f0c030"}.get(severity.lower(), "#6b7280")
    html = _base(
        f'<div style="border-left:3px solid {color};padding-left:16px;margin-bottom:20px;">'
        f'<span style="color:{color};font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.07em;">{severity.upper()}</span>'
        f'<h2 style="color:#eaeaf8;font-size:18px;font-weight:700;margin:4px 0 0 0;">{alert_title}</h2>'
        f'</div>' +
        _p(detail) +
        _btn(f"{APP_URL}/security", "View in dgraph.ai"),
        preheader=f"{severity.upper()}: {alert_title}"
    )
    return await send_email(to, f"[{severity.upper()}] {alert_title}", html)
