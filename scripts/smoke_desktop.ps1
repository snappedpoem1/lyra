param(
  [switch]$AllowLlmFailure
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Net.Http

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$baseUrl = if ($env:VITE_LYRA_API_BASE) { $env:VITE_LYRA_API_BASE.TrimEnd("/") } else { "http://localhost:5000" }
$headers = @{}
if ($env:LYRA_API_TOKEN) {
  $headers["Authorization"] = "Bearer $($env:LYRA_API_TOKEN)"
}

Write-Host "Checking LLM configuration..."
& powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "check_llm_config.ps1")
if ($LASTEXITCODE -ne 0) {
  if ($AllowLlmFailure) {
    Write-Warning "LLM configuration check failed; continuing backend/player smoke because -AllowLlmFailure was set."
  } else {
    exit $LASTEXITCODE
  }
}

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

$artists = Invoke-LyraJson -Method Get -Path "/api/library/artists?limit=5"
Write-Host "Library artists OK: $($artists.count)"

$libraryTracks = Invoke-LyraJson -Method Get -Path "/api/library/tracks?limit=5"
Write-Host "Library tracks OK: $($libraryTracks.count)"

$probeTrackId = $null

if ($vibes.count -gt 0) {
  $playlistId = $vibes.vibes[0].name
  $playlist = Invoke-LyraJson -Method Get -Path "/api/playlists/$playlistId"
  Write-Host "Playlist detail OK: $($playlist.title)"

  if ($playlist.tracks.Count -gt 0) {
    $probeTrackId = $playlist.tracks[0].track_id
  }
}

if (-not $probeTrackId -and $libraryTracks.count -gt 0) {
  $probeTrackId = $libraryTracks.tracks[0].track_id
}

if ($probeTrackId) {
  $dossier = Invoke-LyraJson -Method Get -Path "/api/tracks/$probeTrackId/dossier"
  Write-Host "Dossier OK: $($dossier.track.title)"

  $albums = Invoke-LyraJson -Method Get -Path "/api/library/albums?artist=$([uri]::EscapeDataString($dossier.track.artist))&limit=5"
  Write-Host "Library albums OK: $($albums.count)"

  $flow = Invoke-LyraJson -Method Post -Path "/api/radio/flow" -Body @{ track_id = $probeTrackId; count = 4 }
  Write-Host "Flow OK: $($flow.count)"

  $streamUri = "$baseUrl/api/stream/$probeTrackId"
  $httpClient = [System.Net.Http.HttpClient]::new()
  try {
    $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Get, $streamUri)
    foreach ($key in $headers.Keys) {
      $request.Headers.TryAddWithoutValidation($key, [string]$headers[$key]) | Out-Null
    }
    $response = $httpClient.SendAsync($request, [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
  } finally {
    if ($request) { $request.Dispose() }
  }
  if (-not $response.IsSuccessStatusCode) {
    throw "Stream endpoint returned HTTP $([int]$response.StatusCode)"
  }
  $contentType = $response.Content.Headers.ContentType.MediaType
  if (-not $contentType) {
    throw "Stream endpoint returned no Content-Type header"
  }
  Write-Host "Stream OK: $([int]$response.StatusCode) $contentType"
  $response.Dispose()
  $httpClient.Dispose()
} else {
  throw "No probe track was available from playlists or library."
}

$search = Invoke-LyraJson -Method Post -Path "/api/search" -Body @{ query = "dark ambient"; n = 5; rewrite_with_llm = $false }
Write-Host "Search OK: $($search.count)"

$discovery = Invoke-LyraJson -Method Get -Path "/api/radio/discovery?count=4"
Write-Host "Discovery OK: $($discovery.count)"

$queue = Invoke-LyraJson -Method Post -Path "/api/radio/queue" -Body @{ mode = "discovery"; length = 6 }
Write-Host "Queue OK: $($queue.count)"
