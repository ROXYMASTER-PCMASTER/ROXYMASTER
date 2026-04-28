# INSTALAR_PCBOT.ps1
# Script de instalación para cliente PCBOT
# ROXYMASTER v6.1
# Ejecución: powershell -ExecutionPolicy Bypass -File INSTALAR_PCBOT.ps1

param(
    [string]$IP_PCMASTER = "100.111.179.65",
    [int]$PUERTO_PCMASTER = 5006,
    [string]$ROXY_API_URL = "http://127.0.0.1:50000",
    [string]$ROXY_TOKEN = "tu_token_aqui"
)

# ============================================================================
# VERIFICACIONES INICIALES
# ============================================================================

Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "  ROXYMASTER v6.1 - INSTALADOR PCBOT" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

# Verificar si se ejecuta como admin
$isAdmin = [bool]([System.Security.Principal.WindowsIdentity]::GetCurrent().Groups -match "S-1-5-32-544")
if (-not $isAdmin) {
    Write-Host "[ERROR] Este script requiere privilegios de administrador" -ForegroundColor Red
    Write-Host "Por favor, ejecute nuevamente con permisos elevados" -ForegroundColor Yellow
    exit 1
}

Write-Host "[OK] Permisos de administrador verificados" -ForegroundColor Green

# ============================================================================
# CREAR ESTRUCTURA DE CARPETAS
# ============================================================================

Write-Host ""
Write-Host "Creando estructura de carpetas..." -ForegroundColor Yellow

$CARPETA_BASE = "$env:USERPROFILE\Desktop\ROXYMASTER\PCBOT"

if (-not (Test-Path $CARPETA_BASE)) {
    New-Item -ItemType Directory -Path $CARPETA_BASE -Force | Out-Null
    Write-Host "[OK] Carpeta base creada: $CARPETA_BASE" -ForegroundColor Green
}

$CARPETAS = @(
    "$CARPETA_BASE\scripts",
    "$CARPETA_BASE\logs",
    "$CARPETA_BASE\data",
    "$CARPETA_BASE\config"
)

foreach ($carpeta in $CARPETAS) {
    if (-not (Test-Path $carpeta)) {
        New-Item -ItemType Directory -Path $carpeta -Force | Out-Null
        Write-Host "[OK] Creada: $carpeta" -ForegroundColor Green
    }
}

# ============================================================================
# CREAR ARCHIVO config.json
# ============================================================================

Write-Host ""
Write-Host "Generando configuración..." -ForegroundColor Yellow

$CONFIG_JSON = @{
    version = "6.1"
    pcmaster_ip = $IP_PCMASTER
    pcmaster_port = $PUERTO_PCMASTER
    client_name = $env:COMPUTERNAME
    roxy_api = @{
        url = $ROXY_API_URL
        token = $ROXY_TOKEN
    }
    logging = @{
        nivel = "INFO"
        archivo = "$CARPETA_BASE\logs\pcbot.log"
    }
    network = @{
        reconexion_min = 2
        reconexion_max = 32
        timeout = 10
    }
} | ConvertTo-Json -Depth 10

$CONFIG_JSON | Out-File -FilePath "$CARPETA_BASE\config.json" -Encoding UTF8 -Force
Write-Host "[OK] config.json creado" -ForegroundColor Green

Write-Host "  IP PCMASTER: $IP_PCMASTER" -ForegroundColor Gray
Write-Host "  Puerto: $PUERTO_PCMASTER" -ForegroundColor Gray
Write-Host "  Roxy API: $ROXY_API_URL" -ForegroundColor Gray

# ============================================================================
# VERIFICAR PYTHON Y DEPENDENCIAS
# ============================================================================

Write-Host ""
Write-Host "Verificando Python..." -ForegroundColor Yellow

$PYTHON_CMD = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Python no está instalado o no está en PATH" -ForegroundColor Red
    Write-Host "Por favor, instale Python 3.9+ desde https://www.python.org" -ForegroundColor Yellow
    exit 1
}

Write-Host "[OK] Python encontrado: $PYTHON_CMD" -ForegroundColor Green

# ============================================================================
# INSTALAR DEPENDENCIAS PYTHON
# ============================================================================

Write-Host ""
Write-Host "Instalando dependencias Python..." -ForegroundColor Yellow

$DEPENDENCIAS = @(
    "websockets>=10.0",
    "playwright>=1.40.0",
    "requests>=2.28.0",
    "asyncio-contextmanager>=1.0"
)

