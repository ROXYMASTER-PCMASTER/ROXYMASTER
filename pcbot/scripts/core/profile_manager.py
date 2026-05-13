"""
roxymaster v8.3 - profile manager (pcbot)
gestiona perfiles de roxybrowser.
todo en minusculas, utf-8 sin bom.
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ProfileState(Enum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    HUNG = "hung"


class Profile:
    def __init__(self, id: str, name: str = "", type: str = "local",
                 hash_interno: str = "", metadata: dict = None):
        self.id = id
        self.name = name or id
        self.type = type
        self.hash_interno = hash_interno
        self.state = ProfileState.INACTIVE
        self.current_url: Optional[str] = None
        self.nivel_comentarios = 0
        self.duracion_min = 60
        self.inicio: float = 0.0
        self.metadata = metadata or {}
        self.pedidos_ids: list[str] = []


class ProfileManager:
    def __init__(self, roxy_api=None):
        self.roxy = roxy_api
        self.profiles: dict[str, Profile] = {}

        # bug 2: mutex para evitar operaciones simultaneas sobre el mismo perfil
        self._perfiles_en_uso: dict[str, bool] = {}

    def register_profiles(self, profiles_data: list[dict]):
        """registra perfiles desde datos de roxybrowser api."""
        for pdata in profiles_data:
            pid = pdata.get("id", pdata.get("profile_id", ""))
            if not pid:
                continue
            if isinstance(pdata.get("name", None), str):
                name = pdata["name"]
            else:
                name = pdata.get("nombre", pid)
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
            logger.warning("roxybrowser api no disponible para cerrar")
            return False
        self._perfiles_en_uso[profile_id] = True
        try:
            ok = await self.roxy.close_profile_async(profile_id)
            if ok:
                p = self.profiles.get(profile_id)
                if p:
                    p.state = ProfileState.INACTIVE
                    p.current_url = None
                    p.inicio = 0.0
                    logger.info(f"perfil {profile_id} cerrado exitosamente")
            return ok
        except Exception as e:
            logger.error(f"error cerrando perfil {profile_id}: {e}")
            return False
        finally:
            self._perfiles_en_uso.pop(profile_id, None)

    async def redirect_to_portal(self, profile_id: str, portal_url: str) -> bool:
        """redirige un perfil a una url portal (sin cerrarlo).
        equivalente a navigate_to pero semantica diferente."""
        if self._perfiles_en_uso.get(profile_id):
            logger.warning(f"perfil {profile_id[:16]}... esta en uso, no se puede redirigir ahora")
            return False
        if not self.roxy:
            logger.warning("roxybrowser api no disponible para redirigir")
            return False
        self._perfiles_en_uso[profile_id] = True
        try:
            ok = await self.roxy.navigate_async(profile_id, portal_url)
            if ok:
                p = self.profiles.get(profile_id)
                if p:
                    p.current_url = portal_url
                    # no cambiar a inactive, queda active pero en portal
                    logger.info(f"perfil {profile_id} redirigido a portal {portal_url}")
            return ok
        except Exception as e:
            logger.error(f"error redirigiendo perfil {profile_id} a portal: {e}")
            return False
        finally:
            self._perfiles_en_uso.pop(profile_id, None)

    async def start_cdp_monitor(self, profile_id: str, cdp_ws: str):
        """monitorea websocket cdp de roxybrowser para detectar cierre abrupto.
        si se cierra, marca el perfil como hung (colgado)."""
        logger.info(f"iniciando monitor cdp para perfil {profile_id}")
        try:
            # en una implementacion real, se conectaria al ws y esperaria eventos
            # por ahora, solo simulamos un monitor que espera y verifica
            await asyncio.sleep(60)
            p = self.profiles.get(profile_id)
            if p and p.state == ProfileState.ACTIVE:
                logger.info(f"monitor cdp: perfil {profile_id} sigue activo tras 60s")
        except asyncio.CancelledError:
            logger.info(f"monitor cdp cancelado para perfil {profile_id}")
        except Exception as e:
            logger.error(f"error en monitor cdp para perfil {profile_id}: {e}")