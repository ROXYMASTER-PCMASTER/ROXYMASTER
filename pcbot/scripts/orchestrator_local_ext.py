"""
roxymaster v8.3 - orchestrator ext (pcbot)
extension de orchestrator_local con funcionalidad de agendamiento de pedidos por hora.
importa orchestrator_local para extenderlo via monkey-parche o composicion.
todo en minusculas, utf-8 sin bom.
"""
import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class SchedulerExtension:
    """extiende orchestrator_local con agendamiento de pedidos.
    las instancias deben asignar self.scheduler = SchedulerExtension(orchestrator_self)
    para que los metodos queden disponibles como self._programar_pedido(), etc."""

    def __init__(self, orch):
        self._orch = orch

    async def programar_pedido(self, comando_id: str, params: dict, segundos_hasta_inicio: float):
        """espera segundos_hasta_inicio y luego ejecuta el pedido como inmediato.
        equivalente al original _programar_pedido pero en modulo separado."""
        try:
            logger.info(
                f"pedido {comando_id} programado para ejecutarse en {segundos_hasta_inicio:.0f}s"
            )
            await asyncio.sleep(segundos_hasta_inicio)
            logger.info(f"pedido {comando_id}: hora de ejecucion llegada, ejecutando...")
            # llamar al metodo inmediato del orquestador
            resultado = await self._orch._cmd_asignar_inmediato(params, comando_id)
            # enviar respuesta de ejecucion al ws si es necesario
            if self._orch.ws_client is not None:
                try:
                    await self._orch.ws_client.send_response({
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
            self._orch._pedidos_programados.pop(comando_id, None)

    async def cmd_asignar_programado(self, params: dict, cmd_id: str, hora_inicio_str: str, hora_fin_str: str | None) -> dict:
        """maneja pedido con hora_inicio: programa la ejecucion para el futuro.
        equivalente al original _cmd_asignar_programado pero en modulo separado."""
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
            return await self._orch._cmd_asignar_inmediato(params, cmd_id)

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
            self.programar_pedido(cmd_id, params_programado, segundos_hasta_inicio)
        )
        self._orch._pedidos_programados[cmd_id] = tarea

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

    async def cmd_cancelar(self, params: dict, cmd_id: str) -> dict:
        """cancela un pedido programado."""
        pedido_id = params.get("pedido_id", params.get("codigo", ""))
        if not pedido_id:
            return {"ok": False, "error": "pedido_id requerido para cancelar"}
        tarea = self._orch._pedidos_programados.pop(pedido_id, None)
        if tarea is not None and not tarea.done():
            tarea.cancel()
            logger.info(f"pedido programado {pedido_id} cancelado")
            return {"ok": True, "cancelado": True, "pedido_id": pedido_id}
        return {"ok": False, "error": f"no hay pedido programado con id {pedido_id}"}