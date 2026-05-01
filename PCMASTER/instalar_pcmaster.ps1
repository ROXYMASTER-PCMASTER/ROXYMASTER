# ============================================================================
# ROXYMASTER v6.1 - INSTALADOR PCMASTER (SERVIDOR)
# Ejecutar PRIMERO en la maquina PCMASTER
# Ruta: C:\Users\PCMASTER\Desktop\ROXYMASTER\PCMASTER\INSTALAR_PCMASTER.ps1
# ============================================================================
#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "ROXYMASTER v6.1 - PCMASTER SERVER"

# ============================================================================
# VARIABLES GLOBALES (modificables manualmente)
# ============================================================================
$script:WS_PORT = 5006
$script:HTTP_DASHBOARD_PORT = 8086
$script:TCP_ADMIN_PORT = 5007
$script:TAILSCALE_IP = "100.111.179.65"
$script:IP_LOCAL = "192.168.1.17"
$script:VERSION = "6.1"
$script:MUTEX_NAME = "Global\ROXYMASTER_PCMASTER"

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
            Write-Log "ERROR: PCMASTER ya esta corriendo. Cerrando..." "ERROR"
            Write-Host ""
            Write-Host "========================================" -ForegroundColor Red
            Write-Host "  PCMASTER YA ESTA EN EJECUCION" -ForegroundColor Red
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
# FUNCION: Detectar IPs automaticamente
# ============================================================================
function Get-NetworkInfo {
    Write-Log "Detectando informacion de red..."
    
    # IP Local
    try {
        $ipLocal = (Get-NetIPAddress -AddressFamily IPv4 -PrefixOrigin Manual,Dhcp | 
                    Where-Object { $_.IPAddress -notlike "127.*" } | 
                    Select-Object -First 1).IPAddress
        if ($ipLocal) {
            $script:IP_LOCAL = $ipLocal
            Write-Log "IP Local detectada: $ipLocal"
        }
    } catch {
        Write-Log "Usando IP Local por defecto: $script:IP_LOCAL" "WARN"
    }
    
    # Tailscale IP
    try {
        $tsIP = & tailscale ip -4 2>&1
        if ($LASTEXITCODE -eq 0 -and $tsIP -match '\d+\.\d+\.\d+\.\d+') {
            $script:TAILSCALE_IP = $tsIP.Trim()
            Write-Log "Tailscale IP detectada: $script:TAILSCALE_IP"
        } else {
            Write-Log "Tailscale no detectado. Usando IP por defecto: $script:TAILSCALE_IP" "WARN"
        }
    } catch {
        Write-Log "Tailscale no detectado. Usando IP por defecto: $script:TAILSCALE_IP" "WARN"
    }
}

# ============================================================================
# FUNCION: Verificar requisitos (Ollama, Whisper)
# ============================================================================
function Test-Requisitos {
    $allOk = $true
    
    # Ollama
    try {
        $ollama = & ollama --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Log "Ollama detectado: $ollama"
        } else {
            Write-Log "ADVERTENCIA: Ollama no detectado. Instalelo desde https://ollama.com" "WARN"
            $allOk = $false
        }
    } catch {
        Write-Log "ADVERTENCIA: Ollama no detectado" "WARN"
        $allOk = $false
    }
    
    # Whisper
    try {
        $whisper = & pip show openai-whisper 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Log "Whisper detectado"
        } else {
            Write-Log "ADVERTENCIA: Whisper no instalado. Ejecute: pip install openai-whisper" "WARN"
            $allOk = $false
        }
    } catch {
        Write-Log "ADVERTENCIA: Whisper no detectado" "WARN"
        $allOk = $false
    }
    
    return $allOk
}

# ============================================================================
# FUNCION: Instalar dependencias Python
# ============================================================================
function Install-Dependencies {
    Write-Log "Instalando dependencias Python..."
    
    $packages = @("websockets", "jsonschema", "requests")
    
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
}

