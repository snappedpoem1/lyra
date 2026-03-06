<#
.SYNOPSIS
    Validates the packaged streamrip (rip.exe) acquisition path end-to-end.

.DESCRIPTION
    Confirms:
      1. The bundled rip.exe is present in runtime/bin and .lyra-build/bin/runtime/bin
      2. The binary is executable and reports the correct version
      3. The oracle.acquirers.streamrip module resolves is_available() → True via the
         bundled path (not a host-global install or venv script)
      4. The _build_command() generates a valid streamrip 2.x command line
      5. (Optional) A live dry-run against a configured source succeeds
         — this requires valid credentials and is off by default

    Set LYRA_STREAMRIP_SOURCE to choose the source (default: qobuz).
    Set LYRA_QOBUZ_EMAIL / LYRA_QOBUZ_PASSWORD if attempting a live acquisition.

.PARAMETER LiveAcquire
    Attempt a real acquisition. Requires streamrip credentials in .env.

.PARAMETER ArtistQuery
    Artist name used for the live acquisition test (default: "Burial").

.PARAMETER TrackQuery
    Track title used for the live acquisition test (default: "Archangel").

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\validate_packaged_streamrip.ps1
    powershell -ExecutionPolicy Bypass -File scripts\validate_packaged_streamrip.ps1 -LiveAcquire -ArtistQuery "Burial" -TrackQuery "Archangel"
#>
param(
    [switch]$LiveAcquire,
    [string]$ArtistQuery = "Burial",
    [string]$TrackQuery  = "Archangel"
)

$ErrorActionPreference = "Stop"

function Write-Pass    { param([string]$m) Write-Host "[PASS] $m" -ForegroundColor Green  }
function Write-Fail    { param([string]$m) Write-Host "[FAIL] $m" -ForegroundColor Red    ; $script:Failures++ }
function Write-Info    { param([string]$m) Write-Host "[INFO] $m" -ForegroundColor Cyan   }
function Write-Section { param([string]$m) Write-Host "`n=== $m ===" -ForegroundColor Yellow }

$script:Failures = 0
$repoRoot  = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"

# ── 1. Binary presence ──────────────────────────────────────────────────────
Write-Section "1. Bundled rip.exe presence"

$ripDev    = Join-Path $repoRoot "runtime\bin\rip.exe"
$ripTauri  = Join-Path $repoRoot ".lyra-build\bin\runtime\bin\rip.exe"

foreach ($pair in @(
    @{ Label = "rip.exe (runtime/bin)";               Path = $ripDev   },
    @{ Label = "rip.exe (.lyra-build runtime/bin)";   Path = $ripTauri }
)) {
    if (Test-Path $pair.Path) {
        $kb = [math]::Round((Get-Item $pair.Path).Length / 1KB)
        Write-Pass "$($pair.Label) present — $kb KB"
    } else {
        Write-Fail "$($pair.Label) NOT FOUND at $($pair.Path)"
    }
}

# ── 2. rip.exe --version ────────────────────────────────────────────────────
Write-Section "2. Bundled rip.exe --version"

if (Test-Path $ripDev) {
    $result = & $ripDev --version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Pass "rip.exe --version: $result"
    } else {
        Write-Fail "rip.exe --version exited $LASTEXITCODE : $result"
    }
} else {
    Write-Fail "Skipped: rip.exe not found"
}

# ── 3. rip.exe --help (exit 1 is normal for Click CLI) ─────────────────────
Write-Section "3. Bundled rip.exe --help"

if (Test-Path $ripDev) {
    $helpOutput = & $ripDev --help 2>&1 | Select-Object -First 5
    # Click help exits 0 only when invoked correctly; --help may exit 1
    $firstLine = $helpOutput | Select-Object -First 1
    if ($firstLine -match "Usage" -or $firstLine -match "rip") {
        Write-Pass "rip.exe --help output looks correct: $firstLine"
    } else {
        Write-Fail "rip.exe --help unexpected output: $firstLine"
    }
} else {
    Write-Fail "Skipped: rip.exe not found"
}

# ── 4. Python module: is_available() resolves to bundled tool ───────────────
Write-Section "4. oracle.acquirers.streamrip.is_available() via bundled tool"

