# ============================================================================
# orchestrator.py - logica de envio de comandos a pcbot roxymaster v8.3
# ============================================================================

import asyncio
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

import sqlite3

# ---------------------------------------------------------------------------
# configuracion
# ---------------------------------------------------------------------------
_base_dir = Path(__file__).parent.parent.absolute()
_data_dir = _base_dir / 'data'
_db_path = _data_dir / 'roxymaster.db'

# referencia global al servidor websocket (se inyecta desde server.py)
_ws_server = None
_pending_commands: Dict[str, asyncio.Future] = {}


def set_ws_server(server):
    """inyecta la referencia al websocket server para enviar comandos."""
    global _ws_server
    _ws_server = server


def get_ws_server():
    """obtiene la referencia al websocket server."""
    return _ws_server


# ---------------------------------------------------------------------------
# base de datos de comandos
# ---------------------------------------------------------------------------

def init_orchestrator_db():
    """crea las tablas necesarias para el orquestador."""
    conn = sqlite3.connect(str(_db_path))
    c = conn.cursor()
    c.execute('''
        create table if not exists comandos (
            id integer primary key autoincrement,
            comando_id text unique not null,
            tipo text not null,
            pcbot_id text not null,
            datos json not null,
            estado text default 'pendiente'
                check(estado in ('pendiente', 'enviado', 'ejecutando',
                                 'completado', 'fallido', 'cancelado')),
            fecha_creacion text default (datetime('now', 'localtime')),
            fecha_envio text,
            fecha_respuesta text,
            respuesta json
        )
    ''')
    c.execute('''
        create table if not exists urls_asignadas (
            id integer primary key autoincrement,
            url text not null,
            streamer text not null,
            nivel integer default 0,
            perfiles_requeridos integer default 1,
            duracion_minutos integer default 60,
            comentarios_activados integer default 0,
            pcbot_id text,
            estado text default 'pendiente'
                check(estado in ('pendiente', 'asignada', 'en_progreso',
                                 'completada', 'detenida')),
            fecha_creacion text default (datetime('now', 'localtime')),
            fecha_asignacion text,
            fecha_fin text
        )
    ''')
    c.execute('''
        create table if not exists sesiones_activas (
            id integer primary key autoincrement,
            pcbot_id text not null,
            perfil_id text not null,
            url_actual text,
            inicio text default (datetime('now', 'localtime')),
            ultimo_heartbeat text default (datetime('now', 'localtime')),
            estado text default 'activo'
        )
    ''')
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# gestion de comandos
# ---------------------------------------------------------------------------

def generar_comando_id() -> str:
    """genera un id unico para cada comando."""
    return f"cmd_{int(time.time() * 1000)}_{id(time) % 10000:04d}"


