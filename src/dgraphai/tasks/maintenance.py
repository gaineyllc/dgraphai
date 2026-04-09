"""Periodic maintenance tasks — token cleanup, session expiry."""
from src.dgraphai.tasks.celery_app import app
import logging

log = logging.getLogger("dgraphai.maintenance")


@app.task(name="dgraphai.tasks.maintenance.cleanup_expired_tokens")
def cleanup_expired_tokens():
    """Delete expired password reset and email verification tokens."""
    import asyncio
    asyncio.run(_cleanup_async())


async def _cleanup_async():
    from datetime import datetime, timezone
    from src.dgraphai.db.session import async_session
    from src.dgraphai.db.models import (
        PasswordResetToken, EmailVerificationToken, UserSession
    )
    from sqlalchemy import delete

    now = datetime.now(timezone.utc)
    async with async_session() as db:
        r1 = await db.execute(delete(PasswordResetToken).where(
            PasswordResetToken.expires_at < now))
        r2 = await db.execute(delete(EmailVerificationToken).where(
            EmailVerificationToken.expires_at < now))
        r3 = await db.execute(delete(UserSession).where(
            UserSession.expires_at < now))
        log.info(f"Cleaned up tokens: reset={r1.rowcount} "
                 f"verify={r2.rowcount} sessions={r3.rowcount}")
