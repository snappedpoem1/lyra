param(
  [ValidateSet("dev", "packaged")]
  [string]$Mode = "dev",
  [int]$HealthTimeoutSeconds = 120,
  [switch]$LeaveRunning,
  [switch]$SkipSidecarBuild
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

function Resolve-PackagedHostExe {
  param([string]$RepoRoot)

  $candidates = @(
    (Join-Path $RepoRoot "desktop\renderer-app\src-tauri\target\release\lyra_tauri.exe"),
    (Join-Path $RepoRoot "desktop\renderer-app\src-tauri\target\debug\lyra_tauri.exe")
  )

  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
      return $candidate
    }
  }
  return $null
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

$baseUrl = "http://127.0.0.1:5000"
$desktopDir = Join-Path $repoRoot "desktop"
$rendererDir = Join-Path $repoRoot "desktop\renderer-app"
$hostProcess = $null

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
  Write-Step "starting packaged host: $hostExe"
  $hostProcess = Start-Process -FilePath $hostExe -WorkingDirectory $rendererDir -PassThru
}

Write-Step "waiting for backend health readiness"
if (-not (Wait-HealthReady -BaseUrl $baseUrl -TimeoutSeconds $HealthTimeoutSeconds -HostProcess $hostProcess)) {
  if ($hostProcess -and -not $hostProcess.HasExited) {
    Stop-Process -Id $hostProcess.Id -Force
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
