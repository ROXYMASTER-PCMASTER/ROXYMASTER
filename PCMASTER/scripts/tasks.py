# tasks.py - tareas periodicas roxymaster v8.3
import asyncio
import sqlite3
import logging
import time
from pathlib import Path
from datetime import datetime

_base_dir = Path(__file__).parent.parent.absolute()
_db_path = _base_dir / "data" / "roxymaster.db"
logger = logging.getLogger("roxymaster.tasks")


async def tarea_quema_diaria():
    """quema diaria de tokens inactivos."""
    while True:
        try:
            conn = sqlite3.connect(str(_db_path))
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            # quemar 0.5% diario de tokens inactivos (simplificado)
            c.execute(
                "update wallets set balance = balance * 0.995 where uid != 'pcmaster' and balance > 0"
            )
            conn.commit()
            conn.close()
            logger.info("[quema_diaria] ejecutada")
        except Exception as e:
            logger.error(f"[quema_diaria] error: {e}")
        await asyncio.sleep(86400)  # 24 horas


async def tarea_limpieza_pcbots():
    """limpieza periodica de pcbots inactivos."""
    while True:
        try:
            conn = sqlite3.connect(str(_db_path))
            c = conn.cursor()
            # marcar usuarios inactivos > 7 dias
            c.execute(
                "update usuarios set activo = 0 where ultimo_login < datetime('now', '-7 days', 'localtime') and activo = 1"
            )
            conn.commit()
            conn.close()
            logger.info("[limpieza_pcbots] ejecutada")
        except Exception as e:
            logger.error(f"[limpieza_pcbots] error: {e}")
        await asyncio.sleep(3600)  # 1 hora