# dgraph.ai local stack setup + E2E test runner
# Run from the dgraphai project root:  .\scripts\local_setup.ps1
#
# What this does:
#   1. Checks Docker is running
#   2. Starts docker compose (core services only first, then all)
#   3. Waits for each service to be healthy
#   4. Runs Alembic migrations
#   5. Provisions Keycloak realm
#   6. Starts the API server (if not using compose api service)
#   7. Runs the E2E test suite
#   8. Prints a summary

param(
    [switch]$SkipBuild,      # skip docker compose build
    [switch]$SkipTests,      # start stack only, don't run tests
    [switch]$CoreOnly,       # only start postgres/neo4j/redis (no api/worker/beat)
    [switch]$Reset,          # tear down and rebuild from scratch
    [string]$BaseUrl = "http://localhost:8000"
)

$ErrorActionPreference = "Stop"
$startTime = Get-Date

function Write-Step($msg) {
    Write-Host "`n>>> $msg" -ForegroundColor Cyan
}

function Write-OK($msg) {
    Write-Host "    OK: $msg" -ForegroundColor Green
}

function Write-Fail($msg) {
    Write-Host "    FAIL: $msg" -ForegroundColor Red
}

function Wait-Port($host, $port, $name, $maxSeconds=120) {
    Write-Host "    Waiting for $name on ${host}:${port}..." -NoNewline
    $deadline = (Get-Date).AddSeconds($maxSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $tcp = New-Object System.Net.Sockets.TcpClient
            $tcp.Connect($host, $port)
            $tcp.Close()
            Write-Host " ready" -ForegroundColor Green
            return $true
        } catch {
            Write-Host "." -NoNewline
            Start-Sleep 2
        }
    }
    Write-Host " TIMEOUT" -ForegroundColor Red
    return $false
}

function Wait-Http($url, $name, $maxSeconds=120) {
    Write-Host "    Waiting for $name at $url..." -NoNewline
    $deadline = (Get-Date).AddSeconds($maxSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3 -ErrorAction SilentlyContinue
            if ($r.StatusCode -lt 500) {
                Write-Host " ready ($($r.StatusCode))" -ForegroundColor Green
                return $true
            }
        } catch {}
        Write-Host "." -NoNewline
        Start-Sleep 3
    }
    Write-Host " TIMEOUT" -ForegroundColor Red
    return $false
}

# ── Step 1: Check Docker ──────────────────────────────────────────────────────
Write-Step "Checking Docker"
try {
    $dockerInfo = docker info 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Docker daemon not running" }
    Write-OK "Docker is running"
} catch {
    Write-Fail "Docker Desktop is not running. Please start it and re-run this script."
    exit 1
}

# ── Step 2: Reset if requested ────────────────────────────────────────────────
if ($Reset) {
    Write-Step "Resetting (docker compose down -v)"
    docker compose down -v --remove-orphans
    Write-OK "Stack torn down"
}

# ── Step 3: Start core services ───────────────────────────────────────────────
Write-Step "Starting core services (postgres, neo4j, redis)"
docker compose up -d postgres neo4j redis
if ($LASTEXITCODE -ne 0) { Write-Fail "Failed to start core services"; exit 1 }

# Wait for each core service
Wait-Port "localhost" 5432 "Postgres" 60  | Out-Null
Wait-Port "localhost" 6379 "Redis" 30     | Out-Null
Wait-Port "localhost" 7687 "Neo4j Bolt" 120 | Out-Null
Wait-Http "http://localhost:7474" "Neo4j Browser" 120 | Out-Null

Write-OK "Core services ready"

# ── Step 4: Run Alembic migrations ────────────────────────────────────────────
Write-Step "Running Alembic migrations"
$env:DATABASE_URL = "postgresql+asyncpg://dgraphai:dgraphai-local@localhost:5432/dgraphai"
$env:JWT_SECRET   = "dev-jwt-secret-change-in-production"
$env:DGRAPHAI_ENABLE_DOCS = "true"

uv run alembic upgrade head 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Alembic migration failed"
    exit 1
}
Write-OK "Migrations applied"

if ($CoreOnly) {
    Write-Host "`nCore stack is up. Skipping API + tests (--CoreOnly flag set)." -ForegroundColor Yellow
    Write-Host "  Postgres: localhost:5432"
    Write-Host "  Neo4j:    localhost:7687 (browser: http://localhost:7474)"
    Write-Host "  Redis:    localhost:6379"
    exit 0
}

