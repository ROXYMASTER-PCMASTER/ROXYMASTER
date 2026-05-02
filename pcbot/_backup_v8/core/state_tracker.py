"""
ROXYMASTER v8.0 - STATE TRACKER (PCBOT)
Monitorea el tiempo de sesion por perfil (62 min = 1 ciclo KBT).
Notifica cuando un perfil completa su ciclo para generar tokens.
"""

import asyncio
import logging
import time

logger = logging.getLogger(__name__)

CYCLE_MINUTES = 62
CYCLE_SECONDS = CYCLE_MINUTES * 60


class TrackerEntry:
    def __init__(self, profile_id: str):
        self.profile_id = profile_id
        self.started_at = time.time()
        self.elapsed = 0.0
        self.completed = False
        self.kbt_earned = 0


class StateTracker:
    """
    Controla el temporizador de 62 minutos por perfil.
    Cada perfil activo que completa 62 minutos ininterrumpidos gana KBT.
    """

    def __init__(self):
        self.entries: dict[str, TrackerEntry] = {}
        self.cycle_seconds = CYCLE_SECONDS
        self.on_cycle_complete = None

    def set_on_cycle_complete(self, handler):
        """handler(profile_id, kbt_amount)"""
        self.on_cycle_complete = handler

    def start_tracking(self, profile_id: str):
        if profile_id not in self.entries:
            self.entries[profile_id] = TrackerEntry(profile_id)
        self.entries[profile_id].started_at = time.time()
        self.entries[profile_id].completed = False
        logger.info(f"Tracker iniciado para perfil {profile_id}")

    def stop_tracking(self, profile_id: str):
        if profile_id in self.entries:
            self.entries[profile_id].completed = True
            logger.info(f"Tracker detenido para perfil {profile_id}")

    def get_remaining(self, profile_id: str) -> float:
        """Segundos restantes para completar el ciclo."""
        entry = self.entries.get(profile_id)
        if not entry or entry.completed:
            return 0
        elapsed = time.time() - entry.started_at
        return max(0, self.cycle_seconds - elapsed)

    def get_progress(self, profile_id: str) -> dict:
        """Porcentaje de progreso y tiempo restante."""
        entry = self.entries.get(profile_id)
        if not entry:
            return {"percent": 0, "remaining_sec": 0, "completed": False}

        if entry.completed:
            return {"percent": 100, "remaining_sec": 0, "completed": True}

        elapsed = time.time() - entry.started_at
        percent = min(100, (elapsed / self.cycle_seconds) * 100)
        remaining = max(0, self.cycle_seconds - elapsed)
        return {
            "percent": round(percent, 1),
            "remaining_sec": round(remaining),
            "remaining_min": round(remaining / 60, 1),
            "completed": False
        }

    def get_all_progress(self) -> dict:
        result = {}
        for pid in self.entries:
            result[pid] = self.get_progress(pid)
        return result

    async def check_cycles(self):
        """Verifica si algun perfil completo su ciclo de 62 min."""
        for pid, entry in list(self.entries.items()):
            if entry.completed:
                continue
            elapsed = time.time() - entry.started_at
            if elapsed >= self.cycle_seconds:
                entry.completed = True
                entry.kbt_earned += 1
                logger.info(f"Perfil {pid} completo ciclo de {CYCLE_MINUTES} min. Gano 1 KBT!")
                if self.on_cycle_complete:
                    await self.on_cycle_complete(pid, 1)