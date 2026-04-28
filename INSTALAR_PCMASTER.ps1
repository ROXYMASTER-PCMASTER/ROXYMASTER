# INSTALAR_PCMASTER.ps1
# Script de instalación para servidor PCMASTER
# ROXYMASTER v6.1
# Ejecución: powershell -ExecutionPolicy Bypass -File INSTALAR_PCMASTER.ps1

param(
    [string]$IP_TAILSCALE = "100.111.179.65",
    [int]$PUERTO_WS = 5006,
    [string]$IP_ESCUCHA = "0.0.0.0"
)

# ============================================================================
# VERIFICACIONES INICIALES
# ============================================================================

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  ROXYMASTER v6.1 - INSTALADOR PCMASTER" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Verificar si se ejecuta como admin
$isAdmin = [bool]([System.Security.Principal.WindowsIdentity]::GetCurrent().Groups -match "S-1-5-32-544")
if (-not $isAdmin) {
    Write-Host "[ERROR] Este script requiere privilegios de administrador" -ForegroundColor Red
    Write-Host "Por favor, ejecute: powershell -ExecutionPolicy Bypass -File INSTALAR_PCMASTER.ps1 -RunAs" -ForegroundColor Yellow
    exit 1
}

Write-Host "[OK] Permisos de administrador verificados" -ForegroundColor Green

# ============================================================================
# CREAR ESTRUCTURA DE CARPETAS
# ============================================================================

Write-Host ""
Write-Host "Creando estructura de carpetas..." -ForegroundColor Yellow

$CARPETA_BASE = "$env:USERPROFILE\Desktop\ROXYMASTER\PCMASTER"

if (-not (Test-Path $CARPETA_BASE)) {
    New-Item -ItemType Directory -Path $CARPETA_BASE -Force | Out-Null
    Write-Host "[OK] Carpeta base creada: $CARPETA_BASE" -ForegroundColor Green
}

$CARPETAS = @(
    "$CARPETA_BASE\scripts",
    "$CARPETA_BASE\logs",
    "$CARPETA_BASE\prompts",
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
    server = @{
        ip_servidor = $IP_ESCUCHA
        ws_port = $PUERTO_WS
        tailscale_ip = $IP_TAILSCALE
    }
    logging = @{
        nivel = "INFO"
        archivo = "$CARPETA_BASE\logs\server.log"
    }
    security = @{
        token_timeout = 1800
        rate_limit_capacity = 100
        rate_limit_refill = 10
    }
} | ConvertTo-Json -Depth 10

$CONFIG_JSON | Out-File -FilePath "$CARPETA_BASE\config.json" -Encoding UTF8 -Force
Write-Host "[OK] config.json creado" -ForegroundColor Green

# ============================================================================
# CREAR ARCHIVO variables_globales.py
# ============================================================================

Write-Host ""
Write-Host "Creando módulos Python..." -ForegroundColor Yellow

$VARIABLES_PY = @'
# variables_globales.py
import os
import json

BASE_DIR = os.path.join(os.environ["USERPROFILE"], "Desktop", "ROXYMASTER", "PCMASTER")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

# Versión
VERSION = "6.1"

# Cargar configuración
with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
    CONFIG = json.load(f)

# Parámetros del servidor
PUERTO = CONFIG.get("server", {}).get("ws_port", 5006)
IP_SERVIDOR = CONFIG.get("server", {}).get("ip_servidor", "0.0.0.0")
TAILSCALE_IP = CONFIG.get("server", {}).get("tailscale_ip", "100.111.179.65")

# Parámetros de seguridad
TOKEN_TIMEOUT = CONFIG.get("security", {}).get("token_timeout", 1800)
RATE_LIMIT_CAPACITY = CONFIG.get("security", {}).get("rate_limit_capacity", 100)
RATE_LIMIT_REFILL = CONFIG.get("security", {}).get("rate_limit_refill", 10)

# Rutas
LOG_DIR = os.path.join(BASE_DIR, "logs")
PROMPTS_DIR = os.path.join(BASE_DIR, "prompts")

print(f"[CONFIG] PCMASTER {VERSION} - Puerto {PUERTO}")
'@

$VARIABLES_PY | Out-File -FilePath "$CARPETA_BASE\scripts\variables_globales.py" -Encoding UTF8 -Force
Write-Host "[OK] variables_globales.py creado" -ForegroundColor Green

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
    "requests>=2.28.0",
    "jsonschema>=4.0.0",
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

# ============================================================================
# CREAR ARCHIVO MAESTRO DE PROMPTS
# ============================================================================

Write-Host ""
Write-Host "Creando prompts para IA..." -ForegroundColor Yellow

$PROMPT_MAESTRO = @'
Eres un comentarista de streams profesional y natural. 
Tu objetivo es generar comentarios cortos, naturales y variados que parezcan de un usuario real.
Los comentarios deben ser máximo 60 caracteres.
No repitas comentarios que ya has enviado.
'@

$PROMPT_MAESTRO | Out-File -FilePath "$CARPETA_BASE\prompts\maestro.txt" -Encoding UTF8 -Force
Write-Host "[OK] Prompts creados" -ForegroundColor Green

