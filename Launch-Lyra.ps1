# Launch-Lyra.ps1 - Start Lyra Oracle with local LLM bootstrap (LM Studio -> Ollama fallback)
# Usage examples:
#   .\Launch-Lyra.ps1
#   .\Launch-Lyra.ps1 -LLMBackend auto -Model qwen2.5:14b-instruct
#   .\Launch-Lyra.ps1 -LLMBackend ollama -NoPull

param(
    [int]$Port = 5000,
    [ValidateSet("auto", "lmstudio", "ollama", "none")]
    [string]$LLMBackend = "auto",
    [string]$Model = "",
    [int]$LLMTimeoutSec = 30,
    [switch]$NoPull,
    [switch]$NoOpen,
    [switch]$NoTail
)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

function Write-Step { param($msg) Write-Host "  >> $msg" -ForegroundColor Cyan }
function Write-Ok   { param($msg) Write-Host "  OK $msg" -ForegroundColor Green }
function Write-Warn { param($msg) Write-Host "  !! $msg" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "  XX $msg" -ForegroundColor Red }
$script:StartedOllamaServer = $false

function Stop-OllamaModel {
    param([string]$ModelId)
    if (-not $ModelId) {
        return
    }
    if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
        return
    }
    try {
        & ollama stop $ModelId | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Ok "Unloaded Ollama model '$ModelId'"
        } else {
            Write-Warn "Could not unload Ollama model '$ModelId'"
        }
    } catch {
        Write-Warn "Ollama model unload failed: $($_.Exception.Message)"
    }
}

function Test-JsonEndpoint {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [int]$TimeoutSec = 2
    )
    try {
        $null = Invoke-RestMethod -Uri $Uri -TimeoutSec $TimeoutSec -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Wait-JsonEndpoint {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [int]$MaxWaitSec = 60,
        [int]$IntervalSec = 2
    )
    $elapsed = 0
    while ($elapsed -lt $MaxWaitSec) {
        if (Test-JsonEndpoint -Uri $Uri -TimeoutSec 2) {
            return $true
        }
        Start-Sleep -Seconds $IntervalSec
        $elapsed += $IntervalSec
    }
    return $false
}

function Get-LMStudioLoadedModels {
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:1234/v1/models" -TimeoutSec 3 -ErrorAction Stop
        $ids = @()
        if ($resp -and $resp.data) {
            foreach ($item in $resp.data) {
                if ($item.id) {
                    $ids += [string]$item.id
                }
            }
        }
        return @($ids)
    } catch {
        return @()
    }
}

function Get-LMStudioDiskModels {
    if (-not (Get-Command lms -ErrorAction SilentlyContinue)) {
        return @()
    }
    try {
        $json = & lms ls --json 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $json) {
            return @()
        }
        $parsed = $json | ConvertFrom-Json
        $names = @()

        if ($parsed -is [System.Array]) {
            foreach ($item in $parsed) {
                if ($item.key) {
                    $names += [string]$item.key
                } elseif ($item.modelKey) {
                    $names += [string]$item.modelKey
                } elseif ($item.id) {
                    $names += [string]$item.id
                }
            }
        } elseif ($parsed.models) {
            foreach ($item in $parsed.models) {
                if ($item.key) {
                    $names += [string]$item.key
                } elseif ($item.modelKey) {
                    $names += [string]$item.modelKey
                } elseif ($item.id) {
                    $names += [string]$item.id
                }
            }
        }
        return @($names | Where-Object { $_ } | Select-Object -Unique)
    } catch {
        return @()
    }
}

function Try-LoadLMStudioModel {
    param([string]$ModelKey)
    if (-not $ModelKey) {
        return $false
    }
    if (-not (Get-Command lms -ErrorAction SilentlyContinue)) {
        return $false
    }
    try {
        Write-Step "Loading LM Studio model '$ModelKey'..."
        & lms load --yes $ModelKey | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        Write-Warn "LM Studio load failed for '$ModelKey': $($_.Exception.Message)"
        return $false
    }
}

