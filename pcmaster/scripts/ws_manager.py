# ws_manager.py - gestor de conexiones websocket por usuario y pcbot. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas
# v2.0: soporte multi-pcbot por usuario (lista en lugar de unico dict)

import json
import logging
from datetime import datetime

logger = logging.getLogger("roxymaster.ws_manager")

# ---------------------------------------------------------------------------
# conexiones websocket activas, referenciadas por usuario_id
# v2: cada usuario puede tener multiples pcbots conectados
# ---------------------------------------------------------------------------
# estructura: {usuario_id: [{"ws": websocket, "pcbot_id": str, "conectado_desde": str}, ...]}
_conexiones_por_usuario: dict = {}

# ---------------------------------------------------------------------------
# conexiones websocket activas, referenciadas por pcbot_id
# ---------------------------------------------------------------------------
_conexiones_por_pcbot: dict = {}


def registrar_conexion(usuario_id: int, pcbot_id: str, websocket) -> bool:
    """registra una conexion websocket asociada a un usuario y su pcbot.
    soporta multiples pcbots por usuario."""
    if not usuario_id or not pcbot_id:
        logger.warning(f"[WS-DIAG] registrar_conexion FALLO: usuario_id={usuario_id} pcbot_id={pcbot_id}")
        return False

    ahora = datetime.now().isoformat()
    uid_str = str(usuario_id)

    # agregar a la lista del usuario (crear si no existe)
    if uid_str not in _conexiones_por_usuario:
        _conexiones_por_usuario[uid_str] = []
    # reemplazar si ya existe un registro para este pcbot_id
    for i, conn in enumerate(_conexiones_por_usuario[uid_str]):
        if conn["pcbot_id"] == pcbot_id:
            _conexiones_por_usuario[uid_str][i] = {
                "ws": websocket,
                "pcbot_id": pcbot_id,
                "conectado_desde": ahora,
                "ultimo_heartbeat": ahora,
            }
            break
    else:
        _conexiones_por_usuario[uid_str].append({
            "ws": websocket,
            "pcbot_id": pcbot_id,
            "conectado_desde": ahora,
            "ultimo_heartbeat": ahora,
        })

    _conexiones_por_pcbot[pcbot_id] = {
        "ws": websocket,
        "usuario_id": usuario_id,
        "conectado_desde": ahora,
        "ultimo_heartbeat": ahora,
    }
    logger.info(f"[WS-DIAG] registrar_conexion OK: usuario={usuario_id} pcbot={pcbot_id}")
    return True


def eliminar_conexion(usuario_id=None, pcbot_id=None):
    """elimina una conexion websocket por usuario_id o pcbot_id."""
    if pcbot_id and pcbot_id in _conexiones_por_pcbot:
        info = _conexiones_por_pcbot.pop(pcbot_id, {})
        uid = info.get("usuario_id", usuario_id)
        if uid:
            uid_str = str(uid)
            if uid_str in _conexiones_por_usuario:
                _conexiones_por_usuario[uid_str] = [
                    c for c in _conexiones_por_usuario[uid_str]
                    if c["pcbot_id"] != pcbot_id
                ]
                if not _conexiones_por_usuario[uid_str]:
                    del _conexiones_por_usuario[uid_str]
        logger.info(f"[WS-DIAG] eliminar_conexion: pcbot={pcbot_id}")

    if usuario_id and str(usuario_id) in _conexiones_por_usuario:
        lista = _conexiones_por_usuario.pop(str(usuario_id), [])
        for conn in lista:
            pid = conn.get("pcbot_id")
            if pid and pid in _conexiones_por_pcbot:
                # solo borrar si es el mismo usuario
                info_pc = _conexiones_por_pcbot.get(pid, {})
                if info_pc.get("usuario_id") == usuario_id:
                    _conexiones_por_pcbot.pop(pid, None)
        logger.info(f"[WS-DIAG] eliminar_conexion: usuario={usuario_id}")


def obtener_ws_por_usuario(usuario_id: int):
    """devuelve el websocket del primer pcbot del usuario, o None."""
    lista = _conexiones_por_usuario.get(str(usuario_id))
    if not lista:
        return None
    return lista[0]["ws"] if lista[0] else None


def obtener_ws_por_pcbot(pcbot_id: str):
    """devuelve el websocket de un pcbot, o None si no esta conectado."""
    datos = _conexiones_por_pcbot.get(pcbot_id)
    return datos["ws"] if datos else None


def obtener_pcbot_de_usuario(usuario_id: int) -> str:
    """devuelve el pcbot_id del primer pcbot asociado, o None."""
    lista = _conexiones_por_usuario.get(str(usuario_id))
    if not lista or not lista[0]:
        logger.info(f"[WS-DIAG] obtener_pcbot_de_usuario({usuario_id}) -> None (sin conexiones activas. claves: {list(_conexiones_por_usuario.keys())})")
        return None
    resultado = lista[0]["pcbot_id"]
    logger.info(f"[WS-DIAG] obtener_pcbot_de_usuario({usuario_id}) -> '{resultado}'")
    return resultado


