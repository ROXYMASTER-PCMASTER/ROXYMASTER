# ============================================================================
# server.py - servidor principal roxymaster v8.3
# websocket (5006) para pcbot + fastapi (8086) para dashboard y api
# integra: auth, tokenomics, marketplace, orchestrator, shs
# ============================================================================

import asyncio
import json
import os
import sys
import time
import hashlib
import logging
import threading
import queue
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List, Set

import websockets
from fastapi import FastAPI, HTTPException, Request, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import sqlite3

# ---------------------------------------------------------------------------
# configuracion de rutas (minúsculas)
# ---------------------------------------------------------------------------
_base_dir = Path(__file__).parent.parent.absolute()
_scripts_dir = _base_dir / 'scripts'
_data_dir = _base_dir / 'data'
_db_path = _data_dir / 'roxymaster.db'
_portal_html = _base_dir / 'portal.html'

# agregar scripts al path
sys.path.insert(0, str(_scripts_dir))

# ---------------------------------------------------------------------------
# importar modulos del sistema
# ---------------------------------------------------------------------------
from variables_globales import (
    WS_HOST, WS_PORT, HTTP_HOST, HTTP_PORT,
    SECRETO_SISTEMA, TOKEN_ADMIN,
    K, FX, P_TOKEN, G_DEFAULT, BETA_DEFAULT, HH_MULT_DEFAULT,
    COMISION_MARKETPLACE, COMISIONES_RETIRO, LIMITE_RETIRO_USD,
    NIVELES_STREAMER, UPTIME_NIVELES,
    actualizar_variable, obtener_variables,
)
from auth import (
    verificar_token, generar_token, registrar_usuario,
    autenticar_usuario, obtener_usuario_por_id, obtener_usuario_por_email,
    listar_usuarios, cambiar_rol, init_auth_db,
)
from tokenomics import (
    obtener_balance, acreditar_tokens, debitar_tokens,
    obtener_wallet_por_usuario, crear_wallet, registrar_mineria,
    obtener_historial_token, obtener_estadisticas_kbt,
    calcular_recompensa_mineria, ejecutar_quema_inactividad,
    procesar_retiro, init_tokenomics_db,
)
from marketplace import (
    crear_orden, cancelar_orden, ejecutar_orden,
    listar_ordenes_activas, obtener_orden, obtener_historial_ordenes,
    obtener_estadisticas_marketplace, init_marketplace_db,
)
from orchestrator import (
    set_ws_server, enviar_comando, broadcast_comando,
    asignar_url, activar_comentarios, detener_url,
    obtener_comandos_pendientes, obtener_historial_comandos,
    obtener_urls_asignadas, obtener_sesiones_activas,
    cancelar_comando, init_orchestrator_db,
)
from shs import (
    firmar_respuesta, verificar_y_extraer,
    generar_token_sesion, validar_token_sesion,
    registrar_token_sesion, crear_handshake, crear_heartbeat,
    registrar_evento_seguridad, obtener_eventos_seguridad,
)

# ---------------------------------------------------------------------------
# logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger('roxymaster')

# ---------------------------------------------------------------------------
# estado global del servidor
# ---------------------------------------------------------------------------
_pcbots_conectados: Dict[str, Any] = {}  # pcbot_id -> {ws, info, perfiles, ...}
_perfiles_globales: Dict[str, Dict] = {}  # perfil_id -> {pcbot_id, estado, ...}
_comandos_pendientes: Dict[str, asyncio.Future] = {}
_loop = None

