$ErrorActionPreference = "Stop"
$scripts = "$env:USERPROFILE\desktop\roxymaster\pcbot\scripts"

# Paso 3: Iniciar main.py en background
Write-Host "Iniciando main.py..."
$proc = Start-Process python -ArgumentList "main.py" -WorkingDirectory $scripts -NoNewWindow -PassThru
Start-Sleep 6

# Paso 4: Verificar portal
Write-Host "Verificando portal en http://127.0.0.1:8087/ ..."
try {
    $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8087/" -UseBasicParsing -TimeoutSec 10
    $short = $resp
    if ($resp.Length -gt 200) { $short = $resp.Substring(0, 200) }
    Write-Host "PORTAL RESPONSE (${0} chars): $short"
} catch {
    Write-Host "PORTAL ERROR: $($_.Exception.Message)"
}

# Paso 5: Login
Write-Host "Probando login con test@roxymaster.local..."
try {
    $body = '{"email":"test@roxymaster.local","password":"Test1234"}'
    $login = Invoke-RestMethod -Uri "http://127.0.0.1:8087/api/login" -Method POST -Body $body -ContentType "application/json" -TimeoutSec 10
    Write-Host "LOGIN OK: $login"
} catch {
    Write-Host "LOGIN ERROR: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "pcbot portal ok en http://127.0.0.1:8087. usuario test logueado. esperando conexion a pcmaster."