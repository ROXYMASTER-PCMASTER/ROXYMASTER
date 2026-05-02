# ============================================================================
# ROXYMASTER v6.1 - INSTALADOR PCBOT (CLIENTE BOT)
# Ejecutar en CADA maquina PCBOT
# Ruta: C:\Users\<USUARIO>\Desktop\ROXYMASTER\PCBOT\INSTALAR_PCBOT.ps1
# ============================================================================
#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "ROXYMASTER v6.1 - PCBOT CLIENT"

# ============================================================================
# VARIABLES GLOBALES (modificables manualmente)
# ============================================================================
$script:VERSION = "6.1"
$script:MUTEX_NAME = "Global\ROXYMASTER_PCBOT"
$script:PCMASTER_WS_PORT = 5006

# ============================================================================
# FUNCION: Escribir logs con timestamp
# ============================================================================
function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "$timestamp [$Level] $Message"
    Write-Host $line
    try {
        Add-Content -Path "$script:LOG_FILE" -Value $line -ErrorAction SilentlyContinue
    } catch {}
}

# ============================================================================
# FUNCION: Verificar si ya hay una instancia corriendo (MUTEX)
# ============================================================================
function Test-Mutex {
    try {
        $mutex = New-Object System.Threading.Mutex($false, $script:MUTEX_NAME)
        if (-not $mutex.WaitOne(0)) {
            Write-Log "ERROR: PCBOT ya esta corriendo. Cerrando..." "ERROR"
            Write-Host ""
            Write-Host "========================================" -ForegroundColor Red
            Write-Host "  PCBOT YA ESTA EN EJECUCION" -ForegroundColor Red
            Write-Host "  No se puede abrir una segunda instancia." -ForegroundColor Red
            Write-Host "========================================" -ForegroundColor Red
            exit 1
        }
        return $mutex
    } catch {
        Write-Log "ADVERTENCIA: No se pudo crear mutex, continuando..." "WARN"
        return $null
    }
}

# ============================================================================
# FUNCION: Detectar Python y pip
# ============================================================================
function Test-Python {
    try {
        $pyVer = & python --version 2>&1
        if ($LASTEXITCODE -ne 0) { throw "Python no encontrado" }
        Write-Log "Python detectado: $pyVer"
        
        $pipVer = & pip --version 2>&1
        if ($LASTEXITCODE -ne 0) { throw "pip no encontrado" }
        Write-Log "pip detectado: $pipVer"
        
        return $true
    } catch {
        Write-Log "ERROR: Python/pip no encontrado. Instale Python 3.10+ desde https://python.org" "ERROR"
        return $false
    }
}

# ============================================================================
# FUNCION: Detectar informacion del sistema
# ============================================================================
function Get-SystemInfo {
    Write-Log "Recopilando informacion del sistema..."
    
    # Nombre PC
    $script:NOMBRE_PC = $env:COMPUTERNAME
    Write-Log "Nombre PC: $script:NOMBRE_PC"
    
    # Usuario
    $script:USUARIO = $env:USERNAME
    Write-Log "Usuario: $script:USUARIO"
    
    # IP Local
    try {
        $ipLocal = (Get-NetIPAddress -AddressFamily IPv4 -PrefixOrigin Manual,Dhcp | 
                    Where-Object { $_.IPAddress -notlike "127.*" } | 
                    Select-Object -First 1).IPAddress
        if ($ipLocal) {
            $script:IP_LOCAL = $ipLocal
        } else {
            $script:IP_LOCAL = "127.0.0.1"
        }
        Write-Log "IP Local detectada: $script:IP_LOCAL"
    } catch {
        $script:IP_LOCAL = "127.0.0.1"
        Write-Log "IP Local por defecto: $script:IP_LOCAL" "WARN"
    }
    
    # Tailscale IP
    try {
        $tsIP = & tailscale ip -4 2>&1
        if ($LASTEXITCODE -eq 0 -and $tsIP -match '\d+\.\d+\.\d+\.\d+') {
            $script:IP_TAILSCALE = $tsIP.Trim()
            Write-Log "Tailscale IP detectada: $script:IP_TAILSCALE"
        } else {
            $script:IP_TAILSCALE = "NO_DETECTADO"
            Write-Log "Tailscale no detectado." "WARN"
        }
    } catch {
        $script:IP_TAILSCALE = "NO_DETECTADO"
        Write-Log "Tailscale no detectado." "WARN"
    }
    
    # ID unico del PCBOT
    $script:CLIENT_ID = "$script:NOMBRE_PC-$script:USUARIO"
    Write-Log "Client ID: $script:CLIENT_ID"
}