# ============================================================================
# FUNCION: Crear estructura de archivos inicial
# ============================================================================
function Initialize-DataFiles {
    Write-Log "Inicializando archivos de datos..."
    
    # config.json con puerto_http incluido
    $configPath = Join-Path $script:BASE_DIR "config.json"
    $config = @{
        server = @{
            ip_servidor = $script:IP_LOCAL
            ip_tailscale = $script:TAILSCALE_IP
            ws_port = $script:WS_PORT
            puerto_http = $script:HTTP_DASHBOARD_PORT
        }
        version = $script:VERSION
    }
    
    if (-not (Test-Path $configPath)) {
        $config | ConvertTo-Json -Depth 4 | Set-Content -Path $configPath -Encoding UTF8
        Write-Log "config.json creado"
    } else {
        Write-Log "config.json existente (se conserva)"
    }
    
    # Carpeta prompts
    $promptsDir = Join-Path $script:BASE_DIR "prompts"
    if (-not (Test-Path $promptsDir)) {
        New-Item -ItemType Directory -Path $promptsDir -Force | Out-Null
    }
    
    # prompt_maestro.txt
    $maestroPath = Join-Path $promptsDir "prompt_maestro.txt"
    if (-not (Test-Path $maestroPath)) {
        $plantilla = @"
# PROMPT MAESTRO - JARVIS ROXYMASTER v6.1
# Escribe aqui la personalidad base del JARVIS.
# Este prompt es la semilla de conciencia que evolucionara con el tiempo.
# El sistema leera, escuchara y mirara lives para generar contexto.

Eres un comentarista profesional en streams. 
Tu personalidad es: natural, humana, con errores ortograficos ocasionales.
Debes ser indetectable como bot.
Aprendes de lo que lees, escuchas y miras en cada stream.
Generas comentarios unicos segun el contexto de cada URL.
"@
        Set-Content -Path $maestroPath -Value $plantilla -Encoding UTF8
        Write-Log "prompt_maestro.txt creado (EDITALO con tu personalidad)"
    }
    
    # prompt_comentarista.txt (vacio, se autogenera)
    $comentaPath = Join-Path $promptsDir "prompt_comentarista.txt"
    if (-not (Test-Path $comentaPath)) {
        Set-Content -Path $comentaPath -Value "# Autogenerado por JARVIS" -Encoding UTF8
        Write-Log "prompt_comentarista.txt creado"
    }
    
    # Carpeta data
    $dataDir = Join-Path $script:BASE_DIR "data"
    if (-not (Test-Path $dataDir)) {
        New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
    }
    
    # tokens.json
    $tokensPath = Join-Path $dataDir "tokens.json"
    if (-not (Test-Path $tokensPath)) {
        @{
            tokens_generados = 150000
            tokens_comprados = 0
            tasa_quema_por_hora = 1
            historial = @()
        } | ConvertTo-Json -Depth 4 | Set-Content -Path $tokensPath -Encoding UTF8
        Write-Log "tokens.json creado (150,000 tokens iniciales)"
    }
    
    # pcbots_db.json
    $dbPath = Join-Path $dataDir "pcbots_db.json"
    if (-not (Test-Path $dbPath)) {
        @{ pcbots = @{} } | ConvertTo-Json -Depth 4 | Set-Content -Path $dbPath -Encoding UTF8
        Write-Log "pcbots_db.json creado"
    }
    
    # memoria_ia.json
    $memPath = Join-Path $dataDir "memoria_ia.json"
    if (-not (Test-Path $memPath)) {
        @{ contextos = @{} } | ConvertTo-Json -Depth 4 | Set-Content -Path $memPath -Encoding UTF8
        Write-Log "memoria_ia.json creado"
    }
    
    # Carpeta logs
    $logsDir = Join-Path $script:BASE_DIR "logs"
    if (-not (Test-Path $logsDir)) {
        New-Item -ItemType Directory -Path $logsDir -Force | Out-Null
    }
}

# ============================================================================
# FUNCION: Verificar archivos Python necesarios
# ============================================================================
function Test-PythonFiles {
    $scriptsDir = Join-Path $script:BASE_DIR "scripts"
    
    if (-not (Test-Path $scriptsDir)) {
        New-Item -ItemType Directory -Path $scriptsDir -Force | Out-Null
        Write-Log "Carpeta scripts creada"
    }
    
    $required = @("server_corregido.py", "variables_globales.py", "shs.py")
    $missing = @()
    
    foreach ($file in $required) {
        $path = Join-Path $scriptsDir $file
        if (-not (Test-Path $path)) {
            $missing += $file
        }
    }
    
    if ($missing.Count -gt 0) {
        Write-Log "ADVERTENCIA: Faltan archivos: $($missing -join ', ')" "WARN"
        Write-Log "Asegurese de que los archivos Python existan en: $scriptsDir" "WARN"
        return $false
    }
    
    Write-Log "Archivos Python verificados"
    return $true
}

