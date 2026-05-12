"""
roxymaster v8.3 - profile manager (pcbot)
gestion de perfiles con estados (active/inactive/hung).
navegacion via roxybrowser api, health checks.
todo en minusculas, utf-8 sin bom.
"""

import asyncio
import logging
import time
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
    nivel_comentarios: int = 0
    pedidos_ids: list = field(default_factory=list)  # ids de pedidos que usan este perfil
    metadata: dict = field(default_factory=dict)


class ProfileManager:
    """gestiona perfiles, navegacion y health checks."""

    def __init__(self, roxy_api=None):
        self.profiles: dict[str, Profile] = {}
        self.roxy = roxy_api
        # bug 2: mutex por perfil para evitar operaciones simultaneas
        self._perfiles_en_uso: dict[str, bool] = {}

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
        """navega un perfil a la url indicada via roxybrowser api.
        inicia monitor cdp si es exitoso.
        bug 2: usa mutex para evitar operaciones simultaneas sobre el mismo perfil."""
        if self._perfiles_en_uso.get(profile_id):
            logger.warning(f"perfil {profile_id[:16]}... esta en uso, no se puede navegar ahora")
            return False
        if not self.roxy:
            logger.warning("roxybrowser api no disponible para navegar")
            return False
        self._perfiles_en_uso[profile_id] = True
        try:
            ok = await self.roxy.navigate_async(profile_id, url)
            if ok:
                p = self.profiles.get(profile_id)
                if p:
                    p.current_url = url
                    p.state = ProfileState.ACTIVE
                    p.inicio = time.time()
                    logger.info(f"perfil {profile_id} navegando a {url}")
                    # iniciar monitor cdp para detectar cierre abrupto
                    cdp_ws = self.roxy.get_cdp_ws(profile_id)
                    if cdp_ws:
                        asyncio.create_task(
                            self.start_cdp_monitor(profile_id, cdp_ws)
                        )
            return ok
        except Exception as e:
            logger.error(f"error navegando perfil {profile_id}: {e}")
            return False
        finally:
            self._perfiles_en_uso.pop(profile_id, None)

    async def close_profile(self, profile_id: str) -> bool:
        """cierra un perfil via roxybrowser api.
        bug 2: usa mutex para evitar operaciones simultaneas sobre el mismo perfil."""
        if self._perfiles_en_uso.get(profile_id):
            logger.warning(f"perfil {profile_id[:16]}... esta en uso, no se puede cerrar ahora")
            return False
        if not self.roxy:
            return False
        self._perfiles_en_uso[profile_id] = True
        try:
            # roxy.close_profile es sincrono, ejecutar en executor para no bloquear
            loop = asyncio.get_event_loop()
            ok = await loop.run_in_executor(None, self.roxy.close_profile, profile_id)
            if ok:
                p = self.profiles.get(profile_id)
                if p:
                    p.state = ProfileState.INACTIVE
                    p.current_url = ""
                    p.inicio = 0.0
                    logger.info(f"perfil {profile_id} cerrado")
            return ok
        except Exception as e:
            logger.error(f"error cerrando perfil {profile_id}: {e}")
            return False
        finally:
            self._perfiles_en_uso.pop(profile_id, None)

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

    async def start_cdp_monitor(self, profile_id: str, cdp_ws: str):
        """monitorea la conexion websocket cdp de un perfil.
        si la conexion se cierra inesperadamente, marca el perfil como inactive."""
        if not cdp_ws:
            return
        try:
            import websockets
            async with websockets.connect(cdp_ws, ping_interval=None, close_timeout=5) as ws:
                logger.info(f"monitor cdp iniciado para perfil {profile_id[:16]}...")
                while True:
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=30)
                    except asyncio.TimeoutError:
                        continue
        except websockets.ConnectionClosed:
            logger.warning(f"cdp cerrado abruptamente para perfil {profile_id[:16]}...")
        except Exception as e:
            logger.debug(f"monitor cdp finalizado para perfil {profile_id[:16]}...: {e}")
        # si llegamos aqui, el websocket se cerro -> marcar como inactive
        p = self.profiles.get(profile_id)
        if p and p.state == ProfileState.ACTIVE:
            p.state = ProfileState.INACTIVE
            p.current_url = ""
            logger.info(f"perfil {profile_id[:16]}... marcado como inactive por cdp caido")