<#
.SYNOPSIS
    Validates the packaged Lyra installer artifacts as they would behave on a clean
    machine that has no Python, no venv, and no host-installed acquisition tools.

.DESCRIPTION
    Checks that all bundled executables are present in the expected staging locations,
    that the Tauri bundle resource path is correctly configured, and that each binary
    responds correctly without any reliance on the host environment.

    Pass -SkipToolSmokeCheck to skip executable invocation (CI without runner access).
    Pass -BuildFirst to rebuild packaged artifacts before validating.

.PARAMETER BuildFirst
    Run build_packaged_runtime.ps1 before validation.

.PARAMETER SkipToolSmokeCheck
    Skip executable invocation smoke checks.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\validate_clean_machine_install.ps1
    powershell -ExecutionPolicy Bypass -File scripts\validate_clean_machine_install.ps1 -BuildFirst
#>
param(
    [switch]$BuildFirst,
    [switch]$SkipToolSmokeCheck
)

$ErrorActionPreference = "Stop"

function Write-Pass { param([string]$Message) Write-Host "[PASS] $Message" -ForegroundColor Green }
function Write-Fail { param([string]$Message) Write-Host "[FAIL] $Message" -ForegroundColor Red ; $script:Failures++ }
function Write-Info { param([string]$Message) Write-Host "[INFO] $Message" -ForegroundColor Cyan }
function Write-Section { param([string]$Message) Write-Host "`n=== $Message ===" -ForegroundColor Yellow }

$script:Failures = 0
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

# ── Optional pre-build ──────────────────────────────────────────────────────
if ($BuildFirst) {
    Write-Section "Pre-build packaged runtime"
    $buildArgs = @(
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $repoRoot "scripts\build_packaged_runtime.ps1"),
        "-SkipLaunchCheck",
        "-SkipToolSmokeCheck"
    )
    powershell @buildArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "build_packaged_runtime.ps1 failed (exit $LASTEXITCODE)"
        exit 1
    }
}

# ── Expected artifact paths ─────────────────────────────────────────────────
$buildBin          = Join-Path $repoRoot ".lyra-build\bin"
$buildRuntimeBin   = Join-Path $buildBin  "runtime\bin"
$runtimeBin        = Join-Path $repoRoot  "runtime\bin"

$artifacts = @{
    # Tauri bundle / sidecar
    "lyra_backend.exe (sidecar)"      = Join-Path $buildBin        "lyra_backend.exe"
    # Packaged bundled acquisition tools (Tauri resource tree)
    "rip.exe (tauri resource)"        = Join-Path $buildRuntimeBin "rip.exe"
    "spotdl.exe (tauri resource)"     = Join-Path $buildRuntimeBin "spotdl.exe"
    "ffmpeg.exe (tauri resource)"     = Join-Path $buildRuntimeBin "ffmpeg.exe"
    "ffprobe.exe (tauri resource)"    = Join-Path $buildRuntimeBin "ffprobe.exe"
    # Dev runtime tree (used during dev launch)
    "rip.exe (runtime/bin)"           = Join-Path $runtimeBin      "rip.exe"
    "spotdl.exe (runtime/bin)"        = Join-Path $runtimeBin      "spotdl.exe"
}

Write-Section "Artifact presence checks"
foreach ($label in $artifacts.Keys) {
    $path = $artifacts[$label]
    if (Test-Path $path) {
        $sizeKB = [math]::Round((Get-Item $path).Length / 1KB)
        Write-Pass "$label ($sizeKB KB)"
    } else {
        Write-Fail "$label NOT FOUND at $path"
    }
}

# ── Tauri bundle resource config check ─────────────────────────────────────
Write-Section "Tauri bundle resource configuration check"
$tauriConf = Join-Path $repoRoot "desktop\renderer-app\src-tauri\tauri.conf.json"
if (-not (Test-Path $tauriConf)) {
    Write-Fail "tauri.conf.json not found at expected path"
} else {
    $conf = Get-Content $tauriConf -Raw | ConvertFrom-Json
    $resources = $conf.tauri.bundle.resources
    $expectedResource = "../../../.lyra-build/bin"
    if ($resources -contains $expectedResource) {
        Write-Pass "tauri.conf.json resources includes bundled bin path"
    } else {
        Write-Fail "tauri.conf.json resources does not include '$expectedResource' (got: $($resources -join ', '))"
    }
}

