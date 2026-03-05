param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$ScriptPath = Join-Path $PSScriptRoot "backup_db.ps1"

if ($DryRun) {
    Write-Host "[dry-run] Would register task: LyraOracle_DailyBackup -> $ScriptPath -Type daily"
    Write-Host "[dry-run] Would register task: LyraOracle_WeeklyChromaBackup -> $ScriptPath -Type weekly"
    exit 0
}

$dailyAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -ExecutionPolicy Bypass -File `"$ScriptPath`" -Type daily"
$dailyTrigger = New-ScheduledTaskTrigger -Daily -At "03:00"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable:$false `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask `
    -TaskName "LyraOracle_DailyBackup" `
    -TaskPath "\LyraOracle\" `
    -Action $dailyAction `
    -Trigger $dailyTrigger `
    -Settings $settings `
    -RunLevel Highest `
    -Force | Out-Null

Write-Host "OK - LyraOracle_DailyBackup registered (daily 03:00)"

$weeklyAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -ExecutionPolicy Bypass -File `"$ScriptPath`" -Type weekly"
$weeklyTrigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Sunday -At "04:00"

Register-ScheduledTask `
    -TaskName "LyraOracle_WeeklyChromaBackup" `
    -TaskPath "\LyraOracle\" `
    -Action $weeklyAction `
    -Trigger $weeklyTrigger `
    -Settings $settings `
    -RunLevel Highest `
    -Force | Out-Null

Write-Host "OK - LyraOracle_WeeklyChromaBackup registered (Sundays 04:00)"
Write-Host 'Run "Get-ScheduledTask -TaskPath \LyraOracle\" to verify.'