foreach ($paquete in $DEPENDENCIAS) {
    Write-Host "  Instalando $paquete..." -ForegroundColor Gray
    python -m pip install $paquete --quiet 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "    [OK]" -ForegroundColor Green
    } else {
        Write-Host "    [ADVERTENCIA] Error instalando $paquete" -ForegroundColor Yellow
    }
}

# Instalar navegadores de Playwright
Write-Host ""
Write-Host "Instalando navegadores de Playwright (esto puede tomar tiempo)..." -ForegroundColor Yellow
python -m playwright install chromium --quiet 2>&1 | Out-Null
Write-Host "[OK] Navegadores de Playwright instalados" -ForegroundColor Green

# ============================================================================
# INSTALAR NICEGUI PARA INTERFAZ
# ============================================================================

Write-Host ""
Write-Host "Instalando NiceGUI para interfaz web..." -ForegroundColor Yellow
python -m pip install nicegui --quiet 2>&1 | Out-Null
Write-Host "[OK] NiceGUI instalado" -ForegroundColor Green

# ============================================================================
# CREAR SCRIPTS DE INICIO
# ============================================================================

Write-Host ""
Write-Host "Creando scripts de control..." -ForegroundColor Yellow

$INICIO_PCBOT = @"
@echo off
echo Iniciando ROXYMASTER PCBOT v6.1...
cd /d "$CARPETA_BASE"
python scripts\pcbot.py
pause
"@

$INICIO_PCBOT | Out-File -FilePath "$CARPETA_BASE\INICIAR.bat" -Encoding ASCII -Force
Write-Host "[OK] INICIAR.bat creado" -ForegroundColor Green

$INICIO_UI = @"
@echo off
echo Iniciando Interfaz Web ROXYMASTER v6.1...
cd /d "$CARPETA_BASE"
python scripts\ui.py
pause
"@

$INICIO_UI | Out-File -FilePath "$CARPETA_BASE\INICIAR_UI.bat" -Encoding ASCII -Force
Write-Host "[OK] INICIAR_UI.bat creado" -ForegroundColor Green

# ============================================================================
# VERIFICAR CONECTIVIDAD
# ============================================================================

Write-Host ""
Write-Host "Verificando conectividad a PCMASTER..." -ForegroundColor Yellow