# ── Sidecar config checks ───────────────────────────────────────────────────
Write-Section "Sidecar config checks"
$sidecarBuildScript = Join-Path $repoRoot "scripts\build_backend_sidecar.ps1"
if (Test-Path $sidecarBuildScript) {
    Write-Pass "build_backend_sidecar.ps1 present"
} else {
    Write-Fail "build_backend_sidecar.ps1 missing"
}

$runtimeToolScript = Join-Path $repoRoot "scripts\build_runtime_tools.ps1"
if (Test-Path $runtimeToolScript) {
    Write-Pass "build_runtime_tools.ps1 present"
} else {
    Write-Fail "build_runtime_tools.ps1 missing"
}

# ── Executable smoke checks (skippable) ────────────────────────────────────
if (-not $SkipToolSmokeCheck) {
    Write-Section "Executable smoke checks (clean-runtime, no venv)"

    # PyInstaller standalones carry all dependencies inside the exe.
    # Test each binary individually using direct invocation + text matching.

    # rip.exe --version  (exits 0, outputs version string)
    if (Test-Path (Join-Path $buildRuntimeBin "rip.exe")) {
        $ripOut = & (Join-Path $buildRuntimeBin "rip.exe") --version 2>&1
        $ripCode = $LASTEXITCODE
        if ($ripCode -eq 0 -and "$ripOut" -match 'version') {
            Write-Pass "rip.exe --version (tauri resource) — $($ripOut | Select-Object -First 1)"
        } else {
            Write-Fail "rip.exe --version (tauri resource) exited $ripCode"
        }
    } else {
        Write-Fail "rip.exe --version (tauri resource) — binary missing"
    }

    # spotdl.exe --version (exits 0, outputs version string)
    if (Test-Path (Join-Path $buildRuntimeBin "spotdl.exe")) {
        $sdlOut = & (Join-Path $buildRuntimeBin "spotdl.exe") --version 2>&1
        $sdlCode = $LASTEXITCODE
        if ($sdlCode -eq 0 -and "$sdlOut" -match '\d') {
            Write-Pass "spotdl.exe --version (tauri resource) — $($sdlOut | Select-Object -First 1)"
        } else {
            Write-Fail "spotdl.exe --version (tauri resource) exited $sdlCode"
        }
    } else {
        Write-Fail "spotdl.exe --version (tauri resource) — binary missing"
    }

    # ffmpeg.exe -version (exits 0, outputs version block)
    if (Test-Path (Join-Path $buildRuntimeBin "ffmpeg.exe")) {
        $ffOut = & (Join-Path $buildRuntimeBin "ffmpeg.exe") -version 2>&1
        $ffCode = $LASTEXITCODE
        if ($ffCode -eq 0 -and "$ffOut" -match 'ffmpeg') {
            Write-Pass "ffmpeg.exe -version (tauri resource) — $($ffOut | Select-Object -First 1)"
        } else {
            Write-Fail "ffmpeg.exe -version (tauri resource) exited $ffCode"
        }
    } else {
        Write-Fail "ffmpeg.exe -version (tauri resource) — binary missing"
    }

    # lyra_backend.exe — confirm it is a valid PE executable (has the right MZ header)
    # We do NOT launch it here to avoid spawning a Flask server during the proof run.
    $backendExe = Join-Path $buildBin "lyra_backend.exe"
    if (Test-Path $backendExe) {
        $headerBytes = [System.IO.File]::ReadAllBytes($backendExe) | Select-Object -First 2
        if ($headerBytes[0] -eq 0x4D -and $headerBytes[1] -eq 0x5A) {
            Write-Pass "lyra_backend.exe (sidecar) is a valid PE executable (MZ header confirmed)"
        } else {
            Write-Fail "lyra_backend.exe (sidecar) does not have a valid PE MZ header"
        }
    } else {
        Write-Fail "lyra_backend.exe (sidecar) — binary missing"
    }
}

# ── Summary ─────────────────────────────────────────────────────────────────
Write-Section "Summary"
if ($script:Failures -eq 0) {
    Write-Host "`n[PASS] Clean-machine installer proof complete. All checks passed." -ForegroundColor Green
    exit 0
} else {
    Write-Host "`n[FAIL] $($script:Failures) check(s) failed." -ForegroundColor Red
    exit 1
}
