"""
ROXYMASTER v8.0 - ROXYBROWSER API CLIENT (PCBOT)
Unico modulo que se comunica con la API de RoxyBrowser (127.0.0.1:50000).
"""

import logging
import requests

logger = logging.getLogger(__name__)

ROXY_BASE = "http://127.0.0.1:50000"


class RoxyBrowserAPI:
    """
    Cliente HTTP para RoxyBrowser.
    Asume que los perfiles YA ESTAN INICIADOS manualmente por el usuario.
    """

    def __init__(self, base_url=ROXY_BASE):
        self.base = base_url
        self.timeout = 5

    # ------------------------------------------------------------------
    # Deteccion de perfiles
    # ------------------------------------------------------------------
    def get_profiles(self) -> list:
        """
        Obtiene la lista de perfiles de RoxyBrowser.
        Retorna lista de dicts con llaves: id, name, status, port, wsEndpoint.
        """
        try:
            resp = requests.get(f"{self.base}/api/browsers", timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                profiles = data if isinstance(data, list) else []
                logger.info(f"Perfiles detectados via RoxyBrowser API: {len(profiles)}")
                return profiles
            logger.warning(f"RoxyBrowser API retorno status {resp.status_code}")
            return []
        except requests.ConnectionError:
            logger.warning("RoxyBrowser no detectado en 127.0.0.1:50000")
            return []
        except Exception as e:
            logger.error(f"Error consultando RoxyBrowser: {e}")
            return []

    def get_profile_by_id(self, profile_id: str) -> dict:
        """Obtiene un perfil especifico por su ID."""
        profiles = self.get_profiles()
        for p in profiles:
            if str(p.get("id", "")) == str(profile_id):
                return p
        return {}

    def is_profile_running(self, profile_id: str) -> bool:
        """Verifica si un perfil esta corriendo."""
        p = self.get_profile_by_id(profile_id)
        return p.get("status", "").lower() in ("running", "active", "ok", "")

    # ------------------------------------------------------------------
    # Navegacion de perfiles YA ABIERTOS
    # ------------------------------------------------------------------
    def navigate(self, profile_id: str, url: str) -> bool:
        """
        Navega un perfil YA ABIERTO a una URL.
        Usa la API nativa de RoxyBrowser.
        Retorna True si la orden fue aceptada.
        """
        try:
            resp = requests.post(
                f"{self.base}/api/browser/{profile_id}/navigate",
                json={"url": url},
                timeout=self.timeout
            )
            if resp.status_code == 200:
                logger.info(f"Perfil {profile_id} navegando a: {url}")
                return True
            logger.warning(f"Navigate fallo para perfil {profile_id}: status={resp.status_code}")
            return False
        except Exception as e:
            logger.error(f"Error navegando perfil {profile_id}: {e}")
            return False

    def close_profile(self, profile_id: str) -> bool:
        """Cierra un perfil."""
        try:
            resp = requests.post(
                f"{self.base}/api/browser/{profile_id}/close",
                timeout=self.timeout
            )
            return resp.status_code == 200
        except Exception as e:
            logger.error(f"Error cerrando perfil {profile_id}: {e}")
            return False

    def get_profile_page_url(self, profile_id: str) -> str:
        """Obtiene la URL actual que esta viendo un perfil."""
        try:
            resp = requests.get(
                f"{self.base}/api/browser/{profile_id}/url",
                timeout=self.timeout
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("url", "") if isinstance(data, dict) else ""
            return ""
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def ping(self) -> bool:
        """Verifica si RoxyBrowser esta vivo."""
        try:
            resp = requests.get(f"{self.base}/api/browsers", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def get_version(self) -> str:
        """Obtiene la version de RoxyBrowser."""
        try:
            resp = requests.get(f"{self.base}/api/version", timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("version", "unknown") if isinstance(data, dict) else "unknown"
            return "unknown"
        except Exception:
            return "unknown"