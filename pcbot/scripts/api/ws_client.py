"""
roxymaster v8.3 - websocket client (pcbot)
conexion ws con mensajes firmados via hmac.
modo offline-first: no bloquea el event loop, inicia portal aunque pcmaster no este.
todo en minusculas, utf-8 sin bom.
"""

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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import shs
import cargador_secretos


def _utc_now() -> str:
    """devuelve iso 8601 en utc compatible con python 3.10+."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class WSClient:
    """cliente websocket hacia pcmaster con modo offline-first."""

    def __init__(self, pcmaster_ip: str = "", pcmaster_port: int = 0, pcbot_id: str = ""):
        if not pcmaster_ip:
            pcmaster_ip = cargador_secretos.obtener_ip_pcmaster()
        if not pcmaster_port:
            pcmaster_port = cargador_secretos.obtener_puerto_ws()
        self.uri = f"ws://{pcmaster_ip}:{pcmaster_port}"
        self.pcbot_id = pcbot_id or os.environ.get("COMPUTERNAME", "unknown")
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
        self._secreto_configurado = False
        self._reconnect_task = None

    def configurar_secreto(self, secreto: str):
        """configura el secreto hmac compartido."""
        if secreto:
            shs.set_secreto(secreto)
            cargador_secretos.guardar_secreto_shs(secreto)
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
    # conexion no-bloqueante: retorna inmediatamente
    # --------------------------------------------------------------
    async def connect(self):
        """inicia conexion ws en background, no bloquea event loop."""
        if websockets is None:
            logger.error("websockets no instalado. no se puede conectar.")
            return
        self.running = True
        self._reconnect_task = asyncio.create_task(self._reconnect_loop())

    async def _reconnect_loop(self):
        """loop de reconexion en tarea separada."""
        intentos = 0
        max_intentos = 5
        delay = 3
        while self.running and intentos < max_intentos:
            try:
                logger.info(f"conectando a pcmaster (intento {intentos + 1}/{max_intentos}): {self.uri}")
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
                intentos = 0
                delay = 3
                logger.info(f"conectado a pcmaster")
                await self._send_handshake()
                await self._single_loop()
            except asyncio.TimeoutError:
                intentos += 1
                logger.warning(f"timeout conexion ({intentos}/{max_intentos})")
            except asyncio.CancelledError:
                break
            except Exception as e:
                intentos += 1
                logger.debug(f"error ws: {type(e).__name__}: {str(e)[:60]}")
            finally:
                self.connected = False
                self.ws = None

            if self.running and intentos < max_intentos:
                d = min(delay, 20)
                logger.info(f"reintentando en {d}s")
                delay = min(delay * 1.5, 20)
                await asyncio.sleep(d)

        logger.info(f"modo offline: {intentos} intentos fallidos (max {max_intentos})")
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
    # envio firmado con hmac
    # --------------------------------------------------------------
    async def send(self, data: str):
        """envia mensaje raw."""
        if not self.ws:
            return
        try:
            await asyncio.wait_for(self.ws.send(data), timeout=5)
        except asyncio.TimeoutError:
            logger.debug("timeout enviando mensaje")
        except Exception:
            pass

    async def _send_firmado(self, payload: dict):
        if not self.ws:
            return
        try:
            msg_firmado = shs.firmar_mensaje(payload)
            await asyncio.wait_for(self.ws.send(msg_firmado), timeout=5)
            logger.debug(f"enviado {payload.get('tipo', '?')}")
        except asyncio.TimeoutError:
            logger.debug("timeout enviando mensaje firmado")
        except Exception as e:
            logger.debug(f"_send_firmado error: {type(e).__name__}: {str(e)[:100]}")

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
            "ts": _utc_now(),
        }
        await self._send_firmado(payload)
        logger.info(f"handshake firmado enviado a pcmaster (modo: {self.modo})")

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
            tokens_gen = (
                self.token_engine_ref.get_balance()
                if self.token_engine_ref
                else 0
            )
            payload = {
                "tipo": "heartbeat",
                "pcbot_id": self.pcbot_id,
                "perfiles_roxy": [
                    {
                        "hash": p.get("hash_interno", p.get("hash", "")),
                        "estado": p.get("estado", "inactive"),
                        "url_actual": p.get("url_actual", ""),
                    }
                    for p in self.perfiles_roxy
                ],
                "perfiles_vip": [
                    {
                        "nombre": p.get("nombre", ""),
                        "estado": p.get("estado", "inactive"),
                        "url_actual": p.get("url_actual", ""),
                    }
                    for p in self.perfiles_vip
                ],
                "tokens_generados": tokens_gen,
                "uptime": uptime_str,
                "modo": self.modo,
                "ts": _utc_now(),
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
            logger.warning("firma invalida en mensaje entrante")
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
            logger.error(
                f"error pcmaster: {msg.get('mensaje', msg.get('msg', ''))}"
            )
        elif msg_tipo == "confirmacion_modo":
            logger.info(f"modo confirmado por pcmaster: {msg.get('modo', '')}")

    async def send_result(
        self, command_id: str, success: bool, details: dict = None
    ):
        if not self.connected or not self.ws:
            return
        try:
            payload = {
                "tipo": "resultado",
                "pcbot_id": self.pcbot_id,
                "comando_id": command_id,
                "exito": success,
                "detalles": details or {},
                "ts": _utc_now(),
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
            "ultima_respuesta": (
                int(time.time() - self._last_any_response)
                if self._last_any_response > 0
                else -1
            ),
        }