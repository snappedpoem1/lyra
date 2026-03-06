param(
  [switch]$SkipLaunchCheck,
  [switch]$SkipToolSmokeCheck
)

$ErrorActionPreference = "Stop"

function Write-Step {
  param([string]$Message)
  Write-Host "[packaged-runtime] $Message"
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Step "building bundled acquisition runtime tools"
$toolArgs = @(
  "-ExecutionPolicy", "Bypass",
  "-File", (Join-Path $repoRoot "scripts\build_runtime_tools.ps1")
)
if ($SkipToolSmokeCheck) {
  $toolArgs += "-SkipSmokeCheck"
}
powershell @toolArgs

Write-Step "building backend sidecar"
$sidecarArgs = @(
  "-ExecutionPolicy", "Bypass",
  "-File", (Join-Path $repoRoot "scripts\build_backend_sidecar.ps1")
)
if ($SkipLaunchCheck) {
  $sidecarArgs += "-SkipLaunchCheck"
}
powershell @sidecarArgs
