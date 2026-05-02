"""
ROXYMASTER v8.0 - PROFILE MANAGER (PCBOT)
Gestiona perfiles: abrir, reusar, cerrar, detectar estado.
Se comunica exclusivamente via RoxyBrowserAPI.
"""

import logging
import time

logger = logging.getLogger(__name__)

class ProfileState:
    ACTIVE = "active"
    INACTIVE = "inactive"
    HUNG = "hung"


class Profile:
    def __init__(self, profile_id: str, name: str = "", ws_endpoint: str = ""):
        self.id = profile_id
        self.name = name
        self.ws_endpoint = ws_endpoint
        self.state = ProfileState.INACTIVE
        self.current_url = ""
        self.session_start = 0.0
        self.last_check = 0.0
        self.fail_count = 0


class ProfileManager:
    """
    Gestiona el ciclo de vida de los perfiles en PCBOT.
    Solo utiliza RoxyBrowserAPI para interactuar con perfiles.
    """

    MAX_FAIL_COUNT = 3

    def __init__(self, roxy_api):
        self.api = roxy_api
        self.profiles: dict[str, Profile] = {}

    # ------------------------------------------------------------------
    # Registro de perfiles
    # ------------------------------------------------------------------
    def register_profiles(self, raw_profiles: list):
        """
        Registra perfiles detectados via API de RoxyBrowser.
        raw_profiles: lista de dicts con {id, name, status, wsEndpoint}
        """
        for rp in raw_profiles:
            pid = str(rp.get("id", ""))
            if not pid:
                continue
            if pid not in self.profiles:
                self.profiles[pid] = Profile(
                    profile_id=pid,
                    name=rp.get("name", f"Profile_{pid}"),
                    ws_endpoint=rp.get("wsEndpoint", "")
                )

        for pid in list(self.profiles.keys()):
            if not any(str(r.get("id", "")) == pid for r in raw_profiles):
                del self.profiles[pid]
                logger.info(f"Perfil {pid} removido (ya no existe en RoxyBrowser)")

        logger.info(f"Perfiles registrados: {len(self.profiles)}")

    # ------------------------------------------------------------------
    # Ejecutar comando en perfiles
    # ------------------------------------------------------------------
    async def execute_on_profiles(self, profile_ids: list, url: str, duration_min: float):
        """
        Navega los perfiles indicados a la URL y agenda la redireccion al portal
        tras duration_min minutos.
        Retorna dict {profile_id: success_bool}
        """
        results = {}
        for pid in profile_ids:
            results[pid] = await self._navigate_single(pid, url)
        return results

    async def _navigate_single(self, profile_id: str, url: str) -> bool:
        profile = self.profiles.get(profile_id)
        if not profile:
            logger.warning(f"Perfil {profile_id} no registrado")
            return False

        ok = self.api.navigate(profile_id, url)
        if ok:
            profile.state = ProfileState.ACTIVE
            profile.current_url = url
            profile.session_start = time.time()
            profile.fail_count = 0
            logger.info(f"Perfil {profile_id} navego a {url}")
        else:
            profile.fail_count += 1
            if profile.fail_count >= self.MAX_FAIL_COUNT:
                profile.state = ProfileState.HUNG
                logger.warning(f"Perfil {profile_id} marcado como COLGADO tras {self.MAX_FAIL_COUNT} fallos")
            else:
                profile.state = ProfileState.INACTIVE
        return ok

    # ------------------------------------------------------------------
    # Redirigir al portal
    # ------------------------------------------------------------------
    def redirect_to_portal(self, profile_id: str, portal_url: str) -> bool:
        """Redirige un perfil hacia el portal de inicio."""
        return self.api.navigate(profile_id, portal_url)

    # ------------------------------------------------------------------
    # Verificacion de estado (health check)
    # ------------------------------------------------------------------
    def check_profile_health(self, profile_id: str) -> str:
        """Verifica si un perfil responde. Retorna estado."""
        profile = self.profiles.get(profile_id)
        if not profile:
            return ProfileState.INACTIVE

        current_url = self.api.get_profile_page_url(profile_id)
        if not current_url:
            profile.fail_count += 1
            if profile.fail_count >= self.MAX_FAIL_COUNT:
                profile.state = ProfileState.HUNG
            else:
                profile.state = ProfileState.INACTIVE
        elif current_url != profile.current_url:
            profile.current_url = current_url
            profile.state = ProfileState.ACTIVE
            profile.fail_count = 0

        profile.last_check = time.time()
        return profile.state

    def check_all_health(self) -> dict:
        """Verifica salud de todos los perfiles."""
        states = {ProfileState.ACTIVE: 0, ProfileState.INACTIVE: 0, ProfileState.HUNG: 0}
        for pid in self.profiles:
            s = self.check_profile_health(pid)
            states[s] = states.get(s, 0) + 1
        return states

    # ------------------------------------------------------------------
    # Estado de todos los perfiles
    # ------------------------------------------------------------------
    def get_all_states(self) -> dict:
        """Retorna estados de todos los perfiles para heartbeat."""
        active = []
        inactive = []
        hung = []
        for pid, p in self.profiles.items():
            entry = {
                "id": p.id,
                "name": p.name,
                "current_url": p.current_url,
                "session_seconds": round(time.time() - p.session_start) if p.session_start else 0
            }
            if p.state == ProfileState.ACTIVE:
                active.append(entry)
            elif p.state == ProfileState.HUNG:
                hung.append(entry)
            else:
                inactive.append(entry)

        return {
            "active": active,
            "inactive": inactive,
            "hung": hung,
            "counts": {
                "active": len(active),
                "inactive": len(inactive),
                "hung": len(hung),
                "total": len(self.profiles)
            }
        }