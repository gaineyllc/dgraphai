"""
Transactional email — verification, password reset, alerts.
Uses aiosmtplib for async SMTP. Falls back to console logging in dev.
Configure via env vars: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
                        SMTP_FROM, APP_URL
"""
from __future__ import annotations
import logging
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

log = logging.getLogger("dgraphai.email")

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "noreply@dgraph.ai")
APP_URL   = os.getenv("APP_URL", "https://app.dgraph.ai")


async def send_email(to: str, subject: str, html: str, text: str = "") -> bool:
    """Send an email. Returns True on success, False on failure."""
    if not SMTP_HOST:
        log.info(f"[DEV EMAIL] To: {to}\nSubject: {subject}\n{text or html[:200]}")
        return True

    try:
        import aiosmtplib
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = SMTP_FROM
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
    except Exception as e:
        log.error(f"Failed to send email to {to}: {e}")
        return False


async def send_verification_email(to: str, name: str, token: str) -> bool:
    url = f"{APP_URL}/verify-email?token={token}"
    html = f"""
    <div style="font-family:sans-serif;max-width:500px;margin:0 auto">
      <h2 style="color:#4f8ef7">Verify your email</h2>
      <p>Hi {name or 'there'},</p>
      <p>Click the button below to verify your email address for dgraph.ai.</p>
      <a href="{url}" style="display:inline-block;padding:12px 24px;background:#4f8ef7;
         color:#fff;text-decoration:none;border-radius:8px;font-weight:bold">
        Verify Email
      </a>
      <p style="color:#888;font-size:12px">This link expires in 48 hours.<br>
      If you didn't sign up, you can safely ignore this email.</p>
    </div>
    """
    return await send_email(to, "Verify your dgraph.ai email", html,
                            f"Verify your email: {url}")


async def send_password_reset_email(to: str, name: str, token: str) -> bool:
    url = f"{APP_URL}/reset-password?token={token}"
    html = f"""
    <div style="font-family:sans-serif;max-width:500px;margin:0 auto">
      <h2 style="color:#4f8ef7">Reset your password</h2>
      <p>Hi {name or 'there'},</p>
      <p>Someone requested a password reset for your dgraph.ai account.</p>
      <a href="{url}" style="display:inline-block;padding:12px 24px;background:#4f8ef7;
         color:#fff;text-decoration:none;border-radius:8px;font-weight:bold">
        Reset Password
      </a>
      <p style="color:#888;font-size:12px">This link expires in 1 hour.<br>
      If you didn't request this, you can safely ignore this email.</p>
    </div>
    """
    return await send_email(to, "Reset your dgraph.ai password", html,
                            f"Reset your password: {url}")


async def send_usage_alert_email(to: str, name: str, pct: int, plan: str) -> bool:
    html = f"""
    <div style="font-family:sans-serif;max-width:500px;margin:0 auto">
      <h2 style="color:#f59e0b">Usage alert: {pct}% of limit reached</h2>
      <p>Hi {name or 'there'},</p>
      <p>Your dgraph.ai {plan} plan has reached <strong>{pct}%</strong> of its
      included node allowance.</p>
      <a href="{APP_URL}/usage" style="display:inline-block;padding:12px 24px;
         background:#f59e0b;color:#fff;text-decoration:none;border-radius:8px;font-weight:bold">
        View Usage
      </a>
    </div>
    """
    return await send_email(to, f"dgraph.ai: {pct}% of usage limit reached", html)


async def send_invitation_email(to: str, inviter_name: str,
                                 tenant_name: str, token: str, role: str) -> bool:
    url = f"{APP_URL}/accept-invite?token={token}"
    html = f"""
    <div style="font-family:sans-serif;max-width:500px;margin:0 auto">
      <h2 style="color:#4f8ef7">You're invited to {tenant_name}</h2>
      <p>{inviter_name} has invited you to join <strong>{tenant_name}</strong>
      on dgraph.ai as <strong>{role}</strong>.</p>
      <a href="{url}" style="display:inline-block;padding:12px 24px;background:#4f8ef7;
         color:#fff;text-decoration:none;border-radius:8px;font-weight:bold">
        Accept Invitation
      </a>
      <p style="color:#888;font-size:12px">This invitation expires in 7 days.</p>
    </div>
    """
    return await send_email(to, f"Invitation to join {tenant_name} on dgraph.ai", html,
                            f"Accept your invitation: {url}")
