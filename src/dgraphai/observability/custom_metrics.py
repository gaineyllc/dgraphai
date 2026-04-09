"""Custom Prometheus metrics for dgraph.ai business logic."""
try:
    from prometheus_client import Counter, Histogram, Gauge

    # Graph queries
    GRAPH_QUERY_DURATION = Histogram(
        "dgraphai_graph_query_duration_seconds",
        "Time spent executing graph queries",
        ["query_type"],
        buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
    )

    # Indexing
    INDEXING_JOBS = Counter(
        "dgraphai_indexing_jobs_total",
        "Total indexing jobs by status",
        ["status"],  # started | completed | failed
    )

    NODES_INDEXED = Counter(
        "dgraphai_nodes_indexed_total",
        "Total nodes indexed",
        ["file_category"],
    )

    # Enrichment
    ENRICHMENT_JOBS = Counter(
        "dgraphai_enrichment_jobs_total",
        "Total AI enrichment jobs",
        ["enricher", "status"],  # enricher: llm|vision|code|binary|face
    )

    # Auth events
    AUTH_EVENTS = Counter(
        "dgraphai_auth_events_total",
        "Auth events",
        ["event"],  # login | login_failed | signup | mfa_enrolled | password_reset
    )

    # API keys usage
    API_KEY_REQUESTS = Counter(
        "dgraphai_api_key_requests_total",
        "Requests authenticated via API key",
        ["tenant_id"],
    )

    # Scanner agents
    SCANNER_LAST_SEEN = Gauge(
        "dgraphai_scanner_agent_last_seen_seconds",
        "Unix timestamp of last scanner agent heartbeat",
        ["agent_id"],
    )

    # Celery queue depths (updated by beat task)
    CELERY_QUEUE_DEPTH = Gauge(
        "dgraphai_celery_queue_depth",
        "Number of tasks waiting in each Celery queue",
        ["queue"],
    )

    # Active sessions
    ACTIVE_SESSIONS = Gauge(
        "dgraphai_active_sessions_total",
        "Current active user sessions",
    )

    # GDPR erasure
    GDPR_ERASURE_JOBS = Counter(
        "dgraphai_gdpr_erasure_jobs_total",
        "GDPR erasure jobs",
        ["status"],
    )

except ImportError:
    # prometheus_client not available — create no-op stubs
    class _Noop:
        def labels(self, **_): return self
        def observe(self, *_): pass
        def inc(self, *_): pass
        def set(self, *_): pass

    GRAPH_QUERY_DURATION = INDEXING_JOBS = NODES_INDEXED = _Noop()
    ENRICHMENT_JOBS = AUTH_EVENTS = API_KEY_REQUESTS = _Noop()
    SCANNER_LAST_SEEN = CELERY_QUEUE_DEPTH = ACTIVE_SESSIONS = _Noop()
    GDPR_ERASURE_JOBS = _Noop()
