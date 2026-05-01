"""
ROXYMASTER v8.0 - CONFIG LOADER (PCMASTER)
Carga config.json y expone variables del servidor.
"""

import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_config():
    config_path = os.path.join(BASE_DIR, "config.json")
    with open(config_path, "r", encoding="utf-8-sig") as f:
        return json.load(f)

_cfg = load_config()

# Server
IP_SERVIDOR = _cfg["server"]["ip_servidor"]
IP_TAILSCALE = _cfg["server"]["ip_tailscale"]
WS_PORT = _cfg["server"]["ws_port"]
HTTP_PORT = _cfg["server"]["puerto_http"]

# Directorios
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
DATA_DIR = os.path.join(BASE_DIR, "data")
OBSOLETOS_DIR = os.path.join(BASE_DIR, "obsoletos")

# Portales
ADMIN_PORTAL_PATH = os.path.join(BASE_DIR, "admin.html")
PORTAL_PATH = os.path.join(BASE_DIR, "portal.html")
DASHBOARD_PATH = os.path.join(BASE_DIR, "dashboard.html")

# Version
VERSION = _cfg.get("version", "8.0")

# Modelo Ollama
MODELO_OLLAMA = _cfg.get("ollama", {}).get("modelo", "llama3.2")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OBSOLETOS_DIR, exist_ok=True)