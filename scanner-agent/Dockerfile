# dgraphai Scanner Agent — minimal attack surface
FROM python:3.14-slim AS runtime

RUN groupadd -r scanner && useradd -r -g scanner scanner

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-editable

COPY src/ ./src/

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://127.0.0.1:8080/health').raise_for_status()"

USER scanner
EXPOSE 8080

# Health UI binds to loopback only — not accessible from outside the container
# K8s health probes use exec (not network) or port-forward for UI
CMD ["uv", "run", "uvicorn", "src.main:app", \
     "--host", "127.0.0.1", "--port", "8080", "--log-level", "warning"]