function Resolve-LMStudioExe {
    if ($env:LYRA_LMSTUDIO_EXE -and (Test-Path $env:LYRA_LMSTUDIO_EXE)) {
        return $env:LYRA_LMSTUDIO_EXE
    }

    $candidates = @(
        "C:\Users\Admin\AppData\Local\Programs\LM Studio\LM Studio.exe",
        "C:\Program Files\LM Studio\LM Studio.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return ""
}

function Try-BootLMStudio {
    param([string]$RequestedModel)

    $modelsUri = "http://127.0.0.1:1234/v1/models"

    if (-not (Test-JsonEndpoint -Uri $modelsUri -TimeoutSec 2)) {
        $lmExe = Resolve-LMStudioExe
        if ($lmExe) {
            Write-Step "Starting LM Studio app..."
            try {
                Start-Process -FilePath $lmExe | Out-Null
            } catch {
                Write-Warn "LM Studio app launch failed: $($_.Exception.Message)"
            }
        } else {
            Write-Warn "LM Studio executable not found (set LYRA_LMSTUDIO_EXE if custom path)."
        }

        if (Get-Command lms -ErrorAction SilentlyContinue) {
            try {
                Write-Step "Attempting to start LM Studio local server..."
                Start-Process -FilePath "lms" -ArgumentList @("server", "start") -WindowStyle Hidden | Out-Null
            } catch {
                Write-Warn "lms server start failed: $($_.Exception.Message)"
            }
        }
    }

    if (-not (Wait-JsonEndpoint -Uri $modelsUri -MaxWaitSec 45 -IntervalSec 3)) {
        return @{ ok = $false; reason = "LM Studio API not reachable at :1234" }
    }

    $preferredModel = $RequestedModel
    if (-not $preferredModel -and $env:LYRA_LLM_MODEL) {
        $preferredModel = $env:LYRA_LLM_MODEL
    }

    $loadedModels = Get-LMStudioLoadedModels
    if ($loadedModels.Count -eq 0) {
        $loadCandidate = $preferredModel
        if (-not $loadCandidate) {
            $diskModels = Get-LMStudioDiskModels
            if ($diskModels.Count -gt 0) {
                $loadCandidate = $diskModels[0]
            }
        }
        if ($loadCandidate) {
            $null = Try-LoadLMStudioModel -ModelKey $loadCandidate
            Start-Sleep -Seconds 2
            $loadedModels = Get-LMStudioLoadedModels
        }
    } elseif ($preferredModel -and ($loadedModels -notcontains $preferredModel)) {
        $null = Try-LoadLMStudioModel -ModelKey $preferredModel
        Start-Sleep -Seconds 2
        $loadedModels = Get-LMStudioLoadedModels
    }

    if ($loadedModels.Count -eq 0) {
        return @{ ok = $false; reason = "LM Studio API reachable but no model loaded" }
    }

    if ($preferredModel -and ($loadedModels -notcontains $preferredModel)) {
        return @{ ok = $false; reason = "Requested LM Studio model not loaded: $preferredModel" }
    }

    $modelId = $preferredModel
    if (-not $modelId) {
        $modelId = $loadedModels[0]
    }

    return @{
        ok       = $true
        provider = "lmstudio"
        base_url = "http://127.0.0.1:1234/v1"
        model    = $modelId
        reason   = "LM Studio ready"
    }
}

function Get-OllamaModelList {
    try {
        $lines = & ollama list 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $lines) {
            return @()
        }

        $rows = @()
        foreach ($line in ($lines | Select-Object -Skip 1)) {
            $trimmed = ($line | Out-String).Trim()
            if (-not $trimmed) {
                continue
            }
            $name = ($trimmed -split "\s+")[0]
            if ($name) {
                $rows += $name
            }
        }
        return $rows
    } catch {
        return @()
    }
}

