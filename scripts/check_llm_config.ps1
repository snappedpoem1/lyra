param(
  [switch]$BootstrapLocal = $true
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
    "anthropic" { "anthropic" }
    "disabled" { "disabled" }
    "none" { "disabled" }
    "off" { "disabled" }
    default { "invalid" }
  }

  $baseUrl = "$env:LYRA_LLM_BASE_URL".Trim()
  if (-not $baseUrl) {
    if ($provider -in @("local", "openai_compatible")) {
      $baseUrl = "http://localhost:1234/v1"
    }
    elseif ($provider -eq "openai") {
      $baseUrl = "https://api.openai.com/v1"
    }
    elseif ($provider -eq "anthropic") {
      $baseUrl = "https://api.anthropic.com/v1"
    }
  }

  $timeoutSeconds = 30
  if ("$env:LYRA_LLM_TIMEOUT_SECONDS".Trim() -match '^\d+$') {
    $timeoutSeconds = [Math]::Max(1, [int]$env:LYRA_LLM_TIMEOUT_SECONDS)
  }

  [pscustomobject]@{
    raw_provider = $providerRaw
    provider_type = $provider
    base_url = $baseUrl.TrimEnd("/")
    model = "$env:LYRA_LLM_MODEL".Trim()
    fallback_model = "$env:LYRA_LLM_FALLBACK_MODEL".Trim()
    timeout_seconds = $timeoutSeconds
    api_key = "$env:LYRA_LLM_API_KEY".Trim()
  }
}

function Test-IsLocalBase {
  param([string]$BaseUrl)
  return $BaseUrl -match '^https?://(localhost|127\.0\.0\.1)(:\d+)?(/|$)'
}

function Get-ModelsProbeUrl {
  param([string]$BaseUrl)
  return "$($BaseUrl.TrimEnd('/'))/models"
}

function Test-LlmModels {
  param(
    $Config,
    [int]$ProbeTimeoutSec = 3
  )

  $probeUrl = Get-ModelsProbeUrl -BaseUrl $Config.base_url
  $headers = @{}
  if ($Config.api_key) {
    $headers["Authorization"] = "Bearer $($Config.api_key)"
  }

  try {
    $response = Invoke-RestMethod -Method Get -Uri $probeUrl -Headers $headers -TimeoutSec $ProbeTimeoutSec
    $models = @()
    if ($response.data) {
      $models = @($response.data | ForEach-Object { $_.id } | Where-Object { $_ })
    }
    return [pscustomobject]@{
      ok = $true
      probe_url = $probeUrl
      models = $models
      error = $null
      status = 200
    }
  }
  catch {
    $statusCode = $null
    if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
      $statusCode = [int]$_.Exception.Response.StatusCode
    }
    return [pscustomobject]@{
      ok = $false
      probe_url = $probeUrl
      models = @()
      error = $_.Exception.Message
      status = $statusCode
    }
  }
}

function Find-LmsCli {
  $candidates = @(
    "$env:LYRA_LMS_CLI_EXE".Trim(),
    "$env:LMS_CLI_EXE".Trim(),
    "C:\Users\Admin\.lmstudio\bin\lms.exe",
    (Join-Path $env:USERPROFILE ".lmstudio\bin\lms.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\LM Studio\resources\app\.webpack\lms.exe"),
    (Join-Path $env:LOCALAPPDATA "LM-Studio\resources\app\.webpack\lms.exe"),
    (Join-Path $env:ProgramFiles "LM Studio\resources\app\.webpack\lms.exe"),
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
    (Join-Path $env:LOCALAPPDATA "Programs\LM Studio\LM Studio.exe"),
    (Join-Path $env:LOCALAPPDATA "LM-Studio\LM Studio.exe"),
    (Join-Path $env:ProgramFiles "LM Studio\LM Studio.exe"),
    "C:\Program Files\AMD\AI_Bundle\LMStudio\LM Studio\LM Studio.exe"
  ) | Where-Object { $_ }

  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
      return $candidate
    }
  }
  return $null
}

function Start-LmStudioServer {
  param($Config)

  $result = [ordered]@{
    ready = $false
    started = $false
    method = ""
    probe_url = (Get-ModelsProbeUrl -BaseUrl $Config.base_url)
    error = ""
  }

  if (-not (Test-IsLocalBase -BaseUrl $Config.base_url)) {
    $result.error = "Configured base URL is not local; skipping LM Studio bootstrap."
    return [pscustomobject]$result
  }

  try {
    $uri = [System.Uri]$Config.base_url
    $hostName = if ($uri.Host -eq "localhost") { "127.0.0.1" } else { $uri.Host }
    $port = if ($uri.Port -gt 0) { $uri.Port } else { 1234 }
  }
  catch {
    $hostName = "127.0.0.1"
    $port = 1234
  }

  $cli = Find-LmsCli
  if ($cli) {
    Start-Process -FilePath $cli -ArgumentList @("server", "start", "--port", "$port", "--bind", $hostName) -WorkingDirectory (Split-Path -Parent $cli) -WindowStyle Hidden
    $result.started = $true
    $result.method = "lms_cli"
  }
  else {
    $exe = Find-LmStudioExe
    if (-not $exe) {
      $result.error = "LM Studio CLI and executable were not found."
      return [pscustomobject]$result
    }
    Start-Process -FilePath $exe -WorkingDirectory (Split-Path -Parent $exe)
    $result.started = $true
    $result.method = "desktop_app"
  }

  $attempts = [Math]::Min(15, [Math]::Max(8, $Config.timeout_seconds))
  for ($i = 0; $i -lt $attempts; $i++) {
    Start-Sleep -Seconds 1
    $probe = Test-LlmModels -Config $Config -ProbeTimeoutSec 1
    if ($probe.ok) {
      $result.ready = $true
      return [pscustomobject]$result
    }
  }

  $result.error = "LM Studio endpoint did not become ready before timeout."
  return [pscustomobject]$result
}

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
Load-LyraEnv -RepoRoot $repoRoot

