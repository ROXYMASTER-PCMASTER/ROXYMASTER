"""
roxymaster v8.3 - comms handler (pcbot zombie)
maneja la comunicacion con pcmaster via archivos en unidad z:
- lee mensajes de pcmaster desde z:\pcmaster_msgs\
- escribe mensajes para pcmaster en z:\pcbot_msgs\
- procesa ordenes humanas desde z:\roxymaster_human_tasks\
todo en minusculas, utf-8 sin bom.
"""

import asyncio
import logging
import os
import shutil
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_Z_ROOT = "Z:"
_PCMASTER_MSGS = os.path.join(_Z_ROOT, "pcmaster_msgs")
_PCBOT_MSGS = os.path.join(_Z_ROOT, "pcbot_msgs")
_HUMAN_TASKS = os.path.join(_Z_ROOT, "roxymaster_human_tasks")
_HUMAN_ERRORS = os.path.join(_HUMAN_TASKS, "errores")
_LOGS_SHARED = os.path.join(_Z_ROOT, "logs")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _ts_filename(prefix: str, ext: str = ".txt") -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:21]
    return f"{prefix}_{ts}{ext}"


class CommsHandler:
    """protocolo de mensajeria efimera entre pcbot y pcmaster via archivos."""

    def __init__(self):
        self._ensure_dirs()

    def _ensure_dirs(self):
        for d in [_PCMASTER_MSGS, _PCBOT_MSGS, _HUMAN_TASKS, _HUMAN_ERRORS, _LOGS_SHARED]:
            try:
                os.makedirs(d, exist_ok=True)
            except (OSError, PermissionError) as e:
                logger.warning(f"no se pudo crear directorio {d}: {e}")

    async def leer_mensaje_pcmaster(self) -> Optional[dict]:
        archivos = await self._listar_txt_ordenados(_PCMASTER_MSGS)
        if not archivos:
            return None
        ruta = archivos[0]
        contenido = await self._leer_archivo(ruta)
        if not contenido:
            return None
        mensaje = self._parsear_mensaje(contenido)
        if mensaje:
            mensaje["_ruta"] = ruta
        return mensaje

    async def borrar_mensaje_pcmaster(self, ruta: str):
        try:
            if os.path.isfile(ruta):
                os.remove(ruta)
                logger.info(f"mensaje pcmaster borrado: {ruta}")
        except (OSError, PermissionError) as e:
            logger.error(f"no se pudo borrar {ruta}: {e}")

    async def escribir_mensaje_pcbot(self, estado_conexion: str, error_detectado: str = "ninguno",
                                      pruebas_realizadas: str = "", solicitud: str = "",
                                      requiere_respuesta: bool = False):
        contenido = (
            f"timestamp: {_utc_now()}\n"
            f"remitente: pcbot\n"
            f"estado_conexion: {estado_conexion}\n"
            f"error_detectado: {error_detectado}\n"
            f"pruebas_realizadas: {pruebas_realizadas}\n"
            f"solicitud: {solicitud}\n"
            f"requiere_respuesta: {'true' if requiere_respuesta else 'false'}\n"
        )
        nombre = _ts_filename("msg")
        ruta = os.path.join(_PCBOT_MSGS, nombre)
        try:
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(contenido)
            logger.info(f"mensaje pcbot escrito: {ruta}")
        except (OSError, PermissionError) as e:
            logger.error(f"no se pudo escribir mensaje pcbot: {e}")

    async def procesar_ordenes_humanas(self, ejecutor_orden) -> list:
        procesados = []
        try:
            archivos = sorted([
                os.path.join(_HUMAN_TASKS, f)
                for f in os.listdir(_HUMAN_TASKS)
                if f.endswith(".txt") and f.lower() != "errores"
            ], key=os.path.getmtime)
        except (OSError, FileNotFoundError):
            return procesados

        for ruta in archivos:
            if os.path.isdir(ruta):
                continue
            contenido = await self._leer_archivo(ruta)
            if not contenido:
                continue
            destino = self._extraer_destino(contenido)
            if destino in ("pcbot", "ambos"):
                logger.info(f"orden humana para pcbot: {ruta} (destino={destino})")
                try:
                    if asyncio.iscoroutinefunction(ejecutor_orden):
                        await ejecutor_orden(contenido, ruta)
                    else:
                        ejecutor_orden(contenido, ruta)
                except Exception as e:
                    logger.error(f"error ejecutando orden {ruta}: {e}")
                try:
                    os.remove(ruta)
                    logger.info(f"orden humana eliminada: {ruta}")
                except (OSError, PermissionError) as e:
                    logger.error(f"no se pudo borrar orden {ruta}: {e}")
                procesados.append((ruta, destino))
            elif destino == "pcmaster":
                logger.info(f"orden para pcmaster, ignorada: {ruta}")
            else:
                await self._mover_a_errores(ruta, f"sin destino valido: {destino}")
                procesados.append((ruta, "invalido"))
        return procesados

    async def detectar_stop_bucle(self) -> bool:
        ruta = os.path.join(_Z_ROOT, "stop_bucle.txt")
        if os.path.isfile(ruta):
            logger.warning("archivo stop_bucle.txt detectado. deteniendo bucle.")
            try:
                os.remove(ruta)
            except (OSError, PermissionError):
                pass
            return True
        return False

    async def _listar_txt_ordenados(self, directorio: str) -> list:
        try:
            archivos = [
                os.path.join(directorio, f)
                for f in os.listdir(directorio)
                if f.endswith(".txt") and os.path.isfile(os.path.join(directorio, f))
            ]
            archivos.sort(key=os.path.getmtime)
            return archivos
        except (OSError, FileNotFoundError):
            return []

    async def _leer_archivo(self, ruta: str) -> Optional[str]:
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                return f.read()
        except (OSError, PermissionError, UnicodeDecodeError) as e:
            logger.error(f"error leyendo {ruta}: {e}")
            return None

    def _parsear_mensaje(self, contenido: str) -> dict:
        mensaje = {}
        for linea in contenido.strip().split("\n"):
            if ": " in linea:
                clave, valor = linea.split(": ", 1)
                mensaje[clave.strip()] = valor.strip()
            elif linea.strip():
                mensaje.setdefault("_extra", []).append(linea.strip())
        return mensaje

    def _extraer_destino(self, contenido: str) -> str:
        for linea in contenido.split("\n"):
            linea_strip = linea.strip().lower()
            if linea_strip.startswith("#destino:"):
                partes = linea_strip.split(":", 1)
                if len(partes) == 2:
                    return partes[1].strip()
        return ""

    async def _mover_a_errores(self, ruta: str, razon: str):
        try:
            os.makedirs(_HUMAN_ERRORS, exist_ok=True)
            nombre = os.path.basename(ruta)
            destino = os.path.join(_HUMAN_ERRORS, f"error_{nombre}")
            shutil.move(ruta, destino)
            razon_path = destino + ".razon.txt"
            with open(razon_path, "w", encoding="utf-8") as f:
                f.write(f"movido por: {razon}\nfecha: {_utc_now()}\n")
            logger.info(f"archivo invalido movido a errores: {ruta} -> {destino}")
        except (OSError, PermissionError) as e:
            logger.error(f"no se pudo mover a errores {ruta}: {e}")
