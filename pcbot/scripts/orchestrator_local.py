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
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.profile_manager import ProfileManager, ProfileState
from orchestrator_local_ext import SchedulerExtension

# bug 3: maximo de pedidos por perfil compartido
MAX_PEDIDOS_POR_PERFIL = 5

# portal de redireccion cuando un pedido termina (en vez de cerrar el perfil)
PORTAL_URL = "https://www.wafabot.com"


class OrchestratorLocal:
    def __init__(self, profile_manager: ProfileManager, roxy_api=None):
        self.pm = profile_manager
        self.roxy = roxy_api
        self._running_commands = {}
        self._command_history = []
        self._max_history = 50
        self.ws_client = None

        # tareas de cierre automatico por perfil (pedidos con duracion)
        # profile_id -> asyncio.Task
        self._cierres_pendientes: dict[str, asyncio.Task] = {}

        # registro de pedidos activos (multi-pedido)
        # pedido_id -> {
        #     "url": str,
        #     "duracion": int,
        #     "nivel_comentarios": int,
        #     "inicio": float,
        #     "perfiles": [pid1, pid2, ...],
        #     "comando_id": str,
        # }
        self._pedidos_activos: dict[str, dict] = {}

        # nueva funcionalidad: pedidos programados
        # comando_id -> asyncio.Task
        self._pedidos_programados: dict[str, asyncio.Task] = {}

    def process_command(self, cmd: dict) -> dict:
        """version sincrona para ser llamada desde ws_client.
        convierte a async y ejecuta en event loop actual."""
        cmd_type = cmd.get("tipo", cmd.get("type", ""))
        cmd_id = cmd.get("comando_id", cmd.get("id", str(time.time())))
        params = cmd.get("parametros", cmd.get("data", {}))

        logger.info(f"procesando comando: {cmd_type} (id={cmd_id})")
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # ya estamos dentro de un loop, crear tarea
                import asyncio

                fut = asyncio.ensure_future(self.process_command_async(cmd_type, cmd_id, params))
                return {"ok": True, "async": True, "comando_id": cmd_id}
            else:
                result = loop.run_until_complete(
                    self.process_command_async(cmd_type, cmd_id, params)
                )
                return result
        except RuntimeError:
            # no hay event loop, crear uno nuevo
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    self.process_command_async(cmd_type, cmd_id, params)
                )
                return result
            finally:
                loop.close()

    async def process_command_async(self, cmd_type: str, cmd_id: str, params: dict) -> dict:
        """version async que ejecuta el comando segun su tipo."""
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
        elif cmd_type == "cancelar":
            result = await self._cmd_cancelar(params, cmd_id)
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
        if s in niveles:
            return niveles[s]
        try:
            return int(s)
        except ValueError:
            return 0

    def _calcular_duracion_max(self, pid: str) -> int:
        """calcula la duracion maxima que necesita un perfil
        basado en todos los pedidos activos que lo usan."""
        p = self.pm.get_profile(pid)
        if not p or not p.pedidos_ids:
            return p.duracion_min if p else 0
        duracion_max = 0
        ahora = time.time()
        for pedido_id in p.pedidos_ids:
            pedido = self._pedidos_activos.get(pedido_id)
            if pedido:
                transcurrido = ahora - pedido["inicio"]
                restante = max(0, pedido["duracion"] - transcurrido)
                duracion_max = max(duracion_max, restante)
        if duracion_max == 0:
            duracion_max = p.duracion_min
        return int(duracion_max)

    def _obtener_restante_pedido(self, pedido_id: str) -> int:
        """devuelve segundos restantes de un pedido activo."""
        pedido = self._pedidos_activos.get(pedido_id)
        if not pedido:
            return 0
        transcurrido = time.time() - pedido["inicio"]
        return max(0, int(pedido["duracion"] - transcurrido))

    async def _programar_pedido(self, comando_id: str, params: dict, segundos_hasta_inicio: float):
        """espera segundos_hasta_inicio y luego ejecuta el pedido como inmediato."""
        try:
            logger.info(
                f"pedido {comando_id} programado para ejecutarse en {segundos_hasta_inicio:.0f}s"
            )
            await asyncio.sleep(segundos_hasta_inicio)
            logger.info(f"pedido {comando_id}: hora de ejecucion llegada, ejecutando...")
            resultado = await self._cmd_asignar_inmediato(params, comando_id)
            # enviar respuesta de ejecucion al ws si es necesario
            if self.ws_client is not None:
                try:
                    await self.ws_client.send_response({
                        "tipo": "respuesta_asignar",
                        "comando_id": comando_id,
                        "programado": False,
                        "ejecutado": True,
                        **resultado,
                    })
                    logger.info(f"respuesta de ejecucion enviada para pedido programado {comando_id}")
                except Exception as e:
                    logger.error(f"error enviando respuesta de ejecucion programada: {e}")
        except asyncio.CancelledError:
            logger.info(f"pedido programado {comando_id} cancelado")
        except Exception as e:
            logger.error(f"error ejecutando pedido programado {comando_id}: {e}")
        finally:
            self._pedidos_programados.pop(comando_id, None)

    async def _cmd_cancelar(self, params: dict, cmd_id: str) -> dict:
        """cancela un pedido programado."""
        pedido_id = params.get("pedido_id", params.get("codigo", ""))
        if not pedido_id:
            return {"ok": False, "error": "pedido_id requerido para cancelar"}
        tarea = self._pedidos_programados.pop(pedido_id, None)
        if tarea is not None and not tarea.done():
            tarea.cancel()
            logger.info(f"pedido programado {pedido_id} cancelado")
            return {"ok": True, "cancelado": True, "pedido_id": pedido_id}
        return {"ok": False, "error": f"no hay pedido programado con id {pedido_id}"}

    async def _cmd_asignar(self, params: dict, cmd_id: str) -> dict:
        """asigna perfiles a un pedido, con soporte de agendamiento por hora.
        si hora_inicio esta presente, programa el pedido para el futuro."""
        # extraer campos de agendamiento (opcionales)
        hora_inicio_str = params.get("hora_inicio", None)
        hora_fin_str = params.get("hora_fin", None)

        # caso c: hora_fin sin hora_inicio -> ignorar hora_fin, inmediato
        if hora_fin_str and not hora_inicio_str:
            logger.info("hora_fin presente sin hora_inicio, se ignora hora_fin")
            hora_fin_str = None

        if hora_inicio_str:
            # caso b: pedido programado
            return await self._cmd_asignar_programado(params, cmd_id, hora_inicio_str, hora_fin_str)

        # caso a y c: pedido inmediato
        return await self._cmd_asignar_inmediato(params, cmd_id)

    async def _cmd_asignar_programado(self, params: dict, cmd_id: str, hora_inicio_str: str, hora_fin_str: str | None) -> dict:
        """maneja pedido con hora_inicio: programa la ejecucion para el futuro."""
        try:
            hora_inicio = datetime.fromisoformat(hora_inicio_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return {
                "ok": False,
                "error": f"hora_inicio invalida: {hora_inicio_str}, debe ser iso 8601 utc",
                "comando": "asignar",
            }

        ahora = datetime.now(timezone.utc)
        segundos_hasta_inicio = (hora_inicio - ahora).total_seconds()

        if segundos_hasta_inicio <= 0:
            # ya deberia haber empezado, ejecutar inmediatamente
            logger.info(f"pedido {cmd_id}: hora_inicio {hora_inicio_str} ya paso, ejecutando inmediato")
            return await self._cmd_asignar_inmediato(params, cmd_id)

        # calcular duracion basado en hora_fin si esta presente
        duracion_real = None
        if hora_fin_str:
            try:
                hora_fin = datetime.fromisoformat(hora_fin_str.replace("Z", "+00:00"))
                duracion_real = int((hora_fin - hora_inicio).total_seconds())
                if duracion_real <= 0:
                    duracion_real = None
                    logger.warning(f"hora_fin {hora_fin_str} es anterior a hora_inicio, se ignora")
            except (ValueError, AttributeError):
                logger.warning(f"hora_fin invalida {hora_fin_str}, se ignora")

        # si hay duracion_real, sobreescribir params.duracion para cuando se ejecute
        params_programado = dict(params)
        if duracion_real is not None and duracion_real > 0:
            params_programado["duracion"] = duracion_real

        # programar la tarea
        tarea = asyncio.create_task(
            self._programar_pedido(cmd_id, params_programado, segundos_hasta_inicio)
        )
        self._pedidos_programados[cmd_id] = tarea

        logger.info(
            f"pedido {cmd_id} programado: hora_inicio={hora_inicio_str}, "
            f"hora_fin={hora_fin_str or 'n/a'}, "
            f"segundos_hasta_inicio={int(segundos_hasta_inicio)}, "
            f"duracion={duracion_real or params.get('duracion', 60)}"
        )

        return {
            "ok": True,
            "tipo": "respuesta_asignar",
            "comando_id": cmd_id,
            "programado": True,
            "hora_inicio": hora_inicio_str,
            "hora_fin": hora_fin_str or "",
            "segundos_hasta_inicio": int(segundos_hasta_inicio),
        }

    async def _cmd_asignar_inmediato(self, params: dict, cmd_id: str) -> dict:
        """asigna perfiles a un pedido inmediatamente (logica original con bugs corregidos)."""
        pedido_id = params.get("pedido_id", params.get("codigo", cmd_id))
        url = params.get("url", "")
        if not url:
            return {"ok": False, "error": "parametro obligatorio: url", "comando": "asignar"}
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
            f"asignar: pedido_id={pedido_id}, cantidad={cantidad}, url={url[:50]}, "
            f"duracion={duracion}, nivel_comentarios={nivel_comentarios}"
        )

        if cantidad < 1:
            return {"ok": False, "error": "cantidad debe ser >= 1", "comando": "asignar"}

        # --- verificar si el pedido ya existe (duplicado) ---
        if pedido_id in self._pedidos_activos:
            return {
                "ok": False,
                "error": f"pedido_id ya registrado: {pedido_id}",
                "comando": "asignar",
                "pedido_existente": True,
            }

        # --- paso 1: perfiles que ya estan activos con la misma url y mismo nivel (reutilizar) ---
        # bug 3: filtrar los que ya tienen maximo de pedidos
        reutilizables = []
        for pid, p in self.pm.profiles.items():
            if p.state == ProfileState.ACTIVE \
               and p.current_url == url \
               and p.nivel_comentarios == nivel_comentarios:
                # bug 3: verificar limite de pedidos por perfil
                if len(p.pedidos_ids) >= MAX_PEDIDOS_POR_PERFIL:
                    logger.info(f"perfil {pid} ya tiene {len(p.pedidos_ids)} pedidos (max {MAX_PEDIDOS_POR_PERFIL}), no reutilizable")
                    continue
                reutilizables.append(pid)

        # --- paso 2: perfiles activos con url/nivel diferente (no reutilizables) ---
        # (no se cuentan como disponibles porque hay que cerrarlos primero y reasignar)

        # --- paso 3: inactivos ---
        inactivos = [
            pid for pid, p in self.pm.profiles.items()
            if p.state == ProfileState.INACTIVE
        ]

        # --- paso 4: activos con url diferente (hay que reasignarlos) ---
        reasignables = [
            pid for pid, p in self.pm.profiles.items()
            if p.state == ProfileState.ACTIVE
            and p.current_url
            and (p.current_url != url or p.nivel_comentarios != nivel_comentarios)
            and not p.pedidos_ids  # solo si no tiene pedidos activos
        ]

        disponibles = len(reutilizables) + len(inactivos) + len(reasignables)
        logger.info(
            f"perfiles: {len(reutilizables)} reutilizables (misma url+nivel, respetando max {MAX_PEDIDOS_POR_PERFIL}), "
            f"{len(inactivos)} inactivos, "
            f"{len(reasignables)} reasignables (url/nivel diferente sin pedidos), "
            f"total disponibles={disponibles}, solicitados={cantidad}"
        )

        if disponibles < cantidad:
            estados = self.pm.get_all_states()
            return {
                "ok": False,
                "error": f"no hay suficientes perfiles: {disponibles} disponibles, {cantidad} solicitados",
                "comando": "asignar",
                "estados": estados.get("counts", {}),
                "max_pedidos_por_perfil": MAX_PEDIDOS_POR_PERFIL,
            }

        # --- seleccionar perfiles ---
        seleccionados = []

        # 1. reutilizables
        if len(reutilizables) >= cantidad:
            seleccionados = reutilizables[:cantidad]
            logger.info(f"reutilizando {len(seleccionados)} perfil(es) activos (ya estan en url+nivel)")
        else:
            seleccionados = list(reutilizables)
            faltan = cantidad - len(seleccionados)

            # 2. inactivos
            if faltan > 0 and inactivos:
                tomar = min(faltan, len(inactivos))
                seleccionados.extend(inactivos[:tomar])
                faltan -= tomar

            # 3. reasignables
            if faltan > 0 and reasignables:
                tomar = min(faltan, len(reasignables))
                seleccionados.extend(reasignables[:tomar])
                faltan -= tomar

        # --- registrar pedido ---
        self._pedidos_activos[pedido_id] = {
            "url": url,
            "duracion": duracion,
            "nivel_comentarios": nivel_comentarios,
            "inicio": time.time(),
            "perfiles": seleccionados,
            "comando_id": cmd_id,
        }

        # --- ejecutar acciones por perfil ---
        resultados = []
        for pid in seleccionados:
            try:
                p = self.pm.get_profile(pid)
                if not p:
                    resultados.append({"perfil": pid, "ok": False, "error": "perfil no encontrado"})
                    continue

                # si ya esta activo con la url correcta, solo acumular pedido
                if p.state == ProfileState.ACTIVE and p.current_url == url and p.nivel_comentarios == nivel_comentarios:
                    if pedido_id not in p.pedidos_ids:
                        p.pedidos_ids.append(pedido_id)
                    actualizado = True
                else:
                    # si esta en url diferente y tiene pedidos activos, no se puede reasignar (error de logica)
                    if p.state == ProfileState.ACTIVE and p.pedidos_ids:
                        resultados.append({
                            "perfil": pid, "ok": False,
                            "error": "perfil activo con otros pedidos, no se puede reasignar"
                        })
                        continue

                    # cerrar si esta activo en otra url/nivel
                    if p.state == ProfileState.ACTIVE:
                        logger.info(f"reasignando perfil {pid}: cerrando url actual {p.current_url[:40] if p.current_url else '?'}...")
                        tarea_anterior = self._cierres_pendientes.pop(pid, None)
                        if tarea_anterior is not None and not tarea_anterior.done():
                            tarea_anterior.cancel()
                        try:
                            await self.pm.close_profile(pid)
                        except Exception as e:
                            logger.error(f"error cerrando {pid} para reasignar: {e}")

                    # navegar (bug 2: si devuelve false por mutex, probar otro perfil)
                    success = await self.pm.navigate_to(pid, url)
                    if not success:
                        # bug 2: intentar con otro perfil de los no seleccionados aun
                        logger.warning(f"navegacion fallo para perfil {pid} (posiblemente ocupado), buscando alternativo...")
                        pid_alternativo = None
                        for alt_pid, alt_p in self.pm.profiles.items():
                            if alt_pid not in seleccionados and alt_p.state == ProfileState.INACTIVE:
                                pid_alternativo = alt_pid
                                break
                        if pid_alternativo:
                            logger.info(f"usando perfil alternativo {pid_alternativo} en lugar de {pid}")
                            seleccionados[seleccionados.index(pid)] = pid_alternativo
                            pid = pid_alternativo
                            self._pedidos_activos[pedido_id]["perfiles"] = seleccionados
                            success = await self.pm.navigate_to(pid, url)
                        if not success:
                            resultados.append({"perfil": pid, "ok": False, "error": "fallo al navegar"})
                            continue
                        p = self.pm.get_profile(pid)
                        if p:
                            p.nivel_comentarios = nivel_comentarios
                            p.pedidos_ids = [pedido_id]
                    else:
                        p = self.pm.get_profile(pid)
                        if p:
                            p.nivel_comentarios = nivel_comentarios
                            p.pedidos_ids = [pedido_id]

                # actualizar metadata del perfil
                p = self.pm.get_profile(pid)
                if p:
                    if pedido_id not in p.pedidos_ids:
                        p.pedidos_ids.append(pedido_id)

                resultados.append({"perfil": pid, "ok": True, "reutilizado": p.state == ProfileState.ACTIVE if p else False})

                # cancelar tarea de cierre anterior y reprogramar con la nueva duracion
                tarea_anterior = self._cierres_pendientes.pop(pid, None)
                if tarea_anterior is not None and not tarea_anterior.done():
                    tarea_anterior.cancel()

                duracion_total = self._calcular_duracion_max(pid)
                logger.info(
                    f"duracion calculada para perfil {pid}: {duracion_total}s "
                    f"(pedidos: {p.pedidos_ids if p else '?'})"
                )
                if duracion_total > 0:
                    tarea = asyncio.create_task(
                        self._cierre_automatico(pid, duracion_total)
                    )
                    self._cierres_pendientes[pid] = tarea
                    logger.info(
                        f"tarea de cierre automatico programada para {pid} en {duracion_total}s"
                    )
            except Exception as e:
                resultados.append({"perfil": pid, "ok": False, "error": str(e)})

        cant_exitosa = sum(1 for r in resultados if r["ok"])
        logger.info(
            f"pedido {pedido_id}: {cant_exitosa}/{len(resultados)} perfiles asignados a {url[:40]}"
        )

        return {
            "ok": cant_exitosa > 0,
            "comando": "asignar",
            "pedido_id": pedido_id,
            "cantidad_solicitada": cantidad,
            "cantidad_exitosa": cant_exitosa,
            "resultados": resultados,
            "pedido_info": self._pedidos_activos.get(pedido_id, {}),
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
                p = self.pm.get_profile(pid)
                if p and p.state == ProfileState.ACTIVE and p.current_url == url:
                    p.duracion_min = duracion
                    p.inicio = time.time()
                    tarea_anterior = self._cierres_pendientes.pop(pid, None)
                    if tarea_anterior is not None and not tarea_anterior.done():
                        tarea_anterior.cancel()
                    if duracion > 0:
                        tarea = asyncio.create_task(
                            self._cierre_automatico(pid, duracion)
                        )
                        self._cierres_pendientes[pid] = tarea
                    resultados.append({"perfil": pid, "ok": True, "reutilizado": True})
                    continue
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
        """detiene un perfil o un pedido especifico:
        - si se envia perfil_id: cierra ese perfil (libera todos sus pedidos)
        - si se envia pedido_id: libera los perfiles de ese pedido,
          pero solo cierra si el perfil no tiene otros pedidos activos
        """
        profile_id = params.get("profile_id", params.get("perfil_id", ""))
        pedido_id = params.get("pedido_id", params.get("codigo", ""))

        logger.info(f"detener solicitado: profile_id={profile_id}, pedido_id={pedido_id}")

        if not profile_id and not pedido_id:
            return {"ok": False, "error": "requiere profile_id o pedido_id", "comando": "detener"}

        # caso: detener por pedido
        if pedido_id and not profile_id:
            return await self._detener_por_pedido(pedido_id, cmd_id)

        # caso: detener por perfil
        return await self._detener_por_perfil(profile_id, cmd_id)

    async def _detener_por_pedido(self, pedido_id: str, cmd_id: str) -> dict:
        """libera todos los perfiles de un pedido.
        solo cierra los perfiles que no compartan otros pedidos activos."""
        logger.info(f"deteniendo pedido: {pedido_id}")
        pedido = self._pedidos_activos.pop(pedido_id, None)
        if not pedido:
            return {"ok": False, "error": f"pedido no encontrado: {pedido_id}", "comando": "detener"}

        perfiles = pedido.get("perfiles", [])
        liberados = []
        cerrados = []
        mantenidos = []

        for pid in perfiles:
            p = self.pm.get_profile(pid)
            if not p:
                continue

            # remover este pedido del perfil
            if pedido_id in p.pedidos_ids:
                p.pedidos_ids.remove(pedido_id)
                liberados.append(pid)

            # si aun tiene otros pedidos, mantenerlo activo
            if p.pedidos_ids:
                # reprogramar con la duracion maxima de los pedidos restantes
                nueva_duracion = self._calcular_duracion_max(pid)
                tarea_anterior = self._cierres_pendientes.pop(pid, None)
                if tarea_anterior is not None and not tarea_anterior.done():
                    tarea_anterior.cancel()
                if nueva_duracion > 0:
                    tarea = asyncio.create_task(
                        self._cierre_automatico(pid, nueva_duracion)
                    )
                    self._cierres_pendientes[pid] = tarea
                    logger.info(
                        f"perfil {pid} reprogramado con nueva duracion de {nueva_duracion}s "
                        f"(pedidos restantes: {p.pedidos_ids})"
                    )
                mantenidos.append(pid)
            else:
                # redirigir al portal en vez de cerrar
                try:
                    await self.pm.redirect_to_portal(pid, PORTAL_URL)
                    cerrados.append(pid)
                    logger.info(f"perfil {pid} redirigido al portal al liberar pedido {pedido_id}")
                except Exception as e:
                    logger.error(f"error redirigiendo {pid}: {e}")

        # enviar respuesta de confirmacion
        respuesta = {
            "tipo": "respuesta_detener",
            "comando_id": cmd_id,
            "pedido_id": pedido_id,
            "ok": True,
            "perfiles_liberados": liberados,
            "perfiles_cerrados": cerrados,
            "perfiles_mantenidos": mantenidos,
        }
        if self.ws_client is not None:
            try:
                await self.ws_client.send_response(respuesta)
                logger.info(f"respuesta_detener enviada para pedido {pedido_id}")
            except Exception as e:
                logger.error(f"error enviando respuesta_detener: {e}")

        return respuesta

    async def _detener_por_perfil(self, profile_id: str, cmd_id: str) -> dict:
        """cierra un perfil especifico y libera todos sus pedidos."""
        logger.info(f"deteniendo perfil: {profile_id}")

        # obtener pedidos asociados a este perfil
        p = self.pm.get_profile(profile_id)
        pedidos_afectados = list(p.pedidos_ids) if p else []

        # cancelar tarea de cierre
        tarea = self._cierres_pendientes.pop(profile_id, None)
        if tarea is not None and not tarea.done():
            tarea.cancel()

        # redirigir el perfil al portal en vez de cerrar
        try:
            ok = await self.pm.redirect_to_portal(profile_id, PORTAL_URL)
        except Exception as e:
            logger.error(f"error redirigiendo perfil {profile_id}: {e}")
            ok = False

        # limpiar pedidos asociados
        for pid_pedido in pedidos_afectados:
            pedido = self._pedidos_activos.get(pid_pedido)
            if pedido:
                if profile_id in pedido.get("perfiles", []):
                    pedido["perfiles"].remove(profile_id)
                logger.info(f"perfil {profile_id} removido del pedido {pid_pedido}")

        respuesta = {
            "tipo": "respuesta_detener",
            "comando_id": cmd_id,
            "perfil_id": profile_id,
            "pedidos_afectados": pedidos_afectados,
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
        """espera duracion_seg y cierra el perfil SOLO si no tiene otros pedidos activos.
        si aun tiene pedidos activos, reprograma con la duracion restante maxima.
        bug 1: si duracion_restante <= 0, no reprograma, cierra directamente."""
        try:
            await asyncio.sleep(duracion_seg)

            p = self.pm.get_profile(profile_id)
            if not p:
                self._cierres_pendientes.pop(profile_id, None)
                return

            # verificar si aun tiene pedidos activos
            pedidos_vivos = []
            for pedido_id in list(p.pedidos_ids):
                pedido = self._pedidos_activos.get(pedido_id)
                if pedido:
                    transcurrido = time.time() - pedido["inicio"]
                    if transcurrido < pedido["duracion"]:
                        pedidos_vivos.append(pedido_id)
                    else:
                        # pedido expirado, remover
                        p.pedidos_ids.remove(pedido_id)
                        self._pedidos_activos.pop(pedido_id, None)
                        logger.info(f"pedido {pedido_id} expirado, removido del perfil {profile_id}")
                else:
                    # pedido ya no existe (fue removido)
                    if pedido_id in p.pedidos_ids:
                        p.pedidos_ids.remove(pedido_id)

            if pedidos_vivos:
                # aun tiene pedidos, reprogramar con la duracion maxima restante
                duracion_max = 0
                ahora = time.time()
                for pid_restante in pedidos_vivos:
                    pedido = self._pedidos_activos.get(pid_restante)
                    if pedido:
                        restante = max(0, pedido["duracion"] - (ahora - pedido["inicio"]))
                        duracion_max = max(duracion_max, restante)

                # bug 1: si duracion_max < 1 (incluye fracciones), cerrar directamente
                if int(duracion_max) <= 0:
                    logger.info(
                        f"cierre automatico: perfil {profile_id} sin tiempo restante "
                        f"({len(pedidos_vivos)} pedido(s) activos pero con restante <= 0), cerrando..."
                    )
                    # cerrar directamente
                    if p.state == ProfileState.ACTIVE:
                        ok = await self.pm.redirect_to_portal(profile_id, PORTAL_URL)
                        if ok:
                            logger.info(f"cierre automatico: perfil {profile_id} redirigido al portal (sin tiempo restante)")
                        else:
                            logger.warning(f"cierre automatico: no se pudo redirigir {profile_id} al portal")
                    self._cierres_pendientes.pop(profile_id, None)
                    return

                logger.info(
                    f"cierre automatico: perfil {profile_id} reprogramado "
                    f"({len(pedidos_vivos)} pedido(s) aun activos, proximo cierre en {duracion_max:.0f}s)"
                )
                if duracion_max > 0:
                    tarea = asyncio.create_task(
                        self._cierre_automatico(profile_id, int(duracion_max))
                    )
                    self._cierres_pendientes[profile_id] = tarea
                return

            # sin pedidos activos, cerrar
            if p.state != ProfileState.ACTIVE:
                logger.info(f"cierre automatico: perfil {profile_id} ya no esta activo, saltando")
                self._cierres_pendientes.pop(profile_id, None)
                return

            logger.info(f"cierre automatico: redirigiendo perfil {profile_id} al portal tras {duracion_seg}s")
            ok = await self.pm.redirect_to_portal(profile_id, PORTAL_URL)
            if ok:
                logger.info(f"cierre automatico: perfil {profile_id} redirigido al portal")
            else:
                logger.warning(f"cierre automatico: no se pudo redirigir {profile_id} al portal")
        except asyncio.CancelledError:
            logger.info(f"cierre automatico: cancelado para perfil {profile_id}")
        except Exception as e:
            logger.error(f"cierre automatico: error inesperado en {profile_id}: {e}")
        finally:
            if self._cierres_pendientes.get(profile_id) is asyncio.current_task():
                self._cierres_pendientes.pop(profile_id, None)

    async def _cmd_detener_url(self, params: dict, cmd_id: str) -> dict:
        url = params.get("url", "")
        if not url:
            return {"ok": False, "error": "url requerida"}
        portal_url = PORTAL_URL
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
            return {
                "ok": False,
                "error": f"roxybrowser no responde con la apikey en {self.roxy.base}",
                "apikey_configurada": True,
                "roxy_ping": False,
            }
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
        """devuelve estado completo: conexion, perfiles y pedidos activos."""
        states = self.pm.get_all_states() if self.pm else {}

        # informacion de conexion
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

        # informacion de perfiles
        perfiles_info = {}
        if self.pm:
            for pid, p in self.pm.profiles.items():
                perfiles_info[pid] = {
                    "nombre": p.name,
                    "estado": p.state.name.lower(),
                    "url_actual": p.current_url or "",
                    "duracion_min": p.duracion_min,
                    "nivel_comentarios": p.nivel_comentarios,
                    "pedidos_ids": list(p.pedidos_ids),
                }

        # informacion de pedidos activos
        pedidos_info = {}
        ahora = time.time()
        for pid_pedido, pedido in self._pedidos_activos.items():
            transcurrido = ahora - pedido["inicio"]
            restante = max(0, int(pedido["duracion"] - transcurrido))
            pedidos_info[pid_pedido] = {
                "url": pedido["url"],
                "duracion_total": pedido["duracion"],
                "tiempo_restante": restante,
                "nivel_comentarios": pedido["nivel_comentarios"],
                "perfiles": pedido["perfiles"],
                "comando_id": pedido.get("comando_id", ""),
            }

        # informacion de pedidos programados
        pedidos_programados_info = {}
        for pid_pedido, tarea in self._pedidos_programados.items():
            pedidos_programados_info[pid_pedido] = {
                "programado": True,
                "pendiente": not tarea.done(),
            }

        return {
            "ok": True,
            "estado": {
                "conexion": conexion_info,
                "perfiles": {
                    "counts": states.get("counts", {}),
                    "profiles": perfiles_info,
                },
                "pedidos_activos": pedidos_info,
                "pedidos_programados": pedidos_programados_info,
                "total_pedidos": len(pedidos_info),
                "total_programados": len(pedidos_programados_info),
                "perfiles_libres": states.get("counts", {}).get("inactive", 0),
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
                    datos_roxy = {
                        "ping": ping_ok,
                        "version": version,
                        "perfiles_count": len(perfiles),
                        "perfiles": [
                            {"id": p.get("id", ""), "name": p.get("name", p.get("id", "")), "status": p.get("status", "unknown")}
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
            return {"ok": False, "error": "no hay api de roxybrowser configurada", "comando": "recargar_perfiles"}

        roxy_api_key = params.get("roxy_api_key", "")
        if not roxy_api_key:
            return {"ok": False, "error": "roxy_api_key requerida", "comando": "recargar_perfiles"}

        self.roxy.set_api_key(roxy_api_key)

        try:
            ws_id = self.roxy.get_workspace_id()
            logger.info(f"workspace_id obtenido = {ws_id}")
        except Exception as e:
            logger.error(f"error en get_workspace_id: {e}")
            ws_id = None

        if not ws_id:
            return {"ok": False, "error": "no se pudo obtener workspace_id de roxybrowser", "comando": "recargar_perfiles"}

        try:
            perfiles = self.roxy.get_profiles(ws_id)
            logger.info(f"perfiles obtenidos: {len(perfiles) if perfiles else 0}")
        except Exception as e:
            logger.error(f"error en get_profiles: {e}")
            perfiles = []

        if not perfiles:
            resultado = {"ok": True, "workspace_id": ws_id, "perfiles": []}
        else:
            resultado = {
                "ok": True,
                "workspace_id": ws_id,
                "perfiles": [{"nombre": p["windowName"], "hash": p["dirId"]} for p in perfiles],
            }

        if self.ws_client is not None:
            try:
                await self.ws_client.send_response({
                    "tipo": "respuesta_recargar_perfiles",
                    "comando_id": cmd_id,
                    **resultado,
                })
                logger.info("respuesta recarga enviada exitosamente")
            except Exception as e:
                logger.error(f"error enviando respuesta recarga: {e}", exc_info=True)
        else:
            logger.warning("ws_client es None, no se puede enviar la respuesta")

        return resultado