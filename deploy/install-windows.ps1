# dgraph-agent Windows installer
# Usage:
#   Set-ExecutionPolicy Bypass -Scope Process -Force
#   .\install-windows.ps1 -ApiKey "dga_xxx" -CloudUrl "https://api.dgraph.ai"
#
# What this does:
#   1. Downloads dgraph-agent.exe to C:\Program Files\dgraph-agent\
#   2. Creates a Windows Service (runs as NETWORK SERVICE, auto-start)
#   3. Starts the service

param(
    [Parameter(Mandatory=$true)]
    [string]$ApiKey,

    [string]$CloudUrl = "https://api.dgraph.ai",
    [string]$InstallDir = "C:\Program Files\dgraph-agent",
    [string]$ServiceName = "dgraph-agent",
    [string]$Version = "latest"
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Write-OK($msg)   { Write-Host "    OK: $msg" -ForegroundColor Green }
function Write-Fail($msg) { Write-Host "    FAIL: $msg" -ForegroundColor Red; exit 1 }

Write-Host "dgraph-agent Windows Installer" -ForegroundColor White
Write-Host "================================" -ForegroundColor White

# ── Step 1: Create install directory ──────────────────────────────────────────
Write-Step "Creating install directory: $InstallDir"
if (-not (Test-Path $InstallDir)) {
    New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
}
Write-OK "Directory ready"

# ── Step 2: Download binary ───────────────────────────────────────────────────
Write-Step "Downloading dgraph-agent.exe"

$exePath = Join-Path $InstallDir "dgraph-agent.exe"
$downloadUrl = ""

if ($Version -eq "latest") {
    # Get latest release from GitHub
    try {
        $release = Invoke-RestMethod "https://api.github.com/repos/gaineyllc/dgraphai/releases/latest"
        $asset = $release.assets | Where-Object { $_.name -match "dgraph-agent.*windows.*amd64.*\.exe$" } | Select-Object -First 1
        if ($asset) {
            $downloadUrl = $asset.browser_download_url
        }
    } catch {
        Write-Host "    GitHub unreachable, checking for local binary..." -ForegroundColor Yellow
    }
}

if ($downloadUrl) {
    Write-Host "    Downloading from: $downloadUrl"
    Invoke-WebRequest -Uri $downloadUrl -OutFile $exePath -UseBasicParsing
    Write-OK "Downloaded: $exePath"
} elseif (Test-Path ".\dgraph-agent.exe") {
    # Use local binary if present (dev mode)
    Copy-Item ".\dgraph-agent.exe" $exePath -Force
    Write-OK "Copied local binary: $exePath"
} else {
    Write-Fail "No binary available. Download dgraph-agent.exe from https://github.com/gaineyllc/dgraphai/releases"
}

# ── Step 3: Write config ──────────────────────────────────────────────────────
Write-Step "Writing configuration"

$configPath = Join-Path $InstallDir "config.yaml"
$queuePath  = Join-Path $Env:ProgramData "dgraph-agent\queue.db"

# Ensure data directory exists
$dataDir = Split-Path $queuePath -Parent
if (-not (Test-Path $dataDir)) {
    New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
}

@"
api_endpoint: $CloudUrl
api_key: $ApiKey
log_level: info
health_bind: "127.0.0.1:9090"
metrics_bind: "127.0.0.1:9091"
sync_interval: 5m
queue_path: "$($queuePath.Replace('\','/'))"
enable_secret_scan: true
enable_pii_scan: true
enable_binary_scan: false
"@ | Set-Content $configPath -Encoding UTF8

Write-OK "Config written: $configPath"

# ── Step 4: Test connectivity ─────────────────────────────────────────────────
Write-Step "Testing platform connectivity"
$env:DGRAPH_AGENT_API_KEY    = $ApiKey
$env:DGRAPH_AGENT_API_ENDPOINT = $CloudUrl

$testResult = & "$exePath" test 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-OK "Connection successful"
    Write-Host "    $testResult" -ForegroundColor Gray
} else {
    Write-Fail "Connection test failed:`n$testResult`n`nCheck your API key and cloud URL."
}

# ── Step 5: Install Windows Service ──────────────────────────────────────────
Write-Step "Installing Windows Service: $ServiceName"

# Remove existing service if present
$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    Stop-Service  -Name $ServiceName -Force -ErrorAction SilentlyContinue
    sc.exe delete $ServiceName | Out-Null
    Start-Sleep 2
}

# Create service using sc.exe
$binPath = "`"$exePath`" --config `"$configPath`""
sc.exe create $ServiceName `
    binPath= $binPath `
    start= auto `
    DisplayName= "dgraph.ai Scanner Agent" | Out-Null

if ($LASTEXITCODE -ne 0) {
    Write-Fail "Failed to create Windows service. Try running as Administrator."
}

# Set description
sc.exe description $ServiceName "dgraph.ai on-premises scanner agent. Indexes file metadata and syncs to the knowledge graph." | Out-Null

# Set environment variables for the service
# (Services don't inherit user env vars)
$regPath = "HKLM:\SYSTEM\CurrentControlSet\Services\$ServiceName"
$envVars = "DGRAPH_AGENT_API_KEY=$ApiKey", "DGRAPH_AGENT_API_ENDPOINT=$CloudUrl"
New-ItemProperty -Path $regPath -Name "Environment" -Value $envVars -PropertyType MultiString -Force | Out-Null

Write-OK "Service installed"

# ── Step 6: Start service ─────────────────────────────────────────────────────
Write-Step "Starting service"
Start-Service -Name $ServiceName
Start-Sleep 3

$svc = Get-Service -Name $ServiceName
if ($svc.Status -eq "Running") {
    Write-OK "Service is running!"
} else {
    Write-Host "    Service status: $($svc.Status)" -ForegroundColor Yellow
    Write-Host "    Check logs: Get-EventLog -LogName Application -Source '$ServiceName' -Newest 10"
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "Installation complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Useful commands:" -ForegroundColor White
Write-Host "  Check status:  Get-Service $ServiceName"
Write-Host "  View logs:     Get-EventLog -LogName Application -Source '$ServiceName' -Newest 20"
Write-Host "  Stop agent:    Stop-Service $ServiceName"
Write-Host "  Uninstall:     Stop-Service $ServiceName; sc.exe delete $ServiceName"
Write-Host ""
Write-Host "The agent will now scan and report to: $CloudUrl" -ForegroundColor Cyan
