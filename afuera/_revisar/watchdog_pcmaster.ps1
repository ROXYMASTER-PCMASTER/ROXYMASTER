# watchdog_pcmaster.ps1 - mantiene el servidor siempre encendido
# si se cuelga, lo reinicia automaticamente en 5 segundos

$script = "C:\Users\PCMASTER\Desktop\roxymaster\pcmaster\scripts\server.py"
$log    = "C:\Users\PCMASTER\Desktop\roxymaster\pcmaster\scripts\watchdog.log"
$puerto = 8086

function log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [watchdog] $msg"
    Write-Host $line
    Add-Content -Path $log -Value $line -ErrorAction SilentlyContinue
}

log "iniciando vigilante del servidor"

while ($true) {
    $conexion = Get-NetTCPConnection -LocalPort $puerto -ErrorAction SilentlyContinue | Where-Object { $_.State -eq 'Listen' }
    if (-not $conexion) {
        log "servidor caido. reiniciando..."
        Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like '*server*' -or $_.CommandLine -like '*server.py*' } | Stop-Process -Force
        Start-Sleep -Seconds 2
        Start-Process python -ArgumentList $script -NoNewWindow
        log "servidor reiniciado"
    }
    Start-Sleep -Seconds 10
}
