# config_loader.py - roxymaster v8.3
# carga unificada de configuracion para pcbot

import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.absolute()
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
SECRETOS_DIR = os.path.join(BASE_DIR, "data", "secrets")
CLIENTE_SECRET_PATH = os.path.join(SECRETOS_DIR, "cliente.json")

def load_config() -> dict:
    """carga config.json o devuelve diccionario vacio."""
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}

def obtener_setting(clave: str, default: str = "") -> str:
    """obtiene un setting desde data/secrets/cliente.json o config.json."""
    if os.path.isfile(CLIENTE_SECRET_PATH):
        try:
            with open(CLIENTE_SECRET_PATH, "r", encoding="utf-8") as f:
                secretos = json.load(f)
            valor = secretos.get(clave)
            if valor is not None:
                return str(valor)
        except (json.JSONDecodeError, IOError):
            pass
    cfg = load_config()
    valor = cfg.get(clave)
    if valor is not None:
        return str(valor)
    return default

# cargar configuracion global
_cfg = load_config()

# variables globales - autodetectar hostname si pcbot_id esta vacio
_pcbot_id_cfg = _cfg.get("pcbot", {}).get("pcbot_id", "")
NOMBRE_PC = _pcbot_id_cfg if _pcbot_id_cfg else os.environ.get("COMPUTERNAME", "desconocido")
USUARIO_PC = _cfg.get("pcbot", {}).get("usuario", "")
IP_LOCAL = _cfg.get("pcbot", {}).get("ip_local", "127.0.0.1")
IP_TAILSCALE = _cfg.get("pcbot", {}).get("ip_tailscale", "100.85.100.109")

PCMASTER_HOST = _cfg.get("pcmaster", {}).get("ip_tailscale", "100.111.179.65")
PCMASTER_IP = PCMASTER_HOST
PCMASTER_IP_TAILSCALE = _cfg.get("pcmaster", {}).get("ip_tailscale", "100.111.179.65")
PCMASTER_WS_PORT = _cfg.get("pcmaster", {}).get("ws_port", 8086)
PCMASTER_HTTP_PORT = _cfg.get("pcmaster", {}).get("http_port", 8086)

ROXYBROWSER_API_URL = _cfg.get("roxybrowser", {}).get("api_url", "http://127.0.0.1:50000")
ROXY_WORKSPACE_ID = _cfg.get("roxybrowser", {}).get("workspace_id", "")

VERSION = _cfg.get("version", "8.3")

DATA_DIR = os.path.join(BASE_DIR, "data")
OBSOLETOS_DIR = os.path.join(BASE_DIR, "obsoletos")
PORTAL_PATH = os.path.join(BASE_DIR, "portal.html")
DASHBOARD_PATH = os.path.join(BASE_DIR, "dashboard.html")

HTTP_PORT = 8086
PORTAL_PORT = 8087

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OBSOLETOS_DIR, exist_ok=True)

def save_config(cfg: dict):
    """guarda config.json."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4, ensure_ascii=False)