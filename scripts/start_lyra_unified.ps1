param(
  [ValidateSet("dev", "packaged")]
  [string]$Mode = "dev",
  [int]$HealthTimeoutSeconds = 120,
  [switch]$LeaveRunning,
  [switch]$SkipSidecarBuild,
  [switch]$UseInstalledDataRootContract,
  [string]$LocalAppDataRoot
)

$ErrorActionPreference = "Stop"

function Write-Step {
  param([string]$Message)
  Write-Host "[lyra-unified] $Message"
}

function Invoke-LyraJson {
  param(
    [string]$Method,
    [string]$Uri
  )

  return Invoke-RestMethod -Method $Method -Uri $Uri -TimeoutSec 2
}

function Test-HealthReady {
  param([string]$BaseUrl)
  try {
    $health = Invoke-LyraJson -Method "Get" -Uri "$BaseUrl/api/health"
    return ($health.status -eq "ok") -and ($health.service -eq "lyra-oracle")
  } catch {
    return $false
  }
}

function Wait-HealthReady {
  param(
    [string]$BaseUrl,
    [int]$TimeoutSeconds,
    [System.Diagnostics.Process]$HostProcess = $null
  )

  $maxAttempts = [Math]::Max(1, [int]($TimeoutSeconds * 2))
  for ($attempt = 0; $attempt -lt $maxAttempts; $attempt++) {
    Start-Sleep -Milliseconds 500
    if ($HostProcess -and $HostProcess.HasExited) {
      throw "host process exited before backend became healthy (exit code: $($HostProcess.ExitCode))"
    }
    if (Test-HealthReady -BaseUrl $BaseUrl) {
      return $true
    }
  }
  return $false
}

