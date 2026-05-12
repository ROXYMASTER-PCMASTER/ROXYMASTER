"""
roxymaster v8.3 - pcbot zombie entry point
inicia el bucle asyncio de pcbot zombie que se ejecuta cada 7 minutos.
ejecutar con: python scripts/zombie_entry.py
compatible con python 3.10, utf-8 sin bom.
"""

import asyncio
import logging
import os
import sys

_BASE = r"C:\Users\CYBER\Desktop\roxymaster\pcbot"
sys.path.insert(0, _BASE)

# configurar logging
_LOGS_DIR = os.path.join(_BASE, "logs")
os.makedirs(_LOGS_DIR, exist_ok=True)

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler(os.path.join(_LOGS_DIR, "zombie.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger("zombie_entry")


def ensure_z_drive() -> bool:
    """verifica que la unidad z: este disponible. si falla, la mapea."""
    if os.path.isdir("Z:\\"):
        logger.info("unidad z: disponible")
        return True

    logger.warning("unidad z: no encontrada. intentando mapear...")
    import subprocess
    try:
        # intentar con ip primaria
        result = subprocess.run(
            ["net", "use", "Z:", r"\\192.168.1.17\pcbot_clon", "/persistent:yes"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            logger.info("unidad z: mapeada via 192.168.1.17")
            return True

        # intentar con ip secundaria
        result = subprocess.run(
            ["net", "use", "Z:", r"\\100.111.179.65\pcbot_clon", "/persistent:yes"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            logger.info("unidad z: mapeada via 100.111.179.65")
            return True

        logger.error(f"no se pudo mapear z: ({result.stderr.strip()})")
        return False
    except Exception as e:
        logger.error(f"error mapeando z:: {e}")
        return False


async def main():
    """punto de entrada del zombie pcbot."""
    logger.info("=" * 50)
    logger.info("pcbot zombie v8.3 iniciando...")
    logger.info("=" * 50)

    # verificar unidad z:
    if not ensure_z_drive():
        logger.error("no se puede continuar sin unidad z:. reintentando en cada ciclo...")

    # verificar dependencias
    dependencias_faltantes = []
    try:
        import aiohttp
        logger.info("aiohttp disponible")
    except ImportError:
        dependencias_faltantes.append("aiohttp")

    if dependencias_faltantes:
        logger.warning(f"dependencias faltantes: {dependencias_faltantes}")
        logger.warning("el agente continuara pero las pruebas de red fallaran")

    # iniciar bucle zombie
    try:
        from scripts.pcbot_loop import PcbotLoop

        bucle = PcbotLoop()
        await bucle.iniciar()
    except KeyboardInterrupt:
        logger.info("interrupcion del usuario detectada")
    except Exception as e:
        logger.critical(f"error fatal en zombie: {e}", exc_info=True)
        # escribir errores_pendientes.txt
        try:
            from scripts.error_handler import ErrorHandler
            eh = ErrorHandler()
            import traceback
            tb_str = traceback.format_exc()
            await eh.escribir_errores_pendientes(tb_str, ["reiniciar zombie_entry.py",
                                                           "verificar dependencias",
                                                           "revisar logs"])
        except Exception:
            logger.critical("no se pudo escribir errores_pendientes.txt")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("programa terminado por el usuario")
    except Exception as e:
        logger.critical(f"error no manejado: {e}", exc_info=True)
        sys.exit(1)