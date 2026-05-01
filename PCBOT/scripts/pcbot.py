# pcbot.py - agente principal roxymaster v8.3
import asyncio, os, sys, json, logging, threading, time
from pathlib import Path

_base_dir = Path(__file__).parent.parent.absolute()
_scripts_dir = _base_dir / "scripts"
sys.path.insert(0, str(_scripts_dir))

from detector import detectar_info_sistema, detectar_roxybrowser
from conector_ws import WSClient
from ejecutor import inicializar_playwright
from portal_local import iniciar_servidor_portal
from variables_globales import PCMASTER_IP, PCMASTER_PORT

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pcbot")

playwright_inst = None

async def manejar_comando(tipo, datos):
    logger.info(f"comando recibido: {tipo} -> {datos}")

async def main():
    global playwright_inst
    info = detectar_info_sistema()
    roxy = detectar_roxybrowser()
    logger.info(f"sistema: {info}, roxybrowser: {roxy}")
    
    playwright_inst = await inicializar_playwright()
    
    threading.Thread(target=iniciar_servidor_portal, daemon=True).start()
    
    ws = WSClient(f"ws://{PCMASTER_IP}:{PCMASTER_PORT}", info["hostname"], manejar_comando)
    await ws.connect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\npcbot detenido.")
    except Exception as e:
        logger.error(f"error fatal: {e}")
        raise