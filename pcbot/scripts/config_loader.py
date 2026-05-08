# config_loader.py - roxymaster v8.3
# carga configuración desde archivos json y obtiene token dinámicamente.

import json
import os
import logging
import aiohttp
import asyncio

logger = logging.getLogger("pcbot.config_loader")

CONFIG_PATHS = [
    "config.json",
    "data/roxy_config.json",
    "data/roxy_profiles.json"
]

SECRETS_PATH = "data/secrets/cliente.json"
TOKEN_CACHE_PATH = "data/secrets/token_cache.json"

def cargar_configuracion():
    """carga la configuración desde cualquiera de las rutas disponibles."""
    config = {}
    for path in CONFIG_PATHS:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    config.update(json.load(f))
            except Exception as e:
                logger.warning("error al cargar %s: %s", path, e)
    return config

def guardar_token(token):
    """guarda el token en un archivo de caché."""
    os.makedirs(os.path.dirname(TOKEN_CACHE_PATH), exist_ok=True)
    with open(TOKEN_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump({"token": token}, f)

def cargar_token_cache():
    """carga el token desde el caché si existe."""
    if os.path.exists(TOKEN_CACHE_PATH):
        try:
            with open(TOKEN_CACHE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("token")
        except Exception:
            pass
    return None

async def obtener_token_dinamico(config):
    """obtiene un token de acceso llamando al endpoint de login."""
    email = config.get("email", "")
    password = config.get("password", "")
    base_url = config.get("base_url", "https://www.wafabot.com")
    login_url = f"{base_url}/api/login"

    if not email or not password:
        logger.error("email o password no configurados en roxy_config.json")
        return None

    try:
        async with aiohttp.ClientSession() as session:
            payload = {"email": email, "password": password}
            async with session.post(login_url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    token = data.get("token")
                    if token:
                        guardar_token(token)
                        logger.info("token obtenido dinámicamente")
                        return token
                logger.error("error al obtener token: %s", await resp.text())
    except Exception as e:
        logger.error("excepción al conectar con el servidor de login: %s", e)
    return None

def obtener_token(config):
    """devuelve el token de acceso: primero prueba el caché, luego lo obtiene dinámicamente."""
    token = config.get("token", "") or cargar_token_cache()
    if token:
        return token
    # Si no hay token, se debe obtener asíncronamente (se llama desde el event loop)
    return None
