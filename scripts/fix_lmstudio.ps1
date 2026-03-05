param(
  [int]$TimeoutSeconds = 45,
  [switch]$CleanRestart = $true
)

$ErrorActionPreference = "Stop"

function Load-LyraEnv {
  param([string]$RepoRoot)

  $envPath = Join-Path $RepoRoot ".env"
  if (-not (Test-Path $envPath)) {
    return
  }

  foreach ($line in Get-Content -Path $envPath) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith("#")) {
      continue
    }
    $separator = $trimmed.IndexOf("=")
    if ($separator -lt 1) {
      continue
    }
    $key = $trimmed.Substring(0, $separator).Trim()
    if ([string]::IsNullOrWhiteSpace($key) -or (Test-Path "Env:$key")) {
      continue
    }
    $value = $trimmed.Substring($separator + 1).Trim()
    if (
      ($value.StartsWith('"') -and $value.EndsWith('"')) -or
      ($value.StartsWith("'") -and $value.EndsWith("'"))
    ) {
      $value = $value.Substring(1, $value.Length - 2)
    }
    Set-Item -Path "Env:$key" -Value $value
  }
}

function Get-LyraLlmConfig {
  $providerRaw = "$env:LYRA_LLM_PROVIDER".Trim()
  if (-not $providerRaw) {
    $providerRaw = "local"
  }

  $provider = switch ($providerRaw.ToLowerInvariant()) {
    "lmstudio" { "local" }
    "local" { "local" }
    "openai_compatible" { "openai_compatible" }
    "openai-compatible" { "openai_compatible" }
    "openai" { "openai" }
    default { $providerRaw.ToLowerInvariant() }
  }

  $baseUrl = "$env:LYRA_LLM_BASE_URL".Trim()
  if (-not $baseUrl) {
    $baseUrl = "http://127.0.0.1:1234/v1"
  }

  $timeout = if ("$env:LYRA_LLM_TIMEOUT_SECONDS".Trim() -match '^\d+$') {
    [Math]::Max(1, [int]$env:LYRA_LLM_TIMEOUT_SECONDS)
  } else {
    $TimeoutSeconds
  }

  [pscustomobject]@{
    provider_type = $provider
    base_url = $baseUrl.TrimEnd("/")
    timeout_seconds = $timeout
  }
}

function Test-LlmModels {
  param(
    $Config,
    [int]$ProbeTimeoutSec = 3
  )
  try {
    Invoke-RestMethod -Method Get -Uri "$($Config.base_url)/models" -TimeoutSec $ProbeTimeoutSec | Out-Null
    return $true
  }
  catch {
    return $false
  }
}

function Test-IsLocalBase {
  param([string]$BaseUrl)
  return $BaseUrl -match '^https?://((localhost|127\.0\.0\.1)|((10|192\.168|172\.(1[6-9]|2[0-9]|3[0-1]))\.\d+\.\d+))(:\d+)?(/|$)'
}

function Find-LmsCli {
  $candidates = @(
    "$env:LYRA_LMS_CLI_EXE".Trim(),
    "$env:LMS_CLI_EXE".Trim(),
    (Join-Path $env:USERPROFILE ".lmstudio\bin\lms.exe"),
    "C:\Program Files\AMD\AI_Bundle\LMStudio\LM Studio\resources\app\.webpack\lms.exe"
  ) | Where-Object { $_ }

  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
      return $candidate
    }
  }
  return $null
}

function Find-LmStudioExe {
  $candidates = @(
    "$env:LYRA_LM_STUDIO_EXE".Trim(),
    "$env:LM_STUDIO_EXE".Trim(),
    "C:\Program Files\AMD\AI_Bundle\LMStudio\LM Studio\LM Studio.exe",
    (Join-Path $env:LOCALAPPDATA "Programs\LM Studio\LM Studio.exe"),
    (Join-Path $env:ProgramFiles "LM Studio\LM Studio.exe")
  ) | Where-Object { $_ }

  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
      return $candidate
    }
  }
  return $null
}

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
Load-LyraEnv -RepoRoot $repoRoot
$config = Get-LyraLlmConfig

Write-Host "Lyra LM Studio recovery"
Write-Host "Repo: $repoRoot"

if ($config.provider_type -notin @("local", "openai_compatible", "openai")) {
  [pscustomobject]@{
    ready = $false
    started = $false
    method = "skipped"
    error = "Configured provider '$($config.provider_type)' is not a local/OpenAI-compatible provider."
  } | ConvertTo-Json -Depth 6
  exit 1
}

if (-not (Test-IsLocalBase -BaseUrl $config.base_url)) {
  [pscustomobject]@{
    ready = $true
    started = $false
    method = "skipped_remote_endpoint"
    probe_url = "$($config.base_url)/models"
    note = "Configured endpoint is remote; LM Studio restart is not required."
  } | ConvertTo-Json -Depth 6
  exit 0
}

if ($CleanRestart) {
  Write-Host "Stopping any stuck LM Studio processes first..."
  Get-Process -Name "LM Studio" -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Seconds 2
}

if (Test-LlmModels -Config $config -ProbeTimeoutSec 3) {
  [pscustomobject]@{
    ready = $true
    started = $false
    method = "already_running"
    probe_url = "$($config.base_url)/models"
  } | ConvertTo-Json -Depth 6
  exit 0
}

try {
  $uri = [System.Uri]$config.base_url
  $hostName = if ($uri.Host -eq "localhost") { "127.0.0.1" } else { $uri.Host }
  $port = if ($uri.Port -gt 0) { $uri.Port } else { 1234 }
}
catch {
  $hostName = "127.0.0.1"
  $port = 1234
}

$cli = Find-LmsCli
$method = ""
if ($cli) {
  Start-Process -FilePath $cli -ArgumentList @("server", "start", "--port", "$port", "--bind", $hostName) -WorkingDirectory (Split-Path -Parent $cli) -WindowStyle Hidden
  $method = "lms_cli"
}
else {
  $exe = Find-LmStudioExe
  if (-not $exe) {
    [pscustomobject]@{
      ready = $false
      started = $false
      method = "none"
      error = "LM Studio CLI and executable were not found."
    } | ConvertTo-Json -Depth 6
    exit 1
  }
  Start-Process -FilePath $exe -WorkingDirectory (Split-Path -Parent $exe)
  $method = "desktop_app"
}

for ($i = 0; $i -lt ([Math]::Min($TimeoutSeconds, 20)); $i++) {
  Start-Sleep -Seconds 1
  if (Test-LlmModels -Config $config -ProbeTimeoutSec 1) {
    [pscustomobject]@{
      ready = $true
      started = $true
      method = $method
      probe_url = "$($config.base_url)/models"
    } | ConvertTo-Json -Depth 6
    exit 0
  }
}

[pscustomobject]@{
  ready = $false
  started = $true
  method = $method
  probe_url = "$($config.base_url)/models"
  error = "LM Studio endpoint did not become ready before timeout."
  actions = @(
    "Open LM Studio manually and confirm local server is enabled.",
    "Check that port 1234 is free and the daemon can start.",
    "If local inference is optional, set LYRA_LLM_PROVIDER=disabled until LM Studio is healthy."
  )
} | ConvertTo-Json -Depth 6
exit 1
