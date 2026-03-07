<#
.SYNOPSIS
    Validates the Wave 3 `LYRA_DATA_ROOT` path contract in isolated sandboxes.

.DESCRIPTION
    Probes `oracle.config` with temporary `LOCALAPPDATA` roots so the data-root
    contract can be validated without touching a real user profile. This is the
    parallel-lane acceptance helper for the Wave 3 runtime/data-root cutover.

    By default the script validates:
      - dev default resolution (`%LOCALAPPDATA%\Lyra\dev`)
      - explicit `LYRA_DATA_ROOT` override behavior
      - mutable derived paths staying under the resolved data root
      - build output roots staying outside the user data root

    Use `-AllowPendingContract` while the runtime-owner lane is still landing the
    config/backend changes. In that mode, missing `LYRA_DATA_ROOT` support is
    reported as warnings instead of failures so the script itself can be wired in
    before the core implementation is integrated.

.PARAMETER AllowPendingContract
    Downgrade missing or incomplete data-root contract checks to warnings.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\validate_data_root_contract.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\validate_data_root_contract.ps1 -AllowPendingContract
#>
param(
    [switch]$AllowPendingContract
)

$ErrorActionPreference = "Stop"

function Write-Pass {
    param([string]$Message)
    Write-Host "[PASS] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
    $script:Warnings++
}

function Write-Fail {
    param([string]$Message)
    Write-Host "[FAIL] $Message" -ForegroundColor Red
    $script:Failures++
}

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Write-Section {
    param([string]$Message)
    Write-Host "`n=== $Message ===" -ForegroundColor Yellow
}

function Resolve-FullPath {
    param([string]$PathValue)

    if (-not $PathValue) {
        return ""
    }

    return [System.IO.Path]::GetFullPath($PathValue)
}

