# ws_client.py - roxymaster v8.3
# cliente websocket para pcbot con heartbeat periódico y recepción de api keys.

import asyncio
import json
import logging
import time
from datetime import datetime

import aiohttp
import websockets

from config_loader import cargar_configuracion
from deteccion_perfiles import detectar_perfiles_roxy, detectar_navegadores
from auto_detect import detectar_sistema
from api.roxybrowser_api import RoxyBrowserAPI

logger = logging.getLogger("pcbot.ws_client")

HEARTBEAT_INTERVAL = 60  # segundos

async def conectar_ws(loop=None):
    """establece conexión websocket con pcmaster y ejecuta el bucle de mensajes."""
    config = cargar_configuracion()
    uri = config.get("ws_uri", "ws://100.111.179.65:5006")
    hostname, usuario, ip_local, ip_tailscale, ip_wan, workspace_id = detectar_sistema(config)

    handshake = {
        "tipo": "handshake",
        "hostname": hostname,
        "usuario": usuario,
        "ip_local": ip_local,
        "ip_tailscale": ip_tailscale,
        "ip_wan": ip_wan,
        "workspace_id": workspace_id,
        "perfiles_roxy": detectar_perfiles_roxy(),
        "navegadores": detectar_navegadores(),
        "perfiles_vip": [],
        "modo": "pidiendo_ordenes",
        "version_agente": "8.3"
    }

    while True:
        try:
            async with websockets.connect(uri) as ws:
                await ws.send(json.dumps(handshake))
                logger.info("Conectado a PCMaster. Handshake enviado.")

                heartbeat_task = asyncio.create_task(heartbeat_loop(ws, handshake))

                async for raw in ws:
                    try:
                        msg = json.loads(raw)
                        await procesar_mensaje(ws, msg)
                    except json.JSONDecodeError:
                        logger.error("Mensaje no decodificable: %s", raw)

                heartbeat_task.cancel()
                break
        except (websockets.ConnectionClosed, ConnectionRefusedError, OSError) as e:
            logger.warning("Conexión perdida: %s. Reintentando en 5s...", e)
            await asyncio.sleep(5)

async def heartbeat_loop(ws, handshake):
    """envía heartbeat cada HEARTBEAT_INTERVAL segundos."""
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        perfiles = detectar_perfiles_roxy()
        navegadores = detectar_navegadores()
        heartbeat_msg = {
            **handshake,
            "tipo": "heartbeat",
            "perfiles_roxy": perfiles,
            "navegadores": navegadores,
            "timestamp": datetime.now().isoformat()
        }
        try:
            await ws.send(json.dumps(heartbeat_msg))
            logger.debug("Heartbeat enviado.")
        except websockets.ConnectionClosed:
            logger.warning("Conexión cerrada durante heartbeat.")
            break

async def procesar_mensaje(ws, msg):
    """procesa mensajes recibidos del servidor."""
    tipo = msg.get("tipo", "")

    if tipo == "comando":
        # manejado por orchestrator_local.py
        pass

    elif tipo == "nueva_api_key":
        api_key = msg.get("api_key", "")
        if api_key:
            logger.info("Recibida nueva API Key. Consultando RoxyBrowser...")
            asyncio.create_task(procesar_api_key(ws, api_key))

    elif tipo == "heartbeat_ack":
        api_keys_pendientes = msg.get("api_keys_pendientes", [])
        for api_key in api_keys_pendientes:
            logger.info("API Key pendiente: %s...", api_key[:8])
            asyncio.create_task(procesar_api_key(ws, api_key))

    else:
        logger.debug("Tipo de mensaje desconocido: %s", tipo)

async def procesar_api_key(ws, api_key):
    """obtiene los perfiles de roxybrowser y los envía al servidor."""
    try:
        async with RoxyBrowserAPI(api_key) as roxy:
            perfiles = await roxy.obtener_perfiles()
        if perfiles:
            await ws.send(json.dumps({
                "tipo": "registrar_perfiles",
                "api_key": api_key,
                "perfiles": perfiles
            }))
            logger.info("Enviados %d perfiles al servidor.", len(perfiles))
    except Exception as e:
        logger.error("Error al procesar API Key: %s", e)