# ============================================================================
# CREAR SCRIPT DE INICIO
# ============================================================================

Write-Host ""
Write-Host "Creando scripts de control..." -ForegroundColor Yellow

$INICIO_BATCH = @"
@echo off
echo Iniciando ROXYMASTER PCMASTER v6.1...
cd /d "$CARPETA_BASE"
python scripts\server.py
pause
"@

$INICIO_BATCH | Out-File -FilePath "$CARPETA_BASE\INICIAR.bat" -Encoding ASCII -Force
Write-Host "[OK] INICIAR.bat creado" -ForegroundColor Green

# ============================================================================
# VERIFICAR PUERTOS
# ============================================================================

Write-Host ""
Write-Host "Verificando disponibilidad de puerto $PUERTO_WS..." -ForegroundColor Yellow

$PUERTO_OCUPADO = netstat -ano | Select-String ":$PUERTO_WS " | Select-String "LISTENING"
if ($PUERTO_OCUPADO) {
    Write-Host "[ADVERTENCIA] Puerto $PUERTO_WS puede estar en uso" -ForegroundColor Yellow
    Write-Host "Considere cambiar PUERTO_WS en la configuración" -ForegroundColor Yellow
} else {
    Write-Host "[OK] Puerto $PUERTO_WS disponible" -ForegroundColor Green
}

# ============================================================================
# CREAR ATAJO DE ESCRITORIO (Opcional)
# ============================================================================

Write-Host ""
Write-Host "Creando acceso directo en escritorio..." -ForegroundColor Yellow

$ESCRITORIO = [System.IO.Path]::Combine([Environment]::GetFolderPath('Desktop'))
$ACCESO_DIRECTO = "$ESCRITORIO\PCMASTER_v6.1.lnk"

try {
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortCut($ACCESO_DIRECTO)
    $Shortcut.TargetPath = "$CARPETA_BASE\INICIAR.bat"
    $Shortcut.WorkingDirectory = $CARPETA_BASE
    $Shortcut.Description = "ROXYMASTER PCMASTER v6.1"
    $Shortcut.IconLocation = "powershell.exe,0"
    $Shortcut.Save()
    Write-Host "[OK] Acceso directo creado en escritorio" -ForegroundColor Green
} catch {
    Write-Host "[ADVERTENCIA] No se pudo crear acceso directo" -ForegroundColor Yellow
}

# ============================================================================
# GENERAR BITÁCORA
# ============================================================================

Write-Host ""
Write-Host "Generando bitácora de instalación..." -ForegroundColor Yellow

$FECHA = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$BITACORA = @"
[INSTALACIÓN] PCMASTER v6.1
Fecha: $FECHA
Usuario: $env:USERNAME
Computadora: $env:COMPUTERNAME

ESTRUCTURA CREADA:
$CARPETA_BASE\scripts          - Código Python
$CARPETA_BASE\logs             - Archivos de log
$CARPETA_BASE\prompts          - Prompts para IA
$CARPETA_BASE\config           - Configuración

CONFIGURACIÓN:
IP Servidor: $IP_ESCUCHA
Puerto WebSocket: $PUERTO_WS
Tailscale IP: $IP_TAILSCALE

PRÓXIMOS PASOS:
1. Ejecutar: $CARPETA_BASE\INICIAR.bat
2. El servidor se iniciará en puerto $PUERTO_WS
3. Esperar conexiones de PCBOT clientes
4. Revisar logs en: $CARPETA_BASE\logs\server.log

COMANDOS ÚTILES:
- Ver status: netstat -ano | findstr :$PUERTO_WS
- Revisar logs: Get-Content "$CARPETA_BASE\logs\server.log" -Tail 50
"@

$BITACORA | Out-File -FilePath "$env:USERPROFILE\Desktop\BITACORA_INSTALA_PCMASTER.txt" -Encoding UTF8 -Force

Write-Host "[OK] Bitácora en: $env:USERPROFILE\Desktop\BITACORA_INSTALA_PCMASTER.txt" -ForegroundColor Green

# ============================================================================
# RESUMEN FINAL
# ============================================================================

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  INSTALACIÓN COMPLETADA" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Ubicación: $CARPETA_BASE" -ForegroundColor Cyan
Write-Host "Servidor escuchando en: $IP_ESCUCHA`:$PUERTO_WS" -ForegroundColor Cyan
Write-Host "Tailscale IP: $IP_TAILSCALE`:$PUERTO_WS" -ForegroundColor Cyan
Write-Host ""
Write-Host "Para iniciar el servidor:" -ForegroundColor Yellow
Write-Host "  1. Ejecute: $CARPETA_BASE\INICIAR.bat" -ForegroundColor Gray
Write-Host "  2. O haga doble clic en el acceso directo del escritorio" -ForegroundColor Gray
Write-Host ""
Write-Host "Para revisar logs:" -ForegroundColor Yellow
Write-Host "  Get-Content `"$CARPETA_BASE\logs\server.log`" -Tail 100 -Wait" -ForegroundColor Gray
Write-Host ""