# ============================================================================
# FUNCION: Detectar aplicaciones de perfiles (RoxyBrowser, Multilogin, etc.)
# ============================================================================
function Get-ProfileApps {
    Write-Log "Detectando aplicaciones de gestion de perfiles..."
    
    $apps = @{}
    
    # Rutas comunes de RoxyBrowser
    $roxyPaths = @(
        "$env:ProgramFiles\RoxyBrowser\roxybrowser.exe",
        "${env:ProgramFiles(x86)}\RoxyBrowser\roxybrowser.exe",
        "$env:LOCALAPPDATA\RoxyBrowser\roxybrowser.exe",
        "$env:USERPROFILE\AppData\Local\RoxyBrowser\roxybrowser.exe"
    )
    foreach ($p in $roxyPaths) {
        if (Test-Path $p) { $apps["RoxyBrowser"] = $p; break }
    }
    
    # Multilogin
    $mlPaths = @(
        "$env:ProgramFiles\Multilogin\multilogin.exe",
        "${env:ProgramFiles(x86)}\Multilogin\multilogin.exe"
    )
    foreach ($p in $mlPaths) {
        if (Test-Path $p) { $apps["Multilogin"] = $p; break }
    }
    
    # GoLogin
    $glPaths = @(
        "$env:ProgramFiles\GoLogin\gologin.exe",
        "${env:ProgramFiles(x86)}\GoLogin\gologin.exe"
    )
    foreach ($p in $glPaths) {
        if (Test-Path $p) { $apps["GoLogin"] = $p; break }
    }
    
    # Adspower
    $adPaths = @(
        "$env:ProgramFiles\Adspower\adspower.exe",
        "${env:ProgramFiles(x86)}\Adspower\adspower.exe"
    )
    foreach ($p in $adPaths) {
        if (Test-Path $p) { $apps["Adspower"] = $p; break }
    }
    
    if ($apps.Count -gt 0) {
        Write-Log "Aplicaciones detectadas: $($apps.Keys -join ', ')"
        foreach ($key in $apps.Keys) {
            Write-Host "  [DETECTADO] $key -> $($apps[$key])" -ForegroundColor Green
        }
    } else {
        Write-Log "Sin aplicaciones de perfiles detectadas"
        Write-Host "  [SIN APPS] No se detectaron aplicaciones de gestion de perfiles." -ForegroundColor Yellow
    }
    
    return $apps
}

