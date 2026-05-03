"""
roxymaster v8.3 - deteccion de perfiles (pcbot)
clase que encapsula toda la deteccion del entorno:
roxybrowser, clasificacion, navegadores locales, perfiles vip, ip wan.
"""

import json
import logging
import os
import socket
import subprocess
import time
import requests

from auto_detect import AutoDetect, BROWSER_PATHS

logger = logging.getLogger(__name__)

IFCONFIG_ME_URL = "https://ifconfig.me/ip"
MAX_PCS_POR_IPWAN = 3
PERFILES_VIP_POR_PC = 2
TOTAL_VIP_MAX = 6


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
        self.perfiles_roxy_clasificados = {"listo": [], "no_configurado": [], "colgado": []}
        self.perfiles_vip = []

    def detectar_todo(self) -> dict:
        """ejecuta todas las detecciones en orden."""
        logger.info("iniciando deteccion completa del entorno...")

        # auto_detect base
        detected = self.auto_detect.detect_all()
        self.browsers = detected.get("browsers", {})
        self.profile_apps = detected.get("profile_apps", {})
        self.system_info = detected.get("system", {})

        # roxybrowser
        self._detectar_roxybrowser()

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
    def _detectar_roxybrowser(self):
        """consulta la api de roxybrowser y obtiene perfiles con su hash interno."""
        base_url = "http://127.0.0.1:50000"
        try:
            # obtener info del workspace
            resp_info = requests.get(f"{base_url}/api/info", timeout=5)
            if resp_info.status_code == 200:
                info = resp_info.json()
                self.roxy_api_key = info.get("api_key", "")
                self.roxy_workspace_id = info.get("workspace_id", "")
                logger.info(f"roxybrowser workspace detectado: {self.roxy_workspace_id}")

            # obtener perfiles - cada uno tiene su hash interno de roxybrowser
            resp = requests.get(f"{base_url}/api/browsers", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                profiles = data if isinstance(data, list) else []
                self.roxy_profiles = []
                for p in profiles:
                    profile_hash = p.get("id", p.get("hash", p.get("uuid", "")))
                    self.roxy_profiles.append({
                        "hash_interno": str(profile_hash),
                        "nombre": p.get("name", p.get("nombre", "sin_nombre")),
                        "estado": p.get("status", p.get("estado", "inactive")),
                        "port": p.get("port", 0),
                        "ws_endpoint": p.get("wsEndpoint", ""),
                        "tipo": "roxy",
                        "url_actual": p.get("url", ""),
                    })
                logger.info(f"{len(self.roxy_profiles)} perfiles detectados en roxybrowser")
            else:
                logger.warning(f"roxybrowser api retorno status {resp.status_code}")
        except requests.ConnectionError:
            logger.warning("roxybrowser no detectado en 127.0.0.1:50000")
        except Exception as e:
            logger.error(f"error detectando roxybrowser: {e}")

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
            resp = requests.get(IFCONFIG_ME_URL, timeout=10)
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
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            self.ip_local = s.getsockname()[0]
            s.close()
        except Exception:
            self.ip_local = "127.0.0.1"

        # tailscale intent
        try:
            result = subprocess.run(
                ["tailscale", "ip", "-4"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                self.ip_tailscale = result.stdout.strip()
        except Exception:
            self.ip_tailscale = "0.0.0.0"

    # ------------------------------------------------------------------
    # perfiles vip
    # ------------------------------------------------------------------
    def _crear_perfiles_vip(self):
        """crea hasta 2 perfiles vip por pc usando navegadores locales.
        maximo 3 pcs por ip_wan, total 6 perfiles vip.
        """
        # detectar sesiones abiertas de navegadores
        sesiones_abiertas = self._detectar_sesiones_navegadores()

        vip_count = 0
        vip_list = []

        # priorizar chrome y firefox si estan instalados y abiertos
        navegadores_prioridad = ["chrome", "firefox"]
        if not sesiones_abiertas:
            # si no hay sesiones abiertas, usar los instalados
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

        # si no hay chrome/firefox, usar edge o brave
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
                capture_output=True, text=True, timeout=5
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