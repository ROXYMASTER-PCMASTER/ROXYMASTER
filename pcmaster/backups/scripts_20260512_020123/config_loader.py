# config_loader.py - carga unificada de configuracion y secretos para roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom

import os
import json
from pathlib import Path

# ---------------------------------------------------------------------------
# rutas base (relativas al directorio pcmaster)
# ---------------------------------------------------------------------------
_base_dir = Path(__file__).parent.parent.absolute()
_data_dir = _base_dir / "data"
_scripts_dir = _base_dir / "scripts"
_config_path = _base_dir / "config.json"
_secrets_path = Path(os.environ.get("USERPROFILE", "")) / "desktop" / "roxymaster_secrets" / "config_sensible.json"

# asegurar directorio data
_data_dir.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# carga de config.json (si existe)
# ---------------------------------------------------------------------------
_cfg = {}
if _config_path.exists():
    try:
        with open(_config_path, "r", encoding="utf-8-sig") as _f:
            _cfg = json.load(_f)
    except (json.JSONDecodeError, IOError):
        pass

# ---------------------------------------------------------------------------
# valores desde config.json con valores predeterminados robustos
# ---------------------------------------------------------------------------
server_cfg = _cfg.get("server", {})

ws_host = str(server_cfg.get("ip_servidor", "0.0.0.0"))
ws_port = int(server_cfg.get("ws_port", 5006))
ip_tailscale = str(server_cfg.get("ip_tailscale", "100.111.179.65"))
http_host = str(server_cfg.get("ip_servidor", "0.0.0.0"))
http_port = int(server_cfg.get("puerto_http", 8086))

version = str(_cfg.get("version", "8.3"))

ollama_cfg = _cfg.get("ollama", {})
jarvis_modelo = str(ollama_cfg.get("modelo", "llama3.2"))
jarvis_api_url = str(ollama_cfg.get("api_url", "http://localhost:11434"))

# ---------------------------------------------------------------------------
# carga de secretos sensibles (api token externo)
# ---------------------------------------------------------------------------
roxy_api_token = ""
roxy_workspace_id = ""
if _secrets_path.exists():
    try:
        with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
            _secrets = json.load(_f)
        roxy_api_token = _secrets.get("roxy_api_token", "")
        roxy_workspace_id = _secrets.get("roxy_workspace_id", "")
    except (json.JSONDecodeError, IOError):
        pass

# ---------------------------------------------------------------------------
# seguridad - clave secreta compartida entre pcmaster y pcbot
# ---------------------------------------------------------------------------
secreto_sistema = "r0xym4st3r_s3cr3t0_k3y_v83"
token_admin = "admin_root_token_v83_roxymaster"
token_sesion_secreto = "s3s10n_t0k3n_v83_r0xym4st3r"

# ---------------------------------------------------------------------------
# rutas exportadas como strings (sin mayusculas)
# ---------------------------------------------------------------------------
ruta_base = str(_base_dir)
ruta_data = str(_data_dir)
ruta_db = str(_data_dir / "roxymaster.db")
ruta_scripts = str(_scripts_dir)
ruta_portal = str(_base_dir / "portal.html")
ruta_prompts = str(_base_dir / "prompts")

# ---------------------------------------------------------------------------
# settings globales como diccionario inmutable (acceso centralizado)
# ---------------------------------------------------------------------------
settings = {
    "ws_host": ws_host,
    "ws_port": ws_port,
    "http_host": http_host,
    "http_port": http_port,
    "ip_tailscale": ip_tailscale,
    "version": version,
    "jarvis_modelo": jarvis_modelo,
    "jarvis_api_url": jarvis_api_url,
    "secreto_sistema": secreto_sistema,
    "ruta_base": ruta_base,
    "ruta_data": ruta_data,
    "ruta_db": ruta_db,
    "ruta_portal": ruta_portal,
    "ruta_prompts": ruta_prompts,
}


def cargar_configuracion():
    """carga la configuracion completa como diccionario para uso en server.py."""
    global _cfg, settings
    resultado = {
        "archivo_config": str(_config_path) if _config_path.exists() else "config.json",
        "db_path": str(ruta_db),
        "admin_email": "admin@roxymaster.local",
        "admin_password": "admin123",
        "host": http_host,
        "puerto": http_port,
        "ws_host": ws_host,
        "ws_port": ws_port,
        "ip_tailscale": ip_tailscale,
        "version": version,
        "secreto_sistema": secreto_sistema,
        "ruta_base": ruta_base,
        "ruta_data": ruta_data,
        "ruta_portal": ruta_portal,
        "ruta_prompts": ruta_prompts,
    }
    if _config_path.exists():
        try:
            with open(_config_path, "r", encoding="utf-8-sig") as _f:
                _cfg = json.load(_f)
            sc = _cfg.get("server", {})
            resultado["host"] = sc.get("host", "0.0.0.0")
            resultado["puerto"] = int(sc.get("puerto", 8086))
            resultado["ws_host"] = sc.get("ip_servidor", "0.0.0.0")
            resultado["ws_port"] = int(sc.get("puerto_ws", 5006))
            admin_cfg = _cfg.get("admin", {})
            resultado["admin_email"] = admin_cfg.get("email", "admin@roxymaster.local")
            resultado["admin_password"] = admin_cfg.get("password", "admin123")
        except (json.JSONDecodeError, IOError):
            pass
    return resultado


def obtener_setting(clave: str, valor_predeterminado=None):
    """obtiene un setting global de forma segura, con valor predeterminado opcional."""
    return settings.get(clave, valor_predeterminado)


def recargar_config():
    """recarga config.json en caliente y actualiza settings (para dashboard admin)."""
    global _cfg, ws_host, ws_port, http_host, http_port, settings
    if _config_path.exists():
        try:
            with open(_config_path, "r", encoding="utf-8-sig") as _f:
                _cfg = json.load(_f)
        except (json.JSONDecodeError, IOError):
            return False
    sc = _cfg.get("server", {})
    ws_host = str(sc.get("ip_servidor", ws_host))
    ws_port = int(sc.get("ws_port", ws_port))
    http_host = str(sc.get("ip_servidor", http_host))
    http_port = int(sc.get("puerto_http", http_port))
    settings["ws_host"] = ws_host
    settings["ws_port"] = ws_port
    settings["http_host"] = http_host
    settings["http_port"] = http_port
    return True