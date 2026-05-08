"""
roxymaster v8.3 - state tracker (pcbot)
temporizador de 62 minutos por perfil.
genera eventos de ciclo completado para token_engine.
todo en minusculas, utf-8 sin bom.
"""

import asyncio
import logging
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

CYCLE_DURATION_SECONDS = 62 * 60  # 62 minutos en segundos
GRACIA_ORO = 120  # 2 minutos de tolerancia extra para nivel oro


class StateTracker:
    """temporizador por perfil. llama callback al completar ciclo."""

    def __init__(self, on_cycle_complete: Optional[Callable] = None):
        self._start_times: dict[str, float] = {}
        self._elapsed: dict[str, float] = {}
        self._running: dict[str, bool] = {}
        self._on_cycle = on_cycle_complete or (lambda pid: None)
        self._gracioso: dict[str, int] = {}  # segundos de gracia extra
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    def set_on_cycle_complete(self, callback: Callable):
        """configura callback para ciclo completado."""
        self._on_cycle = callback
        logger.info("state_tracker: callback de ciclo registrado")

    def start_tracking(self, profile_id: str, nivel: str = "bronce"):
        """alias de start_profile para compatibilidad con main.py."""
        self.start_profile(profile_id, nivel)

    async def check_cycles(self):
        """verifica ciclos completados y dispara callback (para main loop)."""
        for pid in self.get_completed_profiles():
            if self._running.get(pid, False):
                logger.info(f"state_tracker: ciclo completo detectado para perfil {pid}")
                try:
                    result = self._on_cycle(pid)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as e:
                    logger.error(f"error en callback de ciclo: {e}")
                self.stop_profile(pid)

    def start_profile(self, profile_id: str, nivel: str = "bronce"):
        """inicia contador para un perfil. se resetea si ya existe."""
        self._start_times[profile_id] = time.time()
        self._elapsed[profile_id] = 0.0
        self._running[profile_id] = True
        self._gracioso[profile_id] = GRACIA_ORO if nivel == "oro" else 0
        logger.info(
            f"state_tracker: perfil {profile_id} iniciado (nivel={nivel}, "
            f"gracia={self._gracioso[profile_id]}s)"
        )

    def stop_profile(self, profile_id: str) -> float:
        """detiene contador. devuelve segundos acumulados."""
        if profile_id in self._start_times:
            self._running[profile_id] = False
            segundos = self.get_elapsed(profile_id)
            if segundos >= CYCLE_DURATION_SECONDS:
                logger.info(f"state_tracker: perfil {profile_id} completo ({segundos}s)")
            else:
                logger.info(
                    f"state_tracker: perfil {profile_id} detenido ({segundos}s de {CYCLE_DURATION_SECONDS}s)"
                )
            return segundos
        return 0.0

    def reset_profile(self, profile_id: str):
        """resetea contador (desconexion parcial antes de completar ciclo)."""
        if profile_id in self._start_times:
            del self._start_times[profile_id]
            self._elapsed[profile_id] = 0.0
            self._running[profile_id] = False
            if profile_id in self._gracioso:
                del self._gracioso[profile_id]
            logger.info(f"state_tracker: perfil {profile_id} reseteado")

    def get_elapsed(self, profile_id: str) -> float:
        """devuelve segundos transcurridos para un perfil."""
        if profile_id in self._start_times and self._running.get(profile_id, False):
            return time.time() - self._start_times[profile_id]
        return self._elapsed.get(profile_id, 0.0)

    def is_complete(self, profile_id: str) -> bool:
        """verifica si un perfil completo el ciclo."""
        elapsed = self.get_elapsed(profile_id)
        gracia = self._gracioso.get(profile_id, 0)
        return elapsed >= (CYCLE_DURATION_SECONDS + gracia)

    def safe_reset_rule(self, profile_id: str, nivel: str = "bronce") -> bool:
        """regla de safe reset: si nivel oro y tiempo >= CYCLE_DURATION, no resetea.
        devuelve True si debe resetearse."""
        elapsed = self.get_elapsed(profile_id)
        if nivel == "oro" and elapsed >= CYCLE_DURATION_SECONDS:
            logger.info(
                f"state_tracker: perfil {profile_id} oro, ciclo completo "
                f"({elapsed}s), no se resetea aunque se desconecte"
            )
            return False
        return True

    def get_all_status(self) -> dict:
        """devuelve estado de todos los perfiles."""
        status = {}
        now = time.time()
        for pid in list(self._start_times.keys()):
            running = self._running.get(pid, False)
            if running:
                elapsed = now - self._start_times.get(pid, now)
            else:
                elapsed = self._elapsed.get(pid, 0.0)
            remaining = max(0.0, CYCLE_DURATION_SECONDS - elapsed)
            status[pid] = {
                "running": running,
                "elapsed_seconds": round(elapsed, 1),
                "remaining_seconds": round(remaining, 1),
                "complete": elapsed >= CYCLE_DURATION_SECONDS,
                "progress_pct": round(min(100.0, (elapsed / CYCLE_DURATION_SECONDS) * 100), 1),
            }
        return status

    def get_completed_profiles(self) -> list[str]:
        """devuelve lista de profile_ids que completaron ciclo."""
        completed = []
        for pid in list(self._start_times.keys()):
            if self.is_complete(pid):
                completed.append(pid)
        return completed

    async def _check_loop(self, interval: float = 5.0):
        """loop interno que revisa ciclos completados cada `interval` segundos."""
        try:
            while not self._stop_event.is_set():
                for pid in self.get_completed_profiles():
                    if self._running.get(pid, False):
                        logger.info(f"state_tracker: ciclo completo para perfil {pid}")
                        self._on_cycle(pid)
                        self.stop_profile(pid)
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("state_tracker: ciclo de verificacion cancelado")

    async def start(self, interval: float = 5.0):
        """inicia el loop de verificacion de ciclos."""
        self._stop_event.clear()
        self._task = asyncio.create_task(self._check_loop(interval))
        logger.info("state_tracker: iniciado")

    async def stop(self):
        """detiene el loop de verificacion."""
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("state_tracker: detenido")