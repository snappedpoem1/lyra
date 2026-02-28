$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$baseUrl = if ($env:VITE_LYRA_API_BASE) { $env:VITE_LYRA_API_BASE.TrimEnd("/") } else { "http://localhost:5000" }
$headers = @{}
if ($env:LYRA_API_TOKEN) {
  $headers["Authorization"] = "Bearer $($env:LYRA_API_TOKEN)"
}

Write-Host "Checking LLM configuration..."
& powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "check_llm_config.ps1")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

function Invoke-LyraJson {
  param(
    [string]$Method,
    [string]$Path,
    [object]$Body = $null
  )
  $uri = "$baseUrl$Path"
  if ($null -ne $Body) {
    return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers -ContentType "application/json" -Body ($Body | ConvertTo-Json -Depth 8)
  }
  return Invoke-RestMethod -Method $Method -Uri $uri -Headers $headers
}

$health = Invoke-LyraJson -Method Get -Path "/api/health"
Write-Host "Health OK: $($health.status)"

$vibes = Invoke-LyraJson -Method Get -Path "/api/vibes"
Write-Host "Vibes OK: $($vibes.count)"

if ($vibes.count -gt 0) {
  $playlistId = $vibes.vibes[0].name
  $playlist = Invoke-LyraJson -Method Get -Path "/api/playlists/$playlistId"
  Write-Host "Playlist detail OK: $($playlist.title)"

  if ($playlist.tracks.Count -gt 0) {
    $trackId = $playlist.tracks[0].track_id
    $dossier = Invoke-LyraJson -Method Get -Path "/api/tracks/$trackId/dossier"
    Write-Host "Dossier OK: $($dossier.track.title)"

    $flow = Invoke-LyraJson -Method Post -Path "/api/radio/flow" -Body @{ track_id = $trackId; count = 4 }
    Write-Host "Flow OK: $($flow.count)"
  }
}

$search = Invoke-LyraJson -Method Post -Path "/api/search" -Body @{ query = "dark ambient"; n = 5; rewrite_with_llm = $false }
Write-Host "Search OK: $($search.count)"

$discovery = Invoke-LyraJson -Method Get -Path "/api/radio/discovery?count=4"
Write-Host "Discovery OK: $($discovery.count)"

$queue = Invoke-LyraJson -Method Post -Path "/api/radio/queue" -Body @{ mode = "discovery"; length = 6 }
Write-Host "Queue OK: $($queue.count)"
