param(
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  $python = "python"
}

if ($DryRun) {
  Write-Host "[dry-run] Would start API: $python lyra_api.py"
  Write-Host "[dry-run] Would run: npm run dev (in desktop/)"
  exit 0
}

Start-Process powershell -ArgumentList "-NoExit", "-Command", "& '$python' lyra_api.py"
Start-Sleep -Seconds 2
Set-Location (Join-Path $repoRoot "desktop")
npm run dev