function Select-OllamaModel {
    param(
        [string[]]$InstalledModels,
        [string]$RequestedModel
    )

    $models = @($InstalledModels)
    $nonCloud = @($models | Where-Object { $_ -and ($_ -notmatch ":cloud$") })

    if ($RequestedModel) {
        return $RequestedModel
    }

    if ($env:LYRA_LLM_MODEL) {
        if ($models -contains $env:LYRA_LLM_MODEL) {
            return $env:LYRA_LLM_MODEL
        }
    }

    # Prefer local models known to work well for Lyra classification tasks.
    $preferred = @(
        "oracle-brain:latest",
        "hf.co/bartowski/Qwen2.5-Coder-14B-Instruct-abliterated-GGUF:Q4_K_M",
        "qwen2.5-coder:0.5b",
        "llama3.2:3b",
        "llama3:latest"
    )
    foreach ($candidate in $preferred) {
        if ($nonCloud -contains $candidate) {
            return $candidate
        }
    }

    if ($nonCloud.Count -gt 0) {
        return $nonCloud[0]
    }
    if ($models.Count -gt 0) {
        return $models[0]
    }
    if ($env:LYRA_LLM_MODEL) {
        return $env:LYRA_LLM_MODEL
    }
    return "oracle-brain:latest"
}

function Try-BootOllama {
    param(
        [string]$RequestedModel,
        [switch]$SkipPull
    )

    $tagsUri = "http://127.0.0.1:11434/api/tags"

    if (-not (Test-JsonEndpoint -Uri $tagsUri -TimeoutSec 2)) {
        if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
            return @{ ok = $false; reason = "ollama command not found" }
        }

        Write-Step "Starting Ollama server..."
        try {
            Start-Process -FilePath "ollama" -ArgumentList @("serve") -WindowStyle Hidden | Out-Null
            $script:StartedOllamaServer = $true
        } catch {
            return @{ ok = $false; reason = "ollama serve launch failed: $($_.Exception.Message)" }
        }
    }

    if (-not (Wait-JsonEndpoint -Uri $tagsUri -MaxWaitSec 30 -IntervalSec 2)) {
        return @{ ok = $false; reason = "Ollama API not reachable at :11434" }
    }

    $installedModels = Get-OllamaModelList

    $modelId = Select-OllamaModel -InstalledModels $installedModels -RequestedModel $RequestedModel

    if ($installedModels -notcontains $modelId) {
        if ($SkipPull) {
            return @{ ok = $false; reason = "Model '$modelId' not installed and -NoPull set" }
        }

        Write-Step "Pulling Ollama model '$modelId'..."
        & ollama pull $modelId
        if ($LASTEXITCODE -ne 0) {
            return @{ ok = $false; reason = "ollama pull failed for '$modelId'" }
        }
    }

    return @{
        ok       = $true
        provider = "ollama"
        base_url = "http://127.0.0.1:11434/v1"
        model    = $modelId
        reason   = "Ollama ready"
    }
}

Push-Location $root