if (-not (Test-Path $pythonExe)) {
    Write-Info "Skipping Python module checks (.venv not present — expected on clean machine target)"
} else {
    # Ensure LYRA_RUNTIME_ROOT points to our runtime dir so find_bundled_tool hits it
    $env:LYRA_RUNTIME_ROOT = Join-Path $repoRoot "runtime"

    $availScript = @"
import sys, os
sys.path.insert(0, r'$($repoRoot -replace "\\", "\\\\")')
os.environ['LYRA_RUNTIME_ROOT'] = r'$((Join-Path $repoRoot "runtime") -replace "\\", "\\\\")'
from oracle.acquirers.streamrip import is_available, _rip_binary
binary = _rip_binary()
if not binary:
    print("NOTFOUND")
    sys.exit(1)
if not is_available():
    print("UNAVAILABLE")
    sys.exit(1)
# Confirm the resolved binary is NOT the venv rip script — it must be a .exe
import pathlib
p = pathlib.Path(binary)
print(f"RESOLVED:{binary}")
sys.exit(0 if p.suffix.lower() == '.exe' else 2)
"@

    $tmpScript = Join-Path $env:TEMP "lyra_streamrip_proof.py"
    $availScript | Set-Content -Path $tmpScript -Encoding UTF8

    $output = & $pythonExe $tmpScript 2>&1
    $code = $LASTEXITCODE

    if ($code -eq 0 -and ($output -join "") -match "RESOLVED:") {
        $resolved = ($output -join " ") -replace ".*RESOLVED:", ""
        Write-Pass "is_available() = True; bundled binary resolved: $resolved"
    } elseif ($code -eq 2) {
        $resolved = ($output -join " ") -replace ".*RESOLVED:", ""
        Write-Fail "Resolved binary is not a .exe (got: $resolved) — may be using venv rip script instead of bundled exe"
    } elseif (($output -join "") -match "NOTFOUND") {
        Write-Fail "is_available() = False — bundled rip.exe not found by find_bundled_tool()"
    } else {
        Write-Fail "Module check failed (exit $code): $($output -join ' ')"
    }

    Remove-Item $tmpScript -ErrorAction SilentlyContinue
}

# ── 5. _build_command() generates correct streamrip 2.x syntax ─────────────
Write-Section "5. _build_command() generates valid streamrip 2.x command"

if (-not (Test-Path $pythonExe)) {
    Write-Info "Skipping Python module checks (.venv not present)"
} else {
    $cmdScript = @"
import sys, os
sys.path.insert(0, r'$($repoRoot -replace "\\", "\\\\")')
os.environ['LYRA_RUNTIME_ROOT'] = r'$((Join-Path $repoRoot "runtime") -replace "\\", "\\\\")'
from oracle.acquirers.streamrip import _build_command
import pathlib
cmd = _build_command("rip.exe", "Burial Archangel", pathlib.Path(r"C:\Temp\staging"))
print(" ".join(cmd))
# Validate: must include 'search', a source token, 'track', the query, '--first'
joined = " ".join(cmd)
assert "search" in cmd, f"missing 'search': {joined}"
assert "track" in cmd, f"missing 'track': {joined}"
assert "--first" in cmd, f"missing '--first': {joined}"
assert "Burial Archangel" in joined, f"missing query: {joined}"
print("OK")
"@

    $tmpCmd = Join-Path $env:TEMP "lyra_streamrip_cmd_proof.py"
    $cmdScript | Set-Content -Path $tmpCmd -Encoding UTF8

    $output = & $pythonExe $tmpCmd 2>&1
    $code = $LASTEXITCODE

    if ($code -eq 0 -and ($output -join "") -match "OK") {
        $cmdLine = $output | Select-Object -First 1
        Write-Pass "_build_command() → $cmdLine"
    } else {
        Write-Fail "_build_command() check failed (exit $code): $($output -join ' ')"
    }

    Remove-Item $tmpCmd -ErrorAction SilentlyContinue
}

# ── 6. Live acquisition (optional, requires credentials) ───────────────────
if ($LiveAcquire) {
    Write-Section "6. Live acquisition dry-run"

    if (-not (Test-Path $pythonExe)) {
        Write-Fail "Cannot run live acquisition check without .venv Python"
    } else {
        Write-Info "Attempting: artist='$ArtistQuery' track='$TrackQuery' source=$($env:LYRA_STREAMRIP_SOURCE)"

        $liveScript = @"
import sys, os, pathlib, tempfile
sys.path.insert(0, r'$($repoRoot -replace "\\", "\\\\")')
os.environ['LYRA_RUNTIME_ROOT'] = r'$((Join-Path $repoRoot "runtime") -replace "\\", "\\\\")'
from oracle.acquirers.streamrip import download
import tempfile
tmp = pathlib.Path(tempfile.mkdtemp(prefix='lyra_streamrip_proof_'))
result = download(
    artist='$ArtistQuery',
    title='$TrackQuery',
    output_dir=tmp,
    timeout_seconds=120,
)
print(f"success={result.get('success')}")
print(f"source={result.get('source')}")
print(f"error={result.get('error')}")
if result.get('path'):
    print(f"path={result['path']}")
sys.exit(0 if result.get('success') else 1)
"@

        $tmpLive = Join-Path $env:TEMP "lyra_streamrip_live_proof.py"
        $liveScript | Set-Content -Path $tmpLive -Encoding UTF8

        $output = & $pythonExe $tmpLive 2>&1
        $code = $LASTEXITCODE

        foreach ($line in $output) { Write-Info $line }

        if ($code -eq 0) {
            Write-Pass "Live acquisition succeeded"
        } else {
            Write-Fail "Live acquisition failed (exit $code)"
        }

        Remove-Item $tmpLive -ErrorAction SilentlyContinue
    }
} else {
    Write-Info "Live acquisition skipped (pass -LiveAcquire to test a real download)"
}

# ── Summary ─────────────────────────────────────────────────────────────────
Write-Section "Summary"
if ($script:Failures -eq 0) {
    Write-Host "`n[PASS] Packaged streamrip proof complete. All checks passed." -ForegroundColor Green
    exit 0
} else {
    Write-Host "`n[FAIL] $($script:Failures) check(s) failed." -ForegroundColor Red
    exit 1
}
