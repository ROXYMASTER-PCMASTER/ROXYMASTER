"""
roxymaster v8.3 - orchestrator local (pcbot)
ejecuta comandos recibidos de pcmaster via websocket.
maneja comandos: asignar, open_url, detener, estado, recargar_perfiles, etc.
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
    def __init__(self, profile_manager: ProfileManager, roxy_api=None):
        self.pm = profile_manager
        self.roxy = roxy_api
        self._running_commands = {}
        self._command_history = []
        self._max_history = 50
        self.ws_client = None
        # tareas de cierre automatico por perfil (pedidos con duracion)
        self._cierres_pendientes: dict[str, asyncio.Task] = {}

    async def process_command(self, cmd: dict) -> dict:
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

    def _parse_nivel_comentarios(self, raw_val) -> int:
        """convierte nivel_comentarios (string o int) a entero:
        "basico" -> 0, "normal" -> 1, "vip" -> 2, int directo."""
        if raw_val is None:
            return 0
        if isinstance(raw_val, int):
            return raw_val
        s = str(raw_val).strip().lower()
        niveles = {"basico": 0, "normal": 1, "vip": 2}
        return niveles.get(s, int(s) if s.isdigit() else 0)

    async def _cmd_asignar(self, params: dict, cmd_id: str) -> dict:
        # validar que el servidor envie todos los parametros (sin defaults)
        if "url" not in params:
            return {"ok": False, "error": "parametro obligatorio: url", "comando": "asignar"}
        url = params["url"]
        if not isinstance(url, str) or not url.strip():
            return {"ok": False, "error": "url debe ser string no vacio", "comando": "asignar"}
        url = url.strip()

        try:
            cantidad = int(params.get("cantidad", params.get("cant", 1)))
        except (ValueError, TypeError):
            return {"ok": False, "error": "cantidad debe ser entero", "comando": "asignar"}

        try:
            duracion = int(params.get("duracion", params.get("duracion_min", 60)))
        except (ValueError, TypeError):
            return {"ok": False, "error": "duracion debe ser entero", "comando": "asignar"}

        nivel_comentarios = self._parse_nivel_comentarios(
            params.get("nivel_comentarios", params.get("nivel", 0))
        )

        logger.info(
            f"asignar: cantidad={cantidad}, url={url[:50]}, duracion={duracion}, nivel_comentarios={nivel_comentarios}"
        )
        profiles = list(self.pm.profiles.keys())
        if not profiles:
            return {"ok": False, "error": "no hay perfiles disponibles", "comando": "asignar"}
        cantidad = min(cantidad, len(profiles))
        if cantidad < 1:
            return {"ok": False, "error": "cantidad debe ser >= 1", "comando": "asignar"}
        asignados = profiles[:cantidad]
        resultados = []
        for pid in asignados:
            try:
                success = await self.pm.navigate_to(pid, url)
                if success:
                    p = self.pm.get_profile(pid)
                    if p:
                        p.duracion_min = duracion
                        p.nivel_comentarios = nivel_comentarios
                    resultados.append({"perfil": pid, "ok": True})
                    # lanzar tarea de cierre automatico si la duracion es positiva
                    if duracion > 0:
                        tarea = asyncio.create_task(
                            self._cierre_automatico(pid, duracion)
                        )
                        self._cierres_pendientes[pid] = tarea
                        logger.info(
                            f"tarea de cierre automatico programada para {pid} en {duracion}s"
                        )
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
                    if duracion > 0:
                        tarea = asyncio.create_task(
                            self._cierre_automatico(pid, duracion)
                        )
                        self._cierres_pendientes[pid] = tarea
                else:
                    resultados.append({"perfil": pid, "ok": False})
            except Exception as e:
                resultados.append({"perfil": pid, "ok": False, "error": str(e)})
        return {"ok": True, "resultados": resultados}

    async def _cmd_detener(self, params: dict, cmd_id: str) -> dict:
        """detiene un perfil especifico: cierra el navegador, marca inactivo,
        cancela temporizador pendiente y envia respuesta de confirmacion."""
        # aceptar profile_id, perfil_id, o extraer de perfiles[]
        profile_id = params.get("profile_id", "")
        if not profile_id:
            profile_id = params.get("perfil_id", "")
        if not profile_id:
            lista = params.get("perfiles", params.get("profile_ids", []))
            if lista:
                profile_id = lista[0] if isinstance(lista, list) else ""
        if not profile_id:
            return {"ok": False, "error": "profile_id requerido", "comando": "detener"}

        logger.info(f"detener perfil solicitado: {profile_id}")

        # cancelar tarea de cierre automatico si existe
        tarea = self._cierres_pendientes.pop(profile_id, None)
        if tarea is not None and not tarea.done():
            tarea.cancel()
            logger.info(f"tarea de cierre automatico cancelada para {profile_id}")

        # cerrar el perfil via api roxybrowser
        try:
            ok = await self.pm.close_profile(profile_id)
            if ok:
                logger.info(f"perfil {profile_id} cerrado exitosamente por comando detener")
            else:
                logger.warning(f"close_profile devolvio false para {profile_id}")
        except Exception as e:
            logger.error(f"error cerrando perfil {profile_id}: {e}")
            ok = False

        # enviar respuesta de confirmacion
        respuesta = {
            "tipo": "respuesta_detener",
            "comando_id": cmd_id,
            "perfil_id": profile_id,
            "ok": ok,
        }
        if self.ws_client is not None:
            try:
                await self.ws_client.send_response(respuesta)
                logger.info(f"respuesta_detener enviada para perfil {profile_id}")
            except Exception as e:
                logger.error(f"error enviando respuesta_detener: {e}")

        return respuesta

    async def _cierre_automatico(self, profile_id: str, duracion_seg: int):
        """espera duracion_seg segundos y cierra el perfil.
        si el perfil ya fue cerrado por otro medio, maneja el error sin propagarse."""
        try:
            await asyncio.sleep(duracion_seg)
            logger.info(f"cierre automatico: cerrando perfil {profile_id} tras {duracion_seg}s")
            ok = await self.pm.close_profile(profile_id)
            if ok:
                logger.info(f"cierre automatico: perfil {profile_id} cerrado")
            else:
                logger.warning(f"cierre automatico: no se pudo cerrar {profile_id} (quizas ya cerrado)")
        except asyncio.CancelledError:
            logger.info(f"cierre automatico: cancelado para perfil {profile_id}")
        except Exception as e:
            logger.error(f"cierre automatico: error inesperado en {profile_id}: {e}")
        finally:
            # limpiar referencia si aun esta en el dict
            if self._cierres_pendientes.get(profile_id) is asyncio.current_task():
                self._cierres_pendientes.pop(profile_id, None)

    async def _cmd_detener_url(self, params: dict, cmd_id: str) -> dict:
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
        url = params.get("url", "")
        logger.info(f"comentarios solicitados para url: {url}")
        return {"ok": True, "comando": "comentarios_activar", "url": url, "mensaje": "comentarios activados (pendiente implementacion playwright)"}

    async def _cmd_configurar_apikey(self, params: dict, cmd_id: str) -> dict:
        apikey = params.get("apikey", params.get("api_key", ""))
        if not apikey:
            return {"ok": False, "error": "apikey requerida"}
        if self.roxy is None:
            return {"ok": False, "error": "no hay api de roxybrowser configurada en el sistema"}
        self.roxy.set_api_key(apikey)
        ping_ok = self.roxy.ping()
        if not ping_ok:
            return {"ok": False, "error": f"roxybrowser no responde con la apikey en {self.roxy.base}", "apikey_configurada": True, "roxy_ping": False}
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
        if perfiles_detallados and self.pm is not None:
            try:
                self.pm.register_profiles(perfiles_detallados)
                logger.info(f"perfiles registrados en profilemanager: {len(perfiles_detallados)}")
            except Exception as e:
                logger.error(f"error registrando perfiles en pm: {e}")
        return resultado

    async def _cmd_estado(self, params: dict, cmd_id: str) -> dict:
        states = self.pm.get_all_states() if self.pm else {}
        conexion_info = {}
        if self.ws_client is not None:
            try:
                if hasattr(self.ws_client, 'get_conexion_status'):
                    conexion_info = self.ws_client.get_conexion_status()
                elif hasattr(self.ws_client, 'get_heartbeat_status'):
                    conexion_info = {"pcbot_id": getattr(self.ws_client, 'pcbot_id', 'unknown'), "heartbeat": self.ws_client.get_heartbeat_status()}
            except Exception as e:
                conexion_info = {"error": str(e)}
        return {
            "ok": True,
            "estado": {
                "conexion": conexion_info,
                "perfiles": {
                    "counts": states.get("counts", {}),
                    "profiles": {pid: {"nombre": p.name, "estado": p.state.name.lower(), "url_actual": p.current_url, "duracion_min": p.duracion_min, "nivel_comentarios": p.nivel_comentarios} for pid, p in self.pm.profiles.items()} if self.pm else {},
                },
            },
        }

    async def _cmd_conexion(self, params: dict, cmd_id: str) -> dict:
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
                    datos_roxy = {"ping": ping_ok, "version": version, "perfiles_count": len(perfiles), "perfiles": [{"id": p.get("id", ""), "name": p.get("name", p.get("id", "")), "status": p.get("status", "unknown")} for p in perfiles[:50]]}
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
                    estado_ws = {"pcbot_id": getattr(self.ws_client, 'pcbot_id', 'unknown'), "heartbeat": self.ws_client.get_heartbeat_status()}
            except Exception as e:
                estado_ws = {"error": str(e)}
        return {"ok": True, "tipo": "conexion", "datos": {"roxybrowser": datos_roxy, "ws": estado_ws, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}}

    async def _cmd_navegar(self, params: dict, cmd_id: str) -> dict:
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
        modo = params.get("modo", "pidiendo_ordenes")
        logger.info(f"cambio de modo solicitado: {modo}")
        return {"ok": True, "modo": modo}

    async def _cmd_recargar(self, params: dict, cmd_id: str) -> dict:
        """recarga perfiles desde roxybrowser usando la apikey."""
        if not self.roxy:
            return await self._responder_error(cmd_id, "no hay api de roxybrowser configurada")

        roxy_api_key = params.get("roxy_api_key", "")
        if not roxy_api_key:
            return await self._responder_error(cmd_id, "roxy_api_key requerida")

        self.roxy.set_api_key(roxy_api_key)

        try:
            ws_id = self.roxy.get_workspace_id()
            logger.info(f"DEBUG: workspace_id obtenido = {ws_id}")
        except Exception as e:
            logger.error(f"ERROR en get_workspace_id: {e}")
            ws_id = None

        if not ws_id:
            logger.error("No se pudo obtener workspace_id. Revisa la conexión a RoxyBrowser y la API key.")
            return await self._responder_error(cmd_id, "no se pudo obtener workspace_id de roxybrowser")

        try:
            perfiles = self.roxy.get_profiles(ws_id)
            logger.info(f"DEBUG: perfiles obtenidos = {perfiles}")
        except Exception as e:
            logger.error(f"ERROR en get_profiles: {e}")
            perfiles = []

        if not perfiles:
            logger.warning(f"no se encontraron perfiles para workspace {ws_id}")
            resultado = {"ok": True, "workspace_id": ws_id, "perfiles": []}
        else:
            resultado = {"ok": True, "workspace_id": ws_id, "perfiles": [{"nombre": p["windowName"], "hash": p["dirId"]} for p in perfiles]}

        # LOG ANTES DE ENVIAR
        logger.info(f"Enviando respuesta al servidor: {resultado}")
        logger.info(f"DEBUG: ws_client = {self.ws_client}, connected = {self.ws_client.connected if self.ws_client else None}")
        if self.ws_client is not None:
            try:
                await self.ws_client.send_response({
                    "tipo": "respuesta_recargar_perfiles",
                    "comando_id": cmd_id,
                    **resultado
                })
                logger.info("Respuesta enviada exitosamente (después de await)")
            except Exception as e:
                logger.error(f"error enviando respuesta recarga: {e}", exc_info=True)
        else:
            logger.warning("ws_client es None, no se puede enviar la respuesta")

        return resultado