function Test-IsRawTauriBuildHost {
  param([string]$HostExe)

  $normalized = [System.IO.Path]::GetFullPath($HostExe)
  return $normalized -like "*\desktop\renderer-app\src-tauri\target\debug\*" -or `
    $normalized -like "*\desktop\renderer-app\src-tauri\target\release\*"
}

function Resolve-PackagedHostExe {
  param([string]$RepoRoot)

  $envOverride = $env:LYRA_PACKAGED_HOST_EXE
  if ($envOverride -and (Test-Path $envOverride)) {
    return (Resolve-Path $envOverride).Path
  }

  $candidates = @(
    (Join-Path $RepoRoot "desktop\renderer-app\src-tauri\target\release\Lyra Oracle.exe"),
    (Join-Path $RepoRoot "desktop\renderer-app\src-tauri\target\release\lyra_tauri.exe"),
    (Join-Path $RepoRoot "desktop\renderer-app\src-tauri\target\release\deps\lyra_tauri.exe"),
    (Join-Path $RepoRoot "desktop\renderer-app\src-tauri\target\debug\Lyra Oracle.exe"),
    (Join-Path $RepoRoot "desktop\renderer-app\src-tauri\target\debug\lyra_tauri.exe"),
    (Join-Path $RepoRoot "desktop\renderer-app\src-tauri\target\debug\deps\lyra_tauri.exe")
  )

  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
      return $candidate
    }
  }
  return $null
}

function Set-PackagedHostEnvironment {
  param(
    [string]$RepoRoot,
    [string]$HostExe,
    [switch]$UseInstalledDataRootContract,
    [string]$LocalAppDataRoot
  )

  $buildRoot = Join-Path $RepoRoot ".lyra-build"
  $logDir = Join-Path $buildRoot "logs\runtime"
  New-Item -ItemType Directory -Path $logDir -Force | Out-Null
  $bootLogPath = Join-Path $logDir "packaged-host-boot.log"

  $env:LYRA_BUILD_ROOT = $buildRoot
  $env:LYRA_BACKEND_MODE = "packaged"
  $env:LYRA_HOST_BOOT_LOG = $bootLogPath
  if ($LocalAppDataRoot) {
    New-Item -ItemType Directory -Path $LocalAppDataRoot -Force | Out-Null
    $env:LOCALAPPDATA = $LocalAppDataRoot
  }

  foreach ($key in @(
    "LYRA_DATA_ROOT",
    "LYRA_LOG_ROOT",
    "LYRA_TEMP_ROOT",
    "LYRA_STATE_ROOT",
    "LYRA_MODEL_CACHE_ROOT",
    "LYRA_BACKEND_LOG_PATH"
  )) {
    [Environment]::SetEnvironmentVariable($key, $null, "Process")
  }

  if (-not $UseInstalledDataRootContract) {
    $dataRoot = Join-Path $buildRoot "data\packaged-smoke"
    $tempRoot = Join-Path $buildRoot "tmp"
    $stateRoot = Join-Path $buildRoot "state"
    $modelCacheRoot = Join-Path $buildRoot "cache\hf"
    $backendLogPath = Join-Path $logDir "packaged-backend.log"
    New-Item -ItemType Directory -Path $dataRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $stateRoot -Force | Out-Null
    New-Item -ItemType Directory -Path $modelCacheRoot -Force | Out-Null
    $env:LYRA_DATA_ROOT = $dataRoot
    $env:LYRA_LOG_ROOT = $logDir
    $env:LYRA_TEMP_ROOT = $tempRoot
    $env:LYRA_STATE_ROOT = $stateRoot
    $env:LYRA_MODEL_CACHE_ROOT = $modelCacheRoot
    $env:LYRA_BACKEND_LOG_PATH = $backendLogPath
  }

  if (Test-IsRawTauriBuildHost -HostExe $HostExe) {
    $env:LYRA_PROJECT_ROOT = $RepoRoot
    $env:LYRA_RUNTIME_ROOT = Join-Path $RepoRoot "runtime"
    $hostDir = Split-Path -Parent $HostExe
    $backendExe = Join-Path $hostDir "bin\lyra_backend.exe"
    if (-not (Test-Path $backendExe)) {
      $backendExe = Join-Path $RepoRoot ".lyra-build\bin\lyra_backend.exe"
    }
    if (Test-Path $backendExe) {
      $env:LYRA_BACKEND_EXE = $backendExe
    }
  }

  return $bootLogPath
}

function Get-PackagedHostWorkingDirectory {
  param([string]$HostExe)

  if (Test-IsRawTauriBuildHost -HostExe $HostExe) {
    return $repoRoot
  }

  return (Split-Path -Parent $HostExe)
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

$baseUrl = "http://127.0.0.1:5000"
$desktopDir = Join-Path $repoRoot "desktop"
$rendererDir = Join-Path $repoRoot "desktop\renderer-app"
$hostProcess = $null
$bootLogPath = $null

if ($HealthTimeoutSeconds -lt 5) {
  throw "HealthTimeoutSeconds must be at least 5"
}

if ($SkipSidecarBuild -and $Mode -ne "packaged") {
  Write-Step "SkipSidecarBuild ignored in dev mode"
}

if ($Mode -eq "packaged" -and -not $SkipSidecarBuild) {
  Write-Step "building packaged runtime (sidecar + bundled acquisition tools)"
  powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "scripts\build_packaged_runtime.ps1")
}

if ($Mode -eq "dev") {
  $npmPath = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
  if (-not $npmPath) {
    throw "npm.cmd not found in PATH"
  }

  Write-Step "starting Tauri dev host (desktop -> npm run dev)"
  $hostProcess = Start-Process -FilePath $npmPath -ArgumentList @("run", "dev") -WorkingDirectory $desktopDir -PassThru
} else {
  $hostExe = Resolve-PackagedHostExe -RepoRoot $repoRoot
  if (-not $hostExe) {
    throw "packaged host binary not found. Build once via: cd desktop\renderer-app; npm run tauri:build -- --debug"
  }
  $bootLogPath = Set-PackagedHostEnvironment `
    -RepoRoot $repoRoot `
    -HostExe $hostExe `
    -UseInstalledDataRootContract:$UseInstalledDataRootContract `
    -LocalAppDataRoot $LocalAppDataRoot
  $hostWorkingDirectory = Get-PackagedHostWorkingDirectory -HostExe $hostExe
  Write-Step "starting packaged host: $hostExe"
  Write-Step "packaged host working directory: $hostWorkingDirectory"
  $hostProcess = Start-Process -FilePath $hostExe -WorkingDirectory $hostWorkingDirectory -PassThru
}

Write-Step "waiting for backend health readiness"
try {
  $ready = Wait-HealthReady -BaseUrl $baseUrl -TimeoutSeconds $HealthTimeoutSeconds -HostProcess $hostProcess
} catch {
  if ($Mode -eq "packaged" -and $bootLogPath -and (Test-Path $bootLogPath)) {
    throw "$($_.Exception.Message). host boot log: $bootLogPath"
  }
  throw
}

if (-not $ready) {
  if ($hostProcess -and -not $hostProcess.HasExited) {
    Stop-Process -Id $hostProcess.Id -Force
  }
  if ($Mode -eq "packaged" -and $bootLogPath -and (Test-Path $bootLogPath)) {
    throw "backend did not become healthy within ${HealthTimeoutSeconds}s. host boot log: $bootLogPath"
  }
  throw "backend did not become healthy within ${HealthTimeoutSeconds}s"
}

Write-Step "Lyra unified launch ready (frontend + backend active)"

if ($LeaveRunning) {
  Write-Step "leaving host process running (pid: $($hostProcess.Id))"
  exit 0
}

Write-Step "attaching to host process lifecycle"
Wait-Process -Id $hostProcess.Id
$hostProcess.Refresh()
if ($hostProcess.ExitCode -ne 0) {
  throw "host process exited with code $($hostProcess.ExitCode)"
}
