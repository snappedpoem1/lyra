# Launch-Lyra.ps1 — Start Lyra Oracle and open the SPA
# Usage: .\Launch-Lyra.ps1

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Push-Location $root

# Activate venv
if (Test-Path ".venv\Scripts\Activate.ps1") {
    . .venv\Scripts\Activate.ps1
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  LYRA ORACLE — Starting Server" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Start the API server in background
$job = Start-Job -ScriptBlock {
    Set-Location $using:root
    if (Test-Path ".venv\Scripts\Activate.ps1") {
        . .venv\Scripts\Activate.ps1
    }
    python lyra_api.py
}

Write-Host "Server starting (job $($job.Id))..." -ForegroundColor Yellow

# Wait for server to be ready
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $resp = Invoke-RestMethod -Uri "http://localhost:5000/health" -TimeoutSec 2 -ErrorAction Stop
        if ($resp.ok) {
            $ready = $true
            break
        }
    } catch {
        # Not ready yet
    }
}

if ($ready) {
    Write-Host ""
    Write-Host "  Server is LIVE at http://localhost:5000" -ForegroundColor Green
    Write-Host "  SPA:      http://localhost:5000/app" -ForegroundColor Green
    Write-Host "  Playlust: http://localhost:5000/playlust" -ForegroundColor Green
    Write-Host ""

    # Open browser
    Start-Process "http://localhost:5000/app"
} else {
    Write-Host "Server did not respond in 30s. Check logs." -ForegroundColor Red
    Receive-Job $job
}

Write-Host "Press Ctrl+C to stop. Job ID: $($job.Id)" -ForegroundColor DarkGray
Write-Host ""

# Stream output until user stops
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
