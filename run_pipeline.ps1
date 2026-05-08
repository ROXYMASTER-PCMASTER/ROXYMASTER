$taskName = "roxymaster_pipeline"

$scriptPath = "$env:USERPROFILE\Desktop\roxymaster\run_pipeline.ps1"

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -File `"$scriptPath`""

# trigger correcto base
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date)

# settings de repetición (ESTO ES LO CORRECTO EN WINDOWS)
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

# repetición cada hora se define aquí (NO en trigger)
$settings.Repetition = New-ScheduledTaskRepetitionPattern `
    -Interval (New-TimeSpan -Hours 1) `
    -Duration (New-TimeSpan -Days 3650)

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -RunLevel Highest `
    -Force

Write-Host "OK: tarea corregida y activa -> $taskName"