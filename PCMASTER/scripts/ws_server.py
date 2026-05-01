# ============================================================================
# ROXYMASTER v7.0 - WEBSOCKET SERVER MODULE
# Maneja conexiones WebSocket de PCBOTs
# ============================================================================

import asyncio
import json
import time
import websockets
from typing import Optional

# Los modulos se comparten via el objeto AppState
# que se inyecta al iniciar el servidor


class WSServer:
    """Servidor WebSocket asincrono para recibir conexiones de PCBOTs."""

    def __init__(self, orchestrator, auth_manager, kbt_engine=None):
        self.orchestrator = orchestrator
        self.auth = auth_manager
        self.kbt = kbt_engine
        self._server: Optional[websockets.WebSocketServer] = None

    # ------------------------------------------------------------------
    # Handlers de mensajes entrantes
    # ------------------------------------------------------------------
    async def handle_identify(self, ws, pcbot_id: str, data: dict):
        """Procesa el handshake de identificacion de un PCBOT."""
        info = {
            "ip_local": data.get("ip_local", ""),
            "ip_tailscale": data.get("ip_tailscale", ""),
            "hostname": data.get("hostname", ""),
            "usuario": data.get("usuario", ""),
            "perfiles": data.get("perfiles", [])
        }
        self.orchestrator.registrar_pcbot(pcbot_id, ws, info)

        # Registrar granjero en KBT si existe
        if self.kbt:
            email = data.get("usuario", pcbot_id).lower()
            try:
                if email not in self.kbt._cache_granjeros if hasattr(self.kbt, '_cache_granjeros') else True:
                    self.kbt.registrar_granjero(email)
            except Exception:
                pass

        await ws.send(json.dumps({
            "tipo": "identify_ack",
            "estado": "ok",
            "pcbot_id": pcbot_id,
            "timestamp": time.time()
        }))
        print(f"[WS] PCBOT identificado: {pcbot_id} ({info.get('hostname', '?')}) - {len(info.get('perfiles', []))} perfiles")

    async def handle_heartbeat(self, pcbot_id: str, data: dict):
        """Procesa heartbeat periodico."""
        estados = data.get("estados", {})
        self.orchestrator.heartbeat(pcbot_id, estados)

        # Acumular minutos en KBT para sesiones activas
        if self.kbt and estados:
            try:
                email = pcbot_id.lower()
                # 10 segundos por heartbeat ≈ 0.167 minutos
                minutos = round(10 / 60, 3)
                for _ in range(estados.get("activos", 0)):
                    self.kbt.acumular_minutos(email, "heartbeat", minutos)
            except Exception:
                pass

    async def handle_evento_perfil(self, pcbot_id: str, data: dict):
        """Procesa eventos de perfiles (abierto, cerrado, colgado, etc.)."""
        evento = data.get("evento", "")
        perfil_id = data.get("perfil_id", "")
        print(f"[WS] Evento PCBOT {pcbot_id}: {evento} -> {perfil_id}")

        # Si inicia sesion de visualizacion, crear sesion KBT
        if self.kbt and evento == "inicio_sesion":
            try:
                email = pcbot_id.upper()
                perfil_nombre = data.get("perfil_nombre", perfil_id)
                self.kbt.iniciar_sesion_perfil(email, perfil_nombre)
            except Exception:
                pass

        # Si cierra sesion, validar minutos
        if self.kbt and evento == "fin_sesion":
            try:
                email = pcbot_id.upper()
                minutos = data.get("minutos", 0)
                self.kbt.validar_sesion_perfil(email, data.get("perfil_id", ""))
            except Exception:
                pass

    async def handle_perfiles_update(self, pcbot_id: str, data: dict):
        """Actualiza la lista de perfiles de un PCBOT."""
        perfiles = data.get("perfiles", [])
        if pcbot_id in self.orchestrator.pcbots_info:
            self.orchestrator.pcbots_info[pcbot_id]["perfiles"] = perfiles
            # Re-mapear
            for p in perfiles:
                pid = p.get("id", p.get("nombre", ""))
                if pid:
                    self.orchestrator.perfiles_map[pid] = pcbot_id

    # ------------------------------------------------------------------
    # Handler principal de conexion
    # ------------------------------------------------------------------
    async def handler(self, ws, path):
        """Maneja una conexion WebSocket entrante."""
        pcbot_id = None
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await ws.send(json.dumps({"tipo": "error", "mensaje": "JSON invalido"}))
                    continue

                tipo = msg.get("tipo", "")
                pcbot_id = msg.get("pcbot_id", pcbot_id or "")

                if tipo == "identify":
                    await self.handle_identify(ws, pcbot_id, msg)
                elif tipo == "heartbeat":
                    await self.handle_heartbeat(pcbot_id, msg)
                elif tipo == "evento_perfil":
                    await self.handle_evento_perfil(pcbot_id, msg)
                elif tipo == "perfiles_update":
                    await self.handle_perfiles_update(pcbot_id, msg)
                elif tipo == "log":
                    print(f"[PCBOT:{pcbot_id}] {msg.get('mensaje', '')}")
                else:
                    await ws.send(json.dumps({
                        "tipo": "ack",
                        "ref": tipo,
                        "estado": "recibido"
                    }))

        except websockets.exceptions.ConnectionClosed:
            print(f"[WS] Conexion cerrada: {pcbot_id}")
        except Exception as e:
            print(f"[WS] Error en handler {pcbot_id}: {e}")
        finally:
            if pcbot_id:
                self.orchestrator.remover_pcbot(pcbot_id)

    # ------------------------------------------------------------------
    # Iniciar / Detener
    # ------------------------------------------------------------------
    async def start(self, host: str, port: int):
        """Inicia el servidor WebSocket."""
        self._server = await websockets.serve(
            self.handler,
            host,
            port,
            ping_timeout=30,
            close_timeout=5,
            open_timeout=10
        )
        print(f"[WS] Servidor WebSocket iniciado en ws://{host}:{port}")

    async def stop(self):
        """Detiene el servidor WebSocket."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()