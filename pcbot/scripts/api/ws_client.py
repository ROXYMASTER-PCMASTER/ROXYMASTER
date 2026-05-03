"""
roxymaster v8.3 - websocket client (pcbot)
conexion ws con mensajes firmados via hmac.
modo offline-first: si no hay conexion, funciona igual.
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
    logger.error("websockets no instalado. ejecuta: pip install websockets")

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import shs


class WSClient:
    """cliente websocket hacia pcmaster con modo offline-first."""

    def __init__(self, pcmaster_ip: str, pcmaster_port: int, pcbot_id: str):
        self.uri = f"ws://{pcmaster_ip}:{pcmaster_port}"
        self.pcbot_id = pcbot_id
        self.ws = None
        self.connected = False
        self.running = False
        self.on_command = None
        self.handshake_data = {}
        self._hb_extra = {}
        self.heartbeat_interval = 10
        self.modo = "pidiendo_ordenes"
        self.perfiles_roxy = []
        self.perfiles_vip = []
        self.token_engine_ref = None
        self._uptime_start = time.time()
        self._last_any_response = 0
        self._last_heartbeat_ok = 0
        self._reconnect_delay = 5
        self._secreto_configurado = False
        self._intentos_offline = 0
        self._max_intentos_offline = 5  # max intentos antes de quedar offline

    def configurar_secreto(self, secreto: str):
        """configura el secreto hmac compartido."""
        if secreto:
            shs.set_secreto(secreto)
            self._secreto_configurado = True
            logger.info("secreto hmac configurado")

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
    # conexion no-bloqueante con limite de intentos
    # --------------------------------------------------------------
    async def connect(self):
        """conecta a pcmaster con timeout y limite de reconexiones."""
        self.running = True
        while self.running and self._intentos_offline < self._max_intentos_offline:
            try:
                logger.info(f"conectando a pcmaster (intento {self._intentos_offline + 1}/{self._max_intentos_offline}): {self.uri}")
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
                self._intentos_offline = 0
                self._reconnect_delay = 5
                logger.info(f"conectado a pcmaster")
                await self._send_handshake()
                await self._single_loop()
            except asyncio.TimeoutError:
                self._intentos_offline += 1
                logger.warning(f"timeout conexion ({self._intentos_offline}/{self._max_intentos_offline})")
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._intentos_offline += 1
                logger.debug(f"error ws: {type(e).__name__}: {str(e)[:60]}")
            finally:
                self.connected = False
                self.ws = None
            if self.running and self._intentos_offline < self._max_intentos_offline:
                d = min(self._reconnect_delay, 20)
                logger.info(f"reintentando en {d}s")
                self._reconnect_delay = min(self._reconnect_delay * 1.5, 20)
                await asyncio.sleep(d)

        # si llegamos aqui, modo offline permanente
        logger.info(f"modo offline: {self._intentos_offline} intentos fallidos")
        self.connected = False
        self.running = False
        # mantener el loop en fondo para no bloquear

    async def disconnect(self):
        self.running = False
        if self.ws:
            try:
                await self.ws.close()
            except Exception:
                pass

    # --------------------------------------------------------------
    # envio firmado con hmac
    # --------------------------------------------------------------
    async def _send_firmado(self, payload: dict):
        if not self.ws:
            return
        try:
            msg_firmado = shs.firmar_mensaje(payload)
            await asyncio.wait_for(self.ws.send(msg_firmado), timeout=5)
        except asyncio.TimeoutError:
            logger.debug("timeout enviando mensaje")
        except Exception:
            pass

    # --------------------------------------------------------------
    # handshake
    # --------------------------------------------------------------
    async def _send_handshake(self):
        hd = self.handshake_data
        payload = {
            "tipo": "registro_pcbot",
            "pcbot_id": hd.get("pcbot_id", self.pcbot_id),
            "usuario": hd.get("usuario", ""),
            "ip_local": hd.get("ip_local", "0.0.0.0"),
            "ip_tailscale": hd.get("ip_tailscale", "0.0.0.0"),
            "ip_wan": hd.get("ip_wan", "0.0.0.0"),
            "perfiles_roxy": hd.get("perfiles_roxy", []),
            "perfiles_vip": hd.get("perfiles_vip", []),
            "navegadores": hd.get("navegadores", []),
            "modo": hd.get("modo", self.modo),
            "ts": datetime.utcnow().isoformat() + "Z",
        }
        await self._send_firmado(payload)
        logger.info(f"handshake firmado enviado a pcmaster (modo: {self.modo})")

    # --------------------------------------------------------------
    # loop: heartbeat + recv
    # --------------------------------------------------------------
    async def _single_loop(self):
        while self.running and self.connected and self.ws:
            try:
                try:
                    await asyncio.wait_for(self.ws.ping(), timeout=5)
                except (asyncio.TimeoutError, Exception):
                    logger.debug("ping fallo, asumiendo desconexion")
                    break

                now = time.time()
                if now - self._last_heartbeat_ok >= self.heartbeat_interval:
                    await self._send_heartbeat()
                    self._last_heartbeat_ok = now

                try:
                    raw = await asyncio.wait_for(self.ws.recv(), timeout=5)
                    await self._process_firmado(raw)
                except asyncio.TimeoutError:
                    continue
            except websockets.ConnectionClosed:
                logger.debug("servidor cerro conexion")
                break
            except Exception:
                logger.debug("error en loop ws")
                break
        self.connected = False
        logger.info("loop ws terminado")

    # --------------------------------------------------------------
    # heartbeat firmado
    # --------------------------------------------------------------
    async def _send_heartbeat(self):
        if not self.ws:
            return
        try:
            uptime_sec = int(time.time() - self._uptime_start)
            uptime_str = f"{uptime_sec // 3600}h {(uptime_sec % 3600) // 60}m"
            tokens_gen = self.token_engine_ref.total() if self.token_engine_ref else 0
            payload = {
                "tipo": "heartbeat",
                "pcbot_id": self.pcbot_id,
                "perfiles_roxy": [
                    {"hash": p.get("hash_interno", p.get("hash", "")),
                     "estado": p.get("estado", "inactive"),
                     "url_actual": p.get("url_actual", "")}
                    for p in self.perfiles_roxy
                ],
                "perfiles_vip": [
                    {"nombre": p.get("nombre", ""),
                     "estado": p.get("estado", "inactive"),
                     "url_actual": p.get("url_actual", "")}
                    for p in self.perfiles_vip
                ],
                "tokens_generados": tokens_gen,
                "uptime": uptime_str,
                "modo": self.modo,
                "ts": datetime.utcnow().isoformat() + "Z",
            }
            await self._send_firmado(payload)
        except Exception:
            pass

    # --------------------------------------------------------------
    # procesamiento de mensajes firmados
    # --------------------------------------------------------------
    async def _process_firmado(self, raw: str):
        if not self._secreto_configurado:
            try:
                msg = json.loads(raw)
                await self._process(msg)
            except json.JSONDecodeError:
                pass
            return
        valido, payload = shs.verificar_mensaje(raw)
        if not valido:
            logger.warning(f"firma invalida en mensaje entrante")
            return
        await self._process(payload)

    async def _process(self, msg: dict):
        msg_tipo = msg.get("tipo", msg.get("type", ""))
        if msg_tipo in ("registro_ok", "ack", "heartbeat_ack"):
            logger.debug(f"pcmaster: {msg_tipo}")
            self._last_any_response = time.time()
        elif msg_tipo == "comando":
            self._last_any_response = time.time()
            if self.on_command:
                await self.on_command(msg.get("data", {}))
        elif msg_tipo == "error":
            logger.error(f"error pcmaster: {msg.get('mensaje', msg.get('msg', ''))}")
        elif msg_tipo == "confirmacion_modo":
            logger.info(f"modo confirmado por pcmaster: {msg.get('modo', '')}")

    async def send_result(self, command_id: str, success: bool, details: dict = None):
        if not self.connected or not self.ws:
            return
        try:
            payload = {
                "tipo": "resultado",
                "pcbot_id": self.pcbot_id,
                "comando_id": command_id,
                "exito": success,
                "detalles": details or {},
                "ts": datetime.utcnow().isoformat() + "Z",
            }
            await self._send_firmado(payload)
        except Exception:
            pass

    # utilidad para consultar estado
    def get_estado(self) -> dict:
        return {
            "conectado": self.connected,
            "uri": self.uri,
            "modo": self.modo,
            "uptime": int(time.time() - self._uptime_start),
            "ultima_respuesta": int(time.time() - self._last_any_response) if self._last_any_response > 0 else -1,
        }