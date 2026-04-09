#!/usr/bin/env bash
# dgraph.ai Test Runner
# Usage:
#   ./tests/run_tests.sh           # all tests
#   ./tests/run_tests.sh unit      # unit tests only (no I/O)
#   ./tests/run_tests.sh e2e       # full API tests
#   ./tests/run_tests.sh p0        # all P0 critical tests
#   ./tests/run_tests.sh p1        # all P1 high-priority
#   ./tests/run_tests.sh p2        # all P2 nice-to-have
#   ./tests/run_tests.sh fast      # unit + e2e excluding slow
#   ./tests/run_tests.sh ci        # unit + e2e P0+P1 (for CI pipeline)
#
# Prerequisites:
#   uv run pytest (dependencies in pyproject.toml [dev])
#   For integration tests: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD env vars

set -e
cd "$(dirname "$0")/.."

MODE="${1:-all}"

case "$MODE" in
  unit)
    echo "🧪 Running unit tests..."
    uv run pytest tests/unit -v --tb=short -m unit
    ;;
  e2e)
    echo "🌐 Running E2E API tests..."
    uv run pytest tests/e2e -v --tb=short -m e2e
    ;;
  integration)
    echo "🔗 Running integration tests (requires Neo4j + Postgres)..."
    uv run pytest tests/integration -v --tb=short -m integration
    ;;
  p0)
    echo "🔴 Running P0 critical path tests..."
    uv run pytest tests/ -v --tb=short -m p0
    ;;
  p1)
    echo "🟡 Running P1 high-priority tests..."
    uv run pytest tests/ -v --tb=short -m p1
    ;;
  p2)
    echo "🟢 Running P2 nice-to-have tests..."
    uv run pytest tests/ -v --tb=short -m p2
    ;;
  fast)
    echo "⚡ Running fast tests (unit + e2e, no slow)..."
    uv run pytest tests/unit tests/e2e -v --tb=short -m "not slow and not integration"
    ;;
  ci)
    echo "🚀 Running CI test suite (unit + e2e P0 + P1)..."
    uv run pytest tests/unit tests/e2e -v --tb=short \
      -m "not slow and not integration" \
      --junitxml=test-results.xml \
      --cov=src/dgraphai \
      --cov-report=term-missing \
      --cov-report=xml
    ;;
  all)
    echo "🔬 Running all tests..."
    uv run pytest tests/ -v --tb=short -m "not integration"
    ;;
  *)
    echo "Unknown mode: $MODE"
    echo "Usage: $0 [unit|e2e|integration|p0|p1|p2|fast|ci|all]"
    exit 1
    ;;
esac