# ============================================================================
# FUNCION: Lanzar servidor Python
# ============================================================================
function Start-Server {
    $scriptsDir = Join-Path $script:BASE_DIR "scripts"
    $serverScript = Join-Path $scriptsDir "server_corregido.py"
    
    if (-not (Test-Path $serverScript)) {
        Write-Log "ERROR: No se encontro $serverScript" "ERROR"
        return $false
    }
    
    Write-Log "========================================"
    Write-Log "  INICIANDO PCMASTER SERVIDOR"
    Write-Log "  IP: $script:IP_LOCAL`:$script:WS_PORT"
    Write-Log "  Tailscale: $script:TAILSCALE_IP"
    Write-Log "  Dashboard HTTP: http://localhost:$script:HTTP_DASHBOARD_PORT/dashboard"
    Write-Log "  Admin TCP: $script:IP_LOCAL`:$script:TCP_ADMIN_PORT"
    Write-Log "  Version: $script:VERSION"
    Write-Log "========================================"
    
    # Ejecutar servidor Python con environment variables
    $env:ROXYMASTER_BASE = $script:BASE_DIR
    $env:ROXYMASTER_PORT = $script:WS_PORT
    
    try {
        Set-Location $scriptsDir
        $process = Start-Process -FilePath "python" -ArgumentList $serverScript -NoNewWindow -PassThru
        Write-Log "Servidor Python iniciado (PID: $($process.Id))"
        return $process
    } catch {
        Write-Log "ERROR al iniciar servidor: $_" "ERROR"
        return $null
    }
}

