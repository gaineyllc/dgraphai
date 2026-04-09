"""
Celery task queue — replaces asyncio background tasks for production reliability.

All long-running operations (indexing, AI enrichment, GDPR erasure,
compliance reports, alert evaluation) run through Celery workers.
This gives us:
  - Durability: tasks survive worker restarts
  - Retry logic: automatic retries with exponential backoff
  - Visibility: task status queryable via Celery/Flower
  - Concurrency: multiple workers, controlled parallelism
  - Rate limiting: don't hammer Neo4j or Ollama

Configure via env:
  CELERY_BROKER_URL  — redis://localhost:6379/0
  CELERY_RESULT_URL  — redis://localhost:6379/1
"""
from __future__ import annotations
import os
from celery import Celery
from kombu import Exchange, Queue

BROKER_URL = os.getenv("CELERY_BROKER_URL",  "redis://localhost:6379/0")
RESULT_URL = os.getenv("CELERY_RESULT_URL",  "redis://localhost:6379/1")

app = Celery("dgraphai", broker=BROKER_URL, backend=RESULT_URL)

app.conf.update(
    # Serialization
    task_serializer   = "json",
    result_serializer = "json",
    accept_content    = ["json"],

    # Reliability
    task_acks_late            = True,     # ack after completion, not before
    task_reject_on_worker_lost= True,     # re-queue on worker crash
    worker_prefetch_multiplier= 1,        # one task at a time per worker (fair scheduling)
    task_track_started        = True,

    # Timeouts
    task_soft_time_limit = 300,    # 5 min soft limit → raises SoftTimeLimitExceeded
    task_time_limit      = 360,    # 6 min hard limit → kills worker

    # Result expiry
    result_expires = 86400,        # 24 hours

    # Retry defaults
    task_default_retry_delay = 60,
    task_max_retries         = 3,

    # Routing — separate queues for priority/isolation
    task_default_queue    = "default",
    task_queues           = (
        Queue("default",    Exchange("default"),    routing_key="default"),
        Queue("indexing",   Exchange("indexing"),   routing_key="indexing"),    # heavy I/O
        Queue("enrichment", Exchange("enrichment"), routing_key="enrichment"),  # GPU/LLM
        Queue("alerts",     Exchange("alerts"),     routing_key="alerts"),      # time-sensitive
        Queue("gdpr",       Exchange("gdpr"),       routing_key="gdpr"),        # compliance
        Queue("exports",    Exchange("exports"),    routing_key="exports"),     # bulk operations
    ),
    task_routes = {
        "dgraphai.tasks.indexer.*":     {"queue": "indexing"},
        "dgraphai.tasks.enrichment.*":  {"queue": "enrichment"},
        "dgraphai.tasks.alerts.*":      {"queue": "alerts"},
        "dgraphai.tasks.gdpr.*":        {"queue": "gdpr"},
        "dgraphai.tasks.exports.*":     {"queue": "exports"},
    },

    # Beat schedule — periodic tasks
    beat_schedule = {
        "evaluate-alerts-every-5-min": {
            "task": "dgraphai.tasks.alerts.evaluate_all_tenant_alerts",
            "schedule": 300,   # every 5 minutes
        },
        "check-cert-expiry-daily": {
            "task": "dgraphai.tasks.alerts.check_certificate_expiry",
            "schedule": 86400,
        },
        "snapshot-usage-daily": {
            "task": "dgraphai.tasks.billing.snapshot_tenant_usage",
            "schedule": 86400,
        },
        "cleanup-expired-tokens-daily": {
            "task": "dgraphai.tasks.maintenance.cleanup_expired_tokens",
            "schedule": 86400,
        },
        "sync-nvd-cves-daily": {
            "task": "dgraphai.tasks.cve_sync.sync_nvd_cves",  # matches @app.task name=
            "schedule": 86400,
            "kwargs": {"days_back": 2},
        },
        "check-cisa-kev-daily": {
            "task": "dgraphai.tasks.cve_sync.check_cisa_kev",
            "schedule": 86400,
        },
        "run-onboarding-check-daily": {
            "task": "dgraphai.tasks.maintenance.cleanup_expired_tokens",
            "schedule": 86400,
        },
        "reenrich-stale-nodes-hourly": {
            "task": "dgraphai.tasks.reenrichment.queue_stale_nodes",
            "schedule": 3600,
        },
    },
)