# ============================================================================
# FUNCION: Detectar navegadores disponibles
# ============================================================================
function Get-Browsers {
    Write-Log "Detectando navegadores disponibles..."
    
    $browsers = @()
    
    # Chrome
    $chromePaths = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    foreach ($p in $chromePaths) {
        if (Test-Path $p) { $browsers += @{nombre="Chrome"; ruta=$p; user_data="$env:LOCALAPPDATA\Google\Chrome\User Data"}; break }
    }
    
    # Edge
    $edgePaths = @(
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe"
    )
    foreach ($p in $edgePaths) {
        if (Test-Path $p) { $browsers += @{nombre="Edge"; ruta=$p; user_data="$env:LOCALAPPDATA\Microsoft\Edge\User Data"}; break }
    }
    
    # Brave
    $bravePaths = @(
        "$env:ProgramFiles\BraveSoftware\Brave-Browser\Application\brave.exe",
        "${env:ProgramFiles(x86)}\BraveSoftware\Brave-Browser\Application\brave.exe",
        "$env:LOCALAPPDATA\BraveSoftware\Brave-Browser\Application\brave.exe"
    )
    foreach ($p in $bravePaths) {
        if (Test-Path $p) { $browsers += @{nombre="Brave"; ruta=$p; user_data="$env:LOCALAPPDATA\BraveSoftware\Brave-Browser\User Data"}; break }
    }
    
    # Firefox
    $ffPaths = @(
        "$env:ProgramFiles\Mozilla Firefox\firefox.exe",
        "${env:ProgramFiles(x86)}\Mozilla Firefox\firefox.exe"
    )
    foreach ($p in $ffPaths) {
        if (Test-Path $p) { $browsers += @{nombre="Firefox"; ruta=$p; user_data="$env:APPDATA\Mozilla\Firefox\Profiles"}; break }
    }
    
    # Opera
    $operaPaths = @(
        "$env:ProgramFiles\Opera\opera.exe",
        "${env:ProgramFiles(x86)}\Opera\opera.exe",
        "$env:LOCALAPPDATA\Programs\Opera\opera.exe"
    )
    foreach ($p in $operaPaths) {
        if (Test-Path $p) { $browsers += @{nombre="Opera"; ruta=$p; user_data="$env:APPDATA\Opera Software\Opera Stable"}; break }
    }
    
    # Vivaldi
    $vivaldiPaths = @(
        "$env:ProgramFiles\Vivaldi\Application\vivaldi.exe",
        "${env:ProgramFiles(x86)}\Vivaldi\Application\vivaldi.exe",
        "$env:LOCALAPPDATA\Vivaldi\Application\vivaldi.exe"
    )
    foreach ($p in $vivaldiPaths) {
        if (Test-Path $p) { $browsers += @{nombre="Vivaldi"; ruta=$p; user_data="$env:LOCALAPPDATA\Vivaldi\User Data"}; break }
    }
    
    Write-Log "Navegadores detectados: $($browsers.Count)"
    foreach ($b in $browsers) {
        Write-Host "  [NAVEGADOR] $($b.nombre) -> $($b.ruta)" -ForegroundColor Cyan
    }
    
    return $browsers
}

# ============================================================================
# FUNCION: Generar config.json para PCBOT
# ============================================================================
function New-ConfigJSON {
    $configPath = Join-Path $script:BASE_DIR "config.json"
    
    $config = @{
        pcbot = @{
            nombre_pc = $script:NOMBRE_PC
            usuario = $script:USUARIO
            ip_local = $script:IP_LOCAL
            ip_tailscale = $script:IP_TAILSCALE
            client_id = $script:CLIENT_ID
        }
        pcmaster = @{
            ip = $script:PCMASTER_IP
            ws_port = $script:PCMASTER_WS_PORT
        }
        version = $script:VERSION
        seguridad = @{
            protocolo = "SHS"
            version = "1.0"
        }
    }
    
    $config | ConvertTo-Json -Depth 4 | Set-Content -Path $configPath -Encoding UTF8
    Write-Log "config.json creado/actualizado"
    Write-Host "  config.json actualizado con informacion del sistema" -ForegroundColor Green
}

# ============================================================================
# FUNCION: Instalar dependencias Python
# ============================================================================
function Install-Dependencies {
    Write-Log "Instalando dependencias Python..."
    
    $packages = @("websockets", "requests", "psutil")
    
    foreach ($pkg in $packages) {
        try {
            $installed = & pip show $pkg 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Log "  $pkg ya instalado"
            } else {
                Write-Log "  Instalando $pkg..."
                & pip install $pkg -q 2>&1 | Out-Null
                if ($LASTEXITCODE -eq 0) {
                    Write-Log "  $pkg instalado correctamente"
                } else {
                    Write-Log "  ERROR instalando $pkg" "ERROR"
                }
            }
        } catch {
            Write-Log "  ERROR con $pkg : $_" "ERROR"
        }
    }
    
    # playwright (opcional, para automatizar navegadores)
    try {
        $pw = & pip show playwright 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Log "  playwright ya instalado"
        } else {
            Write-Log "  playwright no instalado (opcional para navegadores automaticos)"
        }
    } catch {}
}

