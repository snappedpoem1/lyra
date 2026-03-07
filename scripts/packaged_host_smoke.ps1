param(
  [int]$HealthTimeoutSeconds = 120,
  [switch]$RebuildHost,
  [switch]$KeepHostRunning,
  [switch]$AllowExistingBackend,
  [string]$HostExe
)

$ErrorActionPreference = "Stop"

function Write-Step {
  param([string]$Message)
  Write-Host "[packaged-host-smoke] $Message"
}

function Stop-ProcessTree {
  param([int]$RootPid)

  $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $RootPid" -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty ProcessId
  foreach ($childPid in $children) {
    Stop-ProcessTree -RootPid $childPid
  }
  Stop-Process -Id $RootPid -Force -ErrorAction SilentlyContinue
}

function Get-BackendListenerProcessId {
  $listener = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($null -eq $listener) {
    return $null
  }
  return [int]$listener.OwningProcess
}

function Wait-PortReleased {
  param([int]$TimeoutSeconds = 15)

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    if ($null -eq (Get-BackendListenerProcessId)) {
      return $true
    }
    Start-Sleep -Milliseconds 250
  }
  return $false
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

if ($HostExe) {
  $resolvedHostExe = (Resolve-Path $HostExe).Path
  $env:LYRA_PACKAGED_HOST_EXE = $resolvedHostExe
}

if ($RebuildHost) {
  Write-Step "building packaged runtime helpers"
  powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "scripts\build_packaged_runtime.ps1") -SkipLaunchCheck -SkipToolSmokeCheck

  Write-Step "building debug packaged host shell"
  Push-Location (Join-Path $repoRoot "desktop\renderer-app")
  try {
    npm run tauri:build -- --debug
    if ($LASTEXITCODE -ne 0) {
      throw "tauri debug build failed with exit code $LASTEXITCODE"
    }
  } finally {
    Pop-Location
  }
}

if (-not $AllowExistingBackend) {
  $existingListenerPid = Get-BackendListenerProcessId
  if ($existingListenerPid) {
    Write-Step "stopping pre-existing backend listener ($existingListenerPid) for deterministic packaged smoke"
    Stop-ProcessTree -RootPid $existingListenerPid
    if (-not (Wait-PortReleased -TimeoutSeconds 15)) {
      throw "existing backend listener did not release port 5000"
    }
  }
}

$launcherArgs = @(
  "-ExecutionPolicy", "Bypass",
  "-File", (Join-Path $repoRoot "scripts\start_lyra_unified.ps1"),
  "-Mode", "packaged",
  "-SkipSidecarBuild",
  "-HealthTimeoutSeconds", "$HealthTimeoutSeconds",
  "-LeaveRunning"
)

Write-Step "running debug packaged-host launch smoke"
$launcherOutput = powershell @launcherArgs 2>&1
$launcherOutput | ForEach-Object { Write-Host $_ }
if ($LASTEXITCODE -ne 0) {
  throw "packaged host smoke failed with exit code $LASTEXITCODE"
}

if (-not $KeepHostRunning) {
  $pidMatch = $launcherOutput | Select-String -Pattern 'pid:\s*(\d+)'
  if ($pidMatch.Count -gt 0) {
    $rootPid = [int]$pidMatch[-1].Matches[0].Groups[1].Value
    Write-Step "stopping packaged host process tree ($rootPid)"
    Stop-ProcessTree -RootPid $rootPid
  }
}

Write-Step "packaged host smoke passed"
