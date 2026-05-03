"""
ROXYMASTER v8.0 - AUTO DETECT (PCBOT)
Detecta automaticamente apps de perfiles, navegadores y configuracion del sistema.
"""

import os
import logging
import subprocess
import requests

logger = logging.getLogger(__name__)

# Posibles rutas de navegadores
BROWSER_PATHS = {
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ],
    "edge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
    "firefox": [
        r"C:\Program Files\Mozilla Firefox\firefox.exe",
        r"C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
    ],
    "brave": [
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    ],
    "opera": [
        r"C:\Program Files\Opera\launcher.exe",
    ],
}

PROFILE_APPS = {
    "roxybrowser": {"port": 50000, "api_path": "/api/browsers"},
    "multilogin": {"port": 35000, "api_path": "/api/v2/profile"},
    "anty": {"port": 3000, "api_path": "/api/v1/profiles"},
    "adspower": {"port": 50325, "api_path": "/api/v1/user/list"},
    "gologin": {"port": 36910, "api_path": "/api/v2/profiles"},
}


class AutoDetect:
    def __init__(self):
        self.browsers = {}
        self.profile_apps = {}
        self.system_info = {}

    def detect_all(self) -> dict:
        self.detect_browsers()
        self.detect_profile_apps()
        self.detect_system_info()
        return {
            "browsers": self.browsers,
            "profile_apps": self.profile_apps,
            "system": self.system_info,
        }

    def detect_browsers(self) -> dict:
        result = {}
        for name, paths in BROWSER_PATHS.items():
            for p in paths:
                if os.path.isfile(p):
                    result[name] = p
                    break
        self.browsers = result
        logger.info(f"Navegadores detectados: {list(result.keys())}")
        return result

    def detect_profile_apps(self) -> dict:
        result = {}
        for app_name, cfg in PROFILE_APPS.items():
            url = f"http://127.0.0.1:{cfg['port']}{cfg['api_path']}"
            try:
                resp = requests.get(url, timeout=3)
                if resp.status_code in (200, 401, 403):
                    result[app_name] = {
                        "port": cfg["port"],
                        "api": url,
                        "profiles_count": self._count_profiles(app_name, resp)
                    }
                    logger.info(f"App de perfiles detectada: {app_name} en puerto {cfg['port']}")
            except requests.ConnectionError:
                pass
            except requests.Timeout:
                pass
        self.profile_apps = result
        return result

    def _count_profiles(self, app_name, response):
        try:
            data = response.json()
            if app_name == "roxybrowser":
                return len(data) if isinstance(data, list) else 0
            if app_name == "multilogin":
                return len(data.get("data", [])) if isinstance(data, dict) else 0
            if app_name == "adspower":
                return data.get("count", 0) if isinstance(data, dict) else 0
        except Exception:
            pass
        return 0

    def detect_system_info(self) -> dict:
        info = {
            "os": os.name,
            "home": os.path.expanduser("~"),
            "desktop": os.path.join(os.path.expanduser("~"), "Desktop"),
        }
        try:
            out = subprocess.run(
                ["wmic", "ComputerSystem", "get", "TotalPhysicalMemory", "/VALUE"],
                capture_output=True, text=True, timeout=5
            )
            if out.returncode == 0 and out.stdout.strip():
                for line in out.stdout.splitlines():
                    if "TotalPhysicalMemory" in line:
                        val = line.split("=")[1].strip()
                        ram_mb = int(val) // (1024 * 1024)
                        info["ram_mb"] = ram_mb
                        break
        except Exception:
            info["ram_mb"] = 0

        self.system_info = info
        return info

    def get_roxy_profiles(self) -> list:
        try:
            resp = requests.get("http://127.0.0.1:50000/api/browsers", timeout=5)
            if resp.status_code == 200:
                return resp.json() if isinstance(resp.json(), list) else []
        except Exception:
            pass
        return []