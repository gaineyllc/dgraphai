"""Enrichment Celery tasks — stub, wired to the enrichment worker queue."""
from src.dgraphai.tasks.celery_app import app
import logging
log = logging.getLogger("dgraphai.tasks.enrichment")

@app.task(name="dgraphai.tasks.enrichment.enrich_node", queue="enrichment", bind=True, max_retries=2)
def enrich_node(self, tenant_id: str, node_id: str, file_path: str, category: str):
    """Run AI enrichment on a single file node."""
    import asyncio
    asyncio.run(_enrich_async(tenant_id, node_id, file_path, category))

async def _enrich_async(tenant_id, node_id, file_path, category):
    """Dispatch to appropriate enricher based on file category."""
    log.info(f"Enriching {category} node {node_id} for tenant {tenant_id}")
    # Full implementation calls LLM/vision/code enrichers via the Python pipeline
    # Stubbed here — the enrichment pipeline in src/enrichers/ handles the logic
