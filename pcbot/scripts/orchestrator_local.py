"""
roxymaster v8.3 - orchestrator local (pcbot)
ejecuta comandos recibidos de pcmaster via websocket.
maneja open_url, detener, comentar, estado y comandos de sistema.
todo en minusculas, utf-8 sin bom.
"""

import asyncio
import logging
import os
import sys
import time

logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.profile_manager import ProfileManager, ProfileState


class OrchestratorLocal:
    """ejecuta comandos de pcmaster en el pcbot local."""

    def __init__(self, profile_manager: ProfileManager, roxy_api=None):
        self.pm = profile_manager
        self.roxy = roxy_api
        self._running_commands = {}
        self._command_history = []
        self._max_history = 50

    async def process_command(self, cmd: dict) -> dict:
        """procesa un comando entrante y devuelve resultado."""
        cmd_type = cmd.get("tipo", cmd.get("type", ""))
        cmd_id = cmd.get("comando_id", cmd.get("id", str(time.time())))
        params = cmd.get("parametros", cmd.get("data", {}))

        logger.info(f"procesando comando: {cmd_type} (id={cmd_id})")

        if cmd_type == "asignar":
            result = await self._cmd_asignar(params, cmd_id)
        elif cmd_type == "open_url":
            result = await self._cmd_open_url(params, cmd_id)
        elif cmd_type == "detener":
            result = await self._cmd_detener(params, cmd_id)
        elif cmd_type == "detener_url":
            result = await self._cmd_detener_url(params, cmd_id)
        elif cmd_type == "comentarios_activar":
            result = await self._cmd_comentarios(params, cmd_id)
        elif cmd_type == "estado":
            result = await self._cmd_estado(params, cmd_id)
        elif cmd_type == "navegar":
            result = await self._cmd_navegar(params, cmd_id)
        elif cmd_type == "cambiar_modo":
            result = await self._cmd_cambiar_modo(params, cmd_id)
        elif cmd_type == "recargar_perfiles":
            result = await self._cmd_recargar(params, cmd_id)
        elif cmd_type == "ping":
            result = {"ok": True, "tipo": "pong", "ts": time.time()}
        else:
            result = {"ok": False, "error": f"tipo de comando desconocido: {cmd_type}"}

        self._command_history.append({
            "id": cmd_id,
            "tipo": cmd_type,
            "resultado": result,
            "ts": time.time(),
        })
        if len(self._command_history) > self._max_history:
            self._command_history = self._command_history[-self._max_history:]

        return result

    async def _cmd_asignar(self, params: dict, cmd_id: str) -> dict:
        """asignar perfiles a una url."""
        cantidad = int(params.get("cantidad", params.get("cant", 1)))
        url = params.get("url", "")
        duracion = int(params.get("duracion", params.get("duracion_min", 60)))

        if not url:
            return {"ok": False, "error": "url requerida"}

        profiles = list(self.pm.profiles.keys())
        if not profiles:
            return {"ok": False, "error": "no hay perfiles disponibles"}

        cantidad = min(cantidad, len(profiles))
        asignados = profiles[:cantidad]

        resultados = []
        for pid in asignados:
            try:
                # usar navigate_to que es el metodo real de profilemanager
                success = await self.pm.navigate_to(pid, url)
                if success:
                    p = self.pm.get_profile(pid)
                    if p:
                        p.duracion_min = duracion
                    resultados.append({"perfil": pid, "ok": True})
                else:
                    resultados.append({"perfil": pid, "ok": False, "error": "fallo al navegar"})
            except Exception as e:
                resultados.append({"perfil": pid, "ok": False, "error": str(e)})

        return {
            "ok": True,
            "comando": "asignar",
            "cantidad_solicitada": cantidad,
            "cantidad_exitosa": sum(1 for r in resultados if r["ok"]),
            "resultados": resultados,
        }

    async def _cmd_open_url(self, params: dict, cmd_id: str) -> dict:
        """abre url en perfiles especificos."""
        url = params.get("url", "")
        perfiles_ids = params.get("perfiles", params.get("profile_ids", []))
        duracion = int(params.get("duracion", params.get("duracion_min", 60)))

        if not url:
            return {"ok": False, "error": "url requerida"}
        if not perfiles_ids:
            return {"ok": False, "error": "lista de perfiles requerida"}

        resultados = []
        for pid in perfiles_ids:
            try:
                success = await self.pm.navigate_to(pid, url)
                if success:
                    p = self.pm.get_profile(pid)
                    if p:
                        p.duracion_min = duracion
                    resultados.append({"perfil": pid, "ok": True})
                else:
                    resultados.append({"perfil": pid, "ok": False})
            except Exception as e:
                resultados.append({"perfil": pid, "ok": False, "error": str(e)})

        return {"ok": True, "resultados": resultados}

    async def _cmd_detener(self, params: dict, cmd_id: str) -> dict:
        """detiene perfiles especificos redirigiendo a portal publico."""
        perfiles_ids = params.get("perfiles", params.get("profile_ids", []))
        if not perfiles_ids:
            perfiles_ids = list(self.pm.profiles.keys())

        portal_url = "https://www.wafabot.com"
        resultados = []
        for pid in perfiles_ids:
            try:
                await self.pm.redirect_to_portal(pid, portal_url)
                resultados.append({"perfil": pid, "ok": True})
            except Exception as e:
                resultados.append({"perfil": pid, "ok": False, "error": str(e)})

        return {"ok": True, "resultados": resultados}

    async def _cmd_detener_url(self, params: dict, cmd_id: str) -> dict:
        """detiene todos los perfiles en una url especifica."""
        url = params.get("url", "")
        if not url:
            return {"ok": False, "error": "url requerida"}

        portal_url = "https://www.wafabot.com"
        afectados = []
        for pid, p in self.pm.profiles.items():
            if p.current_url and url in p.current_url:
                try:
                    await self.pm.redirect_to_portal(pid, portal_url)
                    afectados.append(pid)
                except Exception:
                    pass

        return {"ok": True, "url": url, "perfiles_detenidos": afectados}

    async def _cmd_comentarios(self, params: dict, cmd_id: str) -> dict:
        """activa comentarios en una url (requiere playwright)."""
        url = params.get("url", "")
        logger.info(f"comentarios solicitados para url: {url}")
        return {
            "ok": True,
            "comando": "comentarios_activar",
            "url": url,
            "mensaje": "comentarios activados (pendiente implementacion playwright)",
        }

    async def _cmd_estado(self, params: dict, cmd_id: str) -> dict:
        """devuelve estado completo del pcbot."""
        states = self.pm.get_all_states() if self.pm else {}
        return {
            "ok": True,
            "estado": {
                "perfiles": {
                    "counts": states.get("counts", {}),
                    "profiles": {
                        pid: {
                            "nombre": p.name,
                            "estado": p.state.name.lower(),
                            "url_actual": p.current_url,
                            "duracion_min": p.duracion_min,
                        }
                        for pid, p in self.pm.profiles.items()
                    } if self.pm else {},
                },
            },
        }

    async def _cmd_navegar(self, params: dict, cmd_id: str) -> dict:
        """navega todos los perfiles a una misma url."""
        url = params.get("url", "")
        if not url:
            return {"ok": False, "error": "url requerida"}

        resultados = []
        for pid in self.pm.profiles:
            try:
                success = await self.pm.navigate_to(pid, url)
                resultados.append({"perfil": pid, "ok": success})
            except Exception as e:
                resultados.append({"perfil": pid, "ok": False, "error": str(e)})

        return {"ok": True, "resultados": resultados}

    async def _cmd_cambiar_modo(self, params: dict, cmd_id: str) -> dict:
        """cambia modo de operacion del pcbot."""
        modo = params.get("modo", "pidiendo_ordenes")
        # el modo se maneja en ws_client, solo registrar
        logger.info(f"cambio de modo solicitado: {modo}")
        return {"ok": True, "modo": modo}

    async def _cmd_recargar(self, params: dict, cmd_id: str) -> dict:
        """recarga perfiles desde roxybrowser api."""
        if not self.roxy:
            return {"ok": False, "error": "no hay api de roxybrowser configurada"}
        try:
            perfiles = self.roxy.get_profiles()
            if perfiles:
                self.pm.register_profiles(perfiles)
                return {"ok": True, "perfiles_cargados": len(perfiles)}
            return {"ok": False, "error": "no se obtuvieron perfiles"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_history(self, limit: int = 10) -> list:
        """devuelve historial de comandos ejecutados."""
        return self._command_history[-limit:]

    def get_stats(self) -> dict:
        """estadisticas del orchestrator."""
        return {
            "total_comandos": len(self._command_history),
            "ultimos_comandos": self._command_history[-5:] if self._command_history else [],
            "comandos_ejecutandose": len(self._running_commands),
        }