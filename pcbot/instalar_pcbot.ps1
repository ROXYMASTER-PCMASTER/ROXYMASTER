# ============================================================================
# roxymaster v8.3 - instalador pcbot (cliente)
# ejecutar en cada maquina pcbot
# ruta: c:\users\<usuario>\desktop\roxymaster\pcbot\instalar_pcbot.ps1
# ============================================================================
#requires -version 5.1
set-strictmode -version latest
$erroractionpreference = "stop"
$host.ui.rawui.windowtitle = "roxymaster v8.3 - pcbot client"

# ============================================================================
# variables globales (modificables manualmente)
# ============================================================================
$script:version = "8.3"
$script:mutex_name = "global\roxymaster_pcbot_v83"
$script:pcmaster_ws_port = 5006

# ============================================================================
# funcion: escribir logs con timestamp
# ============================================================================
function write-log {
    param([string]$message, [string]$level = "info")
    $timestamp = get-date -format "yyyy-mm-dd hh:mm:ss"
    $line = "$timestamp [$level] $message"
    write-host $line
    try {
        add-content -path "$script:log_file" -value $line -erroraction silentlycontinue
    } catch {}
}

# ============================================================================
# funcion: verificar si ya hay una instancia corriendo (mutex)
# ============================================================================
function test-mutex {
    try {
        $mutex = new-object system.threading.mutex($false, $script:mutex_name)
        if (-not $mutex.waitone(0)) {
            write-log "error: pcbot ya esta corriendo. cerrando..." "error"
            write-host ""
            write-host "========================================" -foregroundcolor red
            write-host "  pcbot ya esta en ejecucion" -foregroundcolor red
            write-host "  no se puede abrir una segunda instancia." -foregroundcolor red
            write-host "========================================" -foregroundcolor red
            exit 1
        }
        return $mutex
    } catch {
        write-log "advertencia: no se pudo crear mutex, continuando..." "warn"
        return $null
    }
}

# ============================================================================
# funcion: detectar python y pip
# ============================================================================
function test-python {
    try {
        $pyver = & python --version 2>&1
        if ($lastexitcode -ne 0) { throw "python no encontrado" }
        write-log "python detectado: $pyver"

        $pipver = & pip --version 2>&1
        if ($lastexitcode -ne 0) { throw "pip no encontrado" }
        write-log "pip detectado: $pipver"

        return $true
    } catch {
        write-log "error: python/pip no encontrado. instale python 3.10+ desde https://python.org" "error"
        return $false
    }
}

# ============================================================================
# funcion: detectar informacion del sistema
# ============================================================================
function get-systeminfo {
    write-log "recopilando informacion del sistema..."

    # nombre pc
    $script:nombre_pc = $env:computername
    write-log "nombre pc: $($script:nombre_pc)"

    # usuario
    $script:usuario = $env:username
    write-log "usuario: $($script:usuario)"

    # ip local
    try {
        $iplocal = (get-netipaddress -addressfamily ipv4 -prefixorigin manual,dhcp |
                    where-object { $_.ipaddress -notlike "127.*" } |
                    select-object -first 1).ipaddress
        if ($iplocal) {
            $script:ip_local = $iplocal
        } else {
            $script:ip_local = "127.0.0.1"
        }
        write-log "ip local detectada: $($script:ip_local)"
    } catch {
        $script:ip_local = "127.0.0.1"
        write-log "ip local por defecto: $($script:ip_local)" "warn"
    }

    # tailscale ip
    try {
        $tsip = & tailscale ip -4 2>&1
        if ($lastexitcode -eq 0 -and $tsip -match '\d+\.\d+\.\d+\.\d+') {
            $script:ip_tailscale = $tsip.trim()
            write-log "tailscale ip detectada: $($script:ip_tailscale)"
        } else {
            $script:ip_tailscale = "no_detectado"
            write-log "tailscale no detectado." "warn"
        }
    } catch {
        $script:ip_tailscale = "no_detectado"
        write-log "tailscale no detectado." "warn"
    }

    # id unico del pcbot
    $script:client_id = "$($script:nombre_pc)-$($script:usuario)"
    write-log "client id: $($script:client_id)"
}