# ============================================================================
# FUNCION: Panel de estado y recomendaciones
# ============================================================================
function Show-Panel {
    param($ProfileApps, $Browsers)
    
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  ROXYMASTER v$script:VERSION - PCBOT" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  PC: $script:NOMBRE_PC" -ForegroundColor White
    Write-Host "  Usuario: $script:USUARIO" -ForegroundColor White
    Write-Host "  IP Local: $script:IP_LOCAL" -ForegroundColor White
    Write-Host "  IP Tailscale: $script:IP_TAILSCALE" -ForegroundColor White
    Write-Host "  Client ID: $script:CLIENT_ID" -ForegroundColor White
    Write-Host "----------------------------------------" -ForegroundColor DarkGray
    Write-Host "  PCMASTER Target: $script:PCMASTER_IP`:$script:PCMASTER_WS_PORT" -ForegroundColor White
    Write-Host "----------------------------------------" -ForegroundColor DarkGray
    
    if ($ProfileApps.Count -gt 0) {
        Write-Host "  [APPS DE PERFILES DETECTADAS]" -ForegroundColor Green
        foreach ($key in $ProfileApps.Keys) {
            Write-Host "    $key" -ForegroundColor Gray
        }
        Write-Host ""
        Write-Host "  >> Los perfiles deben crearse MANUALMENTE en la aplicacion" -ForegroundColor Yellow
        Write-Host "  >> Configurar huellas digitales y proxies manualmente" -ForegroundColor Yellow
        Write-Host "  >> Luego iniciar los perfiles para que PCBOT los detecte" -ForegroundColor Yellow
    } else {
        Write-Host "  [MODO NAVEGADORES - SIN APPS]" -ForegroundColor Yellow
        Write-Host "  Navegadores detectados: $($Browsers.Count)" -ForegroundColor Gray
        Write-Host ""
        Write-Host "  >> PCBOT creara 10 perfiles usando los navegadores disponibles" -ForegroundColor Cyan
        Write-Host "  >> Numero maximo de perfiles: 10" -ForegroundColor Cyan
        Write-Host "  >> Se usaran perfiles Chrome para diversificar huella" -ForegroundColor Cyan
    }
    
    Write-Host "----------------------------------------" -ForegroundColor DarkGray
    Write-Host "  PCMASTER: $script:PCMASTER_IP" -ForegroundColor Yellow
    Write-Host "  Puerto: $script:PCMASTER_WS_PORT" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Cyan
}

# ============================================================================
# FUNCION: Lanzar PCBOT Python
# ============================================================================
function Start-PCBOT {
    $scriptsDir = Join-Path $script:BASE_DIR "scripts"
    $pcbotScript = Join-Path $scriptsDir "pcbot.py"
    
    if (-not (Test-Path $pcbotScript)) {
        Write-Log "ERROR: No se encontro $pcbotScript" "ERROR"
        return $false
    }
    
    Write-Log "========================================"
    Write-Log "  INICIANDO PCBOT CLIENT"
    Write-Log "  Conectando a PCMASTER: $script:PCMASTER_IP`:$script:PCMASTER_WS_PORT"
    Write-Log "  Client ID: $script:CLIENT_ID"
    Write-Log "========================================"
    
    $env:ROXYMASTER_BASE = $script:BASE_DIR
    
    try {
        Set-Location $scriptsDir
        $process = Start-Process -FilePath "python" -ArgumentList $pcbotScript -NoNewWindow -PassThru
        Write-Log "PCBOT Python iniciado (PID: $($process.Id))"
        return $process
    } catch {
        Write-Log "ERROR al iniciar PCBOT: $_" "ERROR"
        return $null
    }
}

