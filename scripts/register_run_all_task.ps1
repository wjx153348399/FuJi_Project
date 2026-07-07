param(
    [string]$TaskName = "ZK Realtime Upload",
    [string]$ProjectDir = "D:\PythonProject\ZK",
    [string]$PythonExe = "python",
    [string]$ConfigPath = "config.json",
    [string]$WebConfigPath = "web_config.json",
    [string]$UserId = $env:USERNAME
)

$action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "run_all.py --config `"$ConfigPath`" --web-config `"$WebConfigPath`"" `
    -WorkingDirectory $ProjectDir

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $UserId
$settings = New-ScheduledTaskSettingsSet `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 30)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Start ZK Web dashboard and realtime watcher" `
    -Force
