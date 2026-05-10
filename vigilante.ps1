param([int]$intervaloMinutos = 48)
$toolkitDir = "$env:USERPROFILE\Desktop\roxymaster_report"
$ordenFile = "$env:USERPROFILE\Desktop\orden_para_cline.txt"
$logFile = "$env:USERPROFILE\Desktop\roxymaster\vigilante_log.txt"
function Write-Log { param($msg) "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - $msg" | Out-File -FilePath $logFile -Append -Encoding utf8 }
Write-Log "Vigilante iniciado. Intervalo: $intervaloMinutos minutos"
$bigFiles = @(); $asyncRisks = @()
if (Test-Path "$toolkitDir\big_files.txt") { $bigFiles = Get-Content "$toolkitDir\big_files.txt" -ErrorAction SilentlyContinue }
if (Test-Path "$toolkitDir\async_risks.txt") { $asyncRisks = Get-Content "$toolkitDir\async_risks.txt" -ErrorAction SilentlyContinue }
$ordenes = @()
foreach ($line in $bigFiles) { if ($line -match "(.+\.py) \| (\d+)") { $archivo = $matches[1]; $lineas = $matches[2]; if ($lineas -gt 400) { $ordenes += "DIVIDIR: $archivo ($lineas lineas) -> crear _core.py y _ext.py" } } }
foreach ($line in $asyncRisks) { if ($line -match "while True") { $ordenes += "REVISAR_LOOP: $line" } elseif ($line -match "create_task") { $ordenes += "REVISAR_TASK: $line" } elseif ($line -match "global ") { $ordenes += "REVISAR_GLOBAL: $line" } }
if ($ordenes.Count -gt 0) { "# GENERADO POR VIGILANTE EN $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`n`n$($ordenes -join "`n")" | Out-File -FilePath $ordenFile -Encoding utf8 -Force; Write-Log "Se generaron $($ordenes.Count) ordenes en $ordenFile" }
else { Write-Log "No se detectaron problemas. Todo ok." }
