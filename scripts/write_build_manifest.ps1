param(
    [string]$OutputPath = ".lyra-build\manifests\windows-build-manifest.json"
)

$ErrorActionPreference = "Stop"

function Get-RequiredArtifact {
    param(
        [string]$Label,
        [string[]]$Candidates
    )

    foreach ($candidate in $Candidates) {
        if (Test-Path $candidate) {
            $resolved = (Resolve-Path $candidate).Path
            $hash = Get-FileHash -Path $resolved -Algorithm SHA256
            return [ordered]@{
                path = $resolved
                sha256 = $hash.Hash.ToLowerInvariant()
                size_bytes = (Get-Item $resolved).Length
            }
        }
    }

    throw "required artifact '$Label' not found"
}

function Get-ToolchainValue {
    param(
        [string]$Path,
        [string]$Fallback = ""
    )

    if (-not (Test-Path $Path)) {
        return $Fallback
    }

    return (Get-Content $Path -Raw).Trim()
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$manifestPath = if ([System.IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath
} else {
    Join-Path $repoRoot $OutputPath
}

$manifestDir = Split-Path -Parent $manifestPath
New-Item -ItemType Directory -Path $manifestDir -Force | Out-Null

$runtimeBinRoot = Join-Path $repoRoot ".lyra-build\bin\runtime\bin"
$toolchainFile = Join-Path $repoRoot "rust-toolchain.toml"
$rustChannel = ""
if (Test-Path $toolchainFile) {
    $rustChannel = (
        Select-String -Path $toolchainFile -Pattern 'channel\s*=\s*"([^"]+)"' |
        Select-Object -First 1
    ).Matches.Groups[1].Value
}

$manifest = [ordered]@{
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    platform = "windows"
    toolchains = [ordered]@{
        python = Get-ToolchainValue -Path (Join-Path $repoRoot ".python-version") -Fallback $env:PYTHON_VERSION
        node = Get-ToolchainValue -Path (Join-Path $repoRoot ".node-version") -Fallback $env:NODE_VERSION
        rust = if ($rustChannel) { $rustChannel } else { $env:RUSTUP_TOOLCHAIN }
    }
    artifacts = [ordered]@{
        backend_sidecar = Get-RequiredArtifact -Label "backend sidecar" -Candidates @(
            (Join-Path $repoRoot ".lyra-build\bin\lyra_backend.exe")
        )
        packaged_host = Get-RequiredArtifact -Label "packaged host" -Candidates @(
            (Join-Path $repoRoot "desktop\renderer-app\src-tauri\target\debug\lyra_tauri.exe"),
            (Join-Path $repoRoot "desktop\renderer-app\src-tauri\target\release\lyra_tauri.exe")
        )
        rip = Get-RequiredArtifact -Label "rip.exe" -Candidates @(
            (Join-Path $runtimeBinRoot "rip.exe")
        )
        spotdl = Get-RequiredArtifact -Label "spotdl.exe" -Candidates @(
            (Join-Path $runtimeBinRoot "spotdl.exe")
        )
        ffmpeg = Get-RequiredArtifact -Label "ffmpeg.exe" -Candidates @(
            (Join-Path $runtimeBinRoot "ffmpeg.exe")
        )
        ffprobe = Get-RequiredArtifact -Label "ffprobe.exe" -Candidates @(
            (Join-Path $runtimeBinRoot "ffprobe.exe")
        )
    }
}

$manifest | ConvertTo-Json -Depth 6 | Set-Content -Path $manifestPath -Encoding utf8
Write-Host "[build-manifest] wrote $manifestPath"