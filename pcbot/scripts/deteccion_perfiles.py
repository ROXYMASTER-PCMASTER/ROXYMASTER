"""
roxymaster v8.3 - deteccion de perfiles (pcbot)
clase que encapsula toda la deteccion del entorno:
roxybrowser (via escaneo local de directorios), clasificacion,
navegadores locales, perfiles vip, ip wan.
"""

import asyncio
import json
import logging
import os
import socket
import subprocess
import time
import requests

from auto_detect import AutoDetect, BROWSER_PATHS
from roxybrowser_api import find_workspace_id, RoxyBrowserAPI

logger = logging.getLogger(__name__)

IFCONFIG_ME_URL = "https://ifconfig.me/ip"
MAX_PCS_POR_IPWAN = 3
PERFILES_VIP_POR_PC = 2
TOTAL_VIP_MAX = 6

# rutas de roxybrowser
APPDATA_ROXY = os.path.join(
    os.environ.get("APPDATA", ""), "RoxyBrowser"
)
BROWSER_CACHE_DIR = os.path.join(APPDATA_ROXY, "browser-cache")
ROXY_DATA_DIR = os.path.join(
    os.environ.get("USERPROFILE", ""), ".roxybrowser"
)

# solo los puertos mas comunes de debug
COMMON_DEBUG_PORTS = [9222, 9229, 9999]


async def scan_local_profiles_async(max_profiles=10, timeout_total=8) -> list:
    """escanea directorios locales de roxybrowser (async, con limite).
    usa executor para evitar bloqueo de os.listdir."""
    profiles = []
    t0 = time.time()

    def _scan_sync():
        """escaneo sincrono dentro de executor."""
        res = []
        if not os.path.isdir(BROWSER_CACHE_DIR):
            return res
        try:
            workspaces = os.listdir(BROWSER_CACHE_DIR)
            for ws in workspaces:
                if time.time() - t0 > timeout_total:
                    break
                ws_path = os.path.join(BROWSER_CACHE_DIR, ws)
                if not os.path.isdir(ws_path):
                    continue
                for i, item in enumerate(os.listdir(ws_path)):
                    if time.time() - t0 > timeout_total or len(res) >= max_profiles:
                        break
                    item_path = os.path.join(ws_path, item)
                    if not os.path.isdir(item_path):
                        continue
                    pref_path = os.path.join(item_path, "Preferences")
                    profile_name = item
                    port = 0
                    estado = "inactive"
                    if os.path.isfile(pref_path):
                        try:
                            with open(pref_path, "r", encoding="utf-8", errors="ignore") as f:
                                pref = json.load(f)
                            profile_name = pref.get("profile", {}).get("name", item)
                        except Exception:
                            pass
                    res.append({
                        "hash_interno": ws,
                        "nombre": profile_name,
                        "estado": estado,
                        "port": port,
                        "ws_endpoint": "",
                        "tipo": "roxy",
                        "url_actual": "",
                        "directorio": item_path,
                    })
                if len(res) >= max_profiles:
                    break
        except Exception as e:
            logger.error(f"error en escaneo sincrono: {e}")
        return res

    try:
        loop = asyncio.get_event_loop()
        raw_profiles = await asyncio.wait_for(
            loop.run_in_executor(None, _scan_sync),
            timeout=timeout_total
        )
        # luego detectar puertos activos (async, solo 3 puertos)
        for p in raw_profiles:
            for dp in COMMON_DEBUG_PORTS:
                try:
                    _, writer = await asyncio.wait_for(
                        asyncio.open_connection("127.0.0.1", dp),
                        timeout=0.5
                    )
                    writer.close()
                    await writer.wait_closed()
                    p["port"] = dp
                    p["estado"] = "active"
                    p["ws_endpoint"] = f"ws://127.0.0.1:{dp}"
                    break
                except Exception:
                    continue
        profiles = raw_profiles
    except asyncio.TimeoutError:
        logger.warning(f"scan_local_profiles cancelado por timeout ({timeout_total}s)")
    except Exception as e:
        logger.error(f"error en scan_local_profiles_async: {e}")

    logger.info(f"{len(profiles)} perfiles roxy detectados localmente en {time.time()-t0:.1f}s")
    return profiles