# ── Step 5: Start Keycloak (optional, needed for SSO tests) ───────────────────
Write-Step "Starting Keycloak (SSO)"
docker compose up -d keycloak
Write-Host "    (Keycloak takes ~60s to start — continuing in parallel)"

# ── Step 6: Start API server ──────────────────────────────────────────────────
Write-Step "Starting API server"

# Check if already running (from compose or manual)
try {
    $health = Invoke-WebRequest -Uri "$BaseUrl/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
    if ($health.StatusCode -eq 200) {
        Write-OK "API server already running at $BaseUrl"
    }
} catch {
    # Start via uv directly (faster than docker build for dev)
    Write-Host "    Starting API via uv run..."
    $env:NEO4J_URI      = "bolt://localhost:7687"
    $env:NEO4J_USER     = "neo4j"
    $env:NEO4J_PASSWORD = "fsgraph-local"
    $env:REDIS_URL      = "redis://localhost:6379/0"
    $env:CELERY_BROKER_URL = "redis://localhost:6379/0"
    $env:APP_URL        = $BaseUrl

    Start-Process -FilePath "uv" `
        -ArgumentList "run uvicorn src.main:app --host 127.0.0.1 --port 8000" `
        -WorkingDirectory (Get-Location) `
        -WindowStyle Minimized

    Wait-Http "$BaseUrl/health" "API server" 60 | Out-Null
}

# ── Step 7: Provision Keycloak realm ─────────────────────────────────────────
Write-Step "Provisioning Keycloak realm (dgraphai)"
try {
    $kcReady = Wait-Http "http://localhost:8080/health/ready" "Keycloak" 90
    if ($kcReady) {
        uv run python -c "
from src.dgraphai.auth.keycloak_setup import provision
provision('http://localhost:8080', 'admin', '$BaseUrl')
print('Keycloak realm provisioned')
" 2>&1
        Write-OK "Keycloak realm ready"
    } else {
        Write-Host "    Keycloak not ready yet — SSO tests will be skipped" -ForegroundColor Yellow
    }
} catch {
    Write-Host "    Keycloak provisioning skipped: $_" -ForegroundColor Yellow
}

if ($SkipTests) {
    Write-Host "`nStack is up. Skipping tests (--SkipTests flag set)." -ForegroundColor Yellow
    Write-Host "  API:       $BaseUrl"
    Write-Host "  Docs:      $BaseUrl/docs"
    Write-Host "  Neo4j:     http://localhost:7474"
    Write-Host "  Keycloak:  http://localhost:8080  (admin/admin)"
    exit 0
}

# ── Step 8: Run unit tests ────────────────────────────────────────────────────
Write-Step "Running unit tests (280 tests, no Docker required)"
uv run pytest tests/unit -q --tb=short 2>&1
$unitExit = $LASTEXITCODE
if ($unitExit -eq 0) { Write-OK "All unit tests passed" }
else { Write-Fail "Unit tests failed (exit $unitExit)" }

# ── Step 9: Run E2E tests ─────────────────────────────────────────────────────
Write-Step "Running E2E customer flow tests"
$env:E2E_BASE_URL = $BaseUrl
uv run pytest tests/e2e/test_full_customer_flow.py -v --tb=short 2>&1
$e2eExit = $LASTEXITCODE

# ── Step 10: Summary ──────────────────────────────────────────────────────────
$elapsed = [int]((Get-Date) - $startTime).TotalSeconds

Write-Host "`n$('='*60)" -ForegroundColor Cyan
Write-Host "  dgraph.ai local stack setup complete" -ForegroundColor Cyan
Write-Host "$('='*60)" -ForegroundColor Cyan
Write-Host "  Elapsed:    ${elapsed}s"
Write-Host "  API:        $BaseUrl"
Write-Host "  Docs:       $BaseUrl/docs"
Write-Host "  GraphQL:    $BaseUrl/graphql"
Write-Host "  Neo4j:      http://localhost:7474  (neo4j/fsgraph-local)"
Write-Host "  Keycloak:   http://localhost:8080  (admin/admin)"
Write-Host ""
if ($unitExit -eq 0) {
    Write-Host "  Unit tests:  PASSED" -ForegroundColor Green
} else {
    Write-Host "  Unit tests:  FAILED" -ForegroundColor Red
}
if ($e2eExit -eq 0) {
    Write-Host "  E2E tests:   PASSED" -ForegroundColor Green
} else {
    Write-Host "  E2E tests:   FAILED (see output above)" -ForegroundColor Red
}
Write-Host ""

if ($e2eExit -ne 0) { exit 1 }
