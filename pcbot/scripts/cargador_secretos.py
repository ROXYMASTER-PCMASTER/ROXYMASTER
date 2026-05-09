"""
roxymaster v8.3 - cargador de secretos (pcbot)
lee y gestiona secretos de conexion desde data/secrets/cliente.json.
prioriza variables de entorno pcmaster_ip y pcmaster_ws_port.
todo en minusculas, utf-8 sin bom.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRETS_PATH = os.path.join(BASE_DIR, "data", "secrets", "cliente.json")

_SECRETOS_CACHE = None


def _cargar_secretos() -> dict:
    """carga el archivo de secretos, con cache en memoria."""
    global _SECRETOS_CACHE
    if _SECRETOS_CACHE is not None:
        return _SECRETOS_CACHE

    if not os.path.isfile(SECRETS_PATH):
        logger.warning(f"archivo de secretos no encontrado: {SECRETS_PATH}")
        _SECRETOS_CACHE = {}
        return _SECRETOS_CACHE

    try:
        with open(SECRETS_PATH, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        _SECRETOS_CACHE = data
        logger.debug(f"secretos cargados desde {SECRETS_PATH}")
        return data
    except Exception as e:
        logger.error(f"error cargando secretos: {e}")
        _SECRETOS_CACHE = {}
        return {}


def _guardar_secretos(data: dict) -> bool:
    """guarda el archivo de secretos."""
    global _SECRETOS_CACHE
    try:
        os.makedirs(os.path.dirname(SECRETS_PATH), exist_ok=True)
        with open(SECRETS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        _SECRETOS_CACHE = data
        return True
    except Exception as e:
        logger.error(f"error guardando secretos: {e}")
        return False


def obtener_ip_pcmaster() -> str:
    """devuelve la ip tailscale de pcmaster.
    prioridad: variable de entorno pcmaster_ip -> pcmaster_tailscale_ip -> secrets/cliente.json -> config.json.
    sin valores hardcodeados."""
    # primero variable de entorno
    ip = os.environ.get("PCMASTER_IP", "")
    if ip:
        return ip

    ip = os.environ.get("PCMASTER_TAILSCALE_IP", "")
    if ip:
        return ip

    # segundo secrets/cliente.json
    secrets = _cargar_secretos()
    ip = secrets.get("pcmaster_tailscale_ip", "")
    if ip:
        return ip

    ip = secrets.get("pcmaster_ip", "")
    if ip:
        return ip

    # tercero config.json
    try:
        from config_loader import load_config
        cfg = load_config()
        ip = cfg.get("pcmaster", {}).get("ip_tailscale", "")
        if ip:
            return ip
        ip = cfg.get("pcmaster", {}).get("ip", "")
        if ip:
            return ip
    except Exception:
        pass

    logger.error("no se pudo determinar ip de pcmaster. define pcmaster_ip como variable de entorno.")
    return ""


def obtener_puerto_ws() -> int:
    """devuelve el puerto websocket de pcmaster.
    prioridad: variable de entorno pcmaster_ws_port -> secrets/cliente.json -> config.json -> fallback 8086."""
    puerto_str = os.environ.get("PCMASTER_WS_PORT", "")
    if puerto_str:
        try:
            return int(puerto_str)
        except (ValueError, TypeError):
            pass

    secrets = _cargar_secretos()
    puerto = secrets.get("pcmaster_ws_port", 0)
    if puerto:
        return int(puerto)

    try:
        from config_loader import load_config
        cfg = load_config()
        puerto = cfg.get("pcmaster", {}).get("ws_port", 0)
        if puerto:
            return int(puerto)
    except Exception:
        pass

    return 8086


def obtener_secreto_shs() -> str:
    """devuelve el secreto compartido shs desde cliente.json.
    no tiene fallback hardcodeado por seguridad.
    si no existe, loguea error y devuelve string vacio."""
    secrets = _cargar_secretos()
    secreto = secrets.get("secreto_shs", "")
    if not secreto:
        logger.error(
            "secreto shs no encontrado en data/secrets/cliente.json. "
            "debes obtenerlo del administrador de pcmaster."
        )
        return ""
    return secreto


def guardar_secreto_shs(secreto: str) -> bool:
    """guarda el secreto shs en el archivo de secretos."""
    secrets = _cargar_secretos()
    secrets["secreto_shs"] = secreto
    ok = _guardar_secretos(secrets)
    if ok:
        logger.info("secreto shs guardado en cliente.json")
    return ok


def obtener_pcbot_id():
    """devuelve el id unico del pcbot (hostname)."""
    return os.environ.get("COMPUTERNAME", "desconocido")