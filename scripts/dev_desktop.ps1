param(
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$unifiedScript = Join-Path $repoRoot "scripts\start_lyra_unified.ps1"
if (-not (Test-Path $unifiedScript)) {
  throw "Unified launcher not found: $unifiedScript"
}

if ($DryRun) {
  Write-Host "[dry-run] Deprecated wrapper. Would run unified launcher:"
  Write-Host "[dry-run] powershell -ExecutionPolicy Bypass -File scripts\\start_lyra_unified.ps1 -Mode dev"
  exit 0
}

Write-Warning "scripts/dev_desktop.ps1 is deprecated. Delegating to scripts/start_lyra_unified.ps1."
powershell -ExecutionPolicy Bypass -File $unifiedScript -Mode dev
exit $LASTEXITCODE
