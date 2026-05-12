"""
roxymaster v8.3 - backup manager (pcbot zombie)
copia el proyecto pcbot a un directorio de backups cada 30 min.
mantiene solo los 5 backups mas recientes.
compatible con python 3.10, utf-8 sin bom.
"""

import asyncio
import logging
import os
import shutil
from datetime import datetime, timezone
from typing import List

logger = logging.getLogger(__name__)

_SOURCE = r"C:\Users\CYBER\Desktop\roxymaster\pcbot"
_BACKUP_ROOT = r"C:\Users\CYBER\Desktop\backups_pcbot"
_INTERVAL_SEC = 1800  # 30 minutos
_MAX_BACKUPS = 5


def _backup_name() -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"backup_{ts}"


class BackupManager:
    """gestiona backups automaticos del proyecto pcbot."""

    def __init__(self, source: str = _SOURCE, backup_root: str = _BACKUP_ROOT,
                 interval: int = _INTERVAL_SEC, max_backups: int = _MAX_BACKUPS):
        self._source = source
        self._backup_root = backup_root
        self._interval = interval
        self._max_backups = max_backups
        self._running = False
        self._task: asyncio.Task = None

    async def start(self):
        """inicia el loop de backups en background."""
        self._running = True
        self._task = asyncio.create_task(self._backup_loop())
        logger.info(f"backup manager iniciado (cada {self._interval}s, max {self._max_backups} backups)")

    async def stop(self):
        """detiene el loop de backups."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def ejecutar_backup_ahora(self) -> bool:
        """ejecuta un backup inmediato. retorna true si fue exitoso."""
        return await self._hacer_backup()

    async def _backup_loop(self):
        """loop infinito que hace backups cada N segundos."""
        while self._running:
            await asyncio.sleep(self._interval)
            if not self._running:
                break
            await self._hacer_backup()

    async def _hacer_backup(self) -> bool:
        """copia source a backup_root con timestamp."""
        if not os.path.isdir(self._source):
            logger.error(f"origen no existe: {self._source}")
            return False

        os.makedirs(self._backup_root, exist_ok=True)

        nombre = _backup_name()
        destino = os.path.join(self._backup_root, nombre)

        try:
            # copiar arbol completo
            if os.path.exists(destino):
                shutil.rmtree(destino)
            shutil.copytree(self._source, destino,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git"))
            logger.info(f"backup creado: {destino}")

            # limpiar backups antiguos
            await self._limpiar_viejos()

            return True
        except (OSError, shutil.Error) as e:
            logger.error(f"error en backup: {e}")
            return False

    async def _limpiar_viejos(self):
        """elimina backups excedentes manteniendo solo los max_backups mas recientes."""
        try:
            backups = self._listar_backups()
            if len(backups) <= self._max_backups:
                return
            eliminar = backups[:-self._max_backups]
            for b in eliminar:
                try:
                    if os.path.isdir(b):
                        shutil.rmtree(b)
                        logger.info(f"backup antiguo eliminado: {b}")
                except (OSError, PermissionError) as e:
                    logger.warning(f"no se pudo eliminar backup {b}: {e}")
        except Exception as e:
            logger.error(f"error limpiando backups viejos: {e}")

    def _listar_backups(self) -> List[str]:
        """lista los directorios de backup ordenados por fecha (mas antiguo primero)."""
        if not os.path.isdir(self._backup_root):
            return []
        backups = []
        try:
            for entry in os.listdir(self._backup_root):
                ruta = os.path.join(self._backup_root, entry)
                if os.path.isdir(ruta) and entry.startswith("backup_"):
                    backups.append(ruta)
            backups.sort(key=os.path.getmtime)
        except (OSError, PermissionError) as e:
            logger.error(f"error listando backups: {e}")
        return backups