# ============================================================================
# funcion: detectar aplicaciones de gestion de perfiles
# ============================================================================
function get-profileapps {
    write-log "detectando aplicaciones de gestion de perfiles..."

    $apps = @{}

    # rutas comunes de roxybrowser (nuevas para v8.3)
    $roxypaths = @(
        "$env:programfiles\roxybrowser\roxybrowser.exe",
        "${env:programfiles(x86)}\roxybrowser\roxybrowser.exe",
        "$env:localappdata\roxybrowser\roxybrowser.exe",
        "$env:userprofile\appdata\local\roxybrowser\roxybrowser.exe",
        "c:\roxybrowser\roxybrowser.exe"
    )
    foreach ($p in $roxypaths) {
        if (test-path $p) { $apps["roxybrowser"] = $p; break }
    }

    # multilogin
    $mlpaths = @(
        "$env:programfiles\multilogin\multilogin.exe",
        "${env:programfiles(x86)}\multilogin\multilogin.exe"
    )
    foreach ($p in $mlpaths) {
        if (test-path $p) { $apps["multilogin"] = $p; break }
    }

    # gologin
    $glpaths = @(
        "$env:programfiles\gologin\gologin.exe",
        "${env:programfiles(x86)}\gologin\gologin.exe"
    )
    foreach ($p in $glpaths) {
        if (test-path $p) { $apps["gologin"] = $p; break }
    }

    # adspower
    $adpaths = @(
        "$env:programfiles\adspower\adspower.exe",
        "${env:programfiles(x86)}\adspower\adspower.exe"
    )
    foreach ($p in $adpaths) {
        if (test-path $p) { $apps["adspower"] = $p; break }
    }

    if ($apps.count -gt 0) {
        write-log "aplicaciones detectadas: $($apps.keys -join ', ')"
        foreach ($key in $apps.keys) {
            write-host "  [detectado] $key -> $($apps[$key])" -foregroundcolor green
        }
    } else {
        write-log "sin aplicaciones de perfiles detectadas"
        write-host "  [sin apps] no se detectaron aplicaciones de gestion de perfiles." -foregroundcolor yellow
    }

    return $apps
}

# ============================================================================
# funcion: detectar navegadores disponibles
# ============================================================================
function get-browsers {
    write-log "detectando navegadores disponibles..."

    $browsers = @()

    # chrome
    $chromepaths = @(
        "$env:programfiles\google\chrome\application\chrome.exe",
        "${env:programfiles(x86)}\google\chrome\application\chrome.exe",
        "$env:localappdata\google\chrome\application\chrome.exe"
    )
    foreach ($p in $chromepaths) {
        if (test-path $p) { $browsers += @{nombre="chrome"; ruta=$p; user_data="$env:localappdata\google\chrome\user data"}; break }
    }

    # edge
    $edgepaths = @(
        "${env:programfiles(x86)}\microsoft\edge\application\msedge.exe",
        "$env:programfiles\microsoft\edge\application\msedge.exe"
    )
    foreach ($p in $edgepaths) {
        if (test-path $p) { $browsers += @{nombre="edge"; ruta=$p; user_data="$env:localappdata\microsoft\edge\user data"}; break }
    }

    # brave
    $bravepaths = @(
        "$env:programfiles\bravesoftware\brave-browser\application\brave.exe",
        "${env:programfiles(x86)}\bravesoftware\brave-browser\application\brave.exe",
        "$env:localappdata\bravesoftware\brave-browser\application\brave.exe"
    )
    foreach ($p in $bravepaths) {
        if (test-path $p) { $browsers += @{nombre="brave"; ruta=$p; user_data="$env:localappdata\bravesoftware\brave-browser\user data"}; break }
    }

    # firefox
    $ffpaths = @(
        "$env:programfiles\mozilla firefox\firefox.exe",
        "${env:programfiles(x86)}\mozilla firefox\firefox.exe"
    )
    foreach ($p in $ffpaths) {
        if (test-path $p) { $browsers += @{nombre="firefox"; ruta=$p; user_data="$env:appdata\mozilla\firefox\profiles"}; break }
    }

    # opera
    $operapaths = @(
        "$env:programfiles\opera\opera.exe",
        "${env:programfiles(x86)}\opera\opera.exe",
        "$env:localappdata\programs\opera\opera.exe"
    )
    foreach ($p in $operapaths) {
        if (test-path $p) { $browsers += @{nombre="opera"; ruta=$p; user_data="$env:appdata\opera software\opera stable"}; break }
    }

    write-log "navegadores detectados: $($browsers.count)"
    foreach ($b in $browsers) {
        write-host "  [navegador] $($b.nombre) -> $($b.ruta)" -foregroundcolor cyan
    }

    return $browsers
}

# ============================================================================
# funcion: generar config.json para pcbot
# ============================================================================
function new-configjson {
    $configpath = join-path $script:base_dir "config.json"

    $config = @{
        pcbot = @{
            nombre_pc = $script:nombre_pc
            usuario = $script:usuario
            ip_local = $script:ip_local
            ip_tailscale = $script:ip_tailscale
            client_id = $script:client_id
        }
        pcmaster = @{
            ip = $script:pcmaster_ip
            ws_port = $script:pcmaster_ws_port
        }
        version = $script:version
        seguridad = @{
            protocolo = "shs"
            version = "1.0"
        }
    }

    $config | convertto-json -depth 4 | set-content -path $configpath -encoding utf8
    write-log "config.json creado/actualizado"
    write-host "  config.json actualizado con informacion del sistema" -foregroundcolor green
}

