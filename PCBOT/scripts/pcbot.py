# ============================================================================
# pcbot.py - agente cliente roxymaster v8.3
# detecta automaticamente roxybrowser, perfiles, sistema
# se conecta a pcmaster via websocket con protocolo shs
# ejecuta comandos de orquestacion via playwright
# ============================================================================

import asyncio
import json
import os
import sys
import time
import uuid
import socket
import logging
import subprocess
import threading
import queue
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

import websockets

# ---------------------------------------------------------------------------
# configuracion de rutas (minúsculas, dinámicas)
# ---------------------------------------------------------------------------
_base = Path(__file__).parent.parent.absolute()
_scripts_dir = _base / 'scripts'
_data_dir = _base / 'data'
_config_path = _base / 'config.json'
_portal_dir = _base

# agregar scripts al path
sys.path.insert(0, str(_scripts_dir))

# ---------------------------------------------------------------------------
# importar modulos del sistema
# ---------------------------------------------------------------------------
from variables_globales import (
    pcmaster_ip, pcmaster_port, pcmaster_local_ip,
    ui_port, http_port, portal_port,
    roxybrowser_api_url, roxybrowser_timeout,
    secreto_sistema, version,
    max_perfiles_locales, heartbeat_interval,
    reconnect_delay, max_reconnect_delay,
    tiempo_validacion_perfil, tiempo_colgado_timeout,
    tiempo_revision_colgados,
    cargar_config, guardar_config,
)
from shs import (
    firmar_mensaje, verificar_mensaje,
    crear_mensaje_handshake, crear_mensaje_heartbeat,
    crear_mensaje_respuesta, crear_mensaje_alerta,
    generar_token_sesion,
)

