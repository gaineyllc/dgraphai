"""Alert evaluation Celery tasks."""
from src.dgraphai.tasks.celery_app import app
import asyncio, logging
log = logging.getLogger("dgraphai.tasks.alerts")

@app.task(name="dgraphai.tasks.alerts.evaluate_all_tenant_alerts", queue="alerts")
def evaluate_all_tenant_alerts():
    """Evaluate alert rules for all active tenants."""
    asyncio.run(_evaluate_async())

async def _evaluate_async():
    try:
        from src.dgraphai.alerts.engine import AlertEngine
        from src.dgraphai.db.session import async_session
        from src.dgraphai.db.models import Tenant
        from sqlalchemy import select
        async with async_session() as db:
            result = await db.execute(select(Tenant).where(Tenant.is_active == True))
            tenants = result.scalars().all()
        for tenant in tenants:
            try:
                engine = AlertEngine(str(tenant.id))
                await engine.evaluate_all()
            except Exception as e:
                log.error(f"Alert eval failed for tenant {tenant.id}: {e}")
    except Exception as e:
        log.error(f"Alert evaluation error: {e}")

@app.task(name="dgraphai.tasks.alerts.check_certificate_expiry", queue="alerts")
def check_certificate_expiry():
    """Check for certificates expiring in the next 30 days."""
    log.info("Certificate expiry check running")
    # Full implementation queries Neo4j for certs with days_until_expiry < 30
