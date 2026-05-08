# ws_manager.py - gestor de conexiones websocket por usuario y pcbot. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

import json
import logging
from datetime import datetime

logger = logging.getLogger("roxymaster.ws_manager")

# ---------------------------------------------------------------------------
# conexiones websocket activas, referenciadas por usuario_id
# ---------------------------------------------------------------------------
# estructura: {usuario_id: {"ws": websocket, "pcbot_id": str, "conectado_desde": str}}
_conexiones_por_usuario: dict = {}


# ---------------------------------------------------------------------------
# conexiones websocket activas, referenciadas por pcbot_id
# ---------------------------------------------------------------------------
_conexiones_por_pcbot: dict = {}


def registrar_conexion(usuario_id: int, pcbot_id: str, websocket) -> bool:
    """registra una conexion websocket asociada a un usuario y su pcbot."""
    if not usuario_id or not pcbot_id:
        return False

    ahora = datetime.now().isoformat()
    _conexiones_por_usuario[str(usuario_id)] = {
        "ws": websocket,
        "pcbot_id": pcbot_id,
        "conectado_desde": ahora,
        "ultimo_heartbeat": ahora,
    }
    _conexiones_por_pcbot[pcbot_id] = {
        "ws": websocket,
        "usuario_id": usuario_id,
        "conectado_desde": ahora,
        "ultimo_heartbeat": ahora,
    }
    logger.info(f"ws_registrado: usuario={usuario_id} pcbot={pcbot_id}")
    return True


def eliminar_conexion(usuario_id=None, pcbot_id=None):
    """elimina una conexion websocket por usuario_id o pcbot_id."""
    if usuario_id and str(usuario_id) in _conexiones_por_usuario:
        info = _conexiones_por_usuario.pop(str(usuario_id), {})
        pid = info.get("pcbot_id", pcbot_id)
        if pid:
            _conexiones_por_pcbot.pop(pid, None)
        logger.info(f"ws_eliminado: usuario={usuario_id}")

    if pcbot_id and pcbot_id in _conexiones_por_pcbot:
        info = _conexiones_por_pcbot.pop(pcbot_id, {})
        uid = info.get("usuario_id", usuario_id)
        if uid:
            _conexiones_por_usuario.pop(str(uid), None)
        logger.info(f"ws_eliminado: pcbot={pcbot_id}")


def obtener_ws_por_usuario(usuario_id: int):
    """devuelve el websocket de un usuario, o None si no esta conectado."""
    datos = _conexiones_por_usuario.get(str(usuario_id))
    return datos["ws"] if datos else None


def obtener_ws_por_pcbot(pcbot_id: str):
    """devuelve el websocket de un pcbot, o None si no esta conectado."""
    datos = _conexiones_por_pcbot.get(pcbot_id)
    return datos["ws"] if datos else None


def obtener_pcbot_de_usuario(usuario_id: int) -> str:
    """devuelve el pcbot_id asociado a un usuario, o None."""
    datos = _conexiones_por_usuario.get(str(usuario_id))
    return datos["pcbot_id"] if datos else None


def obtener_usuario_de_pcbot(pcbot_id: str) -> int:
    """devuelve el usuario_id asociado a un pcbot, o None."""
    datos = _conexiones_por_pcbot.get(pcbot_id)
    return datos["usuario_id"] if datos else None


def listar_conexiones() -> list:
    """lista todas las conexiones activas."""
    resultado = []
    for uid, datos in _conexiones_por_usuario.items():
        resultado.append({
            "usuario_id": int(uid),
            "pcbot_id": datos.get("pcbot_id", ""),
            "conectado_desde": datos.get("conectado_desde", ""),
        })
    return resultado


def hay_conexion(usuario_id: int = None, pcbot_id: str = None) -> bool:
    """verifica si existe una conexion activa."""
    if usuario_id and str(usuario_id) in _conexiones_por_usuario:
        return True
    if pcbot_id and pcbot_id in _conexiones_por_pcbot:
        return True
    return False


async def enviar_a_usuario(usuario_id: int, mensaje: dict) -> bool:
    """envia un mensaje json al websocket del usuario."""
    ws = obtener_ws_por_usuario(usuario_id)
    if not ws:
        logger.warning(f"no hay ws para usuario {usuario_id}")
        return False
    try:
        await ws.send_json(mensaje)
        return True
    except Exception as e:
        logger.error(f"error enviando ws a usuario {usuario_id}: {e}")
        eliminar_conexion(usuario_id=usuario_id)
        return False


async def enviar_a_pcbot(pcbot_id: str, mensaje: dict) -> bool:
    """envia un mensaje json al websocket del pcbot."""
    ws = obtener_ws_por_pcbot(pcbot_id)
    if not ws:
        logger.warning(f"no hay ws para pcbot {pcbot_id}")
        return False
    try:
        await ws.send_json(mensaje)
        return True
    except Exception as e:
        logger.error(f"error enviando ws a pcbot {pcbot_id}: {e}")
        eliminar_conexion(pcbot_id=pcbot_id)
        return False


async def enviar_comando_al_pcbot(usuario_id: int, comando: dict) -> dict:
    """envia un comando al pcbot del usuario via websocket.
    wrapper de alto nivel usado por las apis. devuelve {"exito": bool, "error": str}."""
    pcbot_id = obtener_pcbot_de_usuario(usuario_id)
    if not pcbot_id:
        return {"exito": False, "error": "no hay pcbot conectado para este usuario"}

    # armar mensaje con formato que espera el pcbot
    mensaje = {
        "tipo": "comando",
        "accion": comando.get("tipo", comando.get("accion", "desconocido")),
        "parametros": comando.get("parametros", {}),
        "comando_id": comando.get("comando_id", ""),
    }

    ok = await enviar_a_pcbot(pcbot_id, mensaje)
    if not ok:
        return {"exito": False, "error": "no se pudo enviar comando al pcbot"}
    return {"exito": True}


# ---------------------------------------------------------------------------
# alias de compatibilidad (para import desde otros modulos)
# ---------------------------------------------------------------------------
ws_connections = _conexiones_por_usuario