class DeteccionPerfiles:
    """detecta y clasifica todos los perfiles disponibles en el pc."""

    def __init__(self):
        self.auto_detect = AutoDetect()
        self.roxy_profiles = []
        self.roxy_api_key = ""
        self.roxy_workspace_id = ""
        self.browsers = {}
        self.profile_apps = {}
        self.system_info = {}
        self.ip_wan = "0.0.0.0"
        self.ip_local = "0.0.0.0"
        self.ip_tailscale = "0.0.0.0"
        self.perfiles_roxy_clasificados = {
            "listo": [], "no_configurado": [], "colgado": []
        }
        self.perfiles_vip = []
        self._roxy_api = None

    async def detectar_todo(self) -> dict:
        """ejecuta todas las detecciones en orden."""
        logger.info("iniciando deteccion completa del entorno...")

        # auto_detect base
        detected = self.auto_detect.detect_all()
        self.browsers = detected.get("browsers", {})
        self.profile_apps = detected.get("profile_apps", {})
        self.system_info = detected.get("system", {})

        # roxybrowser - deteccion via api + local
        await self._detectar_roxybrowser()

        # clasificar perfiles roxy
        self._clasificar_perfiles_roxy()

        # ip wan
        self._detectar_ip_wan()

        # ips locales
        self._detectar_ips_locales()

        # perfiles vip
        self._crear_perfiles_vip()

        return {
            "roxy_profiles": self.roxy_profiles,
            "roxy_clasificados": self.perfiles_roxy_clasificados,
            "vip_profiles": self.perfiles_vip,
            "browsers": self.browsers,
            "profile_apps": self.profile_apps,
            "system": self.system_info,
            "ip_wan": self.ip_wan,
            "ip_local": self.ip_local,
            "ip_tailscale": self.ip_tailscale,
        }

    # ------------------------------------------------------------------
    # roxybrowser
    # ------------------------------------------------------------------
    async def _detectar_roxybrowser(self):
        """detecta perfiles de roxybrowser: primero intenta via api,
        si falla porque workspace_id no existe, usa escaneo local."""
        # obtener workspace_id
        self.roxy_workspace_id = find_workspace_id()

        if self.roxy_workspace_id:
            # intentar via api
            self._roxy_api = RoxyBrowserAPI(
                api_url="http://127.0.0.1:50000",
                workspace_id=self.roxy_workspace_id
            )
            api_browsers = self._roxy_api.get_profiles()
            if api_browsers:
                logger.info(f"roxybrowser api respondio con {len(api_browsers)} browsers")
                for p in api_browsers:
                    profile_hash = str(p.get("id", p.get("hash", p.get("uuid", ""))))
                    self.roxy_profiles.append({
                        "hash_interno": profile_hash,
                        "nombre": p.get("name", p.get("nombre", "sin_nombre")),
                        "estado": p.get("status", p.get("estado", "inactive")),
                        "port": p.get("port", 0),
                        "ws_endpoint": p.get("wsEndpoint", ""),
                        "tipo": "roxy",
                        "url_actual": p.get("url", ""),
                    })
                return

        # fallback: escaneo local async
        logger.info("usando escaneo local para detectar perfiles roxybrowser")
        local_profiles = await scan_local_profiles_async()
        self.roxy_profiles = local_profiles

        if not self.roxy_workspace_id and local_profiles:
            self.roxy_workspace_id = local_profiles[0].get("hash_interno", "")
            logger.info(f"workspace_id inferido de perfiles locales: {self.roxy_workspace_id}")

    # ------------------------------------------------------------------
    # clasificacion
    # ------------------------------------------------------------------
    def _clasificar_perfiles_roxy(self):
        """clasifica perfiles en listo, no_configurado, colgado."""
        listos = []
        no_config = []
        colgados = []
        for p in self.roxy_profiles:
            estado = p.get("estado", "").lower()
            if estado in ("active", "running", "ok", ""):
                listos.append(p)
            elif estado in ("inactive", "stopped", "closed"):
                no_config.append(p)
            else:
                colgados.append(p)
        self.perfiles_roxy_clasificados = {
            "listo": listos,
            "no_configurado": no_config,
            "colgado": colgados,
        }
        logger.info(
            f"clasificacion: {len(listos)} listos, "
            f"{len(no_config)} no_configurados, {len(colgados)} colgados"
        )

    # ------------------------------------------------------------------
    # ip wan
    # ------------------------------------------------------------------
    def _detectar_ip_wan(self):
        """obtiene ip publica via ifconfig.me."""
        try:
            resp = requests.get(IFCONFIG_ME_URL, timeout=5)
            if resp.status_code == 200:
                self.ip_wan = resp.text.strip()
                logger.info(f"ip wan detectada: {self.ip_wan}")
        except Exception as e:
            logger.warning(f"no se pudo detectar ip wan: {e}")
            self.ip_wan = "0.0.0.0"

    # ------------------------------------------------------------------
    # ips locales
    # ------------------------------------------------------------------
    def _detectar_ips_locales(self):
        """detecta ip local y tailscale."""
        try:
            self.ip_local = socket.gethostbyname(socket.gethostname())
            if self.ip_local.startswith("127."):
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                self.ip_local = s.getsockname()[0]
                s.close()
        except Exception:
            self.ip_local = "127.0.0.1"

        try:
            result = subprocess.run(
                ["tailscale", "ip", "-4"],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0:
                self.ip_tailscale = result.stdout.strip()
        except Exception:
            self.ip_tailscale = "0.0.0.0"

    # ------------------------------------------------------------------
    # perfiles vip
    # ------------------------------------------------------------------
    def _crear_perfiles_vip(self):
        """crea hasta 2 perfiles vip por pc usando navegadores locales."""
        sesiones_abiertas = self._detectar_sesiones_navegadores()
        vip_count = 0
        vip_list = []

        navegadores_prioridad = ["chrome", "firefox"]
        if not sesiones_abiertas:
            navegadores_prioridad = [b for b in navegadores_prioridad if b in self.browsers]
            navegadores_prioridad = navegadores_prioridad[:PERFILES_VIP_POR_PC]

        for nav in navegadores_prioridad:
            if vip_count >= PERFILES_VIP_POR_PC:
                break
            if nav in self.browsers or nav in sesiones_abiertas:
                vip_list.append({
                    "nombre": f"{nav}_vip",
                    "tipo": "vip",
                    "navegador": nav,
                    "ruta": self.browsers.get(nav, ""),
                    "estado": "activo" if nav in sesiones_abiertas else "inactivo",
                    "hash_interno": f"vip_{nav}_{socket.gethostname()}_{int(time.time())}",
                    "url_actual": "",
                })
                vip_count += 1

        if vip_count == 0:
            alternativos = [b for b in ["edge", "brave", "opera"] if b in self.browsers]
            for nav in alternativos[:PERFILES_VIP_POR_PC]:
                vip_list.append({
                    "nombre": f"{nav}_vip",
                    "tipo": "vip",
                    "navegador": nav,
                    "ruta": self.browsers.get(nav, ""),
                    "estado": "inactivo",
                    "hash_interno": f"vip_{nav}_{socket.gethostname()}_{int(time.time())}",
                    "url_actual": "",
                })
                vip_count += 1
                if vip_count >= PERFILES_VIP_POR_PC:
                    break

        self.perfiles_vip = vip_list
        logger.info(f"{len(vip_list)} perfiles vip creados (max {PERFILES_VIP_POR_PC} por pc)")

    def _detectar_sesiones_navegadores(self) -> list:
        """detecta que navegadores tienen ventanas/sesiones abiertas."""
        abiertos = []
        try:
            output = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=3
            )
            if output.returncode == 0:
                for line in output.stdout.splitlines():
                    parts = line.strip().strip('"').split('","')
                    if len(parts) > 0:
                        name = parts[0].lower()
                        if "chrome" in name:
                            abiertos.append("chrome")
                        elif "firefox" in name:
                            abiertos.append("firefox")
                        elif "msedge" in name:
                            abiertos.append("edge")
                        elif "brave" in name:
                            abiertos.append("brave")
        except Exception as e:
            logger.debug(f"error detectando sesiones: {e}")
        return list(set(abiertos))

    # ------------------------------------------------------------------
    # export
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        """exporta toda la informacion como dict."""
        return {
            "roxybrowser": {
                "api_key": self.roxy_api_key,
                "workspace_id": self.roxy_workspace_id,
                "perfiles": self.roxy_profiles,
                "clasificacion": self.perfiles_roxy_clasificados,
            },
            "vip": self.perfiles_vip,
            "browsers": list(self.browsers.keys()),
            "navegadores_detectados": self.browsers,
            "sistema": self.system_info,
            "red": {
                "ip_local": self.ip_local,
                "ip_tailscale": self.ip_tailscale,
                "ip_wan": self.ip_wan,
            },
        }