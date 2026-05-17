# watchdog_pcmaster.ps1 - Monitoreo y reinicio automático del servidor PCMaster
$ErrorActionPreference = "SilentlyContinue"

$logDir = "$env:USERPROFILE\Desktop\roxymaster\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force }

$logFile = "$logDir\watchdog.log"
$serverScript = "$env:USERPROFILE\Desktop\roxymaster\pcmaster\scripts\server.py"

function Write-WatchdogLog($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts - $msg" | Out-File $logFile -Append -Encoding UTF8
}

Write-WatchdogLog "Watchdog iniciado. Buscando proceso uvicorn..."

$process = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*uvicorn*" -or $_.CommandLine -like "*server.py*" }

if (-not $process) {
    Write-WatchdogLog "ALERTA: Servidor PCMaster no encontrado. Reiniciando..."
    Start-Process powershell -ArgumentList "-ExecutionPolicy Bypass -File `"$serverScript`"" -WindowStyle Hidden
    Write-WatchdogLog "Comando de reinicio enviado."
} else {
    Write-WatchdogLog "Servidor PCMaster corriendo (PID: $($process.Id)). Todo OK."
}