function Test-PathWithinRoot {
    param(
        [string]$PathValue,
        [string]$RootPath
    )

    $normalizedPath = Resolve-FullPath -PathValue $PathValue
    $normalizedRoot = Resolve-FullPath -PathValue $RootPath
    if (-not $normalizedPath -or -not $normalizedRoot) {
        return $false
    }

    $rootWithSeparator = $normalizedRoot.TrimEnd('\') + '\'
    return $normalizedPath.StartsWith(
        $rootWithSeparator,
        [System.StringComparison]::OrdinalIgnoreCase
    ) -or $normalizedPath.Equals($normalizedRoot, [System.StringComparison]::OrdinalIgnoreCase)
}

function Write-ContractIssue {
    param([string]$Message)

    if ($AllowPendingContract) {
        Write-Warn $Message
        return
    }

    Write-Fail $Message
}

function Invoke-ConfigProbe {
    param(
        [string]$RepoRoot,
        [string]$PythonExe,
        [string]$LocalAppDataRoot,
        [string]$DataRootOverride,
        [switch]$SimulateFrozen
    )

    $probeRoot = Join-Path $env:TEMP "lyra_data_root_probe_$(Get-Random)"
    $probePath = Join-Path $probeRoot "probe_config.py"
    New-Item -ItemType Directory -Path $probeRoot -Force | Out-Null

    $probeScript = @'
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

if os.environ.get("LYRA_TEST_FROZEN", "").strip().lower() in {"1", "true", "yes", "on"}:
    setattr(sys, "frozen", True)
    test_executable = os.environ.get("LYRA_TEST_EXECUTABLE", "").strip()
    if test_executable:
        setattr(sys, "executable", test_executable)

config = importlib.import_module("oracle.config")

data_root = None
for candidate in ("DATA_ROOT", "LYRA_DATA_ROOT"):
    if hasattr(config, candidate):
        value = getattr(config, candidate)
        if value:
            data_root = value
            break

payload = {
    "project_root": str(getattr(config, "PROJECT_ROOT", "")),
    "data_root": str(data_root) if data_root else "",
    "db_path": str(getattr(config, "LYRA_DB_PATH", "")),
    "chroma_path": str(getattr(config, "CHROMA_PATH", "")),
    "log_root": str(getattr(config, "LOG_ROOT", "")),
    "temp_root": str(getattr(config, "TEMP_ROOT", "")),
    "state_root": str(getattr(config, "STATE_ROOT", "")),
    "model_cache_root": str(getattr(config, "MODEL_CACHE_ROOT", "")),
    "build_root": str(getattr(config, "BUILD_ROOT", "")),
    "staging_root": str(getattr(config, "STAGING_FOLDER", "")),
    "legacy_override": bool(getattr(config, "legacy_data_override_allowed", lambda: False)()),
}

print(json.dumps(payload))
'@

    Set-Content -Path $probePath -Value $probeScript -Encoding UTF8

    $keysToClear = @(
        "LYRA_DATA_ROOT",
        "LYRA_DB_PATH",
        "CHROMA_PATH",
        "CHROMA_DIR",
        "LIBRARY_BASE",
        "LIBRARY_DIR",
        "DOWNLOADS_FOLDER",
        "DOWNLOAD_DIR",
        "STAGING_FOLDER",
        "STAGING_DIR",
        "VIBES_FOLDER",
        "REPORTS_FOLDER",
        "PLAYLISTS_FOLDER",
        "SPOTIFY_DATA_DIR",
        "QUARANTINE_PATH",
        "REJECTED_FOLDER",
        "LYRA_BUILD_ROOT",
        "LYRA_LOG_ROOT",
        "LYRA_TEMP_ROOT",
        "LYRA_STATE_ROOT",
        "LYRA_MODEL_CACHE_ROOT",
        "HUGGINGFACE_HUB_CACHE",
        "HF_HOME",
        "LYRA_TEST_FROZEN",
        "LYRA_TEST_EXECUTABLE"
    )
    $savedEnv = @{}
    foreach ($key in @("LOCALAPPDATA", "PYTHONPATH") + $keysToClear) {
        $savedEnv[$key] = [Environment]::GetEnvironmentVariable($key, "Process")
    }

    try {
        [Environment]::SetEnvironmentVariable("LOCALAPPDATA", $LocalAppDataRoot, "Process")
        [Environment]::SetEnvironmentVariable("PYTHONPATH", $RepoRoot, "Process")
        foreach ($key in $keysToClear) {
            [Environment]::SetEnvironmentVariable($key, $null, "Process")
        }
        if ($DataRootOverride) {
            [Environment]::SetEnvironmentVariable("LYRA_DATA_ROOT", $DataRootOverride, "Process")
        }
        if ($SimulateFrozen) {
            $testExecutable = Join-Path $RepoRoot ".lyra-build\bin\lyra_backend.exe"
            [Environment]::SetEnvironmentVariable("LYRA_TEST_FROZEN", "1", "Process")
            [Environment]::SetEnvironmentVariable("LYRA_TEST_EXECUTABLE", $testExecutable, "Process")
        }

        $probeOutput = & $PythonExe $probePath 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "config probe failed: $($probeOutput -join [Environment]::NewLine)"
        }

        return ($probeOutput | Select-Object -Last 1 | ConvertFrom-Json)
    } finally {
        foreach ($entry in $savedEnv.GetEnumerator()) {
            [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, "Process")
        }
        Remove-Item -Recurse -Force $probeRoot -ErrorAction SilentlyContinue
    }
}

