# ws_client.py - websocket client (pcbot) con formato json plano
# sin hmac. compatible con server.py de pcmaster v8.3.
# todo en minusculas, utf-8 sin bom

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

try:
    import websockets
except ImportError:
    websockets = None
    logger.error("websockets no instalado. ejecuta: pip install websockets")

# rutas: scripts/ para shs, raiz pcbot_clon/ para cargador_secretos
_script_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = os.path.abspath(os.path.join(_script_dir, ".."))
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

import cargador_secretos


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class WSClient:
    """cliente websocket hacia pcmaster.
    formato json plano (sin hmac).
    handshake: envio identify plano, recibe identify_ok.
    """

    def __init__(self, pcmaster_ip: str = "", pcmaster_port: int = 0, pcbot_id: str = ""):
        if not pcmaster_ip:
            pcmaster_ip = cargador_secretos.obtener_ip_pcmaster()
        if not pcmaster_port:
            pcmaster_port = cargador_secretos.obtener_puerto_ws()
        self.uri = f"ws://{pcmaster_ip}:{pcmaster_port}/ws/{pcbot_id}"
        self.pcbot_id = pcbot_id or os.environ.get("COMPUTERNAME", "unknown")
        self.ws = None
        self.connected = False
        self.running = False
        self.on_command = None
        self.modo = "offline"
        self.heartbeat_interval = 30
        self.handshake_data = {}
        self._hb_extra = {}
        self._uptime_start = time.time()
        self._last_heartbeat_ok = 0
        self._reconnect_task = None
        self._intentos_ws = 0
        self._max_intentos_ws = 999999

    def set_handshake(self, data: dict):
        self.handshake_data = data

    def set_command_handler(self, handler):
        self.on_command = handler

    def update_heartbeat_data(self, data: dict):
        self._hb_extra = data

    def cambiar_modo(self, nuevo_modo: str):
        self.modo = nuevo_modo
        logger.info(f"modo cambiado a: {nuevo_modo}")

    # --------------------------------------------------------------
    # conexion no-bloqueante
    # --------------------------------------------------------------
    async def connect(self):
        if websockets is None:
            logger.error("websockets no instalado. no se puede conectar.")
            return
        self.running = True
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self):
        self._intentos_ws = 0
        delay = 3
        while self.running and self._intentos_ws < self._max_intentos_ws:
            try:
                ws = await asyncio.wait_for(
                    websockets.connect(
                        self.uri,
                        ping_interval=None,
                        ping_timeout=None,
                        close_timeout=5,
                        open_timeout=10,
                        max_size=2 ** 20,
                    ),
                    timeout=12,
                )
                self.ws = ws
                self.connected = True
                self._intentos_ws = 0
                logger.info(f"ws conectado a {self.uri}")
                await self._send_handshake()
                await self._single_loop()
            except asyncio.TimeoutError:
                logger.debug("timeout en conexion ws")
            except websockets.InvalidStatusCode as e:
                logger.warning(f"servidor rechazo conexion: http {e.status_code}")
            except websockets.ConnectionClosed as e:
                logger.warning(f"conexion ws cerrada: {e.code} - {e.reason}")
            except OSError as e:
                logger.warning(f"error de red en ws: {e.strerror if hasattr(e, 'strerror') else e}")
            except Exception as e:
                logger.debug(f"error en reconexion: {type(e).__name__}: {str(e)[:100]}")
            finally:
                self.connected = False
                self.ws = None
                self._intentos_ws += 1

            if self.running and self._intentos_ws < self._max_intentos_ws:
                d = min(delay, 20)
                logger.info(f"reintentando en {d}s")
                delay = min(delay * 1.5, 20)
                await asyncio.sleep(d)

        logger.info(f"modo offline: {self._intentos_ws} intentos fallidos")
        self.connected = False
        self.running = False

    async def disconnect(self):
        self.running = False
        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except (asyncio.CancelledError, Exception):
                pass
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass

    # --------------------------------------------------------------
    # envio en formato json plano (sin firma)
    # --------------------------------------------------------------
    async def _send_plano(self, payload: dict):
        if not self.ws:
            return
        try:
            await asyncio.wait_for(self.ws.send(json.dumps(payload)), timeout=5)
            logger.debug(f"enviado {payload.get('tipo', '?')} plano")
        except asyncio.TimeoutError:
            logger.debug("timeout enviando mensaje plano")
        except Exception as e:
            logger.debug(f"error enviando plano: {type(e).__name__}: {str(e)[:100]}")

    # --------------------------------------------------------------
    # handshake (siempre plano)
    # --------------------------------------------------------------
    async def _send_handshake(self):
        hd = self.handshake_data
        payload = {
            "tipo": "handshake",
            "pcbot_id": hd.get("pcbot_id", self.pcbot_id),
            "usuario": hd.get("usuario", ""),
            "ip_local": hd.get("ip_local", "0.0.0.0"),
            "ip_tailscale": hd.get("ip_tailscale", "0.0.0.0"),
            "ip_wan": hd.get("ip_wan", "0.0.0.0"),
            "perfiles_roxy": hd.get("perfiles_roxy", []),
            "perfiles_vip": hd.get("perfiles_vip", []),
            "navegadores": hd.get("navegadores", []),
            "modo": hd.get("modo", self.modo),
        }
        await self._send_plano(payload)
        logger.info("handshake enviado (plano)")

    # --------------------------------------------------------------
    # loop: heartbeat + recv
    # --------------------------------------------------------------
    async def _single_loop(self):
        while self.running and self.connected and self.ws:
            try:
                now = time.time()
                if now - self._last_heartbeat_ok >= self.heartbeat_interval:
                    await self._send_heartbeat()
                    self._last_heartbeat_ok = now

                try:
                    raw = await asyncio.wait_for(self.ws.recv(), timeout=5)
                    await self._process_recibido(raw)
                except asyncio.TimeoutError:
                    continue
            except websockets.ConnectionClosed as e:
                logger.warning(f"servidor cerro conexion: {e.code} - {e.reason}")
                break
            except Exception:
                logger.debug("error en loop ws")
                break
        self.connected = False
        logger.info("loop ws terminado")

    # --------------------------------------------------------------
    # heartbeat (siempre plano)
    # --------------------------------------------------------------
    async def _send_heartbeat(self):
        if not self.ws:
            return
        try:
            uptime_sec = int(time.time() - self._uptime_start)
            uptime_str = f"{uptime_sec // 3600}h {(uptime_sec % 3600) // 60}m"
            payload = {
                "tipo": "heartbeat",
                "pcbot_id": self.pcbot_id,
                "uptime": uptime_str,
                "uptime_sec": uptime_sec,
                "modo": self.modo,
                "conectado_desde": _utc_now(),
            }
            payload.update(self._hb_extra)
            await self._send_plano(payload)
        except Exception as e:
            logger.debug(f"error enviando heartbeat: {e}")

    # --------------------------------------------------------------
    # procesamiento de mensajes recibidos
    # --------------------------------------------------------------
    async def _process_recibido(self, raw: str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("mensaje json invalido recibido")
            return

        tipo = data.get("tipo", "")

        if tipo == "handshake_ok":
            logger.info("identify_ok recibido de pcmaster")
            return

        if tipo == "error":
            logger.warning(f"error del servidor: {data.get('mensaje', 'sin detalle')}")
            return

        if tipo == "ack":
            logger.debug("ack recibido del servidor")
            return

        if self.on_command:
            try:
                await self.on_command(data)
            except Exception as e:
                logger.error(f"error en handler de comando: {e}")

    # --------------------------------------------------------------
    # envio de respuesta a comando (plano)
    # --------------------------------------------------------------
    async def send_response(self, respuesta: dict):
        await self._send_plano(respuesta)
