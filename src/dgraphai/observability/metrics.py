"""
Observability — Prometheus metrics + OpenTelemetry tracing.

Metrics exposed at GET /metrics (Prometheus scrape endpoint).
Tracing exported via OTLP to Jaeger/Tempo/Datadog.

Metrics tracked:
  dgraphai_http_requests_total{method, endpoint, status}
  dgraphai_http_request_duration_seconds{method, endpoint}
  dgraphai_graph_query_duration_seconds{tenant_id, query_type}
  dgraphai_graph_nodes_total{tenant_id, node_type}
  dgraphai_scanner_agent_last_seen{tenant_id, agent_id}
  dgraphai_indexing_jobs_total{tenant_id, status}
  dgraphai_enrichment_jobs_total{tenant_id, status, enricher}
  dgraphai_active_users{tenant_id}
  dgraphai_celery_queue_depth{queue}
"""
from __future__ import annotations
import os
import time
from typing import Callable
from fastapi import FastAPI, Request, Response

OTLP_ENDPOINT = os.getenv("OTLP_ENDPOINT", "")  # e.g. http://jaeger:4317


def setup_metrics(app: FastAPI) -> None:
    """Attach Prometheus + OTLP tracing to a FastAPI app."""
    _setup_prometheus(app)
    if OTLP_ENDPOINT:
        _setup_tracing(app)


def _setup_prometheus(app: FastAPI) -> None:
    try:
        from prometheus_fastapi_instrumentator import Instrumentator
        from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

        # Instrument all HTTP routes
        Instrumentator(
            should_group_status_codes=False,
            should_ignore_untemplated=True,
            should_respect_env_var=True,
            env_var_name="ENABLE_METRICS",
            excluded_handlers=["/metrics", "/api/health"],
        ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

        # Custom business metrics
        import src.dgraphai.observability.custom_metrics as cm  # noqa — registers metrics

    except ImportError:
        # Prometheus not installed — serve empty metrics endpoint
        @app.get("/metrics", include_in_schema=False)
        async def metrics_fallback():
            return Response(content="# Prometheus not installed\n",
                            media_type="text/plain")


def _setup_tracing(app: FastAPI) -> None:
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({"service.name": "dgraphai-api"})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=OTLP_ENDPOINT)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    except ImportError:
        pass  # OpenTelemetry not installed