# ============================================================================
# funcion: instalar dependencias python
# ============================================================================
function install-dependencies {
    write-log "instalando dependencias python..."

    $packages = @("websockets", "requests", "psutil", "aiohttp", "asyncio")

    foreach ($pkg in $packages) {
        try {
            $installed = & pip show $pkg 2>&1
            if ($lastexitcode -eq 0) {
                write-log "  $pkg ya instalado"
            } else {
                write-log "  instalando $pkg..."
                & pip install $pkg -q 2>&1 | out-null
                if ($lastexitcode -eq 0) {
                    write-log "  $pkg instalado correctamente"
                } else {
                    write-log "  error instalando $pkg" "error"
                }
            }
        } catch {
            write-log "  error con $pkg : $_" "error"
        }
    }
}

# ============================================================================
# funcion: crear directorios necesarios
# ============================================================================
function ensure-directories {
    $dirs = @(
        (join-path $script:base_dir "scripts"),
        (join-path $script:base_dir "scripts\core"),
        (join-path $script:base_dir "scripts\api"),
        (join-path $script:base_dir "data"),
        (join-path $script:base_dir "logs")
    )
    foreach ($d in $dirs) {
        if (-not (test-path $d)) {
            new-item -itemtype directory -path $d -force | out-null
            write-log "directorio creado: $d"
        }
    }
}

# ============================================================================
# funcion: panel de estado y recomendaciones
# ============================================================================
function show-panel {
    param($profileapps, $browsers)

    write-host ""
    write-host "========================================" -foregroundcolor cyan
    write-host "  roxymaster v$($script:version) - pcbot" -foregroundcolor cyan
    write-host "========================================" -foregroundcolor cyan
    write-host "  pc: $($script:nombre_pc)" -foregroundcolor white
    write-host "  usuario: $($script:usuario)" -foregroundcolor white
    write-host "  ip local: $($script:ip_local)" -foregroundcolor white
    write-host "  ip tailscale: $($script:ip_tailscale)" -foregroundcolor white
    write-host "  client id: $($script:client_id)" -foregroundcolor white
    write-host "----------------------------------------" -foregroundcolor darkgray
    write-host "  pcmaster target: $($script:pcmaster_ip):$($script:pcmaster_ws_port)" -foregroundcolor white
    write-host "----------------------------------------" -foregroundcolor darkgray

    if ($profileapps.count -gt 0) {
        write-host "  [apps de perfiles detectadas]" -foregroundcolor green
        foreach ($key in $profileapps.keys) {
            write-host "    $key" -foregroundcolor gray
        }
        write-host ""
        write-host "  >> los perfiles deben crearse manualmente en la aplicacion" -foregroundcolor yellow
        write-host "  >> configurar huellas digitales y proxies manualmente" -foregroundcolor yellow
        write-host "  >> luego iniciar los perfiles para que pcbot los detecte" -foregroundcolor yellow
    } else {
        write-host "  [modo navegadores - sin apps]" -foregroundcolor yellow
        write-host "  navegadores detectados: $($browsers.count)" -foregroundcolor gray
        write-host ""
        write-host "  >> pcbot detectara perfiles desde roxybrowser o navegadores" -foregroundcolor cyan
    }

    write-host "----------------------------------------" -foregroundcolor darkgray
    write-host "  pcmaster: $($script:pcmaster_ip)" -foregroundcolor yellow
    write-host "  puerto: $($script:pcmaster_ws_port)" -foregroundcolor yellow
    write-host "========================================" -foregroundcolor cyan
}

# ============================================================================
# funcion: lanzar pcbot python (main.py)
# ============================================================================
function start-pcbot {
    $scriptsdir = join-path $script:base_dir "scripts"
    $pcbotscript = join-path $scriptsdir "main.py"

    if (-not (test-path $pcbotscript)) {
        write-log "error: no se encontro $pcbotscript" "error"
        return $false
    }

    write-log "========================================"
    write-log "  iniciando pcbot client"
    write-log "  conectando a pcmaster: $($script:pcmaster_ip):$($script:pcmaster_ws_port)"
    write-log "  client id: $($script:client_id)"
    write-log "========================================"

    $env:roxymaster_base = $script:base_dir

    try {
        set-location $scriptsdir
        $process = start-process -filepath "python" -argumentlist $pcbotscript -nonewwindow -passthru
        write-log "pcbot python iniciado (pid: $($process.id))"
        return $process
    } catch {
        write-log "error al iniciar pcbot: $_" "error"
        return $null
    }
}

