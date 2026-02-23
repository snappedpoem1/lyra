# Launch-Oracle.ps1 — Start Lyra Oracle (Docker services + Flask API)
# Usage: .\Launch-Oracle.ps1
# Flags: -SkipDocker  (skip Docker startup, useful if services already running)
#        -Port 5000   (Flask port, default 5000)

param(
    [switch]$SkipDocker,
    [int]$Port = 5000
)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $root

function Write-Step { param($msg) Write-Host "  >> $msg" -ForegroundColor Cyan }
function Write-Ok   { param($msg) Write-Host "  OK $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "  !! $msg" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "  XX $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  LYRA ORACLE" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# --- STEP 1: Docker Desktop ---
if (-not $SkipDocker) {
    Write-Step "Checking Docker daemon..."

    $dockerOk = $false
    try {
        $null = docker ps 2>&1
        if ($LASTEXITCODE -eq 0) { $dockerOk = $true }
    } catch {}

    if (-not $dockerOk) {
        Write-Warn "Docker daemon not running. Starting Docker Desktop..."
        $dockerExe = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
        if (Test-Path $dockerExe) {
            Start-Process $dockerExe
            Write-Step "Waiting for Docker daemon (up to 60s)..."
            $waited = 0
            while ($waited -lt 60) {
                Start-Sleep -Seconds 3
                $waited += 3
                try {
                    $null = docker ps 2>&1
                    if ($LASTEXITCODE -eq 0) { $dockerOk = $true; break }
                } catch {}
                Write-Host "    ... $waited`s" -ForegroundColor DarkGray
            }
        } else {
            Write-Warn "Docker Desktop not found at expected path. Skipping Docker startup."
        }
    }

    if ($dockerOk) {
        Write-Ok "Docker daemon is live"

        # --- STEP 2: Docker Compose services ---
        Write-Step "Starting Docker services (docker-compose up -d)..."
        docker-compose up -d 2>&1 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }

        # Wait for Prowlarr
        Write-Step "Waiting for Prowlarr (port 9696)..."
        $prowlarrOk = $false
        for ($i = 0; $i -lt 20; $i++) {
            Start-Sleep -Seconds 3
            try {
                $r = Invoke-RestMethod -Uri "http://localhost:9696/health" -TimeoutSec 2 -ErrorAction Stop
                $prowlarrOk = $true; break
            } catch {}
        }
        if ($prowlarrOk) { Write-Ok "Prowlarr live at :9696" }
        else             { Write-Warn "Prowlarr not responding (acquisition T1 may be limited)" }

        # Wait for rdtclient
        Write-Step "Waiting for rdtclient (port 6500)..."
        $rdtOk = $false
        for ($i = 0; $i -lt 15; $i++) {
            Start-Sleep -Seconds 3
            try {
                $null = Invoke-WebRequest -Uri "http://localhost:6500" -TimeoutSec 2 -ErrorAction Stop
                $rdtOk = $true; break
            } catch {
                if ($_.Exception.Response.StatusCode.value__ -lt 500) { $rdtOk = $true; break }
            }
        }
        if ($rdtOk) { Write-Ok "rdtclient live at :6500" }
        else        { Write-Warn "rdtclient not responding (Real-Debrid may be limited)" }

        # Slskd status (optional, longer startup)
        try {
            $null = Invoke-RestMethod -Uri "http://localhost:5030/api/v0/application" -TimeoutSec 3 -ErrorAction Stop
            Write-Ok "slskd live at :5030"
        } catch {
            Write-Warn "slskd not yet responding (will retry in background)"
        }

    } else {
        Write-Warn "Docker daemon did not start. Continuing without Docker services."
        Write-Warn "Acquisition T1 (Real-Debrid) and T2 (Slskd) will be unavailable."
    }
} else {
    Write-Warn "Skipping Docker startup (-SkipDocker flag set)"
}

Write-Host ""

# --- STEP 3: Activate venv ---
if (Test-Path ".venv\Scripts\Activate.ps1") {
    . .venv\Scripts\Activate.ps1
    Write-Ok "Virtual environment activated"
}

# --- STEP 4: Oracle status check ---
Write-Step "Running oracle status..."
python -m oracle status 2>&1 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }

Write-Host ""

# --- STEP 5: Start Flask API ---
Write-Step "Starting Lyra Oracle API on port $Port..."
$job = Start-Job -ScriptBlock {
    param($r, $p)
    Set-Location $r
    if (Test-Path ".venv\Scripts\Activate.ps1") { . .venv\Scripts\Activate.ps1 }
    $env:FLASK_PORT = $p
    python lyra_api.py
} -ArgumentList $root, $Port

Write-Host "    Flask job $($job.Id) starting..." -ForegroundColor DarkGray

# Wait for Flask
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-RestMethod -Uri "http://localhost:$Port/health" -TimeoutSec 2 -ErrorAction Stop
        if ($r.ok) { $ready = $true; break }
    } catch {}
}

if ($ready) {
    Write-Host ""
    Write-Ok "Lyra Oracle is LIVE"
    Write-Host ""
    Write-Host "    API:      http://localhost:$Port" -ForegroundColor White
    Write-Host "    App:      http://localhost:$Port/app" -ForegroundColor White
    Write-Host "    Playlust: http://localhost:$Port/playlust" -ForegroundColor White
    Write-Host "    Health:   http://localhost:$Port/health" -ForegroundColor White
    Write-Host ""
    Start-Process "http://localhost:$Port/app"
} else {
    Write-Fail "Flask API did not respond within 30s"
    Write-Host ""
    Receive-Job $job
}

Write-Host "Press Ctrl+C to stop. Flask job: $($job.Id)" -ForegroundColor DarkGray
Write-Host ""

try {
    while ($true) {
        Receive-Job $job -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
} finally {
    Stop-Job $job -ErrorAction SilentlyContinue
    Remove-Job $job -Force -ErrorAction SilentlyContinue
    Pop-Location
}