function Test-Scenario {
    param(
        [string]$Name,
        [pscustomobject]$Payload,
        [string]$ExpectedDataRoot
    )

    Write-Section $Name
    Write-Info "Expected data root: $ExpectedDataRoot"
    Write-Info "Observed project root: $($Payload.project_root)"
    if ($Payload.data_root) {
        Write-Info "Observed data root: $($Payload.data_root)"
    } else {
        Write-Info "Observed data root: <missing>"
    }

    if (-not $Payload.data_root) {
        Write-ContractIssue "oracle.config does not expose a data-root authority yet"
        return
    }

    if ((Resolve-FullPath -PathValue $Payload.data_root) -eq (Resolve-FullPath -PathValue $ExpectedDataRoot)) {
        Write-Pass "data root resolved to expected location"
    } else {
        Write-ContractIssue "data root mismatch. expected '$ExpectedDataRoot' got '$($Payload.data_root)'"
    }

    $pathChecks = @(
        @{ Label = "database"; Value = $Payload.db_path; Expected = (Join-Path $ExpectedDataRoot "db\lyra_registry.db") },
        @{ Label = "chroma"; Value = $Payload.chroma_path; Expected = (Join-Path $ExpectedDataRoot "chroma") },
        @{ Label = "logs"; Value = $Payload.log_root; Expected = (Join-Path $ExpectedDataRoot "logs") },
        @{ Label = "temp"; Value = $Payload.temp_root; Expected = (Join-Path $ExpectedDataRoot "tmp") },
        @{ Label = "state"; Value = $Payload.state_root; Expected = (Join-Path $ExpectedDataRoot "state") },
        @{ Label = "model cache"; Value = $Payload.model_cache_root; Expected = (Join-Path $ExpectedDataRoot "cache\hf") },
        @{ Label = "staging"; Value = $Payload.staging_root; Expected = (Join-Path $ExpectedDataRoot "staging") }
    )

    foreach ($check in $pathChecks) {
        if (-not $check.Value) {
            Write-ContractIssue "$($check.Label) path is missing from oracle.config"
            continue
        }

        if ((Resolve-FullPath -PathValue $check.Value) -eq (Resolve-FullPath -PathValue $check.Expected)) {
            Write-Pass "$($check.Label) path matches expected derived location"
            continue
        }

        if (Test-PathWithinRoot -PathValue $check.Value -RootPath $ExpectedDataRoot) {
            Write-ContractIssue "$($check.Label) stays under the data root but does not match the expected child path. expected '$($check.Expected)' got '$($check.Value)'"
        } else {
            Write-ContractIssue "$($check.Label) escapes the data root. expected under '$ExpectedDataRoot' got '$($check.Value)'"
        }
    }

    if (-not $Payload.build_root) {
        Write-ContractIssue "build root is missing from oracle.config"
    } elseif (Test-PathWithinRoot -PathValue $Payload.build_root -RootPath $ExpectedDataRoot) {
        Write-ContractIssue "build root should stay outside user data root but resolved to '$($Payload.build_root)'"
    } else {
        Write-Pass "build root remains separate from user data root"
    }
}

$script:Failures = 0
$script:Warnings = 0
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "python not found at expected path: $pythonExe"
}

$sandboxRoot = Join-Path $env:TEMP "lyra_data_root_validation_$(Get-Random)"
$localAppDataRoot = Join-Path $sandboxRoot "LocalAppData"
$overrideRoot = Join-Path $sandboxRoot "OverrideRoot"
New-Item -ItemType Directory -Path $localAppDataRoot -Force | Out-Null
New-Item -ItemType Directory -Path $overrideRoot -Force | Out-Null

try {
    $devPayload = Invoke-ConfigProbe `
        -RepoRoot $repoRoot `
        -PythonExe $pythonExe `
        -LocalAppDataRoot $localAppDataRoot `
        -DataRootOverride ""
    Test-Scenario -Name "Dev default data-root resolution" -Payload $devPayload -ExpectedDataRoot (Join-Path $localAppDataRoot "Lyra\dev")

    $overridePayload = Invoke-ConfigProbe `
        -RepoRoot $repoRoot `
        -PythonExe $pythonExe `
        -LocalAppDataRoot $localAppDataRoot `
        -DataRootOverride $overrideRoot
    Test-Scenario -Name "Explicit LYRA_DATA_ROOT override" -Payload $overridePayload -ExpectedDataRoot $overrideRoot

    $frozenPayload = Invoke-ConfigProbe `
        -RepoRoot $repoRoot `
        -PythonExe $pythonExe `
        -LocalAppDataRoot $localAppDataRoot `
        -DataRootOverride "" `
        -SimulateFrozen
    Test-Scenario -Name "Frozen installed default data-root resolution" -Payload $frozenPayload -ExpectedDataRoot (Join-Path $localAppDataRoot "Lyra")
} finally {
    Remove-Item -Recurse -Force $sandboxRoot -ErrorAction SilentlyContinue
}

Write-Section "Summary"
if ($script:Failures -eq 0 -and $script:Warnings -eq 0) {
    Write-Host "`n[PASS] Data-root contract validation complete. All checks passed." -ForegroundColor Green
    exit 0
}

if ($script:Failures -eq 0) {
    Write-Host "`n[WARN] Data-root contract validation finished with $($script:Warnings) warning(s)." -ForegroundColor Yellow
    exit 0
}

Write-Host "`n[FAIL] Data-root contract validation found $($script:Failures) failure(s) and $($script:Warnings) warning(s)." -ForegroundColor Red
exit 1
