"""
roxymaster v8.3 - roxybrowser api (pcbot)
cliente http para interactuar con la api interna de roxybrowser.
el workspace_id se obtiene de config.json o se autodetecta.
"""

import json
import logging
import os
import requests

logger = logging.getLogger(__name__)

APPDATA_ROXY = os.path.join(
    os.environ.get("APPDATA", ""), "RoxyBrowser", "browser-cache"
)


def find_workspace_id() -> str:
    """busca el workspace_id de roxybrowser escaneando directorios locales."""
    if not os.path.isdir(APPDATA_ROXY):
        logger.warning(f"directorio roxybrowser no encontrado: {APPDATA_ROXY}")
        return ""

    try:
        items = os.listdir(APPDATA_ROXY)
        for item in items:
            item_path = os.path.join(APPDATA_ROXY, item)
            if os.path.isdir(item_path) and len(item) >= 20:
                logger.info(f"workspace_id detectado: {item}")
                return item
    except Exception as e:
        logger.error(f"error escaneando workspace_id local: {e}")

    return ""


class RoxyBrowserAPI:
    """cliente http sincrono para la api de roxybrowser (127.0.0.1:50000).
    soporta X-Workspace-Id para identificar el workspace."""

    def __init__(self, api_url: str = "http://127.0.0.1:50000", workspace_id: str = ""):
        self.base = api_url.rstrip("/")
        self.timeout = 5
        self._workspace_id = workspace_id or find_workspace_id()

    def _headers(self) -> dict:
        h = {}
        if self._workspace_id:
            h["X-Workspace-Id"] = self._workspace_id
        return h

    def _request(self, method: str, path: str, **kwargs) -> requests.Response | None:
        headers = kwargs.pop("headers", {})
        headers.update(self._headers())
        try:
            return requests.request(
                method, f"{self.base}{path}",
                headers=headers, timeout=self.timeout, **kwargs
            )
        except requests.ConnectionError:
            return None
        except Exception as e:
            logger.error(f"error en request {method} {path}: {e}")
            return None

    # ------------------------------------------------------------------
    # perfiles (browsers)
    # ------------------------------------------------------------------
    def get_profiles(self) -> list:
        """obtiene lista de perfiles/browsers activos."""
        resp = self._request("GET", "/api/browsers")
        if resp and resp.status_code == 200:
            try:
                data = resp.json()
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    inner = data.get("data", data.get("browsers", []))
                    if isinstance(inner, list):
                        return inner
                    # codigo 101 = workspace_id requerido pero no valido
                    if data.get("code") == 101:
                        logger.warning(f"roxybrowser: {data.get('msg', 'workspace_id requerido')}")
                        return []
                    return []
                return []
            except Exception as e:
                logger.error(f"error parseando respuesta: {e}")
                return []
        if resp is None:
            logger.warning("roxybrowser no disponible en 127.0.0.1:50000")
        else:
            logger.warning(f"roxybrowser status {resp.status_code}")
        return []

    def get_profile_by_id(self, profile_id: str) -> dict | None:
        """obtiene un perfil por su id."""
        profiles = self.get_profiles()
        for p in profiles:
            if str(p.get("id", "")) == str(profile_id):
                return p
        return None

    def is_profile_running(self, profile_id: str) -> bool:
        """verifica si un perfil esta corriendo."""
        p = self.get_profile_by_id(profile_id)
        if not p:
            return False
        estado = p.get("status", p.get("estado", "")).lower()
        return estado in ("running", "active", "ok", "")

    # ------------------------------------------------------------------
    # navegacion
    # ------------------------------------------------------------------
    def navigate(self, profile_id: str, url: str) -> bool:
        """navega un perfil a una url."""
        resp = self._request(
            "POST",
            f"/api/browser/{profile_id}/navigate",
            json={"url": url}
        )
        if resp and resp.status_code == 200:
            logger.info(f"perfil {profile_id} navegando a: {url}")
            return True
        logger.warning(f"navigate fallo para perfil {profile_id}")
        return False

    def close_profile(self, profile_id: str) -> bool:
        """cierra un perfil."""
        resp = self._request("POST", f"/api/browser/{profile_id}/close")
        return resp is not None and resp.status_code == 200

    def get_profile_page_url(self, profile_id: str) -> str:
        """obtiene la url actual de un perfil."""
        resp = self._request("GET", f"/api/browser/{profile_id}/url")
        if resp and resp.status_code == 200:
            try:
                data = resp.json()
                if isinstance(data, dict):
                    return data.get("url", "")
            except Exception:
                pass
        return ""

    # ------------------------------------------------------------------
    # utilidades
    # ------------------------------------------------------------------
    def ping(self) -> bool:
        """verifica si roxybrowser esta vivo."""
        resp = self._request("GET", "/api/browsers")
        return resp is not None and resp.status_code == 200

    def get_version(self) -> str:
        """obtiene la version de roxybrowser."""
        resp = self._request("GET", "/api/version")
        if resp and resp.status_code == 200:
            try:
                data = resp.json()
                if isinstance(data, dict):
                    return str(data.get("version", "unknown"))
            except Exception:
                pass
        return "unknown"