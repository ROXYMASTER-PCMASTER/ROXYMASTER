"""
roxymaster v8.3 - error handler (pcbot zombie)
implementa las reglas anti-bucle y anti-error del ecosistema:
- detecta errores repetidos 3 veces -> error_repetido.md
- detecta 2 fallos consecutivos de misma estrategia -> cambia enfoque
- si agente no arranca tras 2 correcciones -> errores_pendientes.txt
- si bucle supera 4 ciclos sin progreso -> pide instrucciones
todo en minusculas, utf-8 sin bom.
"""

import asyncio
import logging
import os
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_DESKTOP = r"C:\Users\CYBER\Desktop\PCWILMER"
_SHARED_LOGS = r"Z:\logs"
_LOGS_LOCAL = r"C:\Users\CYBER\Desktop\roxymaster\pcbot\logs"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class ErrorHandler:
    """gestiona errores segun reglas anti-bucle del ecosistema."""

    def __init__(self):
        self._errores_consecutivos: Dict[str, int] = defaultdict(int)
        self._errores_repetidos: Dict[str, int] = defaultdict(int)
        self._ultimo_error: Optional[str] = None
        self._estrategia_actual: Optional[str] = None
        self._fallos_estrategia: int = 0
        self._ciclos_sin_progreso: int = 0
        self._ultimo_progreso: Optional[str] = None

        # crear directorios necesarios
        for d in [_DESKTOP, _SHARED_LOGS, _LOGS_LOCAL]:
            try:
                os.makedirs(d, exist_ok=True)
            except (OSError, PermissionError):
                pass

    def registrar_error(self, contexto: str, error: str, estrategia_usada: str = ""):
        """registra un error y verifica las reglas anti-bucle."""
        ts = _utc_now()
        logger.error(f"[{ts}] error en {contexto}: {error} (estrategia: {estrategia_usada})")

        # contador de errores repetidos por contexto
        self._errores_repetidos[contexto] += 1

        # verificar si es mismo error consecutivo
        if error == self._ultimo_error:
            self._errores_consecutivos[contexto] += 1
            self._ultimo_error = error
        else:
            self._errores_consecutivos[contexto] = 1
            self._ultimo_error = error

        # verificar estrategia fallida 2 veces
        if estrategia_usada:
            if estrategia_usada == self._estrategia_actual:
                self._fallos_estrategia += 1
            else:
                self._estrategia_actual = estrategia_usada
                self._fallos_estrategia = 1

    def hay_cambio_estrategia_necesario(self) -> bool:
        """retorna true si la misma estrategia ha fallado 2 veces seguidas."""
        return self._fallos_estrategia >= 2

    def marcar_cambio_estrategia(self):
        """resetea el contador de fallos de estrategia y documenta el cambio."""
        logger.info(f"cambio de estrategia documentado (fallos: {self._fallos_estrategia})")
        self._fallos_estrategia = 0
        self._estrategia_actual = None
        # registrar en log
        self._escribir_log_local("cambio_estrategia.log",
                                  f"{_utc_now()} - cambio de estrategia aplicado")

    def hay_error_repetido_critico(self, umbral: int = 3) -> Optional[Tuple[str, int]]:
        """verifica si algun contexto ha fallado mas de umbral veces."""
        for ctx, count in self._errores_repetidos.items():
            if count >= umbral:
                return (ctx, count)
        return None

    async def escribir_error_repetido(self, contexto: str, count: int,
                                       accion: str, comando: str, error_msg: str):
        """escribe error_repetido.md segun reglas anti-bucle."""
        razon = self._analizar_razon(contexto, error_msg)
        alternativas = self._generar_alternativas(contexto)

        contenido = (
            f"# error repetido detectado\n"
            f"timestamp: {_utc_now()}\n\n"
            f"## accion intentada\n{accion}\n\n"
            f"## comando ejecutado\n{comando}\n\n"
            f"## mensaje de error\n{error_msg}\n\n"
            f"## conteo de repeticiones\n{count}\n\n"
            f"## razon probable del fallo\n{razon}\n\n"
            f"## tres caminos alternativos propuestos\n"
        )
        for i, alt in enumerate(alternativas, 1):
            contenido += f"\n{i}. {alt}"

        ruta = os.path.join(_DESKTOP, "error_repetido.md")
        try:
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(contenido)
            logger.info(f"error_repetido.md escrito en {ruta}")

            # copiar a z:\logs tambien
            ruta_z = os.path.join(_SHARED_LOGS, "error_repetido.md")
            with open(ruta_z, "w", encoding="utf-8") as f:
                f.write(contenido)
        except (OSError, PermissionError) as e:
            logger.error(f"no se pudo escribir error_repetido.md: {e}")

    async def escribir_errores_pendientes(self, traceback_str: str, soluciones: List[str]):
        """escribe errores_pendientes.txt cuando el agente no arranca tras 2 correcciones."""
        contenido = (
            f"# errores pendientes - pcbot zombie\n"
            f"timestamp: {_utc_now()}\n\n"
            f"## traceback\n{traceback_str}\n\n"
            f"## soluciones intentadas\n"
        )
        for s in soluciones:
            contenido += f"- {s}\n"

        ruta = os.path.join(_DESKTOP, "errores_pendientes.txt")
        try:
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(contenido)
            logger.info(f"errores_pendientes.txt escrito en {ruta}")
        except (OSError, PermissionError) as e:
            logger.error(f"no se pudo escribir errores_pendientes.txt: {e}")

    def registrar_ciclo_sin_progreso(self):
        """incrementa contador de ciclos sin progreso."""
        self._ciclos_sin_progreso += 1
        logger.warning(f"ciclo sin progreso #{self._ciclos_sin_progreso}")

    def hay_bucle_sin_progreso(self, max_ciclos: int = 4) -> bool:
        """retorna true si hay mas de max_ciclos sin progreso."""
        return self._ciclos_sin_progreso >= max_ciclos

    def resetear_ciclos_sin_progreso(self):
        """resetea el contador de ciclos sin progreso."""
        self._ciclos_sin_progreso = 0

    async def escribir_espera_log(self, recurso: str = ""):
        """escribe en log_espera.txt cada 5 ciclos."""
        ts = _utc_now()
        linea = f"[{ts}] esperando {recurso or 'instrucciones de pcmaster'}\n"
        ruta_local = os.path.join(_LOGS_LOCAL, "log_espera.txt")
        ruta_z = os.path.join(_SHARED_LOGS, "log_espera.txt")
        for r in [ruta_local, ruta_z]:
            try:
                with open(r, "a", encoding="utf-8") as f:
                    f.write(linea)
            except (OSError, PermissionError):
                pass

    async def escribir_instrucciones_humanas(self, mensaje: str):
        """escribe en instrucciones_humanas.txt cuando el bucle se rompe."""
        contenido = (
            f"timestamp: {_utc_now()}\n"
            f"origen: pcbot zombie\n"
            f"mensaje: {mensaje}\n"
            f"accion_requerida: el humano debe dar instrucciones explicitas\n"
        )
        ruta = os.path.join(_SHARED_LOGS, "..", "instrucciones_humanas.txt")
        ruta_abs = os.path.abspath(ruta)
        try:
            with open(ruta_abs, "w", encoding="utf-8") as f:
                f.write(contenido)
            logger.info(f"instrucciones_humanas.txt escrito")
        except (OSError, PermissionError) as e:
            logger.error(f"no se pudo escribir instrucciones_humanas.txt: {e}")

    def _analizar_razon(self, contexto: str, error_msg: str) -> str:
        """analiza la razon probable del error."""
        if "timeout" in error_msg.lower() or "connection" in error_msg.lower():
            return "posible problema de red o servidor caido"
        if "json" in error_msg.lower() or "parse" in error_msg.lower():
            return "formato de respuesta invalido, posible cambio en api"
        if "auth" in error_msg.lower() or "token" in error_msg.lower():
            return "credenciales expiradas o invalidas"
        if "file" in error_msg.lower() or "not found" in error_msg.lower():
            return "archivo o recurso faltante en el sistema de archivos"
        return f"error no clasificado: {error_msg[:100]}"

    def _generar_alternativas(self, contexto: str) -> List[str]:
        """genera 3 caminos alternativos para resolver el error."""
        return [
            f"1. reintentar {contexto} con timeout mas largo y reintentos exponenciales",
            f"2. verificar conectividad de red y disponibilidad del servicio antes de {contexto}",
            f"3. notificar a pcmaster y esperar instrucciones explicitas para {contexto}",
        ]

    def _escribir_log_local(self, nombre: str, contenido: str):
        """escribe un log local en la carpeta de logs."""
        ruta = os.path.join(_LOGS_LOCAL, nombre)
        try:
            with open(ruta, "a", encoding="utf-8") as f:
                f.write(contenido + "\n")
        except (OSError, PermissionError):
            pass