def obtener_todos_pcbots_conectados() -> list:
    """devuelve lista de todos los pcbot_ids conectados actualmente."""
    return list(_conexiones_por_pcbot.keys())


def obtener_usuario_de_pcbot(pcbot_id: str) -> int:
    """devuelve el usuario_id asociado a un pcbot, o None."""
    datos = _conexiones_por_pcbot.get(pcbot_id)
    return datos["usuario_id"] if datos else None


# ---------------------------------------------------------------------------
# funciones nuevas v2: multi-pcbot
# ---------------------------------------------------------------------------
def obtener_pcbots_de_usuario(usuario_id: int) -> list:
    """devuelve lista de todos los pcbots conectados de un usuario.
    cada elemento: {"pcbot_id": str, "websocket": ws, "conectado_desde": str}"""
    lista = _conexiones_por_usuario.get(str(usuario_id), [])
    resultado = []
    for conn in lista:
        resultado.append({
            "pcbot_id": conn["pcbot_id"],
            "websocket": conn["ws"],
            "conectado_desde": conn.get("conectado_desde", ""),
        })
    logger.info(f"[WS-DIAG] obtener_pcbots_de_usuario({usuario_id}) -> {len(resultado)} pcbots")
    return resultado


def contar_pcbots_usuario(usuario_id: int) -> int:
    """devuelve cuantos pcbots tiene conectados un usuario."""
    return len(_conexiones_por_usuario.get(str(usuario_id), []))


# ---------------------------------------------------------------------------
# funciones originales (sin cambios)
# ---------------------------------------------------------------------------
def listar_conexiones() -> list:
    """lista todas las conexiones activas."""
    resultado = []
    for uid_str, lista in _conexiones_por_usuario.items():
        for conn in lista:
            resultado.append({
                "usuario_id": int(uid_str),
                "pcbot_id": conn.get("pcbot_id", ""),
                "conectado_desde": conn.get("conectado_desde", ""),
            })
    logger.info(f"[WS-DIAG] listar_conexiones: {len(resultado)} activas")
    return resultado


def hay_conexion(usuario_id: int = None, pcbot_id: str = None) -> bool:
    """verifica si existe una conexion activa."""
    if usuario_id:
        lista = _conexiones_por_usuario.get(str(usuario_id), [])
        if lista:
            return True
    if pcbot_id and pcbot_id in _conexiones_por_pcbot:
        return True
    return False


async def enviar_a_usuario(usuario_id: int, mensaje: dict) -> bool:
    """envia un mensaje json al websocket del usuario.
    envia al primer pcbot disponible."""
    ws = obtener_ws_por_usuario(usuario_id)
    if not ws:
        logger.warning(f"[WS-DIAG] no hay ws para usuario {usuario_id}")
        return False
    try:
        await ws.send_json(mensaje)
        return True
    except Exception as e:
        logger.error(f"[WS-DIAG] error enviando ws a usuario {usuario_id}: {e}")
        eliminar_conexion(usuario_id=usuario_id)
        return False


async def enviar_a_pcbot(pcbot_id: str, mensaje: dict) -> bool:
    """envia un mensaje json al websocket del pcbot."""
    ws = obtener_ws_por_pcbot(pcbot_id)
    if not ws:
        logger.warning(f"[WS-DIAG] no hay ws para pcbot {pcbot_id}")
        return False
    try:
        await ws.send_json(mensaje)
        logger.info(f"[WS-DIAG] enviado a pcbot {pcbot_id} tipo={mensaje.get('tipo')}")
        return True
    except Exception as e:
        logger.error(f"[WS-DIAG] error enviando ws a pcbot {pcbot_id}: {e}")
        eliminar_conexion(pcbot_id=pcbot_id)
        return False


async def enviar_comando_al_pcbot(usuario_id: int, comando: dict, pcbot_id: str = None) -> dict:
    """envia un comando al pcbot del usuario via websocket.
    wrapper de alto nivel usado por las apis. devuelve {"exito": bool, "error": str}.
    v2: soporta pcbot_id explicito (asignacion directa) o fallback al primer pcbot."""
    if not pcbot_id:
        pcbot_id = obtener_pcbot_de_usuario(usuario_id)
    if not pcbot_id:
        return {"exito": False, "error": "no hay pcbot conectado para este usuario"}

    # armar mensaje con formato que espera el pcbot
    # el tipo debe ser la accion directa (ej: "asignar"), no "comando"
    mensaje = {
        "tipo": comando.get("tipo", comando.get("accion", "asignar")),
        "parametros": comando.get("parametros", {}),
        "comando_id": comando.get("comando_id", ""),
    }

    ok = await enviar_a_pcbot(pcbot_id, mensaje)
    if not ok:
        return {"exito": False, "error": "no se pudo enviar comando al pcbot"}
    return {"exito": True}


# ---------------------------------------------------------------------------