# ---------------------------------------------------------------------------
# fastapi app
# ---------------------------------------------------------------------------
app = FastAPI(
    title='roxymaster api v8.3',
    description='api del ecosistema kbt',
    version='8.3.0',
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


# ============================================================================
# helpers - version mejorada con soporte para x-token y body
# ============================================================================

def get_db() -> sqlite3.Connection:
    """obtiene conexion a la base de datos."""
    conn = sqlite3.connect(str(_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


# cache para extraer token del body (se resuelve asincronamente)
_token_cache: Dict[int, Optional[str]] = {}


def _cache_key(request: Request) -> int:
    return id(request)


async def extraer_token(request: Request) -> Optional[str]:
    """extrae el token de autenticacion de la request.

    busca en orden:
    1. header 'x-token' (usado por portal.html y dashboard)
    2. header 'authorization: bearer ...'
    3. query param 'token'
    4. body json 'token' (para peticiones POST)
    """
    # [1] x-token header
    xtoken = request.headers.get('x-token', '').strip()
    if xtoken:
        return xtoken

    # [2] authorization bearer
    auth = request.headers.get('authorization', '')
    if auth.lower().startswith('bearer '):
        return auth[7:].strip()

    # [3] query param
    qp = request.query_params.get('token', '').strip()
    if qp:
        return qp

    # [4] body json (solo para metodos con body)
    if request.method in ('POST', 'PUT', 'PATCH'):
        try:
            # solo intentamos leer el body si no lo hemos leido antes
            cache_k = _cache_key(request)
            if cache_k in _token_cache:
                return _token_cache[cache_k]

            # leer body raw
            body_bytes = await request.body()
            if body_bytes:
                body = json.loads(body_bytes.decode('utf-8'))
                token = body.get('token', '').strip()
                if token:
                    _token_cache[cache_k] = token
                    return token
            _token_cache[cache_k] = None
        except (json.JSONDecodeError, UnicodeDecodeError, Exception):
            _token_cache[_cache_key(request)] = None

    return None


async def verificar_auth(request: Request) -> Optional[tuple]:
    """verifica autenticacion y devuelve (uid, username, rol)."""
    token = await extraer_token(request)
    if not token:
        return None
    return verificar_token(token)


def crear_respuesta(ok: bool, **kwargs) -> Dict:
    """crea una respuesta estandarizada."""
    return {'ok': ok, **kwargs}


# ============================================================================
# endpoints - portal y estaticos
# ============================================================================

@app.get('/')
async def raiz():
    """redirige al portal."""
    if _portal_html.exists():
        return FileResponse(str(_portal_html), media_type='text/html')
    return HTMLResponse('<h1>roxymaster v8.3</h1><p>portal no encontrado</p>')


@app.get('/portal.html')
async def portal():
    """sirve el portal principal."""
    if _portal_html.exists():
        return FileResponse(str(_portal_html), media_type='text/html')
    return HTMLResponse('<h1>portal no encontrado</h1>', status_code=404)


# ============================================================================
# endpoints - autenticacion
# ============================================================================

@app.post('/api/login')
async def api_login(request: Request):
    """inicia sesion con email y contrasena."""
    try:
        data = await request.json()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        recordar = data.get('recordar', False)

        if not email or not password:
            return crear_respuesta(False, error='email y contrasena requeridos')

        resultado = autenticar_usuario(email, password)
        if not resultado:
            return crear_respuesta(False, error='credenciales invalidas')

        uid, username, rol = resultado
        token = generar_token(uid, username, rol)

        return crear_respuesta(True, token=token, uid=uid, username=username, rol=rol)

    except Exception as e:
        return crear_respuesta(False, error=str(e))


@app.post('/api/register')
async def api_register(request: Request):
    """registra un nuevo usuario."""
    try:
        data = await request.json()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        username = data.get('username', email.split('@')[0] if '@' in email else email)
        codigo_referido = data.get('codigo_referido', 'pcmaster')

        if not email or not password:
            return crear_respuesta(False, error='email y contrasena requeridos')

        if len(password) < 6:
            return crear_respuesta(False, error='la contrasena debe tener al menos 6 caracteres')

        resultado = registrar_usuario(email, password, username, codigo_referido)
        if not resultado['ok']:
            return crear_respuesta(False, error=resultado.get('error', 'error al registrar'))

        uid = resultado['uid']
        token = generar_token(uid, username, 'usuario')

        return crear_respuesta(True, token=token, uid=uid, username=username,
                               rol='usuario', wallet=resultado.get('wallet'))

    except Exception as e:
        return crear_respuesta(False, error=str(e))


@app.get('/api/verify')
async def api_verify_get(request: Request):
    """verifica si el token de sesion es valido (GET)."""
    auth = await verificar_auth(request)
    if not auth:
        return crear_respuesta(False, error='token invalido o expirado')

    uid, username, rol = auth
    return crear_respuesta(True, uid=uid, username=username, rol=rol)


@app.post('/api/verify')
async def api_verify_post(request: Request):
    """verifica si el token de sesion es valido (POST)."""
    auth = await verificar_auth(request)
    if not auth:
        return crear_respuesta(False, error='token invalido o expirado')

    uid, username, rol = auth
    return crear_respuesta(True, uid=uid, username=username, rol=rol)


# ============================================================================
# endpoints - dashboard
# ============================================================================

@app.get('/api/dashboard')
async def api_dashboard(request: Request):
    """devuelve datos del dashboard segun el rol del usuario."""
    auth = await verificar_auth(request)
    if not auth:
        return crear_respuesta(False, error='no autenticado')

    uid, username, rol = auth

    # datos comunes
    total_pcbots = len(_pcbots_conectados)
    total_perfiles = len(_perfiles_globales)
    perfiles_activos = sum(1 for p in _perfiles_globales.values() if p.get('estado') == 'activo_en_uso')
    perfiles_espera = sum(1 for p in _perfiles_globales.values() if p.get('estado') == 'activo_en_espera')
    perfiles_inactivos = sum(1 for p in _perfiles_globales.values() if p.get('estado') == 'desconectado')

    base = {
        'ok': True,
        'uid': uid,
        'username': username,
        'rol': rol,
        'total_pcbots': total_pcbots,
        'total_perfiles': total_perfiles,
        'perfiles_activos': perfiles_activos,
        'perfiles_espera': perfiles_espera,
        'perfiles_inactivos': perfiles_inactivos,
    }

    # datos kbt del usuario
    wallet = obtener_wallet_por_usuario(uid)
    balance = obtener_balance(uid) if wallet else 0
    base['balance'] = balance
    base['wallet'] = wallet

    # datos de admin
    if rol == 'admin':
        stats = obtener_estadisticas_kbt()
        base['stats_kbt'] = stats
        base['variables'] = obtener_variables()
        base['pcbots_detalle'] = [
            {
                'pcbot_id': pid,
                'nombre_pc': info.get('nombre_pc', ''),
                'usuario': info.get('usuario', ''),
                'ip': info.get('ip', ''),
                'perfiles': info.get('perfiles', []),
            }
            for pid, info in _pcbots_conectados.items()
        ]
        base['urls_asignadas'] = obtener_urls_asignadas()
        base['comandos_recientes'] = obtener_historial_comandos(50)
        base['eventos_seguridad'] = obtener_eventos_seguridad(50)

    return base


@app.get('/api/mi_estado')
async def api_mi_estado(request: Request):
    """devuelve el estado detallado del usuario autenticado."""
    auth = await verificar_auth(request)
    if not auth:
        return crear_respuesta(False, error='no autenticado')

    uid, username, rol = auth
    wallet = obtener_wallet_por_usuario(uid)
    balance = obtener_balance(uid) if wallet else 0
    historial = obtener_historial_token(uid, 50) if wallet else []

    # buscar pcbot registrados por este usuario
    conn = get_db()
    c = conn.cursor()
    c.execute(
        'select * from pcbot_registrados where usuario_id = ?',
        (uid,))
    pcbots_usuario = [dict(r) for r in c.fetchall()]
    conn.close()

    return crear_respuesta(
        True,
        uid=uid,
        username=username,
        rol=rol,
        balance=balance,
        wallet=wallet,
        historial=historial,
        pcbots=pcbots_usuario,
    )


# ============================================================================
# endpoints - comandos / orquestador
# ============================================================================

@app.post('/api/comando')
async def api_comando(request: Request):
    """ejecuta un comando de orquestacion."""
    auth = await verificar_auth(request)
    if not auth:
        return crear_respuesta(False, error='no autenticado')

    uid, username, rol = auth

    try:
        data = await request.json()
        accion = data.get('accion', '')
        params = data.get('params', {})

        if accion == 'asignar_url':
            url = params.get('url', '')
            streamer = params.get('streamer', username)
            perfiles = params.get('perfiles', 1)
            duracion = params.get('duracion', 60)
            comentarios = params.get('comentarios', False)
            pcbot_id = params.get('pcbot_id', None)

            if not url:
                return crear_respuesta(False, error='url requerida')

            resultado = await asignar_url(
                url=url,
                streamer=streamer,
                perfiles=perfiles,
                duracion=duracion,
                comentarios=comentarios,
                pcbot_id=pcbot_id,
            )
            return resultado

        elif accion == 'activar_comentarios':
            url = params.get('url', '')
            streamer = params.get('streamer', username)
            if not url:
                return crear_respuesta(False, error='url requerida')
            return await activar_comentarios(url, streamer)

        elif accion == 'detener':
            url = params.get('url', '')
            pcbot_id = params.get('pcbot_id', None)
            if not url:
                return crear_respuesta(False, error='url requerida')
            return await detener_url(url, pcbot_id)

        elif accion == 'broadcast':
            tipo = params.get('tipo', 'info')
            mensaje = params.get('datos', {})
            return await broadcast_comando(tipo, mensaje)

        elif accion == 'cancelar':
            comando_id = params.get('comando_id', '')
            return cancelar_comando(comando_id)

        elif accion == 'estado':
            return crear_respuesta(
                True,
                pcbots=len(_pcbots_conectados),
                perfiles=len(_perfiles_globales),
                comandos_pendientes=len(obtener_comandos_pendientes()),
            )

        else:
            return crear_respuesta(False, error=f'accion desconocida: {accion}')

    except Exception as e:
        return crear_respuesta(False, error=str(e))


@app.get('/api/comandos/pendientes')
async def api_comandos_pendientes(request: Request):
    """lista comandos pendientes."""
    auth = await verificar_auth(request)
    if not auth:
        return crear_respuesta(False, error='no autenticado')
    return crear_respuesta(True, comandos=obtener_comandos_pendientes())


@app.get('/api/comandos/historial')
async def api_comandos_historial(request: Request, limite: int = 100):
    """historial de comandos."""
    auth = await verificar_auth(request)
    if not auth:
        return crear_respuesta(False, error='no autenticado')
    return crear_respuesta(True, historial=obtener_historial_comandos(limite))


@app.get('/api/urls')
async def api_urls(request: Request, estado: str = None):
    """lista urls asignadas."""
    auth = await verificar_auth(request)
    if not auth:
        return crear_respuesta(False, error='no autenticado')
    return crear_respuesta(True, urls=obtener_urls_asignadas(estado))


@app.get('/api/sesiones')
async def api_sesiones(request: Request):
    """sesiones activas."""
    auth = await verificar_auth(request)
    if not auth:
        return crear_respuesta(False, error='no autenticado')
    return crear_respuesta(True, sesiones=obtener_sesiones_activas())


# ============================================================================
# endpoints - kbt / tokenomics
# ============================================================================

@app.get('/api/kbt/balance')
async def api_kbt_balance_get(request: Request):
    """obtiene el balance kbt del usuario (GET)."""
    auth = await verificar_auth(request)
    if not auth:
        return crear_respuesta(False, error='no autenticado')
    uid, _, _ = auth
    balance = obtener_balance(uid)
    wallet = obtener_wallet_por_usuario(uid)
    return crear_respuesta(True, balance=balance, wallet=wallet)


@app.post('/api/kbt/balance')
async def api_kbt_balance_post(request: Request):
    """obtiene el balance kbt del usuario (POST, usado por portal.html)."""
    auth = await verificar_auth(request)
    if not auth:
        return crear_respuesta(False, error='no autenticado')
    uid, _, _ = auth
    balance = obtener_balance(uid)
    wallet = obtener_wallet_por_usuario(uid)
    return crear_respuesta(True, balance=balance, wallet=wallet)


@app.get('/api/kbt/historial')
async def api_kbt_historial(request: Request, limite: int = 50):
    """historial de transacciones kbt."""
    auth = await verificar_auth(request)
    if not auth:
        return crear_respuesta(False, error='no autenticado')
    uid, _, _ = auth
    historial = obtener_historial_token(uid, limite)
    return crear_respuesta(True, historial=historial)


@app.post('/api/kbt/retiro')
async def api_kbt_retiro(request: Request):
    """solicita un retiro de tokens a fiat."""
    auth = await verificar_auth(request)
    if not auth:
        return crear_respuesta(False, error='no autenticado')

    uid, _, _ = auth
    try:
        data = await request.json()
        cantidad = data.get('cantidad', 0)
        if cantidad <= 0:
            return crear_respuesta(False, error='cantidad invalida')

        resultado = procesar_retiro(uid, cantidad)
        return resultado
    except Exception as e:
        return crear_respuesta(False, error=str(e))


@app.post('/api/kbt/mineria')
async def api_kbt_mineria(request: Request):
    """registra mineria de tokens (llamado internamente por el sistema)."""
    auth = await verificar_auth(request)
    if not auth:
        return crear_respuesta(False, error='no autenticado')

    try:
        data = await request.json()
        uid = data.get('uid') or auth[0]
        horas = data.get('horas', 0)
        nivel_uptime = data.get('nivel_uptime', 'bronce')
        es_happy_hour = data.get('happy_hour', False)

        resultado = calcular_recompensa_mineria(uid, horas, nivel_uptime, es_happy_hour)
        return resultado
    except Exception as e:
        return crear_respuesta(False, error=str(e))


@app.get('/api/kbt/estadisticas')
async def api_kbt_estadisticas(request: Request):
    """estadisticas globales del token."""
    auth = await verificar_auth(request)
    if not auth:
        return crear_respuesta(False, error='no autenticado')

    stats = obtener_estadisticas_kbt()
    return crear_respuesta(True, estadisticas=stats)


# ============================================================================
# endpoints - marketplace p2p
# ============================================================================

@app.get('/api/marketplace/ordenes')
async def api_marketplace_ordenes(request: Request, tipo: str = None):
    """lista ordenes activas del marketplace."""
    auth = await verificar_auth(request)
    if not auth:
        return crear_respuesta(False, error='no autenticado')

    ordenes = listar_ordenes_activas(tipo)
    return crear_respuesta(True, ordenes=ordenes, total=len(ordenes))


@app.post('/api/marketplace/crear')
async def api_marketplace_crear(request: Request):
    """crea una orden de compra/venta en el marketplace."""
    auth = await verificar_auth(request)
    if not auth:
        return crear_respuesta(False, error='no autenticado')

    uid, username, _ = auth
    try:
        data = await request.json()
        tipo = data.get('tipo', 'venta')  # venta o compra
        cantidad = data.get('cantidad', data.get('cantidad_tokens', 0))
        precio = data.get('precio', data.get('precio_pen', P_TOKEN))

        if cantidad <= 0:
            return crear_respuesta(False, error='cantidad invalida')

        if precio < 0.94 or precio > 1.06:
            return crear_respuesta(False, error='precio fuera de la banda 0.94-1.06 pen')

        wallet = obtener_wallet_por_usuario(uid)
        if not wallet:
            return crear_respuesta(False, error='wallet no encontrada')

        resultado = crear_orden(tipo, wallet, uid, cantidad, precio)
        return resultado
    except Exception as e:
        return crear_respuesta(False, error=str(e))


@app.post('/api/marketplace/ejecutar')
async def api_marketplace_ejecutar(request: Request):
    """ejecuta una orden del marketplace (comprar)."""
    auth = await verificar_auth(request)
    if not auth:
        return crear_respuesta(False, error='no autenticado')

    uid, username, _ = auth
    try:
        data = await request.json()
        orden_id = data.get('orden_id')

        if not orden_id:
            return crear_respuesta(False, error='orden_id requerido')

        wallet_comprador = obtener_wallet_por_usuario(uid)
        if not wallet_comprador:
            return crear_respuesta(False, error='wallet no encontrada')
        resultado = ejecutar_orden(orden_id, wallet_comprador, uid)
        # actualizar balance local
        if resultado.get('ok'):
            wallet = obtener_wallet_por_usuario(uid)
            balance = obtener_balance(uid) if wallet else 0
            resultado['balance'] = balance

        return resultado
    except Exception as e:
        return crear_respuesta(False, error=str(e))


@app.post('/api/marketplace/cancelar')
async def api_marketplace_cancelar(request: Request):
    """cancela una orden propia del marketplace."""
    auth = await verificar_auth(request)
    if not auth:
        return crear_respuesta(False, error='no autenticado')

    uid, _, _ = auth
    try:
        data = await request.json()
        orden_id = data.get('orden_id')
        if not orden_id:
            return crear_respuesta(False, error='orden_id requerido')

        resultado = cancelar_orden(orden_id)
        return resultado
    except Exception as e:
        return crear_respuesta(False, error=str(e))


@app.get('/api/marketplace/historial')
async def api_marketplace_historial(request: Request, limite: int = 50):
    """historial de operaciones del marketplace."""
    auth = await verificar_auth(request)
    if not auth:
        return crear_respuesta(False, error='no autenticado')

    historial = obtener_historial_ordenes(limite)
    return crear_respuesta(True, historial=historial)


@app.get('/api/marketplace/estadisticas')
async def api_marketplace_estadisticas(request: Request):
    """estadisticas del marketplace."""
    auth = await verificar_auth(request)
    if not auth:
        return crear_respuesta(False, error='no autenticado')

    stats = obtener_estadisticas_marketplace()
    return crear_respuesta(True, estadisticas=stats)


# ============================================================================
# endpoints - admin
# ============================================================================

@app.get('/api/admin/variables')
async def api_admin_variables(request: Request):
    """obtiene todas las variables del sistema (solo admin)."""
    auth = await verificar_auth(request)
    if not auth or auth[2] != 'admin':
        return crear_respuesta(False, error='acceso denegado')

    return crear_respuesta(True, variables=obtener_variables())


@app.post('/api/admin/variables')
async def api_admin_actualizar_variable(request: Request):
    """actualiza una variable del sistema (solo admin)."""
    auth = await verificar_auth(request)
    if not auth or auth[2] != 'admin':
        return crear_respuesta(False, error='acceso denegado')

    try:
        data = await request.json()
        nombre = data.get('nombre', '')
        valor = data.get('valor')

        if not nombre:
            return crear_respuesta(False, error='nombre de variable requerido')

        resultado = actualizar_variable(nombre, valor)
        return resultado
    except Exception as e:
        return crear_respuesta(False, error=str(e))


@app.post('/api/admin/variables/restablecer')
async def api_admin_restablecer_variables(request: Request):
    """restablece todas las variables a sus valores predeterminados."""
    auth = await verificar_auth(request)
    if not auth or auth[2] != 'admin':
        return crear_respuesta(False, error='acceso denegado')

    from variables_globales import restablecer_variables
    resultado = restablecer_variables()
    return resultado


@app.get('/api/admin/usuarios')
async def api_admin_usuarios(request: Request):
    """lista todos los usuarios (solo admin)."""
    auth = await verificar_auth(request)
    if not auth or auth[2] != 'admin':
        return crear_respuesta(False, error='acceso denegado')

    usuarios = listar_usuarios()
    return crear_respuesta(True, usuarios=usuarios)


@app.post('/api/admin/usuarios/rol')
async def api_admin_cambiar_rol(request: Request):
    """cambia el rol de un usuario (solo admin)."""
    auth = await verificar_auth(request)
    if not auth or auth[2] != 'admin':
        return crear_respuesta(False, error='acceso denegado')

    try:
        data = await request.json()
        uid = data.get('uid', '')
        nuevo_rol = data.get('rol', 'usuario')

        if not uid:
            return crear_respuesta(False, error='uid requerido')

        resultado = cambiar_rol(uid, nuevo_rol)
        return resultado
    except Exception as e:
        return crear_respuesta(False, error=str(e))


@app.post('/api/admin/kbt/emitir')
async def api_admin_emitir(request: Request):
    """emite tokens a un usuario (solo admin)."""
    auth = await verificar_auth(request)
    if not auth or auth[2] != 'admin':
        return crear_respuesta(False, error='acceso denegado')

    try:
        data = await request.json()
        uid_destino = data.get('uid', '')
        cantidad = data.get('cantidad', 0)
        concepto = data.get('concepto', 'emision_manual')

        if not uid_destino or cantidad <= 0:
            return crear_respuesta(False, error='uid y cantidad requeridos')

        acreditar_tokens(uid_destino, cantidad, concepto)
        return crear_respuesta(True, mensaje=f'{cantidad} kbt emitidos a {uid_destino}')
    except Exception as e:
        return crear_respuesta(False, error=str(e))


@app.post('/api/admin/kbt/quemar')
async def api_admin_quemar(request: Request):
    """quema tokens de un usuario (solo admin)."""
    auth = await verificar_auth(request)
    if not auth or auth[2] != 'admin':
        return crear_respuesta(False, error='acceso denegado')

    try:
        data = await request.json()
        uid_origen = data.get('uid', '')
        cantidad = data.get('cantidad', 0)
        concepto = data.get('concepto', 'quema_manual')

        if not uid_origen or cantidad <= 0:
            return crear_respuesta(False, error='uid y cantidad requeridos')

        resultado = debitar_tokens(uid_origen, cantidad, concepto)
        return resultado
    except Exception as e:
        return crear_respuesta(False, error=str(e))


@app.post('/api/admin/quema_inactividad')
async def api_admin_quema_inactividad(request: Request):
    """ejecuta quema por inactividad manualmente (solo admin)."""
    auth = await verificar_auth(request)
    if not auth or auth[2] != 'admin':
        return crear_respuesta(False, error='acceso denegado')

    resultado = ejecutar_quema_inactividad()
    return resultado


@app.get('/api/admin/seguridad')
async def api_admin_seguridad(request: Request, limite: int = 100):
    """eventos de seguridad (solo admin)."""
    auth = await verificar_auth(request)
    if not auth or auth[2] != 'admin':
        return crear_respuesta(False, error='acceso denegado')

    eventos = obtener_eventos_seguridad(limite)
    return crear_respuesta(True, eventos=eventos)


@app.get('/api/admin/pcbots')
async def api_admin_pcbots(request: Request):
    """lista todos los pcbot registrados con detalle."""
    auth = await verificar_auth(request)
    if not auth or auth[2] != 'admin':
        return crear_respuesta(False, error='acceso denegado')

    detalle = []
    for pid, info in _pcbots_conectados.items():
        perfiles_info = info.get('perfiles', [])
        detalle.append({
            'pcbot_id': pid,
            'nombre_pc': info.get('nombre_pc', 'desconocido'),
            'usuario': info.get('usuario', ''),
            'ip_local': info.get('ip_local', ''),
            'ip_tailscale': info.get('ip_tailscale', ''),
            'ip_wan': info.get('ip_wan', ''),
            'conectado_desde': info.get('conectado_desde', ''),
            'perfiles': perfiles_info,
            'total_perfiles': len(perfiles_info),
            'activos': sum(1 for p in perfiles_info if p.get('estado') == 'activo'),
        })

    # tambien listar registrados pero desconectados
    conn = get_db()
    c = conn.cursor()
    c.execute('select * from pcbot_registrados order by ultima_conexion desc')
    registrados = [dict(r) for r in c.fetchall()]
    conn.close()

    return crear_respuesta(True, conectados=detalle, registrados=registrados)


# ============================================================================
# websocket server - manejo de pcbot
# ============================================================================

async def manejar_conexion(websocket, path=None):
    """maneja la conexion websocket de un pcbot."""
    pcbot_id = None
    token_sesion = None

    try:
        # esperar handshake
        raw = await asyncio.wait_for(websocket.recv(), timeout=30)
        valido, payload = verificar_y_extraer(raw, SECRETO_SISTEMA)

        if not valido or not payload:
            logger.warning('handshake invalido - firma incorrecta')
            await websocket.close(1008, 'handshake invalido')
            return

        if payload.get('tipo') != 'handshake':
            logger.warning(f'tipo de mensaje inesperado: {payload.get("tipo")}')
            await websocket.close(1008, 'se esperaba handshake')
            return

        pcbot_id = payload.get('pcbot_id', '')
        token = payload.get('token', '')
        info_sistema = payload.get('info_sistema', {})

        if not pcbot_id:
            await websocket.close(1008, 'pcbot_id requerido')
            return

        # validar token de sesion
        if not validar_token_sesion(pcbot_id, token):
            # primer conexion: generar y registrar token
            token = generar_token_sesion(pcbot_id)
            registrar_token_sesion(pcbot_id, token)

        token_sesion = token

        # registrar pcbot
        _pcbots_conectados[pcbot_id] = {
            'ws': websocket,
            'info': info_sistema,
            'conectado_desde': datetime.now().isoformat(),
            'ultimo_heartbeat': datetime.now().isoformat(),
            'perfiles': info_sistema.get('perfiles', []),
            'token_sesion': token,
        }

        # registrar perfiles globales
        for perfil in info_sistema.get('perfiles', []):
            pid = perfil.get('perfil_id', f"{pcbot_id}_{perfil.get('nombre', '')}")
            _perfiles_globales[pid] = {
                **perfil,
                'pcbot_id': pcbot_id,
                'ultimo_update': datetime.now().isoformat(),
            }

        # actualizar/insertar en base de datos
        conn = get_db()
        c = conn.cursor()
        c.execute(
            'insert or replace into pcbot_registrados '
            '(pcbot_id, nombre_pc, usuario, ip_local, ip_tailscale, '
            'ip_wan, token_sesion, estado, ultima_conexion) '
            'values (?, ?, ?, ?, ?, ?, ?, ?, datetime("now", "localtime"))',
            (pcbot_id,
             info_sistema.get('nombre_pc', ''),
             info_sistema.get('usuario', ''),
             info_sistema.get('ip_local', ''),
             info_sistema.get('ip_tailscale', ''),
             info_sistema.get('ip_wan', ''),
             token,
             'conectado'))
        conn.commit()
        conn.close()

        # enviar confirmacion
        respuesta = firmar_respuesta({
            'tipo': 'handshake_ok',
            'pcbot_id': pcbot_id,
            'token_sesion': token,
            'mensaje': 'conexion establecida con pcmaster',
        }, SECRETO_SISTEMA)
        await websocket.send(respuesta)

        logger.info(f'pcbot conectado: {pcbot_id} ({info_sistema.get("nombre_pc", "?")})')

        # notificar al orquestador
        set_ws_server(_WebSocketServerProxy())

        # bucle de mensajes
        async for raw_msg in websocket:
            try:
                valido, payload = verificar_y_extraer(raw_msg, SECRETO_SISTEMA)
                if not valido:
                    logger.warning(f'mensaje invalido de {pcbot_id}')
                    continue

                tipo = payload.get('tipo', '')

                if tipo == 'heartbeat':
                    _pcbots_conectados[pcbot_id]['ultimo_heartbeat'] = datetime.now().isoformat()
                    perfiles = payload.get('perfiles', [])
                    _pcbots_conectados[pcbot_id]['perfiles'] = perfiles

                    # actualizar perfiles globales
                    for p in perfiles:
                        pid = p.get('perfil_id', '')
                        if pid:
                            _perfiles_globales[pid] = {
                                **p,
                                'pcbot_id': pcbot_id,
                                'ultimo_update': datetime.now().isoformat(),
                            }

                    # responder heartbeat
                    resp = firmar_respuesta({
                        'tipo': 'heartbeat_ack',
                        'timestamp': int(time.time()),
                    }, SECRETO_SISTEMA)
                    await websocket.send(resp)

                elif tipo == 'respuesta_comando':
                    comando_id = payload.get('comando_id', '')
                    resultado = payload.get('resultado', {})
                    from orchestrator import procesar_respuesta_comando
                    procesar_respuesta_comando(comando_id, resultado)

                elif tipo == 'alerta':
                    logger.warning(f'alerta de {pcbot_id}: {payload.get("mensaje", "")}')

                else:
                    logger.info(f'mensaje de {pcbot_id}: {tipo}')

            except json.JSONDecodeError:
                logger.warning(f'mensaje no json de {pcbot_id}')
            except Exception as e:
                logger.error(f'error procesando mensaje de {pcbot_id}: {e}')

    except asyncio.TimeoutError:
        logger.warning(f'timeout esperando handshake')
    except websockets.exceptions.ConnectionClosed:
        logger.info(f'conexion cerrada: {pcbot_id or "desconocido"}')
    except Exception as e:
        logger.error(f'error en conexion: {e}')
    finally:
        # limpiar al desconectar
        if pcbot_id and pcbot_id in _pcbots_conectados:
            del _pcbots_conectados[pcbot_id]

            # actualizar db
            conn = get_db()
            c = conn.cursor()
            c.execute(
                "update pcbot_registrados set estado = 'desconectado' "
                'where pcbot_id = ?',
                (pcbot_id,))
            conn.commit()
            conn.close()

            # limpiar perfiles de este pcbot
            to_remove = [pid for pid, p in _perfiles_globales.items()
                         if p.get('pcbot_id') == pcbot_id]
            for pid in to_remove:
                del _perfiles_globales[pid]

            logger.info(f'pcbot desconectado: {pcbot_id}')


class _WebSocketServerProxy:
    """proxy para que el orquestador pueda enviar mensajes via websocket."""

    async def enviar_a_pcbot(self, pcbot_id: str, mensaje: str):
        """envia un mensaje a un pcbot especifico."""
        info = _pcbots_conectados.get(pcbot_id)
        if not info:
            raise Exception(f'pcbot {pcbot_id} no conectado')

        ws = info['ws']
        mensaje_firmado = firmar_respuesta(
            json.loads(mensaje), SECRETO_SISTEMA)
        await ws.send(mensaje_firmado)

    def pcbot_conectados(self) -> List[str]:
        """devuelve lista de pcbot conectados."""
        return list(_pcbots_conectados.keys())


# ============================================================================
# tareas periodicas
# ============================================================================

async def tarea_quema_diaria():
    """ejecuta quema por inactividad cada 24 horas."""
    while True:
        await asyncio.sleep(86400)  # 24 horas
        try:
            logger.info('ejecutando quema diaria por inactividad...')
            resultado = ejecutar_quema_inactividad()
            logger.info(f'quema diaria: {resultado}')
        except Exception as e:
            logger.error(f'error en quema diaria: {e}')


async def tarea_limpieza_pcbots():
    """verifica heartbeats y limpia pcbot inactivos."""
    while True:
        await asyncio.sleep(60)
        ahora = datetime.now()
        desconectados = []
        for pid, info in list(_pcbots_conectados.items()):
            try:
                ultimo_hb = datetime.fromisoformat(info.get('ultimo_heartbeat',
                                                            info.get('conectado_desde', '')))
                if (ahora - ultimo_hb).total_seconds() > 120:
                    desconectados.append(pid)
            except Exception:
                desconectados.append(pid)

        for pid in desconectados:
            logger.info(f'pcbot {pid} sin heartbeat, marcando como desconectado')
            try:
                ws = _pcbots_conectados[pid].get('ws')
                if ws:
                    await ws.close()
            except Exception:
                pass
            _pcbots_conectados.pop(pid, None)

            conn = get_db()
            c = conn.cursor()
            c.execute(
                "update pcbot_registrados set estado = 'desconectado' "
                'where pcbot_id = ?',
                (pid,))
            conn.commit()
            conn.close()


# ============================================================================
# inicializacion de bases de datos
# ============================================================================

def init_all_databases():
    """inicializa todas las bases de datos del sistema."""
    _data_dir.mkdir(parents=True, exist_ok=True)
    init_auth_db()
    init_tokenomics_db()
    init_marketplace_db()
    init_orchestrator_db()
    logger.info('bases de datos inicializadas')


# ============================================================================
# main
# ============================================================================

async def iniciar_websocket_server():
    """inicia el servidor websocket para pcbot."""
    logger.info(f'[ws] iniciando en {WS_HOST}:{WS_PORT}')
    async with websockets.serve(
        manejar_conexion,
        WS_HOST,
        WS_PORT,
        ping_interval=30,
        ping_timeout=10,
        close_timeout=5,
        max_size=10 * 1024 * 1024,
    ):
        await asyncio.Future()


async def iniciar_http_server():
    """inicia el servidor fastapi/http."""
    config = uvicorn.Config(
        app,
        host=HTTP_HOST,
        port=HTTP_PORT,
        log_level='warning',
        access_log=False,
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    """punto de entrada principal."""
    global _loop
    _loop = asyncio.get_event_loop()

    print(f'\n{"=" * 60}')
    print(f'  roxymaster v8.3 - pcmaster server')
    print(f'  ws:  {WS_HOST}:{WS_PORT}')
    print(f'  http: {HTTP_HOST}:{HTTP_PORT}')
    print(f'{"=" * 60}\n')

    # inicializar bases de datos
    init_all_databases()

    # inyectar ws server en orchestrator
    set_ws_server(_WebSocketServerProxy())

    # tareas periodicas
    asyncio.create_task(tarea_quema_diaria())
    asyncio.create_task(tarea_limpieza_pcbots())

    # iniciar ambos servidores concurrentemente
    await asyncio.gather(
        iniciar_websocket_server(),
        iniciar_http_server(),
    )


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\nservidor detenido.')
    except Exception as e:
        logger.error(f'error fatal: {e}')
        raise