# ============================================================================
# FUNCION: Abrir Chrome automaticamente con sesion guardada
# ============================================================================
function Open-BrowserDashboard {
    param([int]$DelaySeconds = 8)
    
    Write-Log "Preparando apertura del navegador en $DelaySeconds segundos..."
    Write-Host ""
    Write-Host "  Abriendo Chrome en $DelaySeconds segundos..." -ForegroundColor Yellow
    
    Start-Sleep -Seconds $DelaySeconds
    
    $dashboardUrl = "http://localhost:$script:HTTP_DASHBOARD_PORT/dashboard"
    $chromePaths = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    
    $chromeExe = $null
    foreach ($path in $chromePaths) {
        if (Test-Path $path) { $chromeExe = $path; break }
    }
    
    if ($chromeExe) {
        Write-Log "Chrome detectado en: $chromeExe"
        Write-Log "Abriendo dashboard: $dashboardUrl"
        Write-Host "  Dashboard PCMASTER: $dashboardUrl" -ForegroundColor Green
        
        $chromeArgs = @(
            "--new-window",
            "--user-data-dir=`"$script:BASE_DIR\chrome_profile`"",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            $dashboardUrl
        )
        
        try {
            Start-Sleep -Seconds 5  # Esperar que el servidor publique /dashboard
            Start-Process -FilePath $chromeExe -ArgumentList $chromeArgs
            Write-Log "Chrome abierto con perfil persistente en: $script:BASE_DIR\chrome_profile"
            Write-Host "  Perfil Chrome guardado en: $script:BASE_DIR\chrome_profile" -ForegroundColor Cyan
            Write-Host "  La sesion se mantendra. Cierre sesion manualmente en Kick/TikTok." -ForegroundColor Yellow
        } catch {
            Write-Log "ERROR al abrir Chrome: $_" "ERROR"
            Write-Host "  Intente abrir manualmente: $dashboardUrl" -ForegroundColor Red
        }
    } else {
        Write-Log "Chrome no detectado. Abrir manualmente: $dashboardUrl"
        Write-Host "  Chrome no detectado. Abra manualmente:" -ForegroundColor Yellow
        Write-Host "  $dashboardUrl" -ForegroundColor Green
    }
}

# ============================================================================
# FUNCION: Panel de estado final
# ============================================================================
function Show-StatusPanel {
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  ROXYMASTER v$script:VERSION - PCMASTER" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  Estado: " -NoNewline
    Write-Host "ESPERANDO CONEXIONES" -ForegroundColor Green
    Write-Host "  IP Local:     $script:IP_LOCAL" -ForegroundColor White
    Write-Host "  IP Tailscale: $script:TAILSCALE_IP" -ForegroundColor White
    Write-Host "  Puerto WS:    $script:WS_PORT" -ForegroundColor White
    Write-Host "  Dashboard:    http://localhost:$script:HTTP_DASHBOARD_PORT/dashboard" -ForegroundColor White
    Write-Host "  Admin TCP:    $script:TCP_ADMIN_PORT" -ForegroundColor White
    Write-Host "----------------------------------------" -ForegroundColor DarkGray
    Write-Host "  Comandos Admin (via TCP/nc):" -ForegroundColor Yellow
    Write-Host "    estado              - Ver estado general" -ForegroundColor Gray
    Write-Host "    perfiles            - Listar perfiles" -ForegroundColor Gray
    Write-Host "    asignar <N> url <URL> duracion <MIN>" -ForegroundColor Gray
    Write-Host "    comentarios_activar url <URL>" -ForegroundColor Gray
    Write-Host "    detener url <URL>" -ForegroundColor Gray
    Write-Host "----------------------------------------" -ForegroundColor DarkGray
    Write-Host "  Prueba desde terminal:" -ForegroundColor Yellow
    Write-Host "    echo estado | nc $script:IP_LOCAL $script:TCP_ADMIN_PORT" -ForegroundColor Gray
    Write-Host "========================================" -ForegroundColor Cyan
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
    Write-Host "  INSTALADOR PCMASTER (SERVIDOR)" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    
    # 1. Determinar ruta base
    $script:BASE_DIR = Join-Path $env:USERPROFILE "Desktop\ROXYMASTER\PCMASTER"
    
    if (-not (Test-Path $script:BASE_DIR)) {
        Write-Host "ERROR: No se encuentra la carpeta:" -ForegroundColor Red
        Write-Host "  $script:BASE_DIR" -ForegroundColor Red
        Write-Host "Cree la carpeta manualmente y coloque los archivos necesarios." -ForegroundColor Red
        exit 1
    }
    
    $script:LOG_FILE = Join-Path $script:BASE_DIR "pcmaster_install.log"
    Write-Log "Iniciando instalador PCMASTER v$script:VERSION"
    Write-Log "Ruta base: $script:BASE_DIR"
    
    # 2. Mutex anti-duplicado
    $mutex = Test-Mutex
    if ($null -eq $mutex) {
        # Error de permisos al crear mutex, continuar (ya se mostro WARN)
    }
    
    # 3. Detectar Python
    if (-not (Test-Python)) { exit 1 }
    
    # 4. Detectar IPs y red
    Get-NetworkInfo
    
    # 5. Verificar requisitos (no bloqueante)
    $reqOk = Test-Requisitos
    if (-not $reqOk) {
        Write-Host ""
        Write-Host "ADVERTENCIA: Algunos requisitos no estan instalados." -ForegroundColor Yellow
        Write-Host "El servidor puede funcionar, pero sin IA completa." -ForegroundColor Yellow
        Write-Host "Instale: Ollama (https://ollama.com) y Whisper (pip install openai-whisper)" -ForegroundColor Yellow
        Write-Host ""
    }
    
    # 6. Instalar dependencias Python
    Install-Dependencies
    
    # 7. Inicializar archivos de datos
    Initialize-DataFiles
    
    # 8. Verificar archivos Python
    $pyOk = Test-PythonFiles
    if (-not $pyOk) {
        Write-Host ""
        Write-Host "========================================" -ForegroundColor Red
        Write-Host "  FALTAN ARCHIVOS PYTHON ESENCIALES" -ForegroundColor Red
        Write-Host "  Coloque server_corregido.py, variables_globales.py" -ForegroundColor Red
        Write-Host "  y shs.py en:" -ForegroundColor Red
        Write-Host "  $script:BASE_DIR\scripts\" -ForegroundColor Red
        Write-Host "========================================" -ForegroundColor Red
        exit 1
    }
    
    # 9. Panel de estado
    Show-StatusPanel
    
    # 10. Lanzar servidor
    Write-Host ""
    Write-Host "Iniciando servidor Python..." -ForegroundColor Yellow
    $process = Start-Server
    
    if ($process) {
        Write-Host ""
        Write-Host "PCMASTER iniciado correctamente." -ForegroundColor Green
        
        # 11. Abrir Chrome automaticamente con dashboard
        Open-BrowserDashboard -DelaySeconds 6
        
        Write-Host "Presione Ctrl+C para detener." -ForegroundColor Gray
        
        # Esperar a que el proceso termine o Ctrl+C
        try {
            $process.WaitForExit()
        } catch {
            Write-Log "Servidor detenido por el usuario"
        }
    }
    
    Write-Log "Instalador PCMASTER finalizado"
}

# Ejecutar
Main