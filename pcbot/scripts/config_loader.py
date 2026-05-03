"""
roxymaster v8.3 - config loader (pcbot)
carga o autogenera config.json para el cliente pcbot.
incluye autodeteccion de ips, workspace_id de roxybrowser, etc.
todo en minusculas, utf-8 sin bom.
"""

import json
import logging
import os
import platform
import socket
import subprocess

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

DEFAULT_CONFIG = {
    "pcbot": {
        "nombre_pc": platform.node(),
        "usuario": os.environ.get("USERNAME", "unknown"),
        "ip_local": "0.0.0.0",
        "ip_tailscale": "0.0.0.0"
    },
    "pcmaster": {
        "ip": "192.168.1.17",
        "ip_tailscale": "100.111.179.65",
        "ws_port": 5006,
        "http_port": 8086
    },
    "roxybrowser": {
        "api_url": "http://127.0.0.1:50000",
        "workspace_id": ""
    },
    "version": "8.3",
    "seguridad": {
        "protocolo": "shs-hmac",
        "version": "1.0"
    }
}


def _detect_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _detect_tailscale_ip() -> str:
    try:
        result = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return "0.0.0.0"


def _find_workspace_id_local() -> str:
    """escanea directorio de roxybrowser para encontrar workspace_id."""
    appdata_roxy = os.path.join(
        os.environ.get("APPDATA", ""), "RoxyBrowser", "browser-cache"
    )
    if not os.path.isdir(appdata_roxy):
        logger.warning(f"roxybrowser browser-cache no encontrado: {appdata_roxy}")
        return ""
    try:
        items = os.listdir(appdata_roxy)
        for item in items:
            item_path = os.path.join(appdata_roxy, item)
            if os.path.isdir(item_path) and len(item) >= 20:
                logger.info(f"workspace_id detectado localmente: {item}")
                return item
    except Exception as e:
        logger.error(f"error escaneando workspace id: {e}")
    return ""


def load_config() -> dict:
    """carga config.json o crea uno por defecto con autodeteccion."""
    if os.path.isfile(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)
    else:
        cfg = DEFAULT_CONFIG.copy()
        cfg["pcbot"]["ip_local"] = _detect_local_ip()
        cfg["pcbot"]["ip_tailscale"] = _detect_tailscale_ip()
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)

    # autocompletar ip_local si esta en 0.0.0.0
    if cfg["pcbot"].get("ip_local", "0.0.0.0") == "0.0.0.0":
        cfg["pcbot"]["ip_local"] = _detect_local_ip()

    # autodetect workspace_id si esta vacio
    roxy_cfg = cfg.get("roxybrowser", {})
    if not roxy_cfg.get("workspace_id", ""):
        ws_id = _find_workspace_id_local()
        if ws_id:
            cfg.setdefault("roxybrowser", {})["workspace_id"] = ws_id
            try:
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=4, ensure_ascii=False)
            except Exception:
                pass

    return cfg


_cfg = load_config()

# variables globales
NOMBRE_PC = _cfg["pcbot"]["nombre_pc"]
USUARIO_PC = _cfg["pcbot"]["usuario"]
IP_LOCAL = _cfg["pcbot"]["ip_local"]
IP_TAILSCALE = _cfg["pcbot"]["ip_tailscale"]

# pcmaster - siempre via tailscale 100.111.179.65 (leido de config)
PCMASTER_HOST = _cfg["pcmaster"].get("ip_tailscale", "100.111.179.65")
PCMASTER_IP = PCMASTER_HOST
PCMASTER_IP_TAILSCALE = _cfg["pcmaster"].get("ip_tailscale", "100.111.179.65")
PCMASTER_WS_PORT = _cfg["pcmaster"]["ws_port"]
PCMASTER_HTTP_PORT = _cfg["pcmaster"]["http_port"]

# roxybrowser
ROXYBROWSER_API_URL = _cfg.get("roxybrowser", {}).get("api_url", "http://127.0.0.1:50000")
ROXY_WORKSPACE_ID = _cfg.get("roxybrowser", {}).get("workspace_id", "")

VERSION = _cfg.get("version", "8.3")

# directorios
DATA_DIR = os.path.join(BASE_DIR, "data")
OBSOLETOS_DIR = os.path.join(BASE_DIR, "obsoletos")
PORTAL_PATH = os.path.join(BASE_DIR, "portal.html")
DASHBOARD_PATH = os.path.join(BASE_DIR, "dashboard.html")

# puertos locales
HTTP_PORT = 8086
PORTAL_PORT = 8087

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OBSOLETOS_DIR, exist_ok=True)


def save_config(cfg: dict):
    """guarda config.json."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)