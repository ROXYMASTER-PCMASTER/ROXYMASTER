"""
ROXYMASTER v8.0 - WEBSOCKET SERVER (PCMASTER)
Servidor async que acepta conexiones de miles de PCBOTs.
"""

import asyncio
import json
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    import websockets
except ImportError:
    websockets = None


class WSServer:
    def __init__(self, host="0.0.0.0", port=5006):
        self.host = host
        self.port = port
        self.clients = {}
        self.client_data = {}
        self.on_identify = None
        self.on_heartbeat = None
        self.on_command_result = None

    # ------------------------------------------------------------------
    # Eventos
    # ------------------------------------------------------------------
    def set_on_identify(self, handler):
        self.on_identify = handler

    def set_on_heartbeat(self, handler):
        self.on_heartbeat = handler

    def set_on_command_result(self, handler):
        self.on_command_result = handler

    # ------------------------------------------------------------------
    # Inicio del servidor
    # ------------------------------------------------------------------
    async def start(self):
        logger.info(f"PCMASTER WS Server iniciando en {self.host}:{self.port}")
        async with websockets.serve(
            self._handle_client,
            self.host,
            self.port,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
            max_size=2**20
        ) as server:
            logger.info("Servidor WS activo. Esperando PCBOTs...")
            await asyncio.Future()

    # ------------------------------------------------------------------
    # Manejo de cliente
    # ------------------------------------------------------------------
    async def _handle_client(self, ws, path=None):
        client_id = None
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                    msg_type = msg.get("type", "")
                    pcbot_id = msg.get("pcbot_id", "")

                    if msg_type == "identify":
                        client_id = pcbot_id or str(time.time())
                        self.clients[client_id] = ws
                        self.client_data[client_id] = {
                            "info": msg.get("data", {}),
                            "connected_at": datetime.utcnow().isoformat() + "Z",
                            "last_heartbeat": time.time(),
                            "heartbeats": 0,
                            "commands_sent": 0,
                            "commands_ok": 0,
                            "commands_fail": 0,
                        }
                        await ws.send(json.dumps({"type": "ack", "pcbot_id": client_id}))
                        logger.info(f"IDENTIFY: {client_id}")
                        if self.on_identify:
                            await self.on_identify(client_id, msg.get("data", {}))

                    elif msg_type == "heartbeat":
                        if client_id and client_id in self.client_data:
                            self.client_data[client_id]["last_heartbeat"] = time.time()
                            self.client_data[client_id]["heartbeats"] += 1
                            if msg.get("data"):
                                self.client_data[client_id]["profile_states"] = msg["data"]
                        if self.on_heartbeat:
                            await self.on_heartbeat(client_id, msg.get("data", {}))

                    elif msg_type == "result":
                        logger.info(f"Resultado de {client_id}: OK={msg.get('success')}")
                        if self.on_command_result:
                            await self.on_command_result(client_id, msg)

                    elif msg_type == "pong":
                        pass

                except json.JSONDecodeError:
                    logger.warning("Mensaje WS no JSON recibido")

        except websockets.ConnectionClosed:
            pass
        except Exception as e:
            logger.error(f"Error en WS client: {e}")
        finally:
            if client_id and client_id in self.clients:
                del self.clients[client_id]
                logger.info(f"Desconectado: {client_id}")

    # ------------------------------------------------------------------
    # Enviar comando a un PCBOT
    # ------------------------------------------------------------------
    async def send_command(self, client_id: str, command: dict) -> bool:
        ws = self.clients.get(client_id)
        if not ws:
            logger.warning(f"Cliente {client_id} no conectado")
            return False
        try:
            msg = {
                "type": "command",
                "data": command,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            await ws.send(json.dumps(msg, ensure_ascii=False))
            if client_id in self.client_data:
                self.client_data[client_id]["commands_sent"] += 1
            return True
        except Exception as e:
            logger.error(f"Error enviando comando a {client_id}: {e}")
            return False

    # ------------------------------------------------------------------
    # Broadcast a todos los clientes
    # ------------------------------------------------------------------
    async def broadcast(self, command: dict):
        tasks = []
        for cid in list(self.clients.keys()):
            tasks.append(self.send_command(cid, command))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        ok = sum(1 for r in results if r is True)
        logger.info(f"Broadcast a {len(tasks)} clientes: {ok} exitos")

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------
    def get_client_ids(self) -> list:
        return list(self.clients.keys())

    def get_client_info(self, client_id: str) -> dict:
        return self.client_data.get(client_id, {})

    def get_all_clients(self) -> dict:
        result = {}
        for cid in self.clients:
            result[cid] = {
                "info": self.client_data.get(cid, {}).get("info", {}),
                "connected_at": self.client_data.get(cid, {}).get("connected_at", ""),
                "heartbeats": self.client_data.get(cid, {}).get("heartbeats", 0),
                "commands_sent": self.client_data.get(cid, {}).get("commands_sent", 0),
                "commands_ok": self.client_data.get(cid, {}).get("commands_ok", 0),
                "commands_fail": self.client_data.get(cid, {}).get("commands_fail", 0),
                "profile_states": self.client_data.get(cid, {}).get("profile_states", {}),
                "last_heartbeat_ago": round(time.time() - self.client_data.get(cid, {}).get("last_heartbeat", 0), 1)
            }
        return result

    def get_connected_count(self) -> int:
        return len(self.clients)