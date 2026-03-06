param(
  [int]$ObserveSeconds = 25
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sidecarExe = Join-Path $repoRoot "desktop\renderer-app\src-tauri\bin\lyra_backend.exe"
$outLog = Join-Path $repoRoot ".tmp\sidecar_out.log"
$errLog = Join-Path $repoRoot ".tmp\sidecar_err.log"

New-Item -ItemType Directory -Path (Join-Path $repoRoot ".tmp") -Force | Out-Null
Remove-Item $outLog, $errLog -ErrorAction SilentlyContinue

$env:LYRA_SKIP_VENV_REEXEC = "1"
$env:LYRA_PROJECT_ROOT = $repoRoot
$env:LYRA_BOOTSTRAP = "0"

$proc = Start-Process -FilePath $sidecarExe -WorkingDirectory $repoRoot -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
Start-Sleep -Seconds $ObserveSeconds

Write-Host "has_exited=$($proc.HasExited) exit_code=$($proc.ExitCode)"
try {
  $health = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:5000/api/health" -TimeoutSec 2
  Write-Host "health_status=$($health.status)"
} catch {
  Write-Host "health_status=unavailable"
}

Write-Host "--- stdout ---"
if (Test-Path $outLog) {
  Get-Content $outLog
}

Write-Host "--- stderr ---"
if (Test-Path $errLog) {
  Get-Content $errLog
}

if (-not $proc.HasExited) {
  Stop-Process -Id $proc.Id -Force
}
