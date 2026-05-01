# ============================================================================
# ROXYMASTER v7.0 - CONFIG MODULE
# Carga config.json y expone variables globales del servidor
# ============================================================================

import os
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(BASE_DIR, "config.json"), "r", encoding="utf-8-sig") as f:
    _cfg = json.load(f)

# Server
IP_SERVIDOR = _cfg["server"]["ip_servidor"]
IP_TAILSCALE = _cfg["server"]["ip_tailscale"]
WS_PORT = _cfg["server"]["ws_port"]
HTTP_PORT = _cfg["server"]["puerto_http"]

# Directorios
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
DATA_DIR = os.path.join(BASE_DIR, "data")
PORTAL_PATH = os.path.join(BASE_DIR, "portal.html")
ADMIN_PORTAL_PATH = os.path.join(BASE_DIR, "admin_portal.html")
DASHBOARD_PATH = os.path.join(BASE_DIR, "dashboard.html")

# Version
VERSION = _cfg.get("version", "7.0")