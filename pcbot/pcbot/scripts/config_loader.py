"""
ROXYMASTER v8.0 - CONFIG LOADER (PCBOT)
Carga o autogenera config.json para el cliente.
"""

import os
import json
import socket
import platform

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
        "api_url": "http://127.0.0.1:50000"
    },
    "version": "8.0",
    "seguridad": {
        "protocolo": "shs-hmac",
        "version": "1.0"
    }
}


def _detect_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _detect_tailscale_ip():
    interfaces = ["Tailscale", "tailscale0", "tun0"]
    for iface in interfaces:
        try:
            import netifaces
            addrs = netifaces.ifaddresses(iface)
            if netifaces.AF_INET in addrs:
                for addr in addrs[netifaces.AF_INET]:
                    ip = addr.get("addr", "")
                    if ip.startswith("100."):
                        return ip
        except Exception:
            pass
    try:
        import subprocess
        result = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return "0.0.0.0"


def load_config():
    if os.path.isfile(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)
    else:
        cfg = DEFAULT_CONFIG.copy()
        cfg["pcbot"]["ip_local"] = _detect_local_ip()
        cfg["pcbot"]["ip_tailscale"] = _detect_tailscale_ip()
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)

    if cfg["pcbot"].get("ip_local", "0.0.0.0") == "0.0.0.0":
        cfg["pcbot"]["ip_local"] = _detect_local_ip()

    return cfg


_cfg = load_config()

# Variables globales
NOMBRE_PC = _cfg["pcbot"]["nombre_pc"]
USUARIO_PC = _cfg["pcbot"]["usuario"]
IP_LOCAL = _cfg["pcbot"]["ip_local"]
IP_TAILSCALE = _cfg["pcbot"]["ip_tailscale"]
# tailscale ip para todas las conexiones a pcmaster (http + ws)
PCMASTER_HOST = _cfg["pcmaster"].get("ip_tailscale", "100.111.179.65")
PCMASTER_IP = PCMASTER_HOST
PCMASTER_IP_TAILSCALE = _cfg["pcmaster"].get("ip_tailscale", "100.111.179.65")
PCMASTER_WS_PORT = _cfg["pcmaster"]["ws_port"]
PCMASTER_HTTP_PORT = _cfg["pcmaster"]["http_port"]
ROXYBROWSER_API_URL = _cfg.get("roxybrowser", {}).get("api_url", "http://127.0.0.1:50000")
VERSION = _cfg.get("version", "8.0")

# Directorios
DATA_DIR = os.path.join(BASE_DIR, "data")
OBSOLETOS_DIR = os.path.join(BASE_DIR, "obsoletos")
PORTAL_PATH = os.path.join(BASE_DIR, "portal.html")
DASHBOARD_PATH = os.path.join(BASE_DIR, "dashboard.html")

# Puertos locales
HTTP_PORT = 8086
PORTAL_PORT = 8087

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OBSOLETOS_DIR, exist_ok=True)


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)