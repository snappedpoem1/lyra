param(
  [string]$BaseUrl = "http://127.0.0.1:5000",
  [int]$StartupTimeoutSeconds = 120,
  [int]$SoakSeconds = 60,
  [int]$RecoverySeekMs = 15000,
  [int]$PositionToleranceMs = 2500,
  [switch]$SkipSidecarBuild,
  [switch]$LeaveBackendRunning
)

$ErrorActionPreference = "Stop"

function Write-Step {
  param([string]$Message)
  Write-Host "[parity-hardening] $Message"
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

function Invoke-LyraJson {
  param(
    [string]$Method,
    [string]$Path,
    [object]$Body = $null
  )

  $uri = "$BaseUrl$Path"
  if ($null -ne $Body) {
    return Invoke-RestMethod -Method $Method -Uri $uri -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 8)
  }
  return Invoke-RestMethod -Method $Method -Uri $uri
}

function Test-HealthReady {
  try {
    $health = Invoke-LyraJson -Method Get -Path "/api/health"
    return ($health.status -eq "ok") -and ($health.service -eq "lyra-oracle")
  } catch {
    return $false
  }
}

function Wait-HealthReady {
  param([int]$TimeoutSeconds)

  $maxAttempts = [Math]::Max(1, [int]($TimeoutSeconds * 2))
  for ($i = 0; $i -lt $maxAttempts; $i++) {
    Start-Sleep -Milliseconds 500
    if (Test-HealthReady) {
      return $true
    }
  }
  return $false
}

function Get-BackendListenerProcessId {
  $listener = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($null -eq $listener) {
    return $null
  }
  return [int]$listener.OwningProcess
}

function Start-Sidecar {
  param([string]$ExePath, [string]$RepoRoot)

  $env:LYRA_PROJECT_ROOT = $RepoRoot
  $env:LYRA_SKIP_VENV_REEXEC = "1"
  $env:LYRA_BOOTSTRAP = "0"
  return Start-Process -FilePath $ExePath -WorkingDirectory $RepoRoot -PassThru
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

$sidecarExe = Join-Path $repoRoot "desktop\renderer-app\src-tauri\bin\lyra_backend.exe"
$startedProcess = $null
$startedRootPid = $null
$startedByThisScript = $false

if (-not $SkipSidecarBuild) {
  Write-Step "building sidecar (launch check skipped; this script validates runtime)"
  powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "scripts\build_backend_sidecar.ps1") -SkipLaunchCheck
}

if (-not (Test-Path $sidecarExe)) {
  throw "sidecar executable not found: $sidecarExe"
}

if (-not (Test-HealthReady)) {
  Write-Step "starting sidecar backend"
  $startedProcess = Start-Sidecar -ExePath $sidecarExe -RepoRoot $repoRoot
  $startedRootPid = $startedProcess.Id
  $startedByThisScript = $true
  if (-not (Wait-HealthReady -TimeoutSeconds $StartupTimeoutSeconds)) {
    if ($startedRootPid) {
      Stop-ProcessTree -RootPid $startedRootPid
    }
    throw "backend did not become healthy within ${StartupTimeoutSeconds}s"
  }
} else {
  Write-Step "backend already healthy; continuing"
}

