# ws_handler.py - manejo de conexiones websocket roxymaster v8.3
import asyncio
import json
import logging
import sqlite3
from pathlib import Path

_base_dir = Path(__file__).parent.parent.absolute()
_db_path = _base_dir / "data" / "roxymaster.db"
logger = logging.getLogger("roxymaster.ws")

# estructuras compartidas
pcbots = {}       # pcbot_id -> datos de conexion
perfiles_map = {}  # perfil_id -> datos
ws_server_ref = None

# alias para compatibilidad con modulos api
_pcbots_conectados = pcbots
_perfiles_globales = perfiles_map


class _WebSocketServerProxy:
    """proxy para acceso al servidor websocket."""

    def __init__(self):
        self.conexiones = {}

    def registrar(self, peer_id, websocket):
        self.conexiones[peer_id] = websocket

    def eliminar(self, peer_id):
        self.conexiones.pop(peer_id, None)

    async def enviar(self, peer_id, mensaje):
        ws = self.conexiones.get(peer_id)
        if ws:
            try:
                await ws.send(json.dumps(mensaje) if isinstance(mensaje, dict) else mensaje)
            except Exception:
                self.eliminar(peer_id)


async def manejar_conexion(websocket, path=None):
    """maneja una conexion websocket entrante."""
    peer = websocket.remote_address
    peer_id = f"{peer[0]}:{peer[1]}"
    logger.info(f"[ws] nueva conexion: {peer_id}")
    try:
        if ws_server_ref:
            ws_server_ref.registrar(peer_id, websocket)
        async for mensaje in websocket:
            try:
                data = json.loads(mensaje)
                tipo = data.get("tipo", "")
                if tipo == "ping":
                    await websocket.send(json.dumps({"tipo": "pong", "ts": data.get("ts", "")}))
                elif tipo == "registro_pcbot":
                    pcbot_id = data.get("pcbot_id", peer_id)
                    pcbots[pcbot_id] = {
                        "pcbot_id": pcbot_id,
                        "ip": peer[0],
                        "conectado": True,
                        "ultimo_ping": asyncio.get_event_loop().time(),
                    }
                    await websocket.send(json.dumps({"tipo": "registro_ok", "pcbot_id": pcbot_id}))
                else:
                    await websocket.send(json.dumps({"tipo": "ack", "recibido": tipo}))
            except json.JSONDecodeError:
                await websocket.send(json.dumps({"tipo": "error", "msg": "json invalido"}))
    except Exception as e:
        logger.error(f"[ws] error {peer_id}: {e}")
    finally:
        logger.info(f"[ws] desconexion: {peer_id}")
        if ws_server_ref:
            ws_server_ref.eliminar(peer_id)


async def enviar(peer_id, mensaje):
    """envia un mensaje a un peer conectado via ws."""
    if ws_server_ref:
        await ws_server_ref.enviar(peer_id, mensaje)


def set_ws_server(server):
    """establece la referencia global al servidor ws."""
    global ws_server_ref
    ws_server_ref = server