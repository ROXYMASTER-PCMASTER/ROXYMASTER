"""
roxymaster v8.3 - orchestrator local (pcbot)
ejecuta comandos recibidos de pcmaster via websocket.
maneja open_url, detener, comentar, estado y comandos de sistema.
incluye comando recargar_perfiles que consulta workspaces y perfiles via apikey.
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
        self.ws_client = None  # se asigna desde main.py

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
        elif cmd_type == "configurar_apikey":
            result = await self._cmd_configurar_apikey(params, cmd_id)
        elif cmd_type == "conexion":
            result = await self._cmd_conexion(params, cmd_id)
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

    async def _cmd_configurar_apikey(self, params: dict, cmd_id: str) -> dict:
        """recibe apikey de roxybrowser desde pcmaster, configura la api
        y devuelve los perfiles detectados con hash_interno, workspace, status."""
        apikey = params.get("apikey", params.get("api_key", ""))
        if not apikey:
            return {"ok": False, "error": "apikey requerida"}

        if self.roxy is None:
            return {"ok": False, "error": "no hay api de roxybrowser configurada en el sistema"}

        # configurar la apikey en roxybrowser api
        self.roxy.set_api_key(apikey)

        # probar conexion con la apikey
        ping_ok = self.roxy.ping()
        if not ping_ok:
            return {
                "ok": False,
                "error": f"roxybrowser no responde con la apikey en {self.roxy.base}",
                "apikey_configurada": True,
                "roxy_ping": False,
            }

        # obtener perfiles detallados (id, name, hash_interno, workspace, status)
        version = self.roxy.get_version()
        workspace_id = self.roxy._workspace_id
        perfiles_detallados = []
        try:
            perfiles_detallados = self.roxy.get_profiles_detallados()
        except Exception as e:
            logger.error(f"error obteniendo perfiles detallados: {e}")

        resultado = {
            "ok": True,
            "tipo": "configurar_apikey",
            "apikey_configurada": True,
            "datos": {
                "roxy_version": version,
                "workspace_id": workspace_id,
                "roxy_ping": True,
                "perfiles_count": len(perfiles_detallados),
                "perfiles": perfiles_detallados,
                "base_url": self.roxy.base,
            },
        }

        logger.info(f"apikey configurada: {len(perfiles_detallados)} perfiles detectados")

        # registrar perfiles en profile manager
        if perfiles_detallados and self.pm is not None:
            try:
                self.pm.register_profiles(perfiles_detallados)
                logger.info(f"perfiles registrados en profilemanager: {len(perfiles_detallados)}")
            except Exception as e:
                logger.error(f"error registrando perfiles en pm: {e}")

        return resultado

    async def _cmd_estado(self, params: dict, cmd_id: str) -> dict:
        """devuelve estado completo del pcbot, incluyendo heartbeat."""
        states = self.pm.get_all_states() if self.pm else {}
        conexion_info = {}
        if self.ws_client is not None:
            try:
                if hasattr(self.ws_client, 'get_conexion_status'):
                    conexion_info = self.ws_client.get_conexion_status()
                elif hasattr(self.ws_client, 'get_heartbeat_status'):
                    conexion_info = {
                        "pcbot_id": getattr(self.ws_client, 'pcbot_id', 'unknown'),
                        "heartbeat": self.ws_client.get_heartbeat_status(),
                    }
            except Exception as e:
                conexion_info = {"error": str(e)}
        return {
            "ok": True,
            "estado": {
                "conexion": conexion_info,
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

    async def _cmd_conexion(self, params: dict, cmd_id: str) -> dict:
        """devuelve datos de roxybrowser y conexion para pcmaster."""
        datos_roxy = {}
        ping_ok = False
        perfiles = []
        version = "unknown"

        if self.roxy is not None:
            try:
                ping_ok = self.roxy.ping()
                if ping_ok:
                    perfiles = self.roxy.get_profiles()
                    version = self.roxy.get_version()
                    datos_roxy = {
                        "ping": ping_ok,
                        "version": version,
                        "perfiles_count": len(perfiles),
                        "perfiles": [
                            {
                                "id": p.get("id", ""),
                                "name": p.get("name", p.get("id", "")),
                                "status": p.get("status", p.get("estado", "unknown")),
                            }
                            for p in perfiles[:50]
                        ],
                    }
                else:
                    datos_roxy = {"ping": False, "error": f"roxybrowser no responde en {self.roxy.base}"}
            except Exception as e:
                datos_roxy = {"ping": False, "error": str(e)}
        else:
            datos_roxy = {"ping": False, "error": "no hay api de roxybrowser configurada"}

        estado_ws = {}
        if self.ws_client is not None:
            try:
                if hasattr(self.ws_client, 'get_conexion_status'):
                    estado_ws = self.ws_client.get_conexion_status()
                elif hasattr(self.ws_client, 'get_heartbeat_status'):
                    estado_ws = {
                        "pcbot_id": getattr(self.ws_client, 'pcbot_id', 'unknown'),
                        "heartbeat": self.ws_client.get_heartbeat_status(),
                    }
            except Exception as e:
                estado_ws = {"error": str(e)}

        return {
            "ok": True,
            "tipo": "conexion",
            "datos": {
                "roxybrowser": datos_roxy,
                "ws": estado_ws,
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
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
        logger.info(f"cambio de modo solicitado: {modo}")
        return {"ok": True, "modo": modo}

    async def _cmd_recargar(self, params: dict, cmd_id: str) -> dict:
        """recarga perfiles desde roxybrowser api usando apikey.
        flujo:
        1. recibe roxy_api_key del comando
        2. consulta workspaces remotos asociados a esa apikey
        3. para cada workspace, obtiene la lista de perfiles
        4. envia respuesta estructurada al servidor"""
        if not self.roxy:
            return await self._responder_error(cmd_id, "no hay api de roxybrowser configurada")

        roxy_api_key = params.get("roxy_api_key", "")
        if not roxy_api_key:
            return await self._responder_error(cmd_id, "roxy_api_key requerida")
        
        # paso 1: obtener workspaces asociados a la apikey
        logger.info("consultando workspaces remotos...")
        workspaces = self.roxy.get_workspaces(roxy_api_key)
        if not workspaces:
            logger.warning("no se encontraron workspaces para la apikey")
            return await self._responder_error(cmd_id, "no se encontraron workspaces para la apikey proporcionada")

        logger.info(f"workspaces encontrados: {len(workspaces)}")

        # paso 2: por cada workspace, obtener perfiles
        resultado_workspaces = []
        total_perfiles = 0
        workspace_original = self.roxy._workspace_id

        for ws in workspaces:
            ws_id = ws.get("workspace_id", "")
            ws_nombre = ws.get("nombre", ws_id)

            # cambiar workspace activo temporalmente
            self.roxy.set_workspace_id(ws_id)

            try:
                perfiles_crudos = self.roxy.get_profiles()
                perfiles_normalizados = []
                for p in perfiles_crudos:
                    # extraer campos relevantes: dirId, name, userName, state, horas
                    perfil = {
                        "hash_id": str(p.get("dirId", p.get("id", p.get("hash_interno", "")))),
                        "nombre": p.get("name", p.get("nombre", "")),
                        "userName": p.get("userName", p.get("username", "")),
                        "estado": p.get("state", p.get("status", p.get("estado", "unknown"))),
                        "horas_conectado": float(p.get("horas_conectado", p.get("horas", 0)) or 0),
                    }
                    if perfil["hash_id"]:
                        perfiles_normalizados.append(perfil)

                resultado_workspaces.append({
                    "workspace_id": ws_id,
                    "nombre": ws_nombre,
                    "perfiles": perfiles_normalizados,
                })
                total_perfiles += len(perfiles_normalizados)
                logger.info(f"workspace {ws_nombre}: {len(perfiles_normalizados)} perfiles")
            except Exception as e:
                logger.error(f"error obteniendo perfiles para workspace {ws_id}: {e}")
                resultado_workspaces.append({
                    "workspace_id": ws_id,
                    "nombre": ws_nombre,
                    "error": str(e),
                    "perfiles": [],
                })

        # restaurar workspace original
        if workspace_original:
            self.roxy.set_workspace_id(workspace_original)

        # paso 3: construir respuesta final
        respuesta = {
            "ok": True,
            "tipo": "respuesta_recargar_perfiles",
            "pcbot_id": os.environ.get("COMPUTERNAME", "desconocido"),
            "comando_id": cmd_id,
            "roxy_api_key": roxy_api_key,
            "total_workspaces": len(resultado_workspaces),
            "total_perfiles": total_perfiles,
            "workspaces": resultado_workspaces,
        }

        logger.info(f"recarga completada: {total_perfiles} perfiles en {len(resultado_workspaces)} workspaces")

        # enviar respuesta al servidor via ws
        if self.ws_client is not None:
            try:
                await self.ws_client.send_response(respuesta)
            except Exception as e:
                logger.error(f"error enviando respuesta recarga al servidor: {e}")

        return respuesta

    async def _responder_error(self, cmd_id: str, mensaje: str) -> dict:
        """construye y envia respuesta de error para recargar_perfiles."""
        error_resp = {
            "ok": False,
            "tipo": "error_recargar_perfiles",
            "pcbot_id": os.environ.get("COMPUTERNAME", "desconocido"),
            "comando_id": cmd_id,
            "error": mensaje,
        }
        if self.ws_client is not None:
            try:
                await self.ws_client.send_response(error_resp)
            except Exception:
                pass
        return error_resp

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