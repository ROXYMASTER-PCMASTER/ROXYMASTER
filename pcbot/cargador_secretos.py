# cargador_secretos.py - carga ip, puerto y secreto shs para pcbot
# roxymaster v8.3 - todo en minusculas, utf-8 sin bom

import os
import json
import logging

logger = logging.getLogger(__name__)

_base_dir = os.path.dirname(os.path.abspath(__file__))
_data_dir = os.path.join(_base_dir, "data")
_secrets_dir = os.path.join(_data_dir, "secrets")
_secrets_file = os.path.join(_secrets_dir, "cliente.json")

_ip_pcmaster = "100.111.179.65"
_puerto_ws = 5006

def _asegurar_directorios():
    os.makedirs(_secrets_dir, exist_ok=True)

def obtener_ip_pcmaster() -> str:
    return _ip_pcmaster

def obtener_puerto_ws() -> int:
    return _puerto_ws

def obtener_secreto_shs() -> str:
    _asegurar_directorios()
    if not os.path.exists(_secrets_file):
        return ""
    try:
        with open(_secrets_file, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data.get("secreto_shs", "")
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"error leyendo secreto shs: {e}")
        return ""

def guardar_secreto_shs(secreto: str):
    _asegurar_directorios()
    data = {}
    if os.path.exists(_secrets_file):
        try:
            with open(_secrets_file, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    data["secreto_shs"] = secreto
    try:
        with open(_secrets_file, "w", encoding="utf-8-sig") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("secreto shs guardado en data/secrets/cliente.json")
    except IOError as e:
        logger.error(f"error guardando secreto shs: {e}")

def obtener_token_session() -> str:
    _asegurar_directorios()
    if not os.path.exists(_secrets_file):
        return ""
    try:
        with open(_secrets_file, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data.get("token_session", "")
    except (json.JSONDecodeError, IOError):
        return ""

def guardar_token_session(token: str):
    _asegurar_directorios()
    data = {}
    if os.path.exists(_secrets_file):
        try:
            with open(_secrets_file, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    data["token_session"] = token
    try:
        with open(_secrets_file, "w", encoding="utf-8-sig") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except IOError as e:
        logger.error(f"error guardando token session: {e}")
