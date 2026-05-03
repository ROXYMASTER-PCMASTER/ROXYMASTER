"""
ROXYMASTER v8.0 - WEBSOCKET CLIENT (PCBOT)
Cliente async que se conecta a PCMASTER via WebSocket.
Envia handshake, heartbeats y recibe comandos de orquestacion.
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
    logger.error("websockets no instalado. Ejecuta: pip install websockets")


class WSClient:
    """
    Cliente WebSocket async hacia PCMASTER.
    Maneja reconexion automatica y cola de comandos pendientes.
    """

    def __init__(self, pcmaster_ip: str, pcmaster_port: int, pcbot_id: str):
        self.uri = f"ws://{pcmaster_ip}:{pcmaster_port}"
        self.pcbot_id = pcbot_id
        self.ws = None
        self.connected = False
        self.running = False
        self.command_queue = asyncio.Queue()
        self.on_command = None  # callback async para comandos
        self.handshake_data = {}
        self.last_heartbeat = 0
        self.heartbeat_interval = 10

    def set_handshake(self, data: dict):
        self.handshake_data = data

    def set_command_handler(self, handler):
        self.on_command = handler

    # ------------------------------------------------------------------
    # Conexion principal
    # ------------------------------------------------------------------
    async def connect(self):
        self.running = True
        while self.running:
            try:
                logger.info(f"Conectando a PCMASTER: {self.uri}")
                async with websockets.connect(
                    self.uri,
                    ping_timeout=10,
                    close_timeout=5,
                    open_timeout=10,
                    max_size=2**20
                ) as ws:
                    self.ws = ws
                    self.connected = True
                    logger.info("Conectado a PCMASTER")

                    await self._send_handshake()
                    await self._run_loop()

            except websockets.ConnectionClosed as e:
                logger.warning(f"Conexion cerrada: {e}")
            except Exception as e:
                logger.error(f"Error conexion WS: {e}")

            self.connected = False
            self.ws = None

            if self.running:
                await asyncio.sleep(5)

    async def disconnect(self):
        self.running = False
        if self.ws:
            await self.ws.close()

    # ------------------------------------------------------------------
    # Handshake
    # ------------------------------------------------------------------
    async def _send_handshake(self):
        msg = {
            "type": "identify",
            "pcbot_id": self.pcbot_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": self.handshake_data
        }
        await self.ws.send(json.dumps(msg, ensure_ascii=False))
        logger.info("Handshake enviado a PCMASTER")

    # ------------------------------------------------------------------
    # Loop principal
    # ------------------------------------------------------------------
    async def _run_loop(self):
        send_task = asyncio.create_task(self._sender_loop())
        recv_task = asyncio.create_task(self._receiver_loop())
        try:
            await asyncio.gather(send_task, recv_task)
        except asyncio.CancelledError:
            pass

    async def _sender_loop(self):
        while self.connected and self.running:
            now = time.time()
            if now - self.last_heartbeat >= self.heartbeat_interval:
                await self.send_heartbeat()
                self.last_heartbeat = now
            await asyncio.sleep(1)

    async def _receiver_loop(self):
        try:
            async for raw in self.ws:
                try:
                    msg = json.loads(raw)
                    await self._process(msg)
                except json.JSONDecodeError:
                    logger.warning(f"Mensaje WS no JSON: {raw[:100]}")
        except websockets.ConnectionClosed:
            pass

    # ------------------------------------------------------------------
    # Procesamiento de mensajes
    # ------------------------------------------------------------------
    async def _process(self, msg: dict):
        msg_type = msg.get("type", "")
        logger.info(f"Mensaje recibido de PCMASTER: {msg_type}")

        if msg_type == "command":
            if self.on_command:
                await self.on_command(msg.get("data", {}))
        elif msg_type == "ack":
            logger.info("PCMASTER ACK recibido")
        elif msg_type == "error":
            logger.error(f"Error desde PCMASTER: {msg.get('message', '')}")
        elif msg_type == "ping":
            await self._send_pong()

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------
    async def send_heartbeat(self):
        if not self.connected or not self.ws:
            return
        try:
            msg = {
                "type": "heartbeat",
                "pcbot_id": self.pcbot_id,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "data": {}
            }
            await self.ws.send(json.dumps(msg, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"Error enviando heartbeat: {e}")

    def update_heartbeat_data(self, data: dict):
        self._hb_extra = data

    async def _send_pong(self):
        try:
            await self.ws.send(json.dumps({"type": "pong", "pcbot_id": self.pcbot_id}))
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Envio de resultados
    # ------------------------------------------------------------------
    async def send_result(self, command_id: str, success: bool, details: dict = None):
        if not self.connected or not self.ws:
            return
        try:
            msg = {
                "type": "result",
                "pcbot_id": self.pcbot_id,
                "command_id": command_id,
                "success": success,
                "details": details or {},
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            await self.ws.send(json.dumps(msg, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"Error enviando resultado: {e}")