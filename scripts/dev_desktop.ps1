$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  $python = "python"
}

Start-Process powershell -ArgumentList "-NoExit", "-Command", "& '$python' lyra_api.py"
Start-Sleep -Seconds 2
Set-Location (Join-Path $repoRoot "desktop")
npm run dev