async def enviar_comando(pcbot_id: str, tipo: str, datos: dict,
                          timeout: float = 30.0) -> Dict[str, Any]:
    """envia un comando a un pcbot especifico y espera respuesta."""
    ws = get_ws_server()
    if not ws:
        return {'ok': False, 'error': 'servidor websocket no disponible'}

    comando_id = generar_comando_id()
    mensaje = {
        'tipo': 'comando',
        'comando_id': comando_id,
        'accion': tipo,
        'datos': datos,
        'timestamp': datetime.now().isoformat(),
    }

    # registrar en base de datos
    conn = sqlite3.connect(str(_db_path))
    c = conn.cursor()
    c.execute(
        'insert into comandos (comando_id, tipo, pcbot_id, datos, estado) '
        'values (?, ?, ?, ?, ?)',
        (comando_id, tipo, pcbot_id, json.dumps(datos), 'pendiente'))
    conn.commit()
    conn.close()

    # crear future para esperar respuesta
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    _pending_commands[comando_id] = future

    try:
        # enviar via websocket
        await ws.enviar_a_pcbot(pcbot_id, json.dumps(mensaje))

        # actualizar estado a enviado
        conn = sqlite3.connect(str(_db_path))
        c = conn.cursor()
        c.execute(
            "update comandos set estado = 'enviado', "
            "fecha_envio = datetime('now', 'localtime') "
            'where comando_id = ?',
            (comando_id,))
        conn.commit()
        conn.close()

        # esperar respuesta con timeout
        respuesta = await asyncio.wait_for(future, timeout=timeout)
        return respuesta

    except asyncio.TimeoutError:
        conn = sqlite3.connect(str(_db_path))
        c = conn.cursor()
        c.execute(
            "update comandos set estado = 'fallido', "
            "respuesta = json('timeout') where comando_id = ?",
            (comando_id,))
        conn.commit()
        conn.close()
        return {'ok': False, 'error': 'timeout esperando respuesta'}

    except Exception as e:
        conn = sqlite3.connect(str(_db_path))
        c = conn.cursor()
        c.execute(
            "update comandos set estado = 'fallido', "
            "respuesta = json(?) where comando_id = ?",
            (json.dumps({'error': str(e)}), comando_id,))
        conn.commit()
        conn.close()
        return {'ok': False, 'error': str(e)}

    finally:
        _pending_commands.pop(comando_id, None)


def procesar_respuesta_comando(comando_id: str, respuesta: dict):
    """procesa la respuesta de un comando desde un pcbot."""
    # actualizar base de datos
    conn = sqlite3.connect(str(_db_path))
    c = conn.cursor()
    c.execute(
        "update comandos set estado = ?, "
        "fecha_respuesta = datetime('now', 'localtime'), "
        "respuesta = json(?) where comando_id = ?",
        ('completado' if respuesta.get('ok') else 'fallido',
         json.dumps(respuesta), comando_id))
    conn.commit()
    conn.close()

    # resolver el future pendiente
    future = _pending_commands.get(comando_id)
    if future and not future.done():
        future.set_result(respuesta)


# ---------------------------------------------------------------------------
# comandos de alto nivel
# ---------------------------------------------------------------------------

async def asignar_url(url: str, streamer: str, perfiles: int = 1,
                       duracion: int = 60, comentarios: bool = False,
                       pcbot_id: Optional[str] = None,
                       nivel_streamer: int = 0) -> Dict[str, Any]:
    """asigna una url a uno o varios perfiles para que abran y comenten."""
    # registrar la url
    conn = sqlite3.connect(str(_db_path))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        'insert into urls_asignadas (url, streamer, nivel, '
        'perfiles_requeridos, duracion_minutos, comentarios_activados, '
        'pcbot_id) values (?, ?, ?, ?, ?, ?, ?)',
        (url, streamer, nivel_streamer, perfiles, duracion,
         1 if comentarios else 0, pcbot_id))
    url_id = c.lastrowid
    conn.commit()

    # si no se especifica pcbot, buscar el primero disponible
    if not pcbot_id:
        c.execute(
            "select pcbot_id from pcbot_registrados "
            "where estado = 'conectado' limit 1")
        row = c.fetchone()
        pcbot_id = row['pcbot_id'] if row else None

    conn.close()

    if not pcbot_id:
        return {'ok': False, 'error': 'no hay pcbot disponibles'}

    return await enviar_comando(pcbot_id, 'asignar_url', {
        'url': url,
        'perfiles': perfiles,
        'duracion': duracion,
        'comentarios': comentarios,
        'streamer': streamer,
        'url_id': url_id,
    })


async def activar_comentarios(url: str, streamer: str) -> Dict[str, Any]:
    """activa la generacion de comentarios para una url."""
    ws = get_ws_server()
    if not ws:
        return {'ok': False, 'error': 'servidor websocket no disponible'}

    # broadcast a todos los pcbot activos con esa url
    resultados = []
    for pcbot_id in ws.pcbot_conectados():
        resultado = await enviar_comando(pcbot_id, 'activar_comentarios', {
            'url': url,
            'streamer': streamer,
        })
        resultados.append({'pcbot_id': pcbot_id, 'resultado': resultado})

    return {'ok': True, 'resultados': resultados}


