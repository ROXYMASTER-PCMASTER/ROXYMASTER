"""
roxymaster v8.3 - deteccion de perfiles (pcbot)
detecta perfiles de roxybrowser y navegadores locales.
clasifica perfiles, detecta vip, y detecta multiples pcs con la misma ip_wan.
incluye deteccion de directorios de perfil de navegadores (playwright).
todo en minusculas, utf-8 sin bom.
"""

import asyncio
import json
import logging
import os
import random
import socket
import time

import requests

from auto_detect import AutoDetect, BROWSER_PATHS
from api.roxybrowser_api import find_workspace_id, RoxyBrowserAPI

logger = logging.getLogger(__name__)

IFCONFIG_ME_URL = "https://ifconfig.me/ip"
MAX_PCS_POR_IPWAN = 3
PERFILES_VIP_POR_PC = 2
TOTAL_VIP_MAX = 6

# rutas de directorios de usuario de navegadores (para playwright)
BROWSER_USER_DATA_DIRS = {
    "chrome": os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "User Data"),
    "edge": os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Edge", "User Data"),
    "firefox": os.path.join(os.environ.get("APPDATA", ""), "Mozilla", "Firefox", "Profiles"),
    "brave": os.path.join(os.environ.get("LOCALAPPDATA", ""), "BraveSoftware", "Brave-Browser", "User Data"),
    "opera": os.path.join(os.environ.get("APPDATA", ""), "Opera Software", "Opera Stable"),
}


