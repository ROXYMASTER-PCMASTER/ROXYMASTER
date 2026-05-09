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

# variables globales - todo desde variables de entorno del so
NOMBRE_PC = os.getenv("COMPUTERNAME", "desconocido")
USUARIO_PC = os.getenv("USERNAME", "")

# ip local y tailscale se detectan dinamicamente
IP_LOCAL = "127.0.0.1"
IP_TAILSCALE = ""

# roxybrowser - solo url base, workspace se autodetecta
ROXYBROWSER_API_URL = "http://127.0.0.1:50000"

VERSION = "8.3"

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