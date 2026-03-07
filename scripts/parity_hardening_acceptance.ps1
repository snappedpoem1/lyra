param(
  [string]$BaseUrl = "http://127.0.0.1:5000",
  [int]$StartupTimeoutSeconds = 120,
  [int]$SoakSeconds = 60,
  [int]$CheckpointIntervalSeconds = 30,
  [int]$ActionIntervalSeconds = 20,
  [int]$RecoverySeekMs = 15000,
  [int]$PositionToleranceMs = 2500,
  [string]$LogDirectory = "",
  [switch]$SkipSidecarBuild,
  [switch]$SkipInstallerProof,
  [switch]$SkipSoakMutations,
  [switch]$LeaveBackendRunning,
  [string]$DataRoot = "",
  [switch]$UseLegacyDataRoot
)

$ErrorActionPreference = "Stop"
$script:ParityLogPath = $null
$script:ParitySnapshotPath = $null

function Write-Step {
  param([string]$Message)

  $line = "{0} [parity-hardening] {1}" -f (Get-Date -Format o), $Message
  Write-Host $line
  if ($script:ParityLogPath) {
    Add-Content -Path $script:ParityLogPath -Value $line
  }
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

function Write-JsonSnapshot {
  param(
    [string]$Label,
    [hashtable]$Extra = @{}
  )

  if (-not $script:ParitySnapshotPath) {
    return
  }

  $payload = [ordered]@{
    ts = (Get-Date -Format o)
    label = $Label
  }
  foreach ($key in $Extra.Keys) {
    $payload[$key] = $Extra[$key]
  }

  try {
    $payload["health"] = Invoke-LyraJson -Method Get -Path "/api/health"
  } catch {
    $payload["health_error"] = $_.Exception.Message
  }

  try {
    $payload["state"] = Invoke-LyraJson -Method Get -Path "/api/player/state"
  } catch {
    $payload["state_error"] = $_.Exception.Message
  }

  try {
    $payload["queue"] = Invoke-LyraJson -Method Get -Path "/api/player/queue"
  } catch {
    $payload["queue_error"] = $_.Exception.Message
  }

  Add-Content -Path $script:ParitySnapshotPath -Value ($payload | ConvertTo-Json -Depth 10 -Compress)
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
  param(
    [int]$TimeoutSeconds,
    [System.Diagnostics.Process]$HostProcess = $null
  )

  $maxAttempts = [Math]::Max(1, [int]($TimeoutSeconds * 2))
  for ($i = 0; $i -lt $maxAttempts; $i++) {
    Start-Sleep -Milliseconds 500
    if ($HostProcess -and $HostProcess.HasExited) {
      throw "backend process exited before health readiness (exit code: $($HostProcess.ExitCode))"
    }
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
  if ($DataRoot) {
    $env:LYRA_DATA_ROOT = $DataRoot
  }
  if ($UseLegacyDataRoot) {
    $env:LYRA_USE_LEGACY_DATA_ROOT = "1"
  }
  return Start-Process -FilePath $ExePath -WorkingDirectory $RepoRoot -PassThru
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

function Ensure-PlaybackActive {
  $state = Invoke-LyraJson -Method Get -Path "/api/player/state"
  $currentTrackId = [string]$state.current_track.track_id
  if ([string]::IsNullOrWhiteSpace($currentTrackId)) {
    throw "player state missing current track during soak"
  }
  if ($state.status -eq "playing") {
    return $state
  }

  $queueIndex = [int]$state.current_queue_index
  $null = Invoke-LyraJson -Method Post -Path "/api/player/play" -Body @{ queue_index = $queueIndex }
  Start-Sleep -Milliseconds 700
  return Invoke-LyraJson -Method Get -Path "/api/player/state"
}

function Wait-PlayerStatus {
  param(
    [string[]]$Statuses,
    [int]$TimeoutMilliseconds = 8000
  )

  $deadline = (Get-Date).AddMilliseconds($TimeoutMilliseconds)
  while ((Get-Date) -lt $deadline) {
    $state = Invoke-LyraJson -Method Get -Path "/api/player/state"
    if ($Statuses -contains [string]$state.status) {
      return $state
    }
    Start-Sleep -Milliseconds 250
  }

  $state = Invoke-LyraJson -Method Get -Path "/api/player/state"
  throw "player did not reach expected status [$($Statuses -join ', ')] (last status: $([string]$state.status))"
}

function Pause-IfPlaying {
  $state = Invoke-LyraJson -Method Get -Path "/api/player/state"
  if ($state.status -ne "playing") {
    return $state
  }

  $null = Invoke-LyraJson -Method Post -Path "/api/player/pause" -Body @{}
  return Wait-PlayerStatus -Statuses @("paused")
}

function Invoke-SoakMutation {
  param([int]$MutationIndex)

  $state = Ensure-PlaybackActive
  $mutationKind = $MutationIndex % 4
  switch ($mutationKind) {
    0 {
      Write-Step "soak action ${MutationIndex}: pause and resume"
      $null = Invoke-LyraJson -Method Post -Path "/api/player/pause" -Body @{}
      Start-Sleep -Milliseconds 800
      $null = Invoke-LyraJson -Method Post -Path "/api/player/play" -Body @{ queue_index = [int]$state.current_queue_index }
      Write-JsonSnapshot -Label "soak-action-pause-resume" -Extra @{ mutation_index = $MutationIndex }
      break
    }
    1 {
      $durationMs = [int]$state.duration_ms
      $positionMs = [int]$state.position_ms
      $seekTargetMs = if ($durationMs -gt 10000) {
        [Math]::Min($positionMs + 5000, $durationMs - 1500)
      } else {
        $positionMs + 1000
      }
      Write-Step "soak action ${MutationIndex}: seek to $seekTargetMs ms"
      $null = Invoke-LyraJson -Method Post -Path "/api/player/seek" -Body @{ position_ms = [int]$seekTargetMs }
      Write-JsonSnapshot -Label "soak-action-seek" -Extra @{
        mutation_index = $MutationIndex
        seek_target_ms = [int]$seekTargetMs
      }
      break
    }
    2 {
      Write-Step "soak action ${MutationIndex}: next then previous"
      $null = Invoke-LyraJson -Method Post -Path "/api/player/next" -Body @{}
      Start-Sleep -Milliseconds 900
      $null = Invoke-LyraJson -Method Post -Path "/api/player/previous" -Body @{}
      Write-JsonSnapshot -Label "soak-action-next-previous" -Extra @{ mutation_index = $MutationIndex }
      break
    }
    default {
      $nextShuffle = -not [bool]$state.shuffle
      $nextRepeat = if ([string]$state.repeat_mode -eq "all") { "off" } else { "all" }
      Write-Step "soak action ${MutationIndex}: mode shuffle=$nextShuffle repeat=$nextRepeat"
      $null = Invoke-LyraJson -Method Post -Path "/api/player/mode" -Body @{
        shuffle = [bool]$nextShuffle
        repeat_mode = $nextRepeat
      }
      Write-JsonSnapshot -Label "soak-action-mode" -Extra @{
        mutation_index = $MutationIndex
        shuffle = [bool]$nextShuffle
        repeat_mode = $nextRepeat
      }
      break
    }
  }
}

function Assert-SoakState {
  param(
    [object]$State,
    [object]$Queue
  )

  if (-not $State.status) {
    throw "player state missing status during soak"
  }
  if (($Queue.count -as [int]) -lt 1) {
    throw "player queue unexpectedly empty during soak"
  }
  if (-not $State.current_track -or [string]::IsNullOrWhiteSpace([string]$State.current_track.track_id)) {
    throw "player state missing current track during soak"
  }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

$resolvedLogDirectory = if ([string]::IsNullOrWhiteSpace($LogDirectory)) {
  Join-Path $repoRoot ".lyra-build\logs\parity"
} else {
  if ([System.IO.Path]::IsPathRooted($LogDirectory)) {
    $LogDirectory
  } else {
    Join-Path $repoRoot $LogDirectory
  }
}
New-Item -ItemType Directory -Force -Path $resolvedLogDirectory | Out-Null
$artifactStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$script:ParityLogPath = Join-Path $resolvedLogDirectory "parity-hardening-$artifactStamp.log"
$script:ParitySnapshotPath = Join-Path $resolvedLogDirectory "parity-hardening-$artifactStamp.jsonl"
Write-Step "writing soak artifacts to $resolvedLogDirectory"

if (-not $SkipInstallerProof) {
  Write-Step "running clean-machine installer proof"
  powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "scripts\validate_clean_machine_install.ps1") -SkipToolSmokeCheck
  if ($LASTEXITCODE -ne 0) {
    throw "clean-machine installer proof failed (exit $LASTEXITCODE)"
  }

  Write-Step "running packaged streamrip proof"
  powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "scripts\validate_packaged_streamrip.ps1")
  if ($LASTEXITCODE -ne 0) {
    throw "packaged streamrip proof failed (exit $LASTEXITCODE)"
  }
}

$sidecarExe = Join-Path $repoRoot ".lyra-build\bin\lyra_backend.exe"
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

if (Test-HealthReady) {
  Write-Step "stopping pre-existing backend listener for deterministic sidecar validation"
  $existingListenerPid = Get-BackendListenerProcessId
  if ($existingListenerPid) {
    Stop-ProcessTree -RootPid $existingListenerPid
    if (-not (Wait-PortReleased -TimeoutSeconds 15)) {
      throw "existing backend listener did not release port 5000"
    }
  }
}

Write-Step "starting sidecar backend"
$startedProcess = Start-Sidecar -ExePath $sidecarExe -RepoRoot $repoRoot
$startedRootPid = $startedProcess.Id
$startedByThisScript = $true
if (-not (Wait-HealthReady -TimeoutSeconds $StartupTimeoutSeconds -HostProcess $startedProcess)) {
  if ($startedRootPid) {
    Stop-ProcessTree -RootPid $startedRootPid
  }
  throw "backend did not become healthy within ${StartupTimeoutSeconds}s"
}

try {
  Write-Step "running Step 1/2 smoke"
  powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "scripts\smoke_step1_step2.ps1") -SkipSidecarBuild -StartupTimeoutSeconds $StartupTimeoutSeconds -SoakSeconds ([Math]::Min($SoakSeconds, 30))
  Write-JsonSnapshot -Label "post-step1-2-smoke"

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
  $playState = Ensure-PlaybackActive
  $durationMs = [int]($playState.duration_ms -as [int])
  $recoverySeekTargetMs = if ($durationMs -gt 0) {
    [Math]::Min($RecoverySeekMs, [Math]::Max(0, $durationMs - 1500))
  } else {
    $RecoverySeekMs
  }
  if ($recoverySeekTargetMs -gt 0) {
    $null = Invoke-LyraJson -Method Post -Path "/api/player/seek" -Body @{ position_ms = $recoverySeekTargetMs }
  }
  $null = Pause-IfPlaying

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
  $restartPid = if ($startedRootPid) { $startedRootPid } else { Get-BackendListenerProcessId }
  if ($null -eq $restartPid) {
    throw "cannot determine backend process listening on port 5000"
  }
  Stop-ProcessTree -RootPid $restartPid
  $startedRootPid = $null
  if (-not (Wait-PortReleased -TimeoutSeconds 15)) {
    throw "backend listener did not release port 5000 after forced restart stop"
  }
  Start-Sleep -Milliseconds 700

  $startedProcess = Start-Sidecar -ExePath $sidecarExe -RepoRoot $repoRoot
  $startedRootPid = $startedProcess.Id
  $startedByThisScript = $true
  if (-not (Wait-HealthReady -TimeoutSeconds $StartupTimeoutSeconds -HostProcess $startedProcess)) {
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
  $deltaMs = [Math]::Abs($afterPositionMs - $recoverySeekTargetMs)

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
  Write-JsonSnapshot -Label "post-restart-recovery" -Extra @{
    before_track_id = $beforeTrackId
    before_queue_count = $beforeQueueCount
    after_track_id = $afterTrackId
    after_queue_count = $afterQueueCount
    position_delta_ms = $deltaMs
    recovery_seek_target_ms = $recoverySeekTargetMs
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

  Write-Step "preparing sustained soak queue"
  $soakTracks = Invoke-LyraJson -Method Get -Path "/api/library/tracks?limit=5"
  if (($soakTracks.count -as [int]) -lt 3) {
    throw "insufficient tracks available for sustained soak queue"
  }
  for ($i = 1; $i -lt [Math]::Min(4, $soakTracks.tracks.Count); $i++) {
    $soakTrackId = [string]$soakTracks.tracks[$i].track_id
    if (-not [string]::IsNullOrWhiteSpace($soakTrackId)) {
      $null = Invoke-LyraJson -Method Post -Path "/api/player/queue/add" -Body @{ track_id = $soakTrackId }
    }
  }
  $null = Invoke-LyraJson -Method Post -Path "/api/player/mode" -Body @{ shuffle = $false; repeat_mode = "all" }
  $null = Invoke-LyraJson -Method Post -Path "/api/player/play" -Body @{ queue_index = 0 }
  Start-Sleep -Milliseconds 900
  Write-JsonSnapshot -Label "pre-soak-ready"

  Write-Step "running sustained stability soak ($SoakSeconds seconds)"
  $deadline = (Get-Date).AddSeconds($SoakSeconds)
  $nextCheckpointAt = (Get-Date).AddSeconds([Math]::Max(5, $CheckpointIntervalSeconds))
  $nextMutationAt = (Get-Date).AddSeconds([Math]::Max(5, $ActionIntervalSeconds))
  $pollCount = 0
  $mutationCount = 0
  while ((Get-Date) -lt $deadline) {
    $state = Invoke-LyraJson -Method Get -Path "/api/player/state"
    $queue = Invoke-LyraJson -Method Get -Path "/api/player/queue"
    Assert-SoakState -State $state -Queue $queue
    $pollCount += 1

    $now = Get-Date
    if ($now -ge $nextCheckpointAt) {
      Write-Step "soak checkpoint: poll=$pollCount mutations=$mutationCount status=$($state.status) track=$([string]$state.current_track.track_id)"
      Write-JsonSnapshot -Label "soak-checkpoint" -Extra @{
        poll_count = $pollCount
        mutation_count = $mutationCount
      }
      $nextCheckpointAt = $now.AddSeconds([Math]::Max(5, $CheckpointIntervalSeconds))
    }

    if (-not $SkipSoakMutations -and $now -ge $nextMutationAt) {
      Invoke-SoakMutation -MutationIndex $mutationCount
      $mutationCount += 1
      $nextMutationAt = (Get-Date).AddSeconds([Math]::Max(5, $ActionIntervalSeconds))
    }

    Start-Sleep -Milliseconds 1000
  }

  Write-JsonSnapshot -Label "post-soak-summary" -Extra @{
    poll_count = $pollCount
    mutation_count = $mutationCount
    soak_seconds = $SoakSeconds
  }
  Write-Step "parity-hardening acceptance passed"
} catch {
  Write-Step "capturing failure diagnostics"
  Write-JsonSnapshot -Label "failure-diagnostics" -Extra @{
    error_message = $_.Exception.Message
    category = $_.CategoryInfo.Category
  }
  throw
} finally {
  if (-not $LeaveBackendRunning -and $startedByThisScript -and $startedRootPid) {
    Write-Step "stopping backend process started by script"
    Stop-ProcessTree -RootPid $startedRootPid
  }
}
