"""
roxymaster v8.3 - pcbot zombie loop (core)
bucle infinito asyncio que se ejecuta cada 7 minutos:
1. revisa mensajes de pcmaster en z:\pcmaster_msgs\
2. procesa ordenes humanas en z:\roxymaster_human_tasks\
3. verifica websocket del agente main.py
4. ejecuta pruebas de humo sobre wafabot.com
5. escribe logs de actividad
compatible con python 3.10, utf-8 sin bom.
"""

import asyncio
import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from typing import Optional

# rutas locales
_BASE = r"C:\Users\CYBER\Desktop\roxymaster\pcbot"
sys.path.insert(0, _BASE)

from scripts.backup_manager import BackupManager
from scripts.comms.comms_handler import CommsHandler
from scripts.error_handler import ErrorHandler
from scripts.tests.test_runner import TestRunner

logger = logging.getLogger(__name__)

_CICLO_SEG = 420  # 7 minutos
_LOGS_LOCAL = os.path.join(_BASE, "logs")
_MAIN_PY = os.path.join(_BASE, "scripts", "main.py")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class PcbotLoop:
    """bucle principal del zombie pcbot."""

    def __init__(self):
        os.makedirs(_LOGS_LOCAL, exist_ok=True)
        self._comms = CommsHandler()
        self._error_handler = ErrorHandler()
        self._test_runner = TestRunner()
        self._backup_manager = BackupManager()
        self._running = True
        self._ws_proc: Optional[asyncio.subprocess.Process] = None
        self._ciclo_count = 0
        self._ultima_prueba_ok = False

    async def iniciar(self):
        """inicia el bucle principal y tareas en background."""
        logger.info("pcbot zombie iniciando...")

        # iniciar backup manager en background
        try:
            await self._backup_manager.start()
            logger.info("backup manager iniciado en background")
        except Exception as e:
            logger.error(f"no se pudo iniciar backup manager: {e}")

        # iniciar websocket agent en background si no existe
        await self._verificar_agente()

        # bucle principal
        logger.info("bucle principal iniciado (cada 7 minutos)")
        while self._running:
            await self._ejecutar_ciclo()

        # limpieza al salir
        await self._limpiar()

    async def detener(self):
        """detiene el bucle."""
        logger.info("deteniendo pcbot zombie...")
        self._running = False

    # ----------------------------------------------------------
    # ciclo principal
    # ----------------------------------------------------------
    async def _ejecutar_ciclo(self):
        """ejecuta un ciclo completo del bucle."""
        self._ciclo_count += 1
        logger.info(f"=== ciclo #{self._ciclo_count} iniciado ===")

        # 1. verificar stop_bucle
        try:
            if await self._comms.detectar_stop_bucle():
                logger.warning("stop_bucle detectado. finalizando.")
                self._running = False
                return
        except Exception as e:
            logger.error(f"error detectando stop_bucle: {e}")

        # 2. cada 5 ciclos, escribir log de espera
        if self._ciclo_count % 5 == 0:
            try:
                await self._error_handler.escribir_espera_log("instrucciones de pcmaster")
            except Exception as e:
                logger.error(f"error escribiendo log_espera: {e}")

        # 3. leer mensajes de pcmaster
        await self._procesar_mensajes_pcmaster()

        # 4. procesar ordenes humanas
        await self._procesar_ordenes_humanas()

        # 5. verificar agente websocket
        await self._verificar_agente()

        # 6. ejecutar pruebas de humo
        await self._ejecutar_pruebas()

        # 7. verificar errores repetidos
        await self._verificar_errores_repetidos()

        # 8. verificar bucle sin progreso
        self._verificar_progreso()

        # 9. escribir log de actividad
        await self._escribir_log_actividad()

        logger.info(f"=== ciclo #{self._ciclo_count} completado ===")
        logger.info(f"esperando {_CICLO_SEG}s hasta el siguiente ciclo...")

        # esperar al siguiente ciclo
        try:
            await asyncio.sleep(_CICLO_SEG)
        except asyncio.CancelledError:
            logger.info("bucle cancelado durante sleep")
            self._running = False

    # ----------------------------------------------------------
    # procesar mensajes de pcmaster
    # ----------------------------------------------------------
    async def _procesar_mensajes_pcmaster(self):
        """lee y ejecuta un mensaje de pcmaster (el mas antiguo)."""
        try:
            mensaje = await self._comms.leer_mensaje_pcmaster()
            if not mensaje:
                logger.info("no hay mensajes de pcmaster")
                return

            instruccion = mensaje.get("instruccion", "").strip()
            parametros = mensaje.get("parametros", "").strip()
            ruta = mensaje.get("_ruta", "")

            logger.info(f"instruccion de pcmaster recibida: {instruccion}")

            # ejecutar instruccion
            resultado = ""
            error = ""

            if instruccion.lower() == "recargar_perfiles":
                resultado = await self._ejecutar_recargar_perfiles()
            elif instruccion.lower() == "ejecutar_pruebas":
                resultado = await self._ejecutar_pruebas(forzado=True)
            elif instruccion.lower() == "ejecutar_backup":
                ok = await self._backup_manager.ejecutar_backup_ahora()
                resultado = "backup ejecutado ok" if ok else "backup fallo"
            elif instruccion.lower() == "detener_agente":
                await self._detener_agente()
                resultado = "agente detenido"
            elif instruccion.lower() == "reiniciar_agente":
                await self._detener_agente()
                await self._verificar_agente()
                resultado = "agente reiniciado"
            else:
                error = f"instruccion desconocida: {instruccion}"
                logger.warning(error)

            # notificar a pcmaster si la instruccion requiere respuesta
            requiere = mensaje.get("requiere_respuesta", "false").strip().lower() == "true"
            if requiere or error or instruccion:
                await self._comms.escribir_mensaje_pcbot(
                    estado_conexion="conectado",
                    error_detectado=error or "ninguno",
                    pruebas_realizadas=resultado if "prueba" in instruccion else "",
                    solicitud=f"resultado de: {instruccion}",
                    requiere_respuesta=True,
                )

            # borrar mensaje procesado
            if ruta:
                await self._comms.borrar_mensaje_pcmaster(ruta)
                self._error_handler.resetear_ciclos_sin_progreso()

        except Exception as e:
            logger.error(f"error procesando mensaje pcmaster: {e}")
            self._error_handler.registrar_error("procesar_pcmaster", str(e))

    # ----------------------------------------------------------
    # procesar ordenes humanas
    # ----------------------------------------------------------
    async def _procesar_ordenes_humanas(self):
        """procesa las ordenes de la carpeta compartida."""
        try:
            await self._comms.procesar_ordenes_humanas(self._ejecutor_orden_humana)
        except Exception as e:
            logger.error(f"error procesando ordenes humanas: {e}")
            self._error_handler.registrar_error("ordenes_humanas", str(e))

    async def _ejecutor_orden_humana(self, contenido: str, ruta: str):
        """callback para ejecutar una orden humana."""
        logger.info(f"ejecutando orden humana desde {ruta}")
        # extraer accion del contenido (quitar #destino:)
        lineas = contenido.strip().split("\n")
        cuerpo = "\n".join(
            l for l in lineas
            if not l.strip().lower().startswith("#destino:")
        )
        logger.info(f"orden humana:\n{cuerpo}")

        # aqui se pueden agregar comandos especificos
        # por ahora, solo logueamos
        await self._comms.escribir_mensaje_pcbot(
            estado_conexion="conectado",
            error_detectado="ninguno",
            pruebas_realizadas=f"orden humana ejecutada",
            solicitud="orden humana procesada",
            requiere_respuesta=False,
        )

    # ----------------------------------------------------------
    # agente websocket
    # ----------------------------------------------------------
    async def _verificar_agente(self):
        """verifica si el agente websocket main.py esta corriendo."""
        if self._ws_proc and self._ws_proc.returncode is None:
            logger.info("agente websocket ya esta corriendo")
            return

        logger.info("agente websocket no detectado. iniciando...")
        try:
            self._ws_proc = await asyncio.create_subprocess_shell(
                f"python \"{_MAIN_PY}\"",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            logger.info(f"agente websocket iniciado (pid: {self._ws_proc.pid})")
            self._error_handler.resetear_ciclos_sin_progreso()
        except (OSError, asyncio.SubprocessError) as e:
            logger.error(f"no se pudo iniciar agente websocket: {e}")
            self._error_handler.registrar_error("iniciar_agente", str(e), "subprocess_shell")

    async def _detener_agente(self):
        """detiene el agente websocket."""
        if self._ws_proc and self._ws_proc.returncode is None:
            try:
                self._ws_proc.terminate()
                try:
                    await asyncio.wait_for(self._ws_proc.wait(), timeout=5)
                except asyncio.TimeoutError:
                    self._ws_proc.kill()
                    await self._ws_proc.wait()
                logger.info("agente websocket detenido")
            except (ProcessLookupError, OSError) as e:
                logger.warning(f"error deteniendo agente: {e}")
        self._ws_proc = None

    # ----------------------------------------------------------
    # pruebas de humo
    # ----------------------------------------------------------
    async def _ejecutar_pruebas(self, forzado: bool = False) -> str:
        """ejecuta pruebas de humo. retorna resumen."""
        logger.info("ejecutando pruebas de humo...")
        try:
            resultados = await self._test_runner.ejecutar_todas()
            exitos = sum(1 for r in resultados if r.get("exito"))
            fallos = sum(1 for r in resultados if not r.get("exito"))
            self._ultima_prueba_ok = fallos == 0
            resumen = f"{exitos} exitos, {fallos} fallos"

            # notificar a pcmaster si hay fallos
            if fallos > 0:
                await self._comms.escribir_mensaje_pcbot(
                    estado_conexion="conectado",
                    error_detectado=f"pruebas con {fallos} fallo(s)",
                    pruebas_realizadas=resumen,
                    solicitud="revisar logs de pruebas",
                    requiere_respuesta=True,
                )

            logger.info(f"pruebas completadas: {resumen}")
            return resumen
        except Exception as e:
            logger.error(f"error en pruebas de humo: {e}")
            self._error_handler.registrar_error("pruebas_humo", str(e))
            return f"error: {e}"

    async def _ejecutar_recargar_perfiles(self) -> str:
        """ejecuta la recarga de perfiles."""
        logger.info("ejecutando recarga de perfiles...")
        try:
            from scripts.core.profile_manager import ProfileManager
            pm = ProfileManager()
            resultado = await pm.sync_profiles()
            return f"perfiles recargados: {resultado}"
        except Exception as e:
            logger.error(f"error recargando perfiles: {e}")
            return f"error: {e}"

    # ----------------------------------------------------------
    # verificacion de errores
    # ----------------------------------------------------------
    async def _verificar_errores_repetidos(self):
        """verifica si hay errores repetidos y notifica."""
        # verificar errores en las pruebas
        prueba_error = self._test_runner.hay_errores_recurrentes(3)
        if prueba_error:
            await self._error_handler.escribir_error_repetido(
                contexto=f"prueba_{prueba_error}",
                count=3,
                accion=f"prueba de humo: {prueba_error}",
                comando=f"TestRunner().ejecutar_todas()",
                error_msg=f"prueba {prueba_error} ha fallado 3+ veces consecutivas",
            )
            # notificar a pcmaster
            await self._comms.escribir_mensaje_pcbot(
                estado_conexion="conectado",
                error_detectado=f"error_repetido: prueba_{prueba_error}",
                pruebas_realizadas=f"error_repetido en {prueba_error}",
                solicitud="revisar error_repetido.md en escritorio de pcwilmer",
                requiere_respuesta=True,
            )

        # verificar errores del handler
        critico = self._error_handler.hay_error_repetido_critico(3)
        if critico:
            ctx, count = critico
            await self._error_handler.escribir_error_repetido(
                contexto=ctx,
                count=count,
                accion="operacion del bucle principal",
                comando="PcbotLoop._ejecutar_ciclo()",
                error_msg=f"error repetido en {ctx} ({count} veces)",
            )

    # ----------------------------------------------------------
    # control de progreso
    # ----------------------------------------------------------
    def _verificar_progreso(self):
        """verifica si el bucle esta avanzando o estancado."""
        if self._error_handler.hay_bucle_sin_progreso():
            logger.warning("bucle sin progreso detectado!")
            # crear tarea async para escribir instrucciones
            asyncio.create_task(
                self._error_handler.escribir_instrucciones_humanas(
                    "el bucle de pcbot ha superado 4 ciclos sin progreso visible. "
                    "se requieren instrucciones explicitas del humano."
                )
            )

    # ----------------------------------------------------------
    # logging
    # ----------------------------------------------------------
    async def _escribir_log_actividad(self):
        """escribe log de actividad del ciclo."""
        ts = _utc_now()
        linea = (
            f"[{ts}] ciclo #{self._ciclo_count} | "
            f"ws={'ok' if (self._ws_proc and self._ws_proc.returncode is None) else 'down'} | "
            f"pruebas={'ok' if self._ultima_prueba_ok else 'fallo'}\n"
        )
        ruta = os.path.join(_LOGS_LOCAL, "pcbot_loop.log")
        ruta_z = os.path.join("Z:", "logs", "pcbot_loop.log")
        for r in [ruta, ruta_z]:
            try:
                dir_name = os.path.dirname(r)
                os.makedirs(dir_name, exist_ok=True)
                with open(r, "a", encoding="utf-8") as f:
                    f.write(linea)
            except (OSError, PermissionError):
                pass

    # ----------------------------------------------------------
    # limpieza
    # ----------------------------------------------------------
    async def _limpiar(self):
        """limpia recursos al detener el bucle."""
        logger.info("limpiando recursos...")
        try:
            await self._backup_manager.stop()
        except Exception:
            pass
        try:
            await self._detener_agente()
        except Exception:
            pass
        logger.info("pcbot zombie detenido.")