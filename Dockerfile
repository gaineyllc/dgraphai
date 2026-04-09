# fsgraph API — multi-stage Docker build
# Stage 1: build frontend
FROM node:22-alpine AS frontend-build
WORKDIR /app/web
COPY web/package*.json ./
RUN npm ci --omit=dev
COPY web/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.14-slim AS runtime

# Security: non-root user
RUN groupadd -r fsgraph && useradd -r -g fsgraph fsgraph

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Python deps
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-editable

# App source
COPY src/ ./src/

# Frontend build artifacts
COPY --from=frontend-build /app/web/dist ./web/dist

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:7474/api/health').raise_for_status()"

USER fsgraph
EXPOSE 7474

CMD ["uv", "run", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "7474", \
     "--workers", "4", "--loop", "uvloop", "--log-level", "info"]