async def detener_url(url: str, pcbot_id: Optional[str] = None) -> Dict[str, Any]:
    """detiene la actividad en una url especifica."""
    if pcbot_id:
        return await enviar_comando(pcbot_id, 'detener_url', {'url': url})

    # broadcast a todos
    ws = get_ws_server()
    if not ws:
        return {'ok': False, 'error': 'servidor websocket no disponible'}

    resultados = []
    for pid in ws.pcbot_conectados():
        resultado = await enviar_comando(pid, 'detener_url', {'url': url})
        resultados.append({'pcbot_id': pid, 'resultado': resultado})

    return {'ok': True, 'resultados': resultados}


async def broadcast_comando(tipo: str, datos: dict) -> Dict[str, Any]:
    """envia un comando a todos los pcbot conectados."""
    ws = get_ws_server()
    if not ws:
        return {'ok': False, 'error': 'servidor websocket no disponible'}

    resultados = []
    for pcbot_id in ws.pcbot_conectados():
        resultado = await enviar_comando(pcbot_id, tipo, datos)
        resultados.append({'pcbot_id': pcbot_id, 'resultado': resultado})

    return {'ok': True, 'total': len(resultados), 'resultados': resultados}


# ---------------------------------------------------------------------------
# consultas
# ---------------------------------------------------------------------------

def obtener_comandos_pendientes(pcbot_id: Optional[str] = None) -> List[Dict]:
    """obtiene comandos pendientes o en ejecucion."""
    conn = sqlite3.connect(str(_db_path))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if pcbot_id:
        c.execute(
            "select * from comandos where pcbot_id = ? "
            "and estado in ('pendiente', 'enviado', 'ejecutando') "
            'order by fecha_creacion desc',
            (pcbot_id,))
    else:
        c.execute(
            "select * from comandos "
            "where estado in ('pendiente', 'enviado', 'ejecutando') "
            'order by fecha_creacion desc')
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def obtener_historial_comandos(limite: int = 100) -> List[Dict]:
    """obtiene el historial de comandos."""
    conn = sqlite3.connect(str(_db_path))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        'select * from comandos order by fecha_creacion desc limit ?',
        (limite,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def obtener_urls_asignadas(estado: Optional[str] = None) -> List[Dict]:
    """obtiene las urls asignadas con filtro opcional de estado."""
    conn = sqlite3.connect(str(_db_path))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if estado:
        c.execute(
            'select * from urls_asignadas where estado = ? '
            'order by fecha_creacion desc',
            (estado,))
    else:
        c.execute(
            'select * from urls_asignadas '
            'order by fecha_creacion desc')
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def obtener_sesiones_activas(pcbot_id: Optional[str] = None) -> List[Dict]:
    """obtiene las sesiones activas de visualizacion."""
    conn = sqlite3.connect(str(_db_path))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if pcbot_id:
        c.execute(
            'select * from sesiones_activas where pcbot_id = ?',
            (pcbot_id,))
    else:
        c.execute('select * from sesiones_activas')
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def cancelar_comando(comando_id: str) -> Dict[str, Any]:
    """cancela un comando pendiente."""
    conn = sqlite3.connect(str(_db_path))
    c = conn.cursor()
    c.execute(
        "update comandos set estado = 'cancelado' "
        'where comando_id = ? and estado = ?',
        (comando_id, 'pendiente'))
    conn.commit()
    affected = c.rowcount
    conn.close()

    # resolver el future si existe
    future = _pending_commands.pop(comando_id, None)
    if future and not future.done():
        future.set_result({'ok': False, 'error': 'cancelado'})

    return {'ok': affected > 0, 'afectados': affected}


# ---------------------------------------------------------------------------
# inicializacion
# ---------------------------------------------------------------------------

init_orchestrator_db()