Write-Host "Lyra LLM configuration check"
Write-Host "Repo: $repoRoot"

$config = Get-LyraLlmConfig
$diagnostic = [ordered]@{
  ok = $false
  config = [ordered]@{
    provider_type = $config.provider_type
    raw_provider = $config.raw_provider
    base_url = $config.base_url
    model = $config.model
    fallback_model = $config.fallback_model
    timeout_seconds = $config.timeout_seconds
    api_key_env_var = "LYRA_LLM_API_KEY"
    api_key_present = [bool]$config.api_key
    supports_model_listing = $config.provider_type -in @("local", "openai_compatible", "openai")
    supports_chat_completions = $config.provider_type -in @("local", "openai_compatible", "openai")
    supports_anthropic_messages = $config.provider_type -eq "anthropic"
  }
  error_type = ""
  error = ""
  actions = @()
  models = @()
  selected_model = if ($config.model) { $config.model } else { $config.fallback_model }
  fallback_used = $false
  supports_model_probe = $config.provider_type -in @("local", "openai_compatible", "openai")
}

if ($config.provider_type -eq "disabled") {
  $diagnostic.ok = $true
  $diagnostic.actions = @("AI-dependent features are disabled by configuration.")
}
elseif ($config.provider_type -eq "invalid") {
  $diagnostic.error_type = "provider_invalid"
  $diagnostic.error = "Unsupported provider '$($config.raw_provider)'."
  $diagnostic.actions = @("Set LYRA_LLM_PROVIDER to one of: openai, anthropic, openai_compatible, local, disabled.")
}
elseif (-not $config.model -and -not $config.fallback_model) {
  $diagnostic.error_type = "model_missing"
  $diagnostic.error = "No primary or fallback model is configured."
  $diagnostic.actions = @("Set LYRA_LLM_MODEL.", "Optionally set LYRA_LLM_FALLBACK_MODEL for automatic recovery.")
}
elseif ($config.provider_type -eq "anthropic") {
  $diagnostic.ok = $true
  if ($config.model.ToLowerInvariant().StartsWith("qwen")) {
    $diagnostic.actions = @("Configured Anthropic provider with a qwen model. Verify the endpoint actually supports that model before enabling agent features.")
  }
}
else {
  $probe = Test-LlmModels -Config $config -ProbeTimeoutSec 3
  if (-not $probe.ok -and $BootstrapLocal -and $config.provider_type -in @("local", "openai_compatible") -and (Test-IsLocalBase -BaseUrl $config.base_url)) {
    $bootstrap = Start-LmStudioServer -Config $config
    $diagnostic.bootstrap = $bootstrap
    $probe = Test-LlmModels -Config $config -ProbeTimeoutSec 3
  }

  if (-not $probe.ok) {
    $diagnostic.error_type = "endpoint_probe_failed"
    $diagnostic.error = if ($probe.status) {
      "Model probe failed with HTTP $($probe.status) from $($probe.probe_url)."
    } else {
      "Model probe failed: $($probe.error)"
    }
    $diagnostic.actions = @(
      "Verify the base URL is reachable.",
      "Run scripts\\fix_lmstudio.ps1 for a local LM Studio restart.",
      "If this endpoint is Anthropic-compatible, set LYRA_LLM_PROVIDER=anthropic."
    )
  }
  else {
    $diagnostic.models = @($probe.models)
    if ($config.model -and ($probe.models -contains $config.model)) {
      $diagnostic.ok = $true
    }
    elseif ($config.fallback_model -and ($probe.models -contains $config.fallback_model)) {
      $diagnostic.ok = $true
      $diagnostic.selected_model = $config.fallback_model
      $diagnostic.fallback_used = $true
      $diagnostic.actions = @("Primary model '$($config.model)' is unavailable; fallback '$($config.fallback_model)' will be used.")
    }
    else {
      $diagnostic.error_type = "model_not_available"
      $diagnostic.error = "Configured model '$($diagnostic.selected_model)' is not present in $($probe.probe_url)."
      $diagnostic.actions = @(
        "Call /v1/models on the configured endpoint and choose a listed model.",
        "Or switch LYRA_LLM_PROVIDER to the correct provider family for that endpoint.",
        "Or set LYRA_LLM_PROVIDER=disabled to disable AI-dependent features cleanly."
      )
    }
  }
}

$diagnostic | ConvertTo-Json -Depth 8
if ($diagnostic.ok) {
  exit 0
}
exit 1
