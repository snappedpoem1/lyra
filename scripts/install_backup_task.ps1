# install_backup_task.ps1 — Register Lyra Oracle backup with Windows Task Scheduler
# Run once as Administrator (or with UAC elevation) to install the tasks.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\install_backup_task.ps1

$ScriptPath = "C:\MusicOracle\scripts\backup_db.ps1"

# ---------------------------------------------------------------------------
# Nightly daily backup — 03:00 every day
# ---------------------------------------------------------------------------
$dailyAction  = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -ExecutionPolicy Bypass -File `"$ScriptPath`" -Type daily"

$dailyTrigger = New-ScheduledTaskTrigger -Daily -At "03:00"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable:$false `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask `
    -TaskName  "LyraOracle_DailyBackup" `
    -TaskPath  "\LyraOracle\" `
    -Action    $dailyAction `
    -Trigger   $dailyTrigger `
    -Settings  $settings `
    -RunLevel  Highest `
    -Force | Out-Null

Write-Host "OK  — LyraOracle_DailyBackup registered (daily 03:00)"

# ---------------------------------------------------------------------------
# Weekly chroma backup — 04:00 every Sunday
# ---------------------------------------------------------------------------
$weeklyAction  = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -ExecutionPolicy Bypass -File `"$ScriptPath`" -Type weekly"

$weeklyTrigger = New-ScheduledTaskTrigger -Weekly -WeeksInterval 1 -DaysOfWeek Sunday -At "04:00"

Register-ScheduledTask `
    -TaskName  "LyraOracle_WeeklyChromaBackup" `
    -TaskPath  "\LyraOracle\" `
    -Action    $weeklyAction `
    -Trigger   $weeklyTrigger `
    -Settings  $settings `
    -RunLevel  Highest `
    -Force | Out-Null

Write-Host "OK  — LyraOracle_WeeklyChromaBackup registered (Sundays 04:00)"
Write-Host ""
Write-Host "Run 'Get-ScheduledTask -TaskPath \LyraOracle\' to verify."
