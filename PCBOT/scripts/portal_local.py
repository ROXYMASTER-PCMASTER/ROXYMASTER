# portal_local.py - servidor HTTP local del pcbot
import asyncio, os, socket, logging
logger = logging.getLogger("portal_local")
async def iniciar_servidor_portal