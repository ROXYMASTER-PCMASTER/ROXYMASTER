"""
roxymaster v8.3 - profile manager (pcbot)
gestion de perfiles con estados (active/inactive/hung).
navegacion via roxybrowser api, health checks.
todo en minusculas, utf-8 sin bom.
"""

import asyncio
import logging
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


class ProfileState(Enum):
    INACTIVE = auto()
    ACTIVE = auto()
    HUNG = auto()


@dataclass
class Profile:
    id: str
    name: str = ""
    type: str = "local"
    state: ProfileState = ProfileState.INACTIVE
    current_url: str = ""
    duracion_min: int = 60
    inicio: float = 0.0
    fail_count: int = 0
    hash_interno: str = ""
    metadata: dict = field(default_factory=dict)


class ProfileManager:
    """gestiona perfiles, navegacion y health checks."""

    def __init__(self, roxy_api=None):
        self.profiles: dict[str, Profile] = {}
        self.roxy = roxy_api

    def register_profiles(self, profiles_data: list):
        """registra perfiles desde datos de roxybrowser o deteccion local."""
        for pdata in profiles_data:
            if isinstance(pdata, dict):
                pid = str(pdata.get("id", pdata.get("hash", "")))
                if not pid:
                    continue
                name = pdata.get("name", pdata.get("nombre", pid))
                ptype = pdata.get("type", pdata.get("tipo", "local"))
                if pid not in self.profiles:
                    self.profiles[pid] = Profile(
                        id=pid,
                        name=name,
                        type=ptype,
                        hash_interno=pdata.get("hash_interno", ""),
                        metadata=pdata,
                    )
                else:
                    self.profiles[pid].name = name
                    self.profiles[pid].metadata = pdata

    def get_profile(self, profile_id: str) -> Optional[Profile]:
        return self.profiles.get(profile_id)

    def get_all_states(self) -> dict:
        counts = {"active": 0, "inactive": 0, "hung": 0}
        states = {}
        for pid, p in self.profiles.items():
            sname = p.state.name.lower()
            states[pid] = sname
            if sname in counts:
                counts[sname] += 1
        return {"states": states, "counts": counts}

    async def navigate_to(self, profile_id: str, url: str) -> bool:
        """navega un perfil a la url indicada via roxybrowser api."""
        if not self.roxy:
            logger.warning("roxybrowser api no disponible para navegar")
            return False
        try:
            ok = self.roxy.navigate(profile_id, url)
            if ok:
                p = self.profiles.get(profile_id)
                if p:
                    p.current_url = url
                    p.state = ProfileState.ACTIVE
                    logger.info(f"perfil {profile_id} navegando a {url}")
            return ok
        except Exception as e:
            logger.error(f"error navegando perfil {profile_id}: {e}")
            return False

    async def close_profile(self, profile_id: str) -> bool:
        """cierra un perfil via roxybrowser api."""
        if not self.roxy:
            return False
        try:
            ok = self.roxy.close_profile(profile_id)
            if ok:
                p = self.profiles.get(profile_id)
                if p:
                    p.state = ProfileState.INACTIVE
                    p.current_url = ""
                    logger.info(f"perfil {profile_id} cerrado")
            return ok
        except Exception as e:
            logger.error(f"error cerrando perfil {profile_id}: {e}")
            return False

    async def redirect_to_portal(self, profile_id: str, portal_url: str) -> bool:
        """redirige un perfil al portal local."""
        return await self.navigate_to(profile_id, portal_url)

    def mark_hung(self, profile_id: str):
        p = self.profiles.get(profile_id)
        if p:
            p.state = ProfileState.HUNG
            p.fail_count += 1
            logger.warning(f"perfil {profile_id} marcado como hung")

    def check_all_health(self) -> dict:
        """verifica health de todos los perfiles.
        marca como hung si fail_count excede 3."""
        health = {}
        for pid, p in self.profiles.items():
            if p.fail_count >= 3:
                p.state = ProfileState.HUNG
                health[pid] = "hung"
            else:
                health[pid] = p.state.name.lower()
        return health

    async def execute_on_profiles(self, pids: list, url: str, duracion: int = 60):
        """asigna una url a una lista de perfiles."""
        tasks = []
        for pid in pids:
            p = self.profiles.get(pid)
            if p and p.state != ProfileState.HUNG:
                p.duracion_min = duracion
                tasks.append(self.navigate_to(pid, url))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def stop_all(self):
        """detiene todos los perfiles activos."""
        tasks = []
        for pid, p in self.profiles.items():
            if p.state == ProfileState.ACTIVE:
                tasks.append(self.close_profile(pid))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def get_activos(self) -> list:
        return [p for p in self.profiles.values() if p.state == ProfileState.ACTIVE]

    def get_inactivos(self) -> list:
        return [p for p in self.profiles.values() if p.state == ProfileState.INACTIVE]