# Import all task modules so Celery autodiscovers task names
# noqa: F401 — imported for side effects (task registration)
from src.dgraphai.tasks import celery_app      # noqa: F401
from src.dgraphai.tasks import indexer          # noqa: F401
from src.dgraphai.tasks import enrichment_tasks # noqa: F401
from src.dgraphai.tasks import alerts           # noqa: F401
from src.dgraphai.tasks import gdpr             # noqa: F401
from src.dgraphai.tasks import cve_sync         # noqa: F401
from src.dgraphai.tasks import reenrichment     # noqa: F401
from src.dgraphai.tasks import maintenance      # noqa: F401
from src.dgraphai.tasks import onboarding       # noqa: F401
