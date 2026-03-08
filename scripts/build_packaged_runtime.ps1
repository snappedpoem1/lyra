param(
  [switch]$SkipLaunchCheck,
  [switch]$SkipToolSmokeCheck,
  [switch]$SkipRuntimeRebuild
)

$ErrorActionPreference = "Stop"

function Write-Step {
  param([string]$Message)
  Write-Host "[packaged-runtime] $Message"
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$stagedRuntimeBin = Join-Path $repoRoot ".lyra-build\bin\runtime\bin"
$stagedSidecarExe = Join-Path $repoRoot ".lyra-build\bin\lyra_backend.exe"
$stagedRuntimeExecutables = @(
  (Join-Path $stagedRuntimeBin "spotdl.exe"),
  (Join-Path $stagedRuntimeBin "rip.exe")
)

function Test-StagedPackagedRuntime {
  param(
    [string]$SidecarPath,
    [string[]]$RuntimeExecutables
  )

  if (-not (Test-Path $SidecarPath)) {
    return $false
  }

  foreach ($executable in $RuntimeExecutables) {
    if (-not (Test-Path $executable)) {
      return $false
    }
  }

  return $true
}

if ($SkipRuntimeRebuild) {
  if (-not (Test-StagedPackagedRuntime -SidecarPath $stagedSidecarExe -RuntimeExecutables $stagedRuntimeExecutables)) {
    throw "SkipRuntimeRebuild requested, but staged packaged runtime artifacts are missing from .lyra-build\\bin."
  }

  Write-Step "reusing existing packaged runtime artifacts"
  Write-Step "  sidecar: $stagedSidecarExe"
  Write-Step "  runtime: $stagedRuntimeBin"
  return
}

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