# Activate venv
if (Test-Path ".venv\Scripts\Activate.ps1") {
    . .venv\Scripts\Activate.ps1
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  LYRA ORACLE - LLM Boot + Server Start" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$llm = @{ ok = $false; provider = "none"; base_url = ""; model = ""; reason = "LLM disabled" }

switch ($LLMBackend) {
    "none" {
        Write-Warn "LLM backend disabled by flag"
        $llm = @{ ok = $false; provider = "none"; base_url = ""; model = ""; reason = "disabled" }
    }
    "lmstudio" {
        Write-Step "Booting LLM backend: LM Studio"
        $llm = Try-BootLMStudio -RequestedModel $Model
        if (-not $llm.ok) { Write-Fail $llm.reason; exit 1 }
    }
    "ollama" {
        Write-Step "Booting LLM backend: Ollama"
        $llm = Try-BootOllama -RequestedModel $Model -SkipPull:$NoPull
        if (-not $llm.ok) { Write-Fail $llm.reason; exit 1 }
    }
    "auto" {
        Write-Step "Booting LLM backend: auto (LM Studio -> Ollama)"
        $lmTry = Try-BootLMStudio -RequestedModel $Model
        if ($lmTry.ok) {
            $llm = $lmTry
        } else {
            Write-Warn $lmTry.reason
            $olTry = Try-BootOllama -RequestedModel $Model -SkipPull:$NoPull
            if ($olTry.ok) {
                $llm = $olTry
            } else {
                Write-Warn $olTry.reason
                $llm = @{ ok = $false; provider = "none"; base_url = ""; model = ""; reason = "no local LLM available" }
            }
        }
    }
}

if ($llm.ok) {
    Write-Ok "LLM ready via $($llm.provider)"
    Write-Host "    base_url: $($llm.base_url)" -ForegroundColor DarkGray
    if ($llm.model) {
        Write-Host "    model:    $($llm.model)" -ForegroundColor DarkGray
    }
} else {
    Write-Warn "Continuing without LLM ($($llm.reason))"
}

Write-Host ""
Write-Step "Starting Lyra API on port $Port..."
$job = Start-Job -ScriptBlock {
    param($r, $p, $provider, $baseUrl, $model, $timeoutSec)

    Set-Location $r
    if (Test-Path ".venv\Scripts\Activate.ps1") {
        . .venv\Scripts\Activate.ps1
    }

    if ($provider) { $env:LYRA_LLM_PROVIDER = $provider }
    if ($baseUrl)  { $env:LYRA_LLM_BASE_URL = $baseUrl }
    if ($model)    { $env:LYRA_LLM_MODEL = $model }
    if ($timeoutSec) { $env:LYRA_LLM_TIMEOUT_SECONDS = [string]$timeoutSec }
    $env:FLASK_PORT = [string]$p

    python lyra_api.py
} -ArgumentList $root, $Port, $llm.provider, $llm.base_url, $llm.model, $LLMTimeoutSec

Write-Host "    Flask job $($job.Id) starting..." -ForegroundColor DarkGray

# Wait for API
$ready = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 1
    try {
        # Avoid /health here because it can trigger expensive live LLM probes.
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/status" -TimeoutSec 2 -ErrorAction Stop
        if ($resp) {
            $ready = $true
            break
        }
    } catch {}
}

if (-not $ready) {
    Write-Fail "Lyra API did not respond in time"
    Receive-Job $job
    Stop-Job $job -ErrorAction SilentlyContinue
    Remove-Job $job -Force -ErrorAction SilentlyContinue
    Pop-Location
    exit 1
}

Write-Host ""
Write-Ok "Lyra API is LIVE"
Write-Host ""
Write-Host "    API:      http://localhost:$Port" -ForegroundColor White
Write-Host "    App:      http://localhost:$Port/app" -ForegroundColor White
Write-Host "    Playlust: http://localhost:$Port/playlust" -ForegroundColor White
Write-Host "    Health:   http://localhost:$Port/health" -ForegroundColor White
Write-Host ""

if (-not $NoOpen) {
    Start-Process "http://localhost:$Port/app"
}

if ($NoTail) {
    Write-Host ""
    Write-Ok "Startup complete. Flask job running in background: $($job.Id)"
    Pop-Location
    return
}

Write-Host "Press Ctrl+C to stop. Flask job: $($job.Id)" -ForegroundColor DarkGray
Write-Host ""

try {
    while ($true) {
        Receive-Job $job -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
} finally {
    Stop-Job $job -ErrorAction SilentlyContinue
    Remove-Job $job -Force -ErrorAction SilentlyContinue
    if ($llm.provider -eq "ollama") {
        Stop-OllamaModel -ModelId $llm.model
        if ($script:StartedOllamaServer) {
            Write-Step "Ollama server remains running (model unloaded)."
        }
    }
    Pop-Location
}
