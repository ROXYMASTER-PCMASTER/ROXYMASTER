import asyncio, threading, logging
from detector import detectar_info_sistema, detectar_roxybrowser
from conector_ws import WSClient
from portal_local import iniciar_portal
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pcbot")
async def manejar_comando(tipo, datos):
    logger.info(f"comando recibido: {tipo} -> {datos}")
async def main():
    info = detectar_info_sistema()
    roxy = detectar_roxybrowser()
    logger.info(f"sistema: {info}, roxy: {roxy}")
    ws = WSClient("ws://192.168.1.17:5006", info["hostname"], manejar_comando)
    threading.Thread(target=iniciar_portal, daemon=True).start()
    await ws.connect()
if __name__ == "__main__":
    asyncio.run(main())