# ---------------------------------------------------------------------------
# logging
# ---------------------------------------------------------------------------
_data_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(str(_data_dir / 'pcbot.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('pcbot')

# ---------------------------------------------------------------------------
# playwright (importacion diferida)
# ---------------------------------------------------------------------------
_playwright = None
_playwright_inst = None


async def _get_playwright():
    """obtiene instancia global de playwright (inicio perezoso)."""
    global _playwright, _playwright_inst
    if _playwright is None:
        from playwright.async_api import async_playwright
        _playwright = async_playwright
    if _playwright_inst is None:
        _playwright_inst = await _playwright().start()
        logger.info('playwright iniciado')
    return _playwright_inst


# ============================================================================
# deteccion automatica del sistema
# ============================================================================

def detectar_info_sistema() -> dict:
    """detecta automaticamente toda la informacion del sistema.

    devuelve diccionario con:
    - nombre_pc, usuario, ip_local, ip_tailscale, ip_wan
    - navegadores_instalados, roxybrowser_detectado
    """
    info = {
        'nombre_pc': os.environ.get('computername', '').lower(),
        'usuario': os.environ.get('username', '').lower(),
        'ip_local': '127.0.0.1',
        'ip_tailscale': '',
        'ip_wan': '',
        'navegadores_instalados': [],
        'roxybrowser_detectado': False,
        'sistema_operativo': 'windows',
    }

    # ip local
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(('8.8.8.8', 80))
        info['ip_local'] = s.getsockname()[0]
        s.close()
    except Exception:
        try:
            info['ip_local'] = socket.gethostbyname(socket.gethostname())
        except Exception:
            pass

    # ip tailscale
    try:
        resultado = subprocess.run(
            ['tailscale', 'ip', '--4'],
            capture_output=True, text=True, timeout=5
        )
        if resultado.returncode == 0:
            info['ip_tailscale'] = resultado.stdout.strip()
    except Exception:
        try:
            # alternativa: leer de la interfaz de red
            resultado = subprocess.run(
                ['ipconfig'],
                capture_output=True, text=True, timeout=10
            )
            for linea in resultado.stdout.split('\n'):
                if '100.' in linea and 'tailscale' in resultado.stdout.lower():
                    partes = linea.strip().split(':')
                    if len(partes) >= 2:
                        ip = partes[-1].strip()
                        if ip.startswith('100.'):
                            info['ip_tailscale'] = ip
                            break
        except Exception:
            pass

    # ip wan
    try:
        import urllib.request
        with urllib.request.urlopen('https://ifconfig.me/ip', timeout=10) as resp:
            info['ip_wan'] = resp.read().decode('utf-8').strip()
    except Exception:
        try:
            with urllib.request.urlopen('https://api.ipify.org', timeout=10) as resp:
                info['ip_wan'] = resp.read().decode('utf-8').strip()
        except Exception:
            info['ip_wan'] = info['ip_local']

    # navegadores instalados
    navegadores = []
    rutas_navegadores = {
        'chrome': [
            r'c:\program files\google\chrome\application\chrome.exe',
            r'c:\program files (x86)\google\chrome\application\chrome.exe',
            os.path.expandvars(r'%localappdata%\google\chrome\application\chrome.exe'),
        ],
        'edge': [
            r'c:\program files (x86)\microsoft\edge\application\msedge.exe',
            r'c:\program files\microsoft\edge\application\msedge.exe',
        ],
        'firefox': [
            r'c:\program files\mozilla firefox\firefox.exe',
            r'c:\program files (x86)\mozilla firefox\firefox.exe',
        ],
        'brave': [
            os.path.expandvars(r'%localappdata%\bravesoftware\brave-browser\application\brave.exe'),
            r'c:\program files\bravesoftware\brave-browser\application\brave.exe',
        ],
        'opera': [
            os.path.expandvars(r'%localappdata%\programs\opera\launcher.exe'),
            r'c:\program files\opera\launcher.exe',
        ],
    }

    for nombre, rutas in rutas_navegadores.items():
        for ruta in rutas:
            if os.path.exists(ruta.lower()):
                navegadores.append(nombre)
                break

    info['navegadores_instalados'] = navegadores

    return info


async def detectar_roxybrowser() -> dict:
    """detecta si roxybrowser esta corriendo y obtiene su informacion.

    devuelve:
    {
        'detectado': bool,
        'token': str,
        'workspace_id': str,
        'perfiles': list,
        'error': str o None
    }
    """
    resultado = {
        'detectado': False,
        'token': '',
        'workspace_id': '',
        'perfiles': [],
        'error': None,
    }

    # verificar si roxybrowser responde
    try:
        import urllib.request
        req = urllib.request.Request(
            f'{roxybrowser_api_url}/browser/health',
            headers={'accept': 'application/json'},
        )
        with urllib.request.urlopen(req, timeout=roxybrowser_timeout) as resp:
            if resp.status != 200:
                resultado['error'] = 'roxybrowser no responde (health check fallido)'
                return resultado
    except Exception as e:
        resultado['error'] = f'roxybrowser no detectado en {roxybrowser_api_url}: {e}'
        return resultado

    resultado['detectado'] = True

    # cargar token del config
    config = cargar_config()
    token = config.get('roxybrowser_token', '')

    if not token:
        resultado['error'] = 'token de roxybrowser no configurado'
        return resultado

    resultado['token'] = token

    # obtener workspace
    try:
        import urllib.request
        req = urllib.request.Request(
            f'{roxybrowser_api_url}/browser/workspace',
            headers={
                'accept': 'application/json',
                'authorization': f'bearer {token}',
            },
        )
        with urllib.request.urlopen(req, timeout=roxybrowser_timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            resultado['workspace_id'] = data.get('workspaceId', data.get('workspace_id', ''))
    except Exception as e:
        logger.warning(f'no se pudo obtener workspace de roxybrowser: {e}')

    # obtener perfiles
    try:
        import urllib.request
        req = urllib.request.Request(
            f'{roxybrowser_api_url}/browser/list_v3',
            headers={
                'accept': 'application/json',
                'authorization': f'bearer {token}',
            },
        )
        with urllib.request.urlopen(req, timeout=roxybrowser_timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            perfiles_raw = data.get('profiles', data.get('data', []))
            if isinstance(perfiles_raw, dict):
                perfiles_raw = list(perfiles_raw.values())

        for p in perfiles_raw:
            perfil_id = p.get('dirId', p.get('dir_id', p.get('id', '')))
            nombre = p.get('name', p.get('nombre', ''))
            estado_raw = p.get('status', p.get('estado', ''))

            # mapear estado
            if estado_raw in ('active', 'activo', 'running'):
                estado = 'activo'
            elif estado_raw in ('inactive', 'inactivo', 'stopped'):
                estado = 'inactivo'
            else:
                estado = 'desconocido'

            resultado['perfiles'].append({
                'perfil_id': perfil_id,
                'nombre': nombre,
                'estado': estado,
                'tipo': 'roxybrowser',
                'proxy': p.get('proxy', ''),
            })

    except Exception as e:
        logger.warning(f'no se pudieron obtener perfiles de roxybrowser: {e}')
        resultado['error'] = f'error listando perfiles: {e}'

    return resultado


# ============================================================================
# cliente pcboot - agente principal
# ============================================================================

class pcbot_cliente:
    """cliente principal del agente pcbot.

    responsable de:
    - detectar sistema y roxybrowser
    - conectarse a pcmaster via websocket con shs
    - enviar heartbeats periodicos
    - recibir y ejecutar comandos de orquestacion
    - mantener el estado de los perfiles
    """

    def __init__(self):
        self.pcbot_id = ''
        self.token_sesion = ''
        self.info_sistema = {}
        self.config = {}
        self.estado_global = {
            'modo': 'conectado',  # conectado | solo_mi
            'conectado_pcmaster': False,
            'tokens_acumulados': 0,
            'tokens_hoy': 0,
        }
        self.perfiles_registrados: List[dict] = []
        self.perfiles_abiertos: Dict[str, Any] = {}  # perfil_id -> {browser, page, ...}
        self.tracker_perfiles: Dict[str, dict] = {}  # perfil_id -> {tiempo_acumulado, ...}
        self.comandos_activos: Dict[str, Any] = {}  # comando_id -> info
        self.running = True
        self.ws_connection = None
        self.ultimo_heartbeat = 0
        self.reconnect_count = 0

    async def inicializar(self):
        """inicializa el cliente: detecta sistema, genera id, carga config."""
        logger.info('=' * 60)
        logger.info(f'  pcbot v{version} - inicializando')
        logger.info('=' * 60)

        # cargar configuracion
        self.config = cargar_config()

        # generar o cargar pcbot_id
        self.pcbot_id = self.config.get('pcbot_id', '')
        if not self.pcbot_id:
            self.pcbot_id = f'pcbot_{uuid.uuid4().hex[:12]}'
            self.config['pcbot_id'] = self.pcbot_id
            guardar_config(self.config)

        # generar token de sesion si no existe
        self.token_sesion = self.config.get('token_sesion', '')
        if not self.token_sesion:
            self.token_sesion = generar_token_sesion(self.pcbot_id)
            self.config['token_sesion'] = self.token_sesion
            guardar_config(self.config)

        # detectar informacion del sistema
        logger.info('detectando informacion del sistema...')
        self.info_sistema = detectar_info_sistema()

        logger.info(f'  pc: {self.info_sistema["nombre_pc"]}')
        logger.info(f'  usuario: {self.info_sistema["usuario"]}')
        logger.info(f'  ip local: {self.info_sistema["ip_local"]}')
        logger.info(f'  ip tailscale: {self.info_sistema["ip_tailscale"]}')
        logger.info(f'  ip wan: {self.info_sistema["ip_wan"]}')
        logger.info(f'  navegadores: {", ".join(self.info_sistema["navegadores_instalados"]) or "ninguno"}')

        # detectar roxybrowser
        logger.info('detectando roxybrowser...')
        rb_info = await detectar_roxybrowser()
        if rb_info['detectado']:
            logger.info(f'  roxybrowser detectado: {len(rb_info["perfiles"])} perfiles')
            logger.info(f'  workspace: {rb_info["workspace_id"]}')
            for p in rb_info['perfiles']:
                logger.info(f'    - {p["nombre"]} ({p["estado"]})')
        else:
            logger.info(f'  roxybrowser: {rb_info.get("error", "no detectado")}')

        # combinar perfiles
        self.perfiles_registrados = rb_info.get('perfiles', [])

        # agregar perfiles locales si no hay roxybrowser
        if not rb_info['detectado'] and len(self.perfiles_registrados) < max_perfiles_locales:
            for i in range(max_perfiles_locales):
                self.perfiles_registrados.append({
                    'perfil_id': f'local_{self.pcbot_id}_{i}',
                    'nombre': f'perfil_local_{i+1}',
                    'estado': 'inactivo',
                    'tipo': 'local',
                    'proxy': '',
                })

        # agregar info de roxybrowser al info_sistema
        self.info_sistema['roxybrowser_detectado'] = rb_info['detectado']
        self.info_sistema['roxybrowser_token'] = rb_info.get('token', '')
        self.info_sistema['roxybrowser_workspace'] = rb_info.get('workspace_id', '')
        self.info_sistema['perfiles'] = self.perfiles_registrados

        logger.info(f'inicializacion completa: {len(self.perfiles_registrados)} perfiles registrados')

    async def conectar_pcmaster(self):
        """bucle principal de conexion a pcmaster con reconexion automatica."""
        direccion = self.config.get('pcmaster_ip', pcmaster_ip)
        puerto = self.config.get('pcmaster_port', pcmaster_port)
        url = f'ws://{direccion}:{puerto}'

        while self.running:
            try:
                logger.info(f'conectando a pcmaster: {url}')
                async with websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                    max_size=10 * 1024 * 1024,
                ) as ws:
                    self.ws_connection = ws
                    self.estado_global['conectado_pcmaster'] = True
                    self.reconnect_count = 0
                    logger.info('conectado a pcmaster')

                    # enviar handshake
                    handshake_msg = crear_mensaje_handshake(
                        self.pcbot_id,
                        self.token_sesion,
                        self.info_sistema,
                        secreto_sistema,
                    )
                    await ws.send(handshake_msg)
                    logger.info('handshake enviado')

                    # esperar confirmacion
                    respuesta = await asyncio.wait_for(ws.recv(), timeout=30)
                    valido, payload = verificar_mensaje(respuesta, secreto_sistema)
                    if valido and payload.get('tipo') == 'handshake_ok':
                        logger.info(f'handshake confirmado: {payload.get("mensaje", "")}')
                        # actualizar token si el servidor envio uno nuevo
                        nuevo_token = payload.get('token_sesion', '')
                        if nuevo_token and nuevo_token != self.token_sesion:
                            self.token_sesion = nuevo_token
                            self.config['token_sesion'] = nuevo_token
                            guardar_config(self.config)
                    else:
                        logger.warning(f'handshake no confirmado: {payload}')
                        await ws.close()
                        await self._esperar_reconexion()
                        continue

                    # iniciar heartbeats
                    heartbeat_task = asyncio.create_task(self._enviar_heartbeats())
                    comando_task = asyncio.create_task(self._recibir_comandos(ws))

                    # esperar hasta desconexion
                    try:
                        await asyncio.gather(heartbeat_task, comando_task)
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        logger.error(f'error en tareas: {e}')
                    finally:
                        heartbeat_task.cancel()
                        comando_task.cancel()

            except websockets.exceptions.ConnectionClosed:
                logger.warning('conexion con pcmaster cerrada')
            except (ConnectionRefusedError, OSError) as e:
                logger.warning(f'no se pudo conectar a pcmaster: {e}')
            except asyncio.TimeoutError:
                logger.warning('timeout esperando respuesta de pcmaster')
            except Exception as e:
                logger.error(f'error en conexion: {type(e).__name__}: {e}')

            self.ws_connection = None
            self.estado_global['conectado_pcmaster'] = False

            if self.running:
                await self._esperar_reconexion()

    async def _esperar_reconexion(self):
        """espera antes de reintentar conexion, con backoff progresivo."""
        delay = min(reconnect_delay * (2 ** self.reconnect_count), max_reconnect_delay)
        self.reconnect_count += 1
        logger.info(f'reintentando conexion en {delay}s (intento {self.reconnect_count})...')
        await asyncio.sleep(delay)

    async def _enviar_heartbeats(self):
        """envia heartbeats periodicos a pcmaster."""
        while self.running and self.ws_connection:
            try:
                await asyncio.sleep(heartbeat_interval)
                if not self.ws_connection:
                    break

                estado = {
                    'modo': self.estado_global['modo'],
                    'tokens_acumulados': self.estado_global['tokens_acumulados'],
                    'perfiles': self.perfiles_registrados,
                }

                hb_msg = crear_mensaje_heartbeat(
                    self.pcbot_id, estado, secreto_sistema
                )
                await self.ws_connection.send(hb_msg)
                self.ultimo_heartbeat = time.time()

                logger.debug(f'heartbeat enviado: {len(self.perfiles_registrados)} perfiles')

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f'error enviando heartbeat: {e}')
                break

    async def _recibir_comandos(self, ws):
        """recibe y procesa comandos de pcmaster."""
        while self.running:
            try:
                raw_msg = await ws.recv()
                valido, payload = verificar_mensaje(raw_msg, secreto_sistema)

                if not valido:
                    logger.warning('mensaje con firma invalida recibido')
                    continue

                tipo = payload.get('tipo', '')

                if tipo == 'heartbeat_ack':
                    # confirmacion de heartbeat, no hacer nada
                    pass

                elif tipo == 'comando':
                    comando_id = payload.get('comando_id', '')
                    accion = payload.get('accion', '')
                    params = payload.get('params', {})

                    logger.info(f'comando recibido: {accion} ({comando_id})')
                    resultado = await self._ejecutar_comando(accion, params)

                    # enviar respuesta
                    resp_msg = crear_mensaje_respuesta(
                        self.pcbot_id, comando_id, resultado, secreto_sistema
                    )
                    await ws.send(resp_msg)

                elif tipo == 'ping':
                    # responder con pong
                    from shs import firmar_mensaje
                    pong = firmar_mensaje({'tipo': 'pong', 'pcbot_id': self.pcbot_id},
                                          secreto_sistema)
                    await ws.send(pong)

                elif tipo == 'detener':
                    logger.info('comando de detencion recibido de pcmaster')
                    self.running = False
                    break

                else:
                    logger.info(f'mensaje recibido: {tipo}')

            except asyncio.CancelledError:
                break
            except websockets.exceptions.ConnectionClosed:
                logger.warning('conexion cerrada mientras se esperaban comandos')
                break
            except Exception as e:
                logger.error(f'error recibiendo comandos: {e}')
                break

    async def _ejecutar_comando(self, accion: str, params: dict) -> dict:
        """ejecuta un comando recibido de pcmaster.

        acciones soportadas:
        - abrir_url: abre una url en perfiles especificos
        - cerrar_perfil: cierra un perfil
        - comentar: activa comentarios automaticos
        - detener_url: detiene la actividad en una url
        - estado: devuelve el estado actual
        """
        try:
            if accion == 'abrir_url':
                return await self._comando_abrir_url(params)
            elif accion == 'cerrar_perfil':
                return await self._comando_cerrar_perfil(params)
            elif accion == 'comentar':
                return await self._comando_comentar(params)
            elif accion == 'detener_url':
                return await self._comando_detener_url(params)
            elif accion == 'estado':
                return {
                    'ok': True,
                    'perfiles': len(self.perfiles_registrados),
                    'activos': len(self.perfiles_abiertos),
                    'modo': self.estado_global['modo'],
                }
            elif accion == 'detener':
                self.running = False
                return {'ok': True, 'mensaje': 'deteniendo agente'}
            else:
                return {'ok': False, 'error': f'accion desconocida: {accion}'}

        except Exception as e:
            logger.error(f'error ejecutando comando {accion}: {e}')
            return {'ok': False, 'error': str(e)}

    async def _comando_abrir_url(self, params: dict) -> dict:
        """abre una url en perfiles especificos usando playwright."""
        url = params.get('url', '')
        streamer = params.get('streamer', '')
        perfiles_solicitados = params.get('perfiles', 1)
        duracion = params.get('duracion', 0)  # 0 = indefinido
        comentarios = params.get('comentarios', False)

        if not url:
            return {'ok': False, 'error': 'url requerida'}

        # asegurar que la url tenga protocolo
        if not url.startswith('http'):
            url = 'https://' + url

        logger.info(f'abriendo url: {url} ({perfiles_solicitados} perfiles)')

        # seleccionar perfiles a usar
        perfiles_a_usar = []
        for p in self.perfiles_registrados:
            if p['perfil_id'] not in self.perfiles_abiertos:
                perfiles_a_usar.append(p)
                if len(perfiles_a_usar) >= perfiles_solicitados:
                    break

        if len(perfiles_a_usar) < perfiles_solicitados:
            logger.warning(f'solo {len(perfiles_a_usar)} perfiles disponibles de {perfiles_solicitados}')

        # iniciar playwright
        playwright = await _get_playwright()

        resultados = []
        for perfil in perfiles_a_usar:
            try:
                # abrir navegador
                browser = await playwright.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox']
                )
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                               'AppleWebKit/537.36 (KHTML, like Gecko) '
                               'Chrome/120.0.0.0 Safari/537.36'
                )
                page = await context.new_page()

                # navegar a la url
                await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                logger.info(f'  {perfil["nombre"]}: url abierta')

                self.perfiles_abiertos[perfil['perfil_id']] = {
                    'browser': browser,
                    'context': context,
                    'page': page,
                    'url': url,
                    'streamer': streamer,
                    'inicio': time.time(),
                    'duracion': duracion,
                    'comentarios': comentarios,
                }

                resultados.append({
                    'perfil_id': perfil['perfil_id'],
                    'nombre': perfil['nombre'],
                    'estado': 'abierto',
                })

            except Exception as e:
                logger.error(f'error abriendo url en {perfil["nombre"]}: {e}')
                resultados.append({
                    'perfil_id': perfil['perfil_id'],
                    'nombre': perfil['nombre'],
                    'estado': 'error',
                    'error': str(e),
                })

        return {
            'ok': len(resultados) > 0,
            'url': url,
            'perfiles_usados': len(resultados),
            'resultados': resultados,
        }

    async def _comando_cerrar_perfil(self, params: dict) -> dict:
        """cierra un perfil especifico."""
        perfil_id = params.get('perfil_id', '')

        if not perfil_id:
            return {'ok': False, 'error': 'perfil_id requerido'}

        if perfil_id not in self.perfiles_abiertos:
            return {'ok': False, 'error': 'perfil no esta abierto'}

        info = self.perfiles_abiertos.pop(perfil_id)

        try:
            if info.get('page'):
                await info['page'].close()
            if info.get('context'):
                await info['context'].close()
            if info.get('browser'):
                await info['browser'].close()
            return {'ok': True, 'mensaje': f'perfil {perfil_id} cerrado'}
        except Exception as e:
            return {'ok': False, 'error': str(e)}

    async def _comando_comentar(self, params: dict) -> dict:
        """activa/desactiva comentarios en un perfil."""
        perfil_id = params.get('perfil_id', '')
        activar = params.get('activar', True)

        if not perfil_id:
            return {'ok': False, 'error': 'perfil_id requerido'}

        if perfil_id not in self.perfiles_abiertos:
            return {'ok': False, 'error': 'perfil no esta abierto'}

        self.perfiles_abiertos[perfil_id]['comentarios'] = activar
        estado = 'activados' if activar else 'desactivados'
        return {'ok': True, 'mensaje': f'comentarios {estado} en perfil {perfil_id}'}

    async def _comando_detener_url(self, params: dict) -> dict:
        """detiene todos los perfiles con una url especifica."""
        url = params.get('url', '')

        if not url:
            return {'ok': False, 'error': 'url requerida'}

        if not url.startswith('http'):
            url = 'https://' + url

        cerrados = 0
        for perfil_id, info in list(self.perfiles_abiertos.items()):
            if info.get('url') == url:
                try:
                    if info.get('page'):
                        await info['page'].close()
                    if info.get('context'):
                        await info['context'].close()
                    if info.get('browser'):
                        await info['browser'].close()
                except Exception:
                    pass
                del self.perfiles_abiertos[perfil_id]
                cerrados += 1

        return {'ok': True, 'perfiles_cerrados': cerrados}

    async def _watchdog_colgados(self):
        """verifica perfiles colgados y los recupera."""
        while self.running:
            await asyncio.sleep(tiempo_revision_colgados)
            ahora = time.time()

            for perfil_id, info in list(self.perfiles_abiertos.items()):
                try:
                    tiempo_activo = ahora - info.get('inicio', ahora)
                    duracion = info.get('duracion', 0)

                    # si tiene duracion y ya paso, cerrar
                    if duracion > 0 and tiempo_activo >= duracion * 60:
                        logger.info(f'perfil {perfil_id}: duracion cumplida ({duracion}min), cerrando')
                        await self._comando_cerrar_perfil({'perfil_id': perfil_id})
                        continue

                    # verificar si la pagina sigue viva
                    if info.get('page'):
                        try:
                            titulo = await info['page'].title()
                        except Exception:
                            logger.warning(f'perfil {perfil_id}: pagina colgada, reintentando')
                            try:
                                await info['page'].reload()
                            except Exception:
                                # cerrar y reabrir
                                await self._comando_cerrar_perfil({'perfil_id': perfil_id})
                                await self._comando_abrir_url({
                                    'url': info['url'],
                                    'streamer': info.get('streamer', ''),
                                    'perfiles': 1,
                                })

                except Exception as e:
                    logger.error(f'error en watchdog para {perfil_id}: {e}')

    async def iniciar_servidor_ui(self):
        """inicia el servidor websocket para la ui local (nicegui)."""
        try:
            import websockets
            async def manejar_ui(ws, path=None):
                """maneja conexiones de la ui local."""
                try:
                    async for msg in ws:
                        try:
                            data = json.loads(msg)
                            accion = data.get('accion', '')

                            if accion == 'estado':
                                estado = self._obtener_estado_ui()
                                await ws.send(json.dumps(estado))
                            elif accion == 'switch':
                                modo = data.get('modo', 'conectado')
                                self.estado_global['modo'] = modo
                                await ws.send(json.dumps({'ok': True, 'modo': modo}))
                            elif accion == 'comando':
                                comando_accion = data.get('comando_accion', '')
                                params = data.get('params', {})
                                resultado = await self._ejecutar_comando(comando_accion, params)
                                await ws.send(json.dumps(resultado))
                            else:
                                await ws.send(json.dumps({'error': 'accion desconocida'}))

                        except json.JSONDecodeError:
                            await ws.send(json.dumps({'error': 'json invalido'}))
                except Exception as e:
                    logger.error(f'ui websocket error: {e}')

            logger.info(f'[ui] servidor websocket en 127.0.0.1:{ui_port}')
            async with websockets.serve(manejar_ui, '127.0.0.1', ui_port):
                await asyncio.Future()

        except Exception as e:
            logger.error(f'error iniciando servidor ui: {e}')

    def _obtener_estado_ui(self) -> dict:
        """obtiene el estado para la ui."""
        perfiles_data = []
        for p in self.perfiles_registrados:
            pid = p.get('perfil_id', '')
            activo = pid in self.perfiles_abiertos
            info = self.perfiles_abiertos.get(pid, {})
            url_actual = info.get('url', 'ninguna')
            estado = 'activo' if activo else 'inactivo'

            perfiles_data.append({
                'nombre': p.get('nombre', ''),
                'perfil_id': pid,
                'activo': activo,
                'url_actual': url_actual if activo else 'ninguna',
                'estado': estado,
                'tipo': p.get('tipo', 'local'),
            })

        return {
            'ok': True,
            'pcbot_id': self.pcbot_id,
            'usuario': self.info_sistema.get('usuario', ''),
            'pc_name': self.info_sistema.get('nombre_pc', ''),
            'ip_local': self.info_sistema.get('ip_local', ''),
            'ip_tailscale': self.info_sistema.get('ip_tailscale', ''),
            'modo': self.estado_global['modo'],
            'conectado_pcmaster': self.estado_global['conectado_pcmaster'],
            'tokens_acumulados': self.estado_global['tokens_acumulados'],
            'total_perfiles': len(self.perfiles_registrados),
            'perfiles_activos': len(self.perfiles_abiertos),
            'perfiles': perfiles_data,
        }