try {
  Write-Step "running Step 1/2 smoke"
  powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "scripts\smoke_step1_step2.ps1") -SkipSidecarBuild -StartupTimeoutSeconds $StartupTimeoutSeconds -SoakSeconds ([Math]::Min($SoakSeconds, 30))

  Write-Step "preparing restart recovery assertion state"
  $tracks = Invoke-LyraJson -Method Get -Path "/api/library/tracks?limit=3"
  if (($tracks.count -as [int]) -lt 1) {
    throw "no tracks available for restart recovery assertion"
  }
  $firstTrackId = [string]$tracks.tracks[0].track_id
  if ([string]::IsNullOrWhiteSpace($firstTrackId)) {
    throw "library response missing track_id"
  }
  $null = Invoke-LyraJson -Method Post -Path "/api/player/queue/add" -Body @{ track_id = $firstTrackId }
  $null = Invoke-LyraJson -Method Post -Path "/api/player/play" -Body @{ queue_index = 0 }
  Start-Sleep -Milliseconds 700
  $null = Invoke-LyraJson -Method Post -Path "/api/player/seek" -Body @{ position_ms = $RecoverySeekMs }
  $null = Invoke-LyraJson -Method Post -Path "/api/player/pause" -Body @{}

  $stateBefore = Invoke-LyraJson -Method Get -Path "/api/player/state"
  $queueBefore = Invoke-LyraJson -Method Get -Path "/api/player/queue"
  $beforeTrackId = [string]$stateBefore.current_track.track_id
  $beforeQueueCount = [int]$queueBefore.count
  if ([string]::IsNullOrWhiteSpace($beforeTrackId)) {
    throw "restart precondition failed: no current track id"
  }
  if ($beforeQueueCount -lt 1) {
    throw "restart precondition failed: queue empty"
  }

  Write-Step "forcing backend restart"
  $listenerPid = Get-BackendListenerProcessId
  if ($null -eq $listenerPid) {
    throw "cannot determine backend process listening on port 5000"
  }
  Stop-Process -Id $listenerPid -Force
  Start-Sleep -Milliseconds 700

  $startedProcess = Start-Sidecar -ExePath $sidecarExe -RepoRoot $repoRoot
  $startedRootPid = $startedProcess.Id
  $startedByThisScript = $true
  if (-not (Wait-HealthReady -TimeoutSeconds $StartupTimeoutSeconds)) {
    if ($startedRootPid) {
      Stop-ProcessTree -RootPid $startedRootPid
    }
    throw "backend did not recover after forced restart"
  }

  Write-Step "asserting queue/state recovery after restart"
  $stateAfter = Invoke-LyraJson -Method Get -Path "/api/player/state"
  $queueAfter = Invoke-LyraJson -Method Get -Path "/api/player/queue"

  $afterTrackId = [string]$stateAfter.current_track.track_id
  $afterQueueCount = [int]$queueAfter.count
  $afterPositionMs = [int]$stateAfter.position_ms
  $deltaMs = [Math]::Abs($afterPositionMs - $RecoverySeekMs)

  if ($afterTrackId -ne $beforeTrackId) {
    throw "restart recovery failed: current track mismatch ($beforeTrackId -> $afterTrackId)"
  }
  if ($afterQueueCount -lt $beforeQueueCount) {
    throw "restart recovery failed: queue shrank unexpectedly ($beforeQueueCount -> $afterQueueCount)"
  }
  if ($stateAfter.status -ne "paused") {
    throw "restart recovery failed: expected paused state, got '$($stateAfter.status)'"
  }
  if ($deltaMs -gt $PositionToleranceMs) {
    throw "restart recovery failed: position drift $deltaMs ms exceeds tolerance $PositionToleranceMs ms"
  }

  Write-Step "validating SSE contract post-restart"
  $prevNativeErrorMode = $PSNativeCommandUseErrorActionPreference
  $PSNativeCommandUseErrorActionPreference = $false
  try {
    $sseText = & curl.exe -sN --max-time 8 "$BaseUrl/ws/player" 2>$null
    if (($LASTEXITCODE -ne 0) -and ($LASTEXITCODE -ne 28)) {
      throw "curl failed while reading post-restart SSE stream (exit code: $LASTEXITCODE)"
    }
  } finally {
    $PSNativeCommandUseErrorActionPreference = $prevNativeErrorMode
  }
  $sseJoined = ($sseText | Out-String)
  if ([string]::IsNullOrWhiteSpace($sseJoined) -or $sseJoined -notmatch '"type"\s*:\s*"player_state_changed"') {
    throw "post-restart SSE stream did not include player_state_changed"
  }

  Write-Step "running short stability soak ($SoakSeconds seconds)"
  $deadline = (Get-Date).AddSeconds($SoakSeconds)
  while ((Get-Date) -lt $deadline) {
    $state = Invoke-LyraJson -Method Get -Path "/api/player/state"
    if (-not $state.status) {
      throw "player state missing status during soak"
    }
    Start-Sleep -Milliseconds 1000
  }

  Write-Step "parity-hardening acceptance passed"
} finally {
  if (-not $LeaveBackendRunning -and $startedByThisScript -and $startedRootPid) {
    Write-Step "stopping backend process started by script"
    Stop-ProcessTree -RootPid $startedRootPid
  }
}
