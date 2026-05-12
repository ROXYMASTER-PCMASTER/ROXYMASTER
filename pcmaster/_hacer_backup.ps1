$ts = Get-Date -Format "yyyyMMdd_HHmm"
$bd = "C:\Users\PCMASTER\Desktop\roxymaster_backups\snapshots"
New-Item -ItemType Directory -Force -Path $bd | Out-Null
$src = "c:\Users\PCMASTER\Desktop\roxymaster\pcmaster\scripts"
Copy-Item "$src\orchestrator.py" "$bd\orchestrator_$ts.py" -Force
Copy-Item "$src\ws_manager.py" "$bd\ws_manager_$ts.py" -Force
Copy-Item "$src\api_pedidos.py" "$bd\api_pedidos_$ts.py" -Force
Copy-Item "$src\server.py" "$bd\server_$ts.py" -Force
Write-Output "backup ok: $ts"