# ============================================================================
# servidor http para dashboard local
# ============================================================================

_http_port = http_port

def _build_http_response(status_code, content_type, body_bytes, extra_headers=None):
    """construye respuesta http completa."""
    status_msgs = {200: 'ok', 400: 'bad request', 404: 'not found',
                   405: 'method not allowed', 500: 'internal server error'}
    msg = status_msgs.get(status_code, 'unknown')
    headers = [
        f'http/1.1 {status_code} {msg}',
        f'content-type: {content_type}',
        f'content-length: {len(body_bytes)}',
        'access-control-allow-origin: *',
        'connection: close'
    ]
    if extra_headers:
        headers.extend(extra_headers)
    return '\r\n'.join(headers).encode('utf-8') + b'\r\n\r\n' + body_bytes


def _parse_http_request(raw_data):
    """parsea una solicitud http cruda."""
    try:
        text = raw_data.decode('utf-8', errors='replace')
        lines = text.split('\r\n')
        if not lines:
            return None, None, {}, b''

        first = lines[0].split(' ')
        metodo = first[0].upper() if len(first) > 0 else ''
        ruta_full = first[1] if len(first) > 1 else '/'
        parsed = urlparse(ruta_full)
        ruta = parsed.path

        headers = {}
        for line in lines[1:]:
            if ':' in line:
                k, v = line.split(':', 1)
                headers[k.strip().lower()] = v.strip()
            elif line == '':
                break

        body_start = text.find('\r\n\r\n')
        body = b''
        if body_start >= 0:
            body = raw_data[body_start + 4:]

            # leer mas si hay content-length
            cl = int(headers.get('content-length', 0))
            if cl > 0 and len(body) < cl:
                body = raw_data[body_start + 4:body_start + 4 + cl]

        return metodo, ruta, headers, body
    except Exception:
        return None, None, {}, b''


