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
        self._profile_manager = None
        self._orchestrator = None

        # contadores de heartbeat
        self._heartbeats_enviados = 0
        self._acks_recibidos = 0
        self._ultimo_heartbeat_ts = 0.0
        self._ultimo_ack_ts = 0.0
        self._handshake_ok_recibido = False

    def set_profile_manager(self, pm):
        """asigna el profile manager para incluir datos de perfiles en heartbeat."""
        self._profile_manager = pm

    def set_orchestrator(self, orch):
        """asigna el orchestrator para incluir datos de pedidos activos en heartbeat."""
        self._orchestrator = orch

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
    # estado publico del heartbeat
    # --------------------------------------------------------------
    def get_heartbeat_status(self) -> dict:
        """devuelve estadisticas de heartbeat para monitoreo."""
        ahora = time.time()
        segs_desde_ultimo_hb = 0.0
        if self._ultimo_heartbeat_ts > 0:
            segs_desde_ultimo_hb = ahora - self._ultimo_heartbeat_ts
        segs_desde_ultimo_ack = 0.0
        if self._ultimo_ack_ts > 0:
            segs_desde_ultimo_ack = ahora - self._ultimo_ack_ts
        uptime_sec = int(ahora - self._uptime_start)
        return {
            "conectado": self.connected,
            "heartbeats_enviados": self._heartbeats_enviados,
            "acks_recibidos": self._acks_recibidos,
            "ultimo_heartbeat_hace_seg": round(segs_desde_ultimo_hb, 1),
            "ultimo_ack_hace_seg": round(segs_desde_ultimo_ack, 1),
            "handshake_confirmado": self._handshake_ok_recibido,
            "modo": self.modo,
            "uptime_seg": uptime_sec,
            "uptime_str": f"{uptime_sec // 3600}h {(uptime_sec % 3600) // 60}m",
            "intentos_reconexion": self._intentos_ws,
        }

    def get_conexion_status(self) -> dict:
        """resumen completo de conexion para el comando estado."""
        hb = self.get_heartbeat_status()
        return {
            "pcbot_id": self.pcbot_id,
            "uri": self.uri,
            "heartbeat": hb,
        }

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
                logger.error(f"error en reconexion: {type(e).__name__}: {str(e)[:300]}", exc_info=True)
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
            logger.error(f"_send_plano: ws es None, no se puede enviar {payload.get('tipo', '?')}")
            return
        try:
            # websockets 13+ tiene ws.close_state, websockets 16+ puede no tener .closed
            # usar try/except para detectar cierre sin depender de .closed o .close_state
            await asyncio.wait_for(self.ws.send(json.dumps(payload)), timeout=5)
            logger.info(f"_send_plano: enviado {payload.get('tipo', '?')} correctamente")
        except websockets.ConnectionClosed:
            logger.error(f"_send_plano: websocket cerrado al enviar {payload.get('tipo', '?')}")
        except asyncio.TimeoutError:
            logger.error(f"_send_plano: timeout enviando {payload.get('tipo', '?')} (5s)")
        except AttributeError as e:
            logger.error(f"_send_plano: error de atributo ws: {e}")
        except Exception as e:
            logger.error(f"_send_plano: error enviando {payload.get('tipo', '?')}: {type(e).__name__}: {str(e)[:200]}")

    # --------------------------------------------------------------
    # handshake (siempre plano)
    # --------------------------------------------------------------
    async def _send_handshake(self):
        hd = self.handshake_data
        payload = {
            "tipo": "handshake",
            "pcbot_id": hd.get("pcbot_id", self.pcbot_id),
            "hostname": hd.get("hostname", hd.get("pcbot_id", self.pcbot_id)),
            "ip_local": hd.get("ip_local", "0.0.0.0"),
            "ip_tailscale": hd.get("ip_tailscale", "0.0.0.0"),
            "ip_wan": hd.get("ip_wan", "0.0.0.0"),
            "sistema_operativo": hd.get("sistema_operativo", ""),
            "version_agente": hd.get("version_agente", "8.3"),
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
    # heartbeat (siempre plano) con datos de perfiles
    # --------------------------------------------------------------
    async def _send_heartbeat(self):
        if not self.ws:
            return
        try:
            ahora = time.time()
            uptime_sec = int(ahora - self._uptime_start)
            uptime_str = f"{uptime_sec // 3600}h {(uptime_sec % 3600) // 60}m"
            payload = {
                "tipo": "heartbeat",
                "pcbot_id": self.pcbot_id,
                "uptime": uptime_str,
                "uptime_sec": uptime_sec,
                "modo": self.modo,
                "conectado_desde": _utc_now(),
            }
            # agregar datos de perfiles activos desde profile manager
            perfiles = []
            if self._profile_manager is not None:
                for pid, p in self._profile_manager.profiles.items():
                    entry = {"profile_id": pid}
                    if p.name:
                        entry["nombre"] = p.name
                    activo = p.state.name == "ACTIVE"
                    entry["activo"] = activo
                    if activo and p.inicio > 0:
                        entry["tiempo_conectado_seg"] = int(ahora - p.inicio)
                    entry["url"] = p.current_url or ""
                    perfiles.append(entry)
            payload["perfiles"] = perfiles

            # agregar datos de pedidos activos desde orchestrator
            pedidos = []
            if self._orchestrator is not None:
                now_ts = time.time()
                for pid_pedido, pedido in self._orchestrator._pedidos_activos.items():
                    transcurrido = now_ts - pedido["inicio"]
                    restante = max(0, int(pedido["duracion"] - transcurrido))
                    pedidos.append({
                        "pedido_id": pid_pedido,
                        "url": pedido["url"][:80],
                        "duracion_total": pedido["duracion"],
                        "tiempo_restante": restante,
                        "nivel_comentarios": pedido["nivel_comentarios"],
                        "perfiles_count": len(pedido["perfiles"]),
                    })
            payload["pedidos_activos"] = pedidos

            payload.update(self._hb_extra)
            await self._send_plano(payload)
            # actualizar contadores despues de enviar
            self._heartbeats_enviados += 1
            self._ultimo_heartbeat_ts = ahora
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
        logger.debug(f"mensaje recibido por ws: tipo={tipo}, datos={data}")

        if tipo == "handshake_ok":
            self._handshake_ok_recibido = True
            logger.info("handshake_ok recibido de pcmaster")
            return

        if tipo == "error":
            logger.warning(f"error del servidor: {data.get('mensaje', 'sin detalle')}")
            return

        if tipo == "ack":
            self._acks_recibidos += 1
            self._ultimo_ack_ts = time.time()
            logger.debug(f"ack recibido del servidor (total: {self._acks_recibidos})")
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
        tipo = respuesta.get("tipo", "?")
        ws_ok = self.ws is not None
        logger.info(f"send_response llamado, tipo={tipo}, ws conectado={ws_ok}")
        await self._send_plano(respuesta)
        logger.info(f"send_response: completado envio de {tipo}")