# ============================================================================
# main
# ============================================================================
function main {
    clear-host

    # banner
    write-host ""
    write-host "========================================" -foregroundcolor cyan
    write-host "  roxymaster v$($script:version)" -foregroundcolor cyan
    write-host "  instalador pcbot (cliente)" -foregroundcolor cyan
    write-host "========================================" -foregroundcolor cyan
    write-host ""

    # 1. determinar ruta base (detecta la carpeta pcbot)
    $script:base_dir = join-path $env:userprofile "desktop\roxymaster\pcbot"
    # si no existe, probar minusculas
    if (-not (test-path $script:base_dir)) {
        $script:base_dir = join-path $env:userprofile "desktop\roxymaster\pcbot"
    }
    # si aun no existe, probar la ruta actual
    if (-not (test-path $script:base_dir)) {
        $script:base_dir = (get-location).path
    }

    if (-not (test-path $script:base_dir)) {
        write-host "error: no se encuentra la carpeta pcbot." -foregroundcolor red
        write-host "asegurate de que exista: $($env:userprofile)\desktop\roxymaster\pcbot" -foregroundcolor red
        exit 1
    }

    $script:log_file = join-path $script:base_dir "pcbot_install.log"
    write-log "iniciando instalador pcbot v$($script:version)"
    write-log "ruta base: $($script:base_dir)"

    # 2. mutex anti-duplicado
    $mutex = test-mutex
    if ($null -eq $mutex) { }

    # 3. detectar python
    if (-not (test-python)) { exit 1 }

    # 4. recopilar info del sistema
    get-systeminfo

    # 5. leer ip del pcmaster desde config.json si existe
    $configpath = join-path $script:base_dir "config.json"
    if (test-path $configpath) {
        try {
            $existingconfig = get-content $configpath -raw | convertfrom-json
            if ($existingconfig.pcmaster -and $existingconfig.pcmaster.ip) {
                $script:pcmaster_ip = $existingconfig.pcmaster.ip
            }
        } catch {}
    }
    if (-not $script:pcmaster_ip) {
        $script:pcmaster_ip = "100.111.179.65"  # ip tailscale de pcmaster por defecto
    }
    write-log "pcmaster target: $($script:pcmaster_ip):$($script:pcmaster_ws_port)"

    # 6. detectar apps de perfiles y navegadores
    $profileapps = get-profileapps
    $browsers = get-browsers

    # 7. crear directorios necesarios
    ensure-directories

    # 8. generar/actualizar config.json
    new-configjson

    # 9. instalar dependencias
    install-dependencies

    # 10. verificar archivos python (main.py en lugar de pcbot.py)
    $scriptsdir = join-path $script:base_dir "scripts"
    $requiredfiles = @(
        (join-path $scriptsdir "main.py"),
        (join-path $scriptsdir "config_loader.py"),
        (join-path $scriptsdir "shs.py"),
        (join-path $scriptsdir "deteccion_perfiles.py"),
        (join-path $scriptsdir "http_portal.py"),
        (join-path $scriptsdir "core\state_tracker.py"),
        (join-path $scriptsdir "core\token_engine.py"),
        (join-path $scriptsdir "core\profile_manager.py"),
        (join-path $scriptsdir "api\ws_client.py"),
        (join-path $scriptsdir "api\roxybrowser_api.py")
    )

    $missingfiles = @()
    foreach ($f in $requiredfiles) {
        if (-not (test-path $f)) {
            $missingfiles += $f
        }
    }

    if ($missingfiles.count -gt 0) {
        write-host ""
        write-host "========================================" -foregroundcolor red
        write-host "  archivos faltantes:" -foregroundcolor red
        foreach ($mf in $missingfiles) {
            write-host "    $mf" -foregroundcolor red
        }
        write-host "========================================" -foregroundcolor red
        write-host "  copia los archivos de scripts desde pcmaster o el repositorio." -foregroundcolor yellow
        # no salimos, puede que algunos modulos se carguen dinamicamente
    }

    # 11. panel de estado
    show-panel -profileapps $profileapps -browsers $browsers

    # 12. lanzar pcbot
    write-host ""
    write-host "iniciando cliente pcbot..." -foregroundcolor yellow
    $process = start-pcbot

    if ($process) {
        write-host ""
        write-host "pcbot iniciado correctamente." -foregroundcolor green
        write-host "conectado a pcmaster: $($script:pcmaster_ip):$($script:pcmaster_ws_port)" -foregroundcolor white
        write-host "portal local: http://127.0.0.1:8087" -foregroundcolor white
        write-host "presione ctrl+c para detener." -foregroundcolor gray

        try {
            $process.waitforexit()
        } catch {
            write-log "pcbot detenido por el usuario"
        }
    }

    write-log "instalador pcbot finalizado"
}

# ejecutar
main