# ============================================================================
# MAIN
# ============================================================================
function Main {
    Clear-Host
    
    # Banner
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  ROXYMASTER v$script:VERSION" -ForegroundColor Cyan
    Write-Host "  INSTALADOR PCBOT (CLIENTE BOT)" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    
    # 1. Determinar ruta base (dinamica, detecta el usuario actual)
    $script:BASE_DIR = Join-Path $env:USERPROFILE "Desktop\ROXYMASTER\PCBOT"
    
    if (-not (Test-Path $script:BASE_DIR)) {
        Write-Host "ERROR: No se encuentra la carpeta:" -ForegroundColor Red
        Write-Host "  $script:BASE_DIR" -ForegroundColor Red
        Write-Host "Cree la carpeta manualmente y coloque los archivos necesarios." -ForegroundColor Red
        exit 1
    }
    
    $script:LOG_FILE = Join-Path $script:BASE_DIR "pcbot_install.log"
    Write-Log "Iniciando instalador PCBOT v$script:VERSION"
    Write-Log "Ruta base: $script:BASE_DIR"
    
    # 2. Mutex anti-duplicado
    $mutex = Test-Mutex
    if ($null -eq $mutex) { }
    
    # 3. Detectar Python
    if (-not (Test-Python)) { exit 1 }
    
    # 4. Recopilar info del sistema
    Get-SystemInfo
    
    # 5. Leer IP del PCMASTER desde config.json si existe
    $configPath = Join-Path $script:BASE_DIR "config.json"
    if (Test-Path $configPath) {
        try {
            $existingConfig = Get-Content $configPath -Raw | ConvertFrom-Json
            if ($existingConfig.pcmaster -and $existingConfig.pcmaster.ip) {
                $script:PCMASTER_IP = $existingConfig.pcmaster.ip
            }
        } catch {}
    }
    if (-not $script:PCMASTER_IP) {
        $script:PCMASTER_IP = "100.111.179.65"  # IP Tailscale de PCMASTER por defecto
    }
    Write-Log "PCMASTER target: $script:PCMASTER_IP`:$script:PCMASTER_WS_PORT"
    
    # 6. Detectar apps de perfiles y navegadores
    $profileApps = Get-ProfileApps
    $browsers = Get-Browsers
    
    # 7. Generar/actualizar config.json
    New-ConfigJSON
    
    # 8. Instalar dependencias
    Install-Dependencies
    
    # 9. Verificar archivos Python
    $scriptsDir = Join-Path $script:BASE_DIR "scripts"
    if (-not (Test-Path (Join-Path $scriptsDir "pcbot.py"))) {
        Write-Host ""
        Write-Host "========================================" -ForegroundColor Red
        Write-Host "  FALTA pcbot.py" -ForegroundColor Red
        Write-Host "  Coloque pcbot.py y shs.py en:" -ForegroundColor Red
        Write-Host "  $scriptsDir" -ForegroundColor Red
        Write-Host "========================================" -ForegroundColor Red
        exit 1
    }
    
    # 10. Panel de estado
    Show-Panel -ProfileApps $profileApps -Browsers $browsers
    
    # 11. Lanzar PCBOT
    Write-Host ""
    Write-Host "Iniciando cliente PCBOT..." -ForegroundColor Yellow
    $process = Start-PCBOT
    
    if ($process) {
        Write-Host ""
        Write-Host "PCBOT iniciado correctamente." -ForegroundColor Green
        Write-Host "Conectado a PCMASTER: $script:PCMASTER_IP`:$script:PCMASTER_WS_PORT" -ForegroundColor White
        Write-Host "Presione Ctrl+C para detener." -ForegroundColor Gray
        
        try {
            $process.WaitForExit()
        } catch {
            Write-Log "PCBOT detenido por el usuario"
        }
    }
    
    Write-Log "Instalador PCBOT finalizado"
}

# Ejecutar
Main