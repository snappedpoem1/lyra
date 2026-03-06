<#
.SYNOPSIS
    Validates an installed Lyra desktop app directory or installed host executable.

.DESCRIPTION
    This script is meant for the blank-machine installer lane. It verifies the
    installed host executable exists, checks common sidecar/runtime-tool layouts,
    and can optionally launch the installed app via the packaged-host smoke path.

    Supported sidecar/runtime layouts include:
      - <app>\Lyra Oracle.exe
      - <app>\bin\lyra_backend.exe
      - <app>\resources\lyra_backend.exe
      - <app>\resources\bin\lyra_backend.exe
      - <app>\runtime\bin\*.exe
      - <app>\resources\runtime\bin\*.exe

.PARAMETER InstalledExe
    Full path to the installed `Lyra Oracle.exe`.

.PARAMETER InstalledRoot
    App install directory. If omitted, the script probes common local install paths.

.PARAMETER SkipLaunchSmoke
    Skip launching the installed app after artifact validation.

.PARAMETER HealthTimeoutSeconds
    Timeout used for installed launch smoke.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\validate_installed_runtime.ps1 -InstalledRoot "$env:LOCALAPPDATA\Programs\Lyra Oracle"
    powershell -ExecutionPolicy Bypass -File scripts\validate_installed_runtime.ps1 -InstalledExe "C:\Users\Admin\AppData\Local\Programs\Lyra Oracle\Lyra Oracle.exe"
#>
param(
    [string]$InstalledExe,
    [string]$InstalledRoot,
    [switch]$SkipLaunchSmoke,
    [int]$HealthTimeoutSeconds = 60
)

$ErrorActionPreference = "Stop"

function Write-Pass { param([string]$Message) Write-Host "[PASS] $Message" -ForegroundColor Green }
function Write-Fail { param([string]$Message) Write-Host "[FAIL] $Message" -ForegroundColor Red ; $script:Failures++ }
function Write-Info { param([string]$Message) Write-Host "[INFO] $Message" -ForegroundColor Cyan }
function Write-Section { param([string]$Message) Write-Host "`n=== $Message ===" -ForegroundColor Yellow }

function Resolve-InstalledRoot {
    param(
        [string]$ExplicitExe,
        [string]$ExplicitRoot
    )

    if ($ExplicitExe) {
        $resolvedExe = (Resolve-Path $ExplicitExe).Path
        return Split-Path -Parent $resolvedExe
    }

    if ($ExplicitRoot) {
        return (Resolve-Path $ExplicitRoot).Path
    }

    $candidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Lyra Oracle"),
        (Join-Path $env:ProgramFiles "Lyra Oracle"),
        (Join-Path ${env:ProgramFiles(x86)} "Lyra Oracle")
    ) | Where-Object { $_ -and (Test-Path $_) }

    foreach ($candidate in $candidates) {
        if (Test-Path (Join-Path $candidate "Lyra Oracle.exe")) {
            return (Resolve-Path $candidate).Path
        }
    }

    throw "installed Lyra app root not found; pass -InstalledExe or -InstalledRoot"
}

function Resolve-InstalledExePath {
    param([string]$RootPath, [string]$ExplicitExe)

    if ($ExplicitExe) {
        return (Resolve-Path $ExplicitExe).Path
    }

    $candidate = Join-Path $RootPath "Lyra Oracle.exe"
    if (Test-Path $candidate) {
        return (Resolve-Path $candidate).Path
    }
    throw "installed host exe not found under '$RootPath'"
}

$script:Failures = 0
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$appRoot = Resolve-InstalledRoot -ExplicitExe $InstalledExe -ExplicitRoot $InstalledRoot
$hostExe = Resolve-InstalledExePath -RootPath $appRoot -ExplicitExe $InstalledExe

$sidecarCandidates = @(
    (Join-Path $appRoot "lyra_backend.exe"),
    (Join-Path $appRoot "bin\lyra_backend.exe"),
    (Join-Path $appRoot "resources\lyra_backend.exe"),
    (Join-Path $appRoot "resources\bin\lyra_backend.exe")
)
$runtimeBinCandidates = @(
    (Join-Path $appRoot "runtime\bin"),
    (Join-Path $appRoot "resources\runtime\bin"),
    (Join-Path $appRoot "bin\runtime\bin")
)

Write-Section "Installed app root"
Write-Info "Root: $appRoot"
Write-Info "Host: $hostExe"

Write-Section "Host executable"
if (Test-Path $hostExe) {
    Write-Pass "installed host exe present"
} else {
    Write-Fail "installed host exe missing: $hostExe"
}

Write-Section "Installed sidecar candidates"
$resolvedSidecar = $null
foreach ($candidate in $sidecarCandidates) {
    if (Test-Path $candidate) {
        if (-not $resolvedSidecar) {
            $resolvedSidecar = (Resolve-Path $candidate).Path
        }
        $sizeKB = [math]::Round((Get-Item $candidate).Length / 1KB)
        Write-Pass "sidecar present: $candidate ($sizeKB KB)"
    } else {
        Write-Info "not present: $candidate"
    }
}
if (-not $resolvedSidecar) {
    Write-Fail "no installed sidecar candidate found"
}

Write-Section "Installed runtime/bin candidates"
$resolvedRuntimeBin = $null
foreach ($candidate in $runtimeBinCandidates) {
    if (Test-Path $candidate) {
        if (-not $resolvedRuntimeBin) {
            $resolvedRuntimeBin = (Resolve-Path $candidate).Path
        }
        Write-Pass "runtime/bin candidate present: $candidate"
    } else {
        Write-Info "not present: $candidate"
    }
}
if (-not $resolvedRuntimeBin) {
    Write-Fail "no installed runtime/bin candidate found"
} else {
    foreach ($tool in @("rip.exe", "spotdl.exe", "ffmpeg.exe", "ffprobe.exe")) {
        $toolPath = Join-Path $resolvedRuntimeBin $tool
        if (Test-Path $toolPath) {
            $sizeKB = [math]::Round((Get-Item $toolPath).Length / 1KB)
            Write-Pass "$tool present in installed runtime/bin ($sizeKB KB)"
        } else {
            Write-Fail "$tool missing from installed runtime/bin: $toolPath"
        }
    }
}

if (-not $SkipLaunchSmoke -and (Test-Path $hostExe)) {
    Write-Section "Installed launch smoke"
    $smokeArgs = @(
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $repoRoot "scripts\packaged_host_smoke.ps1"),
        "-HostExe", $hostExe,
        "-HealthTimeoutSeconds", "$HealthTimeoutSeconds"
    )
    powershell @smokeArgs
    if ($LASTEXITCODE -eq 0) {
        Write-Pass "installed launch smoke passed"
    } else {
        Write-Fail "installed launch smoke failed (exit $LASTEXITCODE)"
    }
}

Write-Section "Summary"
if ($script:Failures -eq 0) {
    Write-Host "`n[PASS] Installed runtime validation complete. All checks passed." -ForegroundColor Green
    exit 0
}

Write-Host "`n[FAIL] $($script:Failures) check(s) failed." -ForegroundColor Red
exit 1
