# backup_db.ps1 — Lyra Oracle nightly/weekly backup
# Backs up lyra_registry.db (nightly) and chroma_storage/ (weekly)
# Retention: 7 daily + 4 weekly, older copies are purged
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\backup_db.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\backup_db.ps1 -Type weekly

param(
    [ValidateSet("daily", "weekly", "both")]
    [string]$Type = "both"
)

$ProjectRoot  = Split-Path -Parent $PSScriptRoot
$BackupRoot   = Join-Path $ProjectRoot "backups"
$DbSource     = Join-Path $ProjectRoot "lyra_registry.db"
$ChromaSource = Join-Path $ProjectRoot "chroma_storage"
$LogFile      = Join-Path $BackupRoot "backup_log.txt"

$DateTag    = Get-Date -Format "yyyy-MM-dd"
$WeekTag    = "week-$(Get-Date -UFormat '%Y-W%V')"

# ---------------------------------------------------------------------------
function Write-Log {
    param([string]$Message)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $Message"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line
}

# ---------------------------------------------------------------------------
function Backup-Daily {
    $dest = Join-Path $BackupRoot "lyra_registry_$DateTag.db"
    if (Test-Path $dest) {
        Write-Log "SKIP daily — $dest already exists"
        return
    }
    if (-not (Test-Path $DbSource)) {
        Write-Log "ERROR daily — source not found: $DbSource"
        return
    }
    Copy-Item -Path $DbSource -Destination $dest -Force
    Write-Log "OK   daily — copied to $dest"

    # Purge: keep newest 7 daily backups
    $dailies = Get-ChildItem $BackupRoot -Filter "lyra_registry_????-??-??.db" |
               Sort-Object LastWriteTime -Descending
    if ($dailies.Count -gt 7) {
        $dailies | Select-Object -Skip 7 | ForEach-Object {
            Remove-Item $_.FullName -Force
            Write-Log "PURGE daily — $($_.Name)"
        }
    }
}

# ---------------------------------------------------------------------------
function Backup-Weekly {
    $dest = Join-Path $BackupRoot "chroma_$WeekTag"
    if (Test-Path $dest) {
        Write-Log "SKIP weekly — $dest already exists"
        return
    }
    if (-not (Test-Path $ChromaSource)) {
        Write-Log "ERROR weekly — source not found: $ChromaSource"
        return
    }
    Copy-Item -Path $ChromaSource -Destination $dest -Recurse -Force
    Write-Log "OK   weekly — copied chroma_storage to $dest"

    # Purge: keep newest 4 weekly chroma backups
    $weeklies = Get-ChildItem $BackupRoot -Filter "chroma_week-*" -Directory |
                Sort-Object LastWriteTime -Descending
    if ($weeklies.Count -gt 4) {
        $weeklies | Select-Object -Skip 4 | ForEach-Object {
            Remove-Item $_.FullName -Recurse -Force
            Write-Log "PURGE weekly — $($_.Name)"
        }
    }
}

# ---------------------------------------------------------------------------
# Ensure backup dir exists
New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null

Write-Log "=== Lyra Oracle backup started (type=$Type) ==="

switch ($Type) {
    "daily"  { Backup-Daily }
    "weekly" { Backup-Weekly }
    "both"   { Backup-Daily; Backup-Weekly }
}

Write-Log "=== Backup complete ==="