def iniciar_servidor_http(cliente: pcbot_cliente):
    """inicia el servidor http local para dashboard y portal."""
    import socket as sock_mod
    server_sock = sock_mod.socket(sock_mod.AF_INET, sock_mod.SOCK_STREAM)
    server_sock.setsockopt(sock_mod.SOL_SOCKET, sock_mod.SO_REUSEADDR, 1)
    server_sock.setblocking(False)

    try:
        server_sock.bind(('127.0.0.1', _http_port))
        server_sock.listen(10)
        logger.info(f'[http] dashboard en http://127.0.0.1:{_http_port}/dashboard')
        logger.info(f'[http] portal en http://127.0.0.1:{_http_port}/portal.html')
    except Exception as e:
        logger.error(f'no se pudo iniciar servidor http en puerto {_http_port}: {e}')
        try:
            server_sock.close()
        except Exception:
            pass
        return

    loop_local = asyncio.get_event_loop()

    async def manejar_http(cli_sock, addr):
        try:
            cli_sock.setblocking(False)
            data = b''
            while True:
                try:
                    chunk = await loop_local.sock_recv(cli_sock, 8192)
                    if not chunk:
                        break
                    data += chunk
                    if b'\r\n\r\n' in data:
                        metodo, _, headers, _ = _parse_http_request(data)
                        cl = int(headers.get('content-length', 0))
                        body_start = data.find(b'\r\n\r\n')
                        if body_start >= 0 and len(data) - (body_start + 4) >= cl:
                            break
                except Exception:
                    break

            if not data:
                return

            metodo, ruta, headers, body = _parse_http_request(data)

            # cors preflight
            if metodo == 'OPTIONS':
                respuesta = _build_http_response(200, 'text/plain', b'', [
                    'access-control-allow-methods: get, post, options',
                    'access-control-allow-headers: content-type, authorization'
                ])
                await loop_local.sock_sendall(cli_sock, respuesta)
                return

            if metodo == 'GET':
                if ruta == '/' or ruta == '/portal.html':
                    portal_path = _portal_dir / 'portal.html'
                    if portal_path.exists():
                        with open(portal_path, 'rb') as f:
                            contenido = f.read()
                        respuesta = _build_http_response(200, 'text/html; charset=utf-8', contenido)
                    else:
                        respuesta = _build_http_response(404, 'text/plain', b'portal no encontrado')
                    await loop_local.sock_sendall(cli_sock, respuesta)

                elif ruta == '/dashboard' or ruta == '/dashboard.html':
                    dash_path = _portal_dir / 'dashboard.html'
                    if dash_path.exists():
                        with open(dash_path, 'rb') as f:
                            contenido = f.read()
                        respuesta = _build_http_response(200, 'text/html; charset=utf-8', contenido)
                    else:
                        respuesta = _build_http_response(404, 'text/plain', b'dashboard no encontrado')
                    await loop_local.sock_sendall(cli_sock, respuesta)

                elif ruta == '/api/estado':
                    estado = cliente._obtener_estado_ui()
                    contenido = json.dumps(estado).encode('utf-8')
                    respuesta = _build_http_response(200, 'application/json', contenido)
                    await loop_local.sock_sendall(cli_sock, respuesta)

                else:
                    respuesta = _build_http_response(404, 'text/plain', b'not found')
                    await loop_local.sock_sendall(cli_sock, respuesta)

            elif metodo == 'POST':
                if ruta == '/api/switch':
                    try:
                        data_json = json.loads(body.decode('utf-8', errors='replace')) if body else {}
                        modo = data_json.get('modo', 'conectado')
                        cliente.estado_global['modo'] = modo
                        logger.info(f'modo cambiado a: {modo}')
                        resp = json.dumps({'resultado': f'modo cambiado a {modo}'}).encode('utf-8')
                        respuesta = _build_http_response(200, 'application/json', resp)
                    except Exception as e:
                        resp = json.dumps({'error': str(e)}).encode('utf-8')
                        respuesta = _build_http_response(400, 'application/json', resp)
                    await loop_local.sock_sendall(cli_sock, respuesta)

                elif ruta == '/api/comando':
                    try:
                        data_json = json.loads(body.decode('utf-8', errors='replace')) if body else {}
                        accion = data_json.get('accion', '')
                        params = data_json.get('params', {})
                        resultado = await cliente._ejecutar_comando(accion, params)
                        resp = json.dumps(resultado).encode('utf-8')
                        respuesta = _build_http_response(200, 'application/json', resp)
                    except Exception as e:
                        resp = json.dumps({'error': str(e)}).encode('utf-8')
                        respuesta = _build_http_response(400, 'application/json', resp)
                    await loop_local.sock_sendall(cli_sock, respuesta)

                else:
                    respuesta = _build_http_response(404, 'text/plain', b'not found')
                    await loop_local.sock_sendall(cli_sock, respuesta)

        except Exception as e:
            logger.debug(f'error http: {type(e).__name__}')
        finally:
            try:
                cli_sock.close()
            except Exception:
                pass

    async def bucle_http():
        while cliente.running:
            try:
                cli, addr = await loop_local.sock_accept(server_sock)
                asyncio.create_task(manejar_http(cli, addr))
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(0.1)

    return bucle_http


