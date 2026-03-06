param(
  [string]$BaseUrl = "http://127.0.0.1:5000",
  [int]$SoakSeconds = 90,
  [int]$StartupTimeoutSeconds = 180,
  [switch]$SkipSidecarBuild
)

$ErrorActionPreference = "Stop"

function Write-Step {
  param([string]$Message)
  Write-Host "[step1-2-smoke] $Message"
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
    return $health.status -eq "ok"
  } catch {
    return $false
  }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $repoRoot

$sidecarExe = Join-Path $repoRoot "desktop\renderer-app\src-tauri\bin\lyra_backend.exe"
$startedSidecar = $false
$sidecarProcess = $null
$sidecarRootPid = $null

if (-not $SkipSidecarBuild) {
  Write-Step "building packaged sidecar executable"
  powershell -ExecutionPolicy Bypass -File (Join-Path $repoRoot "scripts\build_backend_sidecar.ps1")
}

if (-not (Test-Path $sidecarExe)) {
  throw "sidecar executable not found: $sidecarExe"
}

if (-not (Test-HealthReady)) {
  Write-Step "starting sidecar backend process"
  $env:LYRA_PROJECT_ROOT = $repoRoot
  $env:LYRA_SKIP_VENV_REEXEC = "1"
  $env:LYRA_BOOTSTRAP = "0"
  $sidecarProcess = Start-Process -FilePath $sidecarExe -WorkingDirectory $repoRoot -PassThru
  $sidecarRootPid = $sidecarProcess.Id
  $startedSidecar = $true

  $ready = $false
  $maxAttempts = [Math]::Max(1, [int]($StartupTimeoutSeconds * 2))
  for ($i = 0; $i -lt $maxAttempts; $i++) {
    Start-Sleep -Milliseconds 500
    if ($sidecarProcess.HasExited) {
      throw "sidecar process exited before health readiness (exit code: $($sidecarProcess.ExitCode))"
    }
    if (Test-HealthReady) {
      $ready = $true
      break
    }
  }
  if (-not $ready) {
    throw "backend did not become healthy in time (${StartupTimeoutSeconds}s timeout)"
  }
} else {
  Write-Step "backend already running; using existing process"
}

try {
  Write-Step "checking health + library"
  $health = Invoke-LyraJson -Method Get -Path "/api/health"
  if ($health.status -ne "ok") {
    throw "health status was not ok"
  }
  $tracks = Invoke-LyraJson -Method Get -Path "/api/library/tracks?limit=4"
  if (($tracks.count -as [int]) -lt 1) {
    throw "no tracks available for player smoke"
  }

  $trackIds = @()
  foreach ($row in $tracks.tracks) {
    if ($row.track_id) {
      $trackIds += [string]$row.track_id
    }
  }
  if ($trackIds.Count -lt 1) {
    throw "library response did not include track ids"
  }

  Write-Step "resetting queue with test tracks"
  foreach ($trackId in $trackIds[0..([Math]::Min(2, $trackIds.Count - 1))]) {
    $null = Invoke-LyraJson -Method Post -Path "/api/player/queue/add" -Body @{ track_id = $trackId }
  }
  $queue = Invoke-LyraJson -Method Get -Path "/api/player/queue"
  if (($queue.count -as [int]) -lt 1) {
    throw "queue did not contain test tracks"
  }

  Write-Step "running canonical player commands"
  $null = Invoke-LyraJson -Method Post -Path "/api/player/play" -Body @{ queue_index = 0 }
  Start-Sleep -Milliseconds 900
  $null = Invoke-LyraJson -Method Post -Path "/api/player/seek" -Body @{ position_ms = 10000 }
  $null = Invoke-LyraJson -Method Post -Path "/api/player/mode" -Body @{ shuffle = $false; repeat_mode = "one" }
  Start-Sleep -Milliseconds 500
  $null = Invoke-LyraJson -Method Post -Path "/api/player/pause" -Body @{}
  $null = Invoke-LyraJson -Method Post -Path "/api/player/play" -Body @{ queue_index = 0 }

  Write-Step "soak polling player state for $SoakSeconds seconds"
  $deadline = (Get-Date).AddSeconds($SoakSeconds)
  $polls = 0
  while ((Get-Date) -lt $deadline) {
    $state = Invoke-LyraJson -Method Get -Path "/api/player/state"
    if (-not $state.status) {
      throw "player state missing status"
    }
    $polls += 1
    Start-Sleep -Milliseconds 1000
  }
  Write-Step "state polling complete ($polls polls)"

  Write-Step "checking player SSE stream contract"
  $prevNativeErrorMode = $PSNativeCommandUseErrorActionPreference
  $PSNativeCommandUseErrorActionPreference = $false
  try {
    $sseText = & curl.exe -sN --max-time 8 "$BaseUrl/ws/player" 2>$null
    if (($LASTEXITCODE -ne 0) -and ($LASTEXITCODE -ne 28)) {
      throw "curl failed while reading SSE stream (exit code: $LASTEXITCODE)"
    }
  } finally {
    $PSNativeCommandUseErrorActionPreference = $prevNativeErrorMode
  }
  $sseJoined = ($sseText | Out-String)
  if ([string]::IsNullOrWhiteSpace($sseJoined) -or $sseJoined -notmatch '"type"\s*:\s*"player_state_changed"') {
    throw "SSE stream did not include player_state_changed"
  }

  $null = Invoke-LyraJson -Method Post -Path "/api/player/pause" -Body @{}
  Write-Step "step 1 + step 2 smoke passed"
} finally {
  if ($startedSidecar -and $sidecarRootPid) {
    Write-Step "stopping sidecar process"
    Stop-ProcessTree -RootPid $sidecarRootPid
  }
}
