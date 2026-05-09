"""
roxymaster v8.3 - roxybrowser api (pcbot)
cliente http para interactuar con la api interna de roxybrowser.
ahora soporta autenticacion por apikey (x-api-key header).
el workspace_id se autodetecta o se recibe via api.
con estrategia multi-endpoint por compatibilidad.
incluye get_workspaces() para listar workspaces remotos.
todo en minusculas, utf-8 sin bom.
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
    soporta x-api-key para autenticacion, X-Workspace-Id header y workspaceId como query param.
    roxybrowser v8.3 requiere query param workspaceId en todos los endpoints."""

    def __init__(self, api_url: str = "http://127.0.0.1:50000", workspace_id: str = "", api_key: str = ""):
        self.base = api_url.rstrip("/")
        self.timeout = 5
        self._workspace_id = workspace_id or find_workspace_id()
        self._api_key = api_key
        self._last_raw_profiles = []  # cache del ultimo get_profiles

    def set_api_key(self, api_key: str):
        """configura la apikey de roxybrowser."""
        self._api_key = api_key
        logger.info("apikey de roxybrowser configurada")

    def set_workspace_id(self, workspace_id: str):
        """configura el workspace_id manualmente."""
        self._workspace_id = workspace_id
        logger.info(f"workspace_id configurado: {workspace_id}")

    def get_api_key(self) -> str:
        return self._api_key

    def _headers(self) -> dict:
        h = {}
        if self._api_key:
            h["x-api-key"] = self._api_key
        if self._workspace_id:
            h["X-Workspace-Id"] = self._workspace_id
        return h

    def _request(self, method: str, path: str, **kwargs) -> requests.Response | None:
        headers = kwargs.pop("headers", {})
        headers.update(self._headers())
        params = kwargs.pop("params", {})
        # workspaceId como query param siempre que exista workspace_id,
        # porque roxybrowser v8.3 lo requiere en todos los endpoints
        if self._workspace_id and "workspaceId" not in str(params) and "workspaceId" not in path:
            params["workspaceId"] = self._workspace_id
        try:
            return requests.request(
                method, f"{self.base}{path}",
                headers=headers, params=params, timeout=self.timeout, **kwargs
            )
        except requests.ConnectionError:
            return None
        except Exception as e:
            logger.error(f"error en request {method} {path}: {e}")
            return None

    # ------------------------------------------------------------------
    # workspaces - listar workspaces remotos asociados a una apikey
    # ------------------------------------------------------------------
    def get_workspaces(self, api_key: str = "") -> list:
        """obtiene lista de workspaces asociados a una apikey.
        si se pasa api_key, se usa temporalmente para la consulta.
        devuelve lista de dicts con id y name."""
        if api_key:
            old_key = self._api_key
            self._api_key = api_key
            restored = False
        else:
            old_key = None
            restored = True

        try:
            resp = self._request("GET", "/api/workspaces")
            if resp is None:
                logger.warning("roxybrowser no responde en get_workspaces")
                return []

            if resp.status_code == 200:
                try:
                    data = resp.json()
                except Exception:
                    logger.warning("respuesta json invalida en get_workspaces")
                    return []

                if isinstance(data, list):
                    return self._normalizar_workspaces(data)

                if isinstance(data, dict):
                    for key in ("data", "workspaces", "items", "results"):
                        inner = data.get(key, [])
                        if isinstance(inner, list):
                            return self._normalizar_workspaces(inner)
                    # si el dict mismo tiene id, es un workspace unico
                    if data.get("id") or data.get("workspace_id"):
                        return self._normalizar_workspaces([data])

                return []

            logger.warning(f"get_workspaces status {resp.status_code}")
            return []
        finally:
            if old_key is not None and not restored:
                self._api_key = old_key

    def _normalizar_workspaces(self, workspaces: list) -> list:
        """normaliza la lista de workspaces a formato estandar."""
        result = []
        for w in workspaces:
            if isinstance(w, dict):
                wid = w.get("id", "") or w.get("workspace_id", "") or w.get("_id", "")
                name = w.get("name", "") or w.get("nombre", "") or w.get("title", "")
                if wid:
                    result.append({
                        "workspace_id": str(wid),
                        "nombre": str(name),
                    })
        return result

    # ------------------------------------------------------------------
    # perfiles (browsers) - estrategia multi-endpoint
    # ------------------------------------------------------------------
    def get_profiles(self) -> list:
        """obtiene lista de perfiles/browsers activos.
        prueba varios endpoints en orden porque la api de roxybrowser
        cambia entre versiones (v2.7 vs v3.8).
        workspaceId se envia automaticamente como query param por _request.
        """
        # lista de (path, descripcion) a probar en orden
        rutas = [
            ("/api/browsers", "api simple"),
            (f"/api/workspace/{self._workspace_id}/browsers", "workspace en path"),
            ("/api/workspace/browsers", "workspace en path sin id"),
        ]
        # tambien probar con query param explicito
        if self._workspace_id:
            resp, data = self._try_path(f"/api/browsers?workspaceId={self._workspace_id}")
            if resp and data:
                self._last_raw_profiles = data
                return data

        for path, desc in rutas:
            if not self._workspace_id and "workspace" in path and self._workspace_id not in path:
                continue
            resp, data = self._try_path(path)
            if resp and data:
                logger.info(f"perfiles obtenidos via {desc}: {len(data)}")
                self._last_raw_profiles = data
                return data
            elif resp is not None:
                continue

        logger.warning("no se pudieron obtener perfiles de roxybrowser")
        self._last_raw_profiles = []
        return []

    def _try_path(self, path: str) -> tuple:
        """intenta obtener perfiles desde un path.
        devuelve (response_data, parsed_data) si success, (resp, []) si falla."""
        resp = self._request("GET", path)
        if resp is None:
            return None, []

        if resp.status_code == 200:
            try:
                data = resp.json()
            except Exception:
                return resp, []

            if isinstance(data, list):
                return resp, data

            if isinstance(data, dict):
                # varios formatos posibles
                for key in ("data", "browsers", "profiles", "items", "results"):
                    inner = data.get(key, [])
                    if isinstance(inner, list) and len(inner) > 0:
                        return resp, inner

                # codigo 101 = workspace_id requerido
                if data.get("code") == 101:
                    logger.warning(f"roxybrowser {path}: {data.get('msg', 'workspace_id requerido')}")
                    return resp, []

                # si el dict tiene keys que parecen perfiles, convertirlo
                if len(data) > 0:
                    return resp, [data]

            return resp, []

        # error 400/404/500
        logger.debug(f"roxybrowser {path} -> status {resp.status_code}")
        return resp, []

    def get_profiles_detallados(self) -> list:
        """obtiene perfiles con campos completos: id, name, hash_interno, workspace, status.
        utl para enviar al servidor cuando se configura la apikey."""
        perfiles = self.get_profiles()
        result = []
        for p in perfiles:
            result.append({
                "id": str(p.get("id", "")),
                "name": p.get("name", p.get("nombre", "")),
                "hash_interno": p.get("hash_interno", p.get("hash", "")),
                "workspace": p.get("workspace", p.get("workspace_id", self._workspace_id)),
                "status": p.get("status", p.get("estado", "unknown")),
            })
        return result

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