# ============================================================================
# main
# ============================================================================

async def main():
    """punto de entrada principal del agente pcbot."""
    cliente = pcbot_cliente()
    await cliente.inicializar()

    logger.info(f'pcbot iniciado: {cliente.pcbot_id}')
    logger.info(f'perfiles registrados: {len(cliente.perfiles_registrados)}')

    # tareas concurrentes
    tareas = [
        asyncio.create_task(cliente.conectar_pcmaster()),
        asyncio.create_task(cliente.iniciar_servidor_ui()),
        asyncio.create_task(cliente._watchdog_colgados()),
    ]

    # servidor http
    http_task = asyncio.create_task(iniciar_servidor_http(cliente)())
    tareas.append(http_task)

    try:
        await asyncio.gather(*tareas)
    except KeyboardInterrupt:
        logger.info('detenido por usuario')
    except Exception as e:
        logger.error(f'error en main: {e}')
    finally:
        cliente.running = False
        for t in tareas:
            t.cancel()

        # cerrar todos los perfiles abiertos
        for perfil_id, info in list(cliente.perfiles_abiertos.items()):
            try:
                if info.get('page'):
                    await info['page'].close()
                if info.get('context'):
                    await info['context'].close()
                if info.get('browser'):
                    await info['browser'].close()
            except Exception:
                pass

        # cerrar playwright
        global _playwright_inst
        if _playwright_inst:
            try:
                await _playwright_inst.stop()
            except Exception:
                pass

        logger.info('pcbot detenido')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f'error fatal: {e}')
        sys.exit(1)