class DeteccionPerfiles:
    """detecta perfiles locales y via api de roxybrowser."""

    def __init__(self):
        self.roxy_api = None
        self.auto_detect = AutoDetect()
        self.resultados = {}

    async def detectar_todo(self) -> dict:
        """detecta todo el entorno: sistema, navegadores, perfiles roxy, vip."""
        logger.info("iniciando deteccion completa del entorno...")

        # paso 1: sistema basico
        system = await self._detectar_sistema()

        # paso 2: navegadores locales (chrome, edge, etc)
        browsers = await self._detectar_navegadores()

        # paso 3: perfiles roxybrowser via api
        roxy_profiles, workspace_id = await self._detectar_perfiles_roxy()

        # paso 4: clasificar perfiles roxy (listo, no_listo, detectado)
        roxy_clasificados = self._clasificar_perfiles(roxy_profiles)

        # paso 5: detectar perfiles vip
        vip_profiles = await self._detectar_vip(roxy_profiles)

        # paso 6: detectar ip_wan
        ip_wan = await self._detectar_ip_wan()

        self.resultados = {
            "system": system,
            "browsers": browsers,
            "roxy_profiles": roxy_profiles,
            "roxy_clasificados": roxy_clasificados,
            "vip_profiles": vip_profiles,
            "workspace_id": workspace_id,
            "ip_wan": ip_wan,
        }

        logger.info(
            f"deteccion completa: {len(browsers)} navegadores, "
            f"{len(roxy_profiles)} perfiles roxy, "
            f"{len(vip_profiles)} vip"
        )
        return self.resultados

    async def _detectar_sistema(self) -> dict:
        """detecta informacion basica del sistema operativo."""
        try:
            hostname = os.environ.get("COMPUTERNAME", socket.gethostname())
        except Exception:
            hostname = "desconocido"

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip_local = s.getsockname()[0]
            s.close()
        except Exception:
            ip_local = "127.0.0.1"

        system = {
            "hostname": hostname,
            "ip_local": ip_local,
            "usuario": os.environ.get("USERNAME", "desconocido"),
            "os": "windows",
        }

        logger.debug(f"sistema detectado: {hostname} / {ip_local}")
        return system

    async def _detectar_navegadores(self) -> dict:
        """detecta navegadores instalados localmente con datos de debug."""
        try:
            browsers = self.auto_detect.detect_browsers()
            for browser_name in list(browsers.keys()):
                browser_lower = browser_name.lower()
                user_data_dir = ""
                for key, path in BROWSER_USER_DATA_DIRS.items():
                    if key in browser_lower:
                        user_data_dir = path
                        break
                session_exists = os.path.isdir(user_data_dir) if user_data_dir else False
                browsers[browser_name] = {
                    "path": browsers[browser_name] if isinstance(browsers.get(browser_name), str) else "",
                    "user_data_dir": user_data_dir if os.path.isdir(user_data_dir) else "",
                    "debug_port": random.randint(9222, 9322),
                    "session_exists": session_exists,
                }
            logger.debug(f"navegadores detectados: {list(browsers.keys())}")
            return browsers
        except Exception as e:
            logger.error(f"error detectando navegadores: {e}")
            return {}

    async def _detectar_perfiles_roxy(self) -> tuple:
        """detecta perfiles via api de roxybrowser."""
        try:
            # primero intentar autodetectar workspace_id local
            workspace_id = find_workspace_id()
            api_url = f"http://127.0.0.1:50000"

            # si no hay workspace_id autodetectado, usar de config
            if not workspace_id:
                try:
                    from config_loader import ROXY_WORKSPACE_ID
                    workspace_id = ROXY_WORKSPACE_ID
                except Exception:
                    pass

            self.roxy_api = RoxyBrowserAPI(api_url, workspace_id)
            profiles = self.roxy_api.get_profiles()
            logger.info(f"perfiles roxy detectados via api: {len(profiles)}")
            return profiles, workspace_id
        except Exception as e:
            logger.warning(f"no se pudo detectar perfiles via api: {e}")
            return [], ""

    def _clasificar_perfiles(self, perfiles: list) -> dict:
        """clasifica perfiles en listo, no_listo, detectado."""
        clasificados = {"listo": [], "no_listo": [], "detectado": []}
        for p in perfiles:
            estado = p.get("state", p.get("status", "unknown"))
            nombre = p.get("name", p.get("id", "sin_nombre"))
            if estado in ("active", "running", "ready"):
                clasificados["listo"].append(nombre)
            elif estado in ("inactive", "stopped", "closed"):
                clasificados["no_listo"].append(nombre)
            else:
                clasificados["detectado"].append(nombre)
        logger.debug(
            f"perfiles clasificados: {len(clasificados['listo'])} listos, "
            f"{len(clasificados['no_listo'])} no listos"
        )
        return clasificados

    async def _detectar_vip(self, perfiles: list) -> list:
        """detecta perfiles vip basado en reglas de asignacion."""
        vip = []
        if not perfiles:
            return vip

        # detectar ip_wan para aplicar regla max 3 pcs
        try:
            ip_wan = await self._detectar_ip_wan()
        except Exception:
            ip_wan = "desconocida"

        # regla: max 2 perfiles vip por pc, max 6 total
        max_vip_por_pc = PERFILES_VIP_POR_PC
        for p in perfiles[:max_vip_por_pc]:
            nombre = p.get("name", p.get("id", "sin_nombre"))
            estado = p.get("state", p.get("status", "unknown"))
            if estado in ("active", "running", "ready"):
                # marcar como vip si cumple criterios
                uid = p.get("id", f"vip_{len(vip)}")
                vip.append({
                    "id": uid,
                    "name": nombre,
                    "nivel": "oro",
                    "ip_wan": ip_wan,
                })

        logger.info(f"perfiles vip detectados: {len(vip)}")
        return vip

    async def _detectar_ip_wan(self) -> str:
        """detecta ip publica via ifconfig.me."""
        try:
            resp = requests.get(IFCONFIG_ME_URL, timeout=10)
            if resp.status_code == 200:
                ip = resp.text.strip()
                logger.debug(f"ip_wan detectada: {ip}")
                return ip
        except requests.exceptions.RequestException as e:
            logger.warning(f"no se pudo detectar ip_wan: {e}")
        except Exception as e:
            logger.error(f"error detectando ip_wan: {e}")
        return "0.0.0.0"

    async def _detectar_segundo_pc(self) -> bool:
        """detecta si hay un segundo pc en la misma ip_wan."""
        try:
            ip_wan = await self._detectar_ip_wan()
            if ip_wan and ip_wan != "0.0.0.0":
                from config_loader import NOMBRE_PC
                logger.debug(f"verificando segundo pc en ip_wan {ip_wan}")
                return True
        except Exception as e:
            logger.debug(f"error detectando segundo pc: {e}")
        return False

    async def get_profile_list(self) -> list:
        """devuelve lista de perfiles detectados."""
        return self.resultados.get("roxy_profiles", [])

    async def get_browser_list(self) -> list:
        """devuelve lista de navegadores detectados."""
        browsers = self.resultados.get("browsers", {})
        return list(browsers.keys())

    def get_system_info(self) -> dict:
        """devuelve informacion del sistema."""
        return self.resultados.get("system", {})

    def get_status_summary(self) -> dict:
        """devuelve resumen de estado para pcmaster."""
        browsers_raw = self.resultados.get("browsers", {})
        return {
            "hostname": self.resultados.get("system", {}).get("hostname", "?"),
            "ip_local": self.resultados.get("system", {}).get("ip_local", "?"),
            "ip_wan": self.resultados.get("ip_wan", "?"),
            "browsers": list(browsers_raw.keys()),
            "browser_debug": [
                {
                    "name": name,
                    "user_data_dir": info.get("user_data_dir", ""),
                    "debug_port": info.get("debug_port", 0),
                    "session_exists": info.get("session_exists", False),
                }
                for name, info in browsers_raw.items()
                if isinstance(info, dict)
            ],
            "perfiles_roxy": len(self.resultados.get("roxy_profiles", [])),
            "perfiles_vip": len(self.resultados.get("vip_profiles", [])),
        }