try {
    $TEST_CONEXION = Test-NetConnection -ComputerName $IP_PCMASTER -Port $PUERTO_PCMASTER -WarningAction SilentlyContinue
    if ($TEST_CONEXION.TcpTestSucceeded) {
        Write-Host "[OK] Conexión a $IP_PCMASTER`:$PUERTO_PCMASTER exitosa" -ForegroundColor Green
    } else {
        Write-Host "[ADVERTENCIA] No se puede conectar a $IP_PCMASTER`:$PUERTO_PCMASTER" -ForegroundColor Yellow
        Write-Host "Asegúrese de que PCMASTER esté en ejecución" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[ADVERTENCIA] No se pudo verificar conectividad: $($_.Exception.Message)" -ForegroundColor Yellow
}

# ============================================================================
# CREAR ATAJO DE ESCRITORIO
# ============================================================================

Write-Host ""
Write-Host "Creando accesos directos en escritorio..." -ForegroundColor Yellow

$ESCRITORIO = [System.IO.Path]::Combine([Environment]::GetFolderPath('Desktop'))

try {
    $WshShell = New-Object -ComObject WScript.Shell
    
    # Acceso para PCBOT
    $Shortcut_PCBOT = $WshShell.CreateShortCut("$ESCRITORIO\PCBOT_v6.1.lnk")
    $Shortcut_PCBOT.TargetPath = "$CARPETA_BASE\INICIAR.bat"
    $Shortcut_PCBOT.WorkingDirectory = $CARPETA_BASE
    $Shortcut_PCBOT.Description = "ROXYMASTER PCBOT v6.1"
    $Shortcut_PCBOT.IconLocation = "powershell.exe,0"
    $Shortcut_PCBOT.Save()
    Write-Host "[OK] Acceso directo PCBOT creado" -ForegroundColor Green
    
    # Acceso para UI
    $Shortcut_UI = $WshShell.CreateShortCut("$ESCRITORIO\ROXYMASTER_UI_v6.1.lnk")
    $Shortcut_UI.TargetPath = "$CARPETA_BASE\INICIAR_UI.bat"
    $Shortcut_UI.WorkingDirectory = $CARPETA_BASE
    $Shortcut_UI.Description = "ROXYMASTER Interfaz Web v6.1"
    $Shortcut_UI.IconLocation = "powershell.exe,0"
    $Shortcut_UI.Save()
    Write-Host "[OK] Acceso directo UI creado" -ForegroundColor Green
} catch {
    Write-Host "[ADVERTENCIA] No se pudieron crear accesos directos" -ForegroundColor Yellow
}

# ============================================================================
# GENERAR BITÁCORA
# ============================================================================

Write-Host ""
Write-Host "Generando bitácora de instalación..." -ForegroundColor Yellow

$FECHA = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$BITACORA = @"
[INSTALACIÓN] PCBOT v6.1
Fecha: $FECHA
Usuario: $env:USERNAME
Computadora: $env:COMPUTERNAME

ESTRUCTURA CREADA:
$CARPETA_BASE\scripts          - Código Python
$CARPETA_BASE\logs             - Archivos de log
$CARPETA_BASE\data             - Datos persistentes
$CARPETA_BASE\config           - Configuración

CONFIGURACIÓN DE CONEXIÓN:
PCMASTER IP: $IP_PCMASTER
Puerto WebSocket: $PUERTO_PCMASTER
Roxy API: $ROXY_API_URL

INTERFAZ WEB:
URL: http://localhost:8090
Puerto: 8090

PRÓXIMOS PASOS:

1. INICIAR PCBOT (Cliente):
   Ejecutar: $CARPETA_BASE\INICIAR.bat
   
2. INICIAR INTERFAZ WEB (Opcional):
   Ejecutar: $CARPETA_BASE\INICIAR_UI.bat
   Acceder a: http://localhost:8090

3. VERIFICAR CONEXIÓN:
   Revisar logs: Get-Content "$CARPETA_BASE\logs\pcbot.log" -Tail 50

COMANDOS ÚTILES:
- Ver procesos Python: Get-Process python
- Revisar logs en tiempo real: Get-Content "$CARPETA_BASE\logs\pcbot.log" -Tail 20 -Wait
- Matar proceso: Stop-Process -Name python -Force

TROUBLESHOOTING:
- Si no se conecta, verificar que PCMASTER esté ejecutándose
- Revisar firewall y puerto $PUERTO_PCMASTER abierto
- Verificar configuración de Roxy API en config.json

INFORMACIÓN:
Versión: 6.1
Última actualización: $FECHA
Soporte: https://github.com/ROXYMASTER/v6
"@

$BITACORA | Out-File -FilePath "$env:USERPROFILE\Desktop\BITACORA_INSTALA_PCBOT.txt" -Encoding UTF8 -Force

Write-Host "[OK] Bitácora en: $env:USERPROFILE\Desktop\BITACORA_INSTALA_PCBOT.txt" -ForegroundColor Green

# ============================================================================
# RESUMEN FINAL
# ============================================================================

Write-Host ""
Write-Host "=====================================" -ForegroundColor Green
Write-Host "  INSTALACIÓN COMPLETADA" -ForegroundColor Green
Write-Host "=====================================" -ForegroundColor Green
Write-Host ""
Write-Host "Ubicación: $CARPETA_BASE" -ForegroundColor Cyan
Write-Host "Computadora: $env:COMPUTERNAME" -ForegroundColor Cyan
Write-Host "Conexión a: $IP_PCMASTER`:$PUERTO_PCMASTER" -ForegroundColor Cyan
Write-Host ""
Write-Host "PRÓXIMOS PASOS:" -ForegroundColor Yellow
Write-Host ""
Write-Host "1. Iniciar PCBOT:" -ForegroundColor Gray
Write-Host "   Ejecute: $CARPETA_BASE\INICIAR.bat" -ForegroundColor Gray
Write-Host ""
Write-Host "2. (Opcional) Iniciar Interfaz Web:" -ForegroundColor Gray
Write-Host "   Ejecute: $CARPETA_BASE\INICIAR_UI.bat" -ForegroundColor Gray
Write-Host "   Acceda a: http://localhost:8090" -ForegroundColor Gray
Write-Host ""
Write-Host "3. Verificar conexión:" -ForegroundColor Gray
Write-Host "   Get-Content `"$CARPETA_BASE\logs\pcbot.log`" -Tail 50 -Wait" -ForegroundColor Gray
Write-Host ""
Write-Host "Se han creado accesos directos en el escritorio" -ForegroundColor Green
Write-Host ""
