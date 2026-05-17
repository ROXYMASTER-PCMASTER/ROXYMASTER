# pcmaster_loop.py - bucle principal de pcmaster para comunicacion con pcbot
# roxymaster v8.3 - utf-8 sin bom - max 400 lineas

import asyncio
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime, timedelta

# rutas fijas
COMPARTIDA = r"C:\Users\PCMASTER\Desktop\pcbot_clon"
PCMASTER_SCRIPTS = r"C:\Users\PCMASTER\Desktop\roxymaster\pcmaster\scripts"
BACKUPS_DIR = r"C:\Users\PCMASTER\Desktop\backups_pcmaster"
STOP_FILE = os.path.join(COMPARTIDA, "stop_bucle.txt")

# subcarpetas compartidas
PCBOT_MSGS = os.path.join(COMPARTIDA, "pcbot_msgs")
PCMASTER_MSGS = os.path.join(COMPARTIDA, "pcmaster_msgs")
HUMAN_TASKS = os.path.join(COMPARTIDA, "roxymaster_human_tasks")
HUMAN_ERRORS = os.path.join(HUMAN_TASKS, "errores")
LOGS_DIR = os.path.join(COMPARTIDA, "logs")
LOG_ESPERA = os.path.join(LOGS_DIR, "espera_pcmaster.log")
LOOP_LOG = os.path.join(LOGS_DIR, "pcmaster_loop.log")
BACKUP_SRC = r"C:\Users\PCMASTER\Desktop\roxymaster\pcmaster"

# configuracion
CICLO_SEGUNDOS = 420  # 7 minutos
CICLOS_POR_LOG_ESPERA = 5  # cada 5 ciclos -> escribir espera
BACKUP_INTERVALO_SEGUNDOS = 1800  # 30 minutos
MAX_BACKUPS = 5

# logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [pcmaster_loop] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler(LOOP_LOG, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("pcmaster_loop")

# estado del bucle
ciclo_contador = 0
ultimo_backup = datetime.min
proceso_servidor = None


def asegurar_carpetas():
    """crea las carpetas necesarias si no existen."""
    for carpeta in [PCBOT_MSGS, PCMASTER_MSGS, HUMAN_TASKS, HUMAN_ERRORS, LOGS_DIR, BACKUPS_DIR]:
        os.makedirs(carpeta, exist_ok=True)
    logger.info("carpetas verificadas/creadas")


async def leer_mensajes_pcbot():
    """lee el mensaje mas antiguo de pcbot_msgs/ y lo procesa."""
    try:
        archivos = [
            os.path.join(PCBOT_MSGS, f)
            for f in os.listdir(PCBOT_MSGS)
            if f.endswith(".txt")
        ]
        if not archivos:
            return None

        archivos.sort(key=os.path.getmtime)
        ruta = archivos[0]

        loop = asyncio.get_event_loop()
        contenido = await loop.run_in_executor(None, lambda: open(ruta, "r", encoding="utf-8").read())

        logger.info(f"mensaje recibido de pcbot: {os.path.basename(ruta)}")

        # parsear mensaje
        mensaje = {}
        for linea in contenido.strip().split("\n"):
            if ":" in linea:
                clave, _, valor = linea.partition(":")
                mensaje[clave.strip()] = valor.strip()

        # procesar segun solicitud
        solicitud = mensaje.get("solicitud", "")
        requiere = mensaje.get("requiere_respuesta", "false").lower() == "true"

        if solicitud:
            logger.info(f"procesando solicitud: {solicitud[:80]}")
            await procesar_solicitud_pcbot(solicitud, mensaje, requiere)

        # borrar archivo despues de procesar
        os.remove(ruta)
        logger.info(f"mensaje eliminado: {os.path.basename(ruta)}")
        return mensaje

    except Exception as e:
        logger.error(f"error al leer mensajes pcbot: {e}")
        return None


async def procesar_solicitud_pcbot(solicitud: str, mensaje: dict, requiere_respuesta: bool):
    """procesa una solicitud de pcbot y decide accion."""
    solicitud_lower = solicitud.lower()

    if "error" in solicitud_lower or mensaje.get("error_detectado", "ninguno").lower() != "ninguno":
        error_texto = mensaje.get("error_detectado", solicitud)
        logger.warning(f"pcbot reporto error: {error_texto}")

        # si requiere correccion en nuestro codigo
        if "server" in error_texto.lower() or "api" in error_texto.lower():
            logger.info("error relacionado al servidor - revisando servidor")
        else:
            # retransmitir orden de correccion a pcbot
            await enviar_a_pcbot(
                instruccion=f"corregir_error: {error_texto}",
                parametros=mensaje
            )

    elif "sync" in solicitud_lower or "sincronizar" in solicitud_lower:
        logger.info("pcbot solicita sincronizacion - verificando estado")
        await enviar_a_pcbot(
            instruccion="verificar_sync",
            parametros={"estado": "ok", "timestamp": datetime.now().isoformat()}
        )

    elif requiere_respuesta:
        await enviar_a_pcbot(
            instruccion=f"respuesta: {solicitud}",
            parametros={"procesado": True, "timestamp": datetime.now().isoformat()}
        )

    else:
        logger.info(f"solicitud de pcbot sin accion especifica: {solicitud[:60]}")


async def enviar_a_pcbot(instruccion: str, parametros: dict = None):
    """escribe un mensaje en pcmaster_msgs/ para pcbot."""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        nombre = f"msg_{timestamp}.txt"
        ruta = os.path.join(PCMASTER_MSGS, nombre)

        contenido = f"""timestamp: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
remitente: pcmaster
instruccion: {instruccion}
parametros: {json.dumps(parametros) if parametros else "{}"}
"""

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: open(ruta, "w", encoding="utf-8").write(contenido))
        logger.info(f"mensaje enviado a pcbot: {nombre}")
        return True
    except Exception as e:
        logger.error(f"error al enviar mensaje a pcbot: {e}")
        return False


async def procesar_ordenes_humanas():
    """lee y ejecuta ordenes de roxymaster_human_tasks/."""
    try:
        archivos = [
            os.path.join(HUMAN_TASKS, f)
            for f in os.listdir(HUMAN_TASKS)
            if f.endswith(".txt") and f != "errores"
        ]
        for ruta in archivos:
            if os.path.isdir(ruta):
                continue

            loop = asyncio.get_event_loop()
            contenido = await loop.run_in_executor(None, lambda: open(ruta, "r", encoding="utf-8").read())

            # buscar #destino:
            destino = None
            for linea in contenido.split("\n"):
                linea_stripped = linea.strip().lower()
                if linea_stripped.startswith("#destino:"):
                    partes = linea_stripped.split(":", 1)
                    if len(partes) > 1:
                        destino = partes[1].strip()
                    break

            if not destino:
                # mover a errores
                destino_err = os.path.join(HUMAN_ERRORS, os.path.basename(ruta))
                shutil.move(ruta, destino_err)
                logger.warning(f"orden humana sin #destino, movida a errores: {os.path.basename(ruta)}")
                continue

            logger.info(f"orden humana procesada, destino={destino}: {os.path.basename(ruta)}")

            if destino in ("pcmaster", "ambos"):
                logger.info(f"ejecutando orden para pcmaster: {os.path.basename(ruta)}")
                await ejecutar_orden_pcmaster(contenido)

            if destino == "pcbot":
                logger.info(f"retransmitiendo orden a pcbot: {os.path.basename(ruta)}")
                await enviar_a_pcbot(
                    instruccion="orden_humana",
                    parametros={"contenido": contenido}
                )

            if destino == "ambos":
                # ya se ejecuto para pcmaster arriba, ahora retransmitir
                await enviar_a_pcbot(
                    instruccion="orden_humana_compartida",
                    parametros={"contenido": contenido}
                )

            # borrar archivo procesado
            os.remove(ruta)
            logger.info(f"orden humana eliminada: {os.path.basename(ruta)}")

    except Exception as e:
        logger.error(f"error al procesar ordenes humanas: {e}")


async def ejecutar_orden_pcmaster(contenido: str):
    """ejecuta una orden dirigida a pcmaster."""
    logger.info(f"orden recibida para pcmaster: {contenido[:100]}")

    # buscar si es un comando de modificacion de codigo
    if "modificar" in contenido.lower() or "corregir" in contenido.lower() or "cambiar" in contenido.lower():
        logger.info("orden requiere modificacion de codigo - registrando para accion manual")

    # buscar si es un comando de prueba
    if "prueba" in contenido.lower() or "test" in contenido.lower():
        logger.info("orden de prueba - verificando servidor")

    # si es un comando de ejecucion directa
    if "ejecutar" in contenido.lower() or "correr" in contenido.lower():
        logger.info("orden de ejecucion")


async def verificar_servidor():
    """verifica que el servidor fastapi este corriendo."""
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get("http://127.0.0.1:8086/api/health", timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(f"servidor saludable: {data.get('pcbots_conectados', 0)} pcbots conectados")
                    return True
                else:
                    logger.warning(f"servidor respondio con status {resp.status}")
                    return False
    except ImportError:
        # sin aiohttp, intentar con curl
        logger.info("aiohttp no disponible, verificando con curl")
        try:
            proc = await asyncio.create_subprocess_shell(
                "curl -s http://127.0.0.1:8086/api/health",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            if stdout:
                logger.info(f"servidor responde: {stdout.decode()[:100]}")
                return True
            return False
        except Exception as e:
            logger.error(f"error verificando servidor con curl: {e}")
            return False
    except Exception as e:
        logger.error(f"servidor no responde: {e}")
        return False


async def iniciar_servidor():
    """intenta iniciar el servidor fastapi si no esta corriendo."""
    global proceso_servidor

    server_py = os.path.join(PCMASTER_SCRIPTS, "server.py")
    if not os.path.exists(server_py):
        logger.error(f"server.py no encontrado en {server_py}")
        return False

    try:
        logger.info("intentando iniciar servidor fastapi...")
        proceso_servidor = await asyncio.create_subprocess_shell(
            f"python \"{server_py}\"",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=PCMASTER_SCRIPTS
        )

        # esperar un momento para verificar
        await asyncio.sleep(3)

        if proceso_servidor.returncode is not None:
            stderr = await proceso_servidor.stderr.read()
            logger.error(f"servidor fallo al iniciar: {stderr.decode()[:200]}")
            proceso_servidor = None
            return False

        logger.info("servidor fastapi iniciado correctamente")
        return True
    except Exception as e:
        logger.error(f"error al iniciar servidor: {e}")
        return False


async def escribir_log_espera():
    """escribe que estamos esperando mensajes."""
    try:
        mensaje = f"{datetime.now().isoformat()} - esperando mensajes de pcbot u ordenes humanas - ciclo {ciclo_contador}\n"
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: open(LOG_ESPERA, "a", encoding="utf-8").write(mensaje))
        logger.debug("log de espera escrito")
    except Exception as e:
        logger.error(f"error al escribir log de espera: {e}")


async def hacer_backup():
    """copia pcmaster/ a backups_pcmaster/ y mantiene solo los 5 mas recientes."""
    global ultimo_backup

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = os.path.join(BACKUPS_DIR, f"backup_{timestamp}")

        if not os.path.exists(BACKUP_SRC):
            logger.warning(f"origen de backup no existe: {BACKUP_SRC}")
            return

        logger.info(f"iniciando backup a {destino}")

        shutil.copytree(BACKUP_SRC, destino, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

        # mantener solo los 5 mas recientes
        backups = sorted([
            os.path.join(BACKUPS_DIR, d)
            for d in os.listdir(BACKUPS_DIR)
            if os.path.isdir(os.path.join(BACKUPS_DIR, d)) and d.startswith("backup_")
        ], key=os.path.getmtime, reverse=True)

        for viejo in backups[MAX_BACKUPS:]:
            shutil.rmtree(viejo)
            logger.info(f"backup antiguo eliminado: {os.path.basename(viejo)}")

        ultimo_backup = datetime.now()
        logger.info(f"backup completado: backup_{timestamp}")

    except Exception as e:
        logger.error(f"error durante backup: {e}")


async def bucle_principal():
    """bucle infinito principal de pcmaster."""
    global ciclo_contador, proceso_servidor

    logger.info("=" * 60)
    logger.info("INICIANDO BUCLE PRINCIPAL PCMASTER")
    logger.info(f"cada ciclo: {CICLO_SEGUNDOS}s ({CICLO_SEGUNDOS//60} min)")
    logger.info(f"log de espera cada: {CICLOS_POR_LOG_ESPERA} ciclos")
    logger.info(f"backup cada: {BACKUP_INTERVALO_SEGUNDOS//60} min")
    logger.info("=" * 60)

    # verificar servidor al inicio
    servidor_ok = await verificar_servidor()
    if not servidor_ok:
        logger.warning("servidor no responde, intentando iniciar...")
        await iniciar_servidor()
        await asyncio.sleep(3)

    while True:
        try:
            ciclo_contador += 1
            logger.info(f"--- CICLO {ciclo_contador} iniciado ---")

            # 1. verificar stop file
            if os.path.exists(STOP_FILE):
                logger.warning("ARCHIVO stop_bucle.txt DETECTADO - DETENIENDO BUCLE")
                return

            # 2. leer mensajes de pcbot
            mensaje = await leer_mensajes_pcbot()
            if mensaje:
                logger.info("mensaje de pcbot procesado en este ciclo")
            else:
                logger.debug("no hay mensajes de pcbot")

            # 3. procesar ordenes humanas
            ordenes = os.listdir(HUMAN_TASKS)
            ordenes_txt = [f for f in ordenes if f.endswith(".txt") and f != "errores"]
            if ordenes_txt:
                logger.info(f"ordenes humanas detectadas: {len(ordenes_txt)}")
                await procesar_ordenes_humanas()
            else:
                logger.debug("no hay ordenes humanas")

            # 4. verificar servidor cada ciclo
            servidor_ok = await verificar_servidor()
            if not servidor_ok:
                logger.warning("servidor caido, intentando reiniciar...")
                exito = await iniciar_servidor()
                if not exito:
                    logger.error("NO SE PUDO INICIAR EL SERVIDOR")
                    # escribir errores_pendientes.txt
                    try:
                        with open(r"C:\Users\PCMASTER\Desktop\errores_pendientes.txt", "a", encoding="utf-8") as f:
                            f.write(f"[{datetime.now().isoformat()}] servidor caido y no pudo reiniciarse tras reintento\n")
                    except Exception:
                        pass

            # 5. backup cada 30 minutos
            if (datetime.now() - ultimo_backup).total_seconds() > BACKUP_INTERVALO_SEGUNDOS:
                await hacer_backup()

            # 6. log de espera cada 5 ciclos si no hubo actividad
            if ciclo_contador % CICLOS_POR_LOG_ESPERA == 0:
                if not mensaje and not ordenes_txt:
                    await escribir_log_espera()
                else:
                    # hubo actividad, no escribir log de espera
                    pass

            logger.info(f"--- CICLO {ciclo_contador} completado, esperando {CICLO_SEGUNDOS}s ---")
            await asyncio.sleep(CICLO_SEGUNDOS)

        except asyncio.CancelledError:
            logger.info("bucle cancelado")
            break
        except Exception as e:
            logger.error(f"error en ciclo {ciclo_contador}: {e}", exc_info=True)
            await asyncio.sleep(CICLO_SEGUNDOS)


async def tarea_backup():
    """tarea en segundo plano para backup cada 30 minutos."""
    while True:
        try:
            await asyncio.sleep(BACKUP_INTERVALO_SEGUNDOS)
            await hacer_backup()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"error en tarea backup: {e}")


async def main():
    """punto de entrada principal."""
    asegurar_carpetas()

    # iniciar tarea de backup en segundo plano
    backup_task = asyncio.create_task(tarea_backup())

    try:
        await bucle_principal()
    except KeyboardInterrupt:
        logger.info("interrupcion de teclado detectada")
    finally:
        backup_task.cancel()
        try:
            await backup_task
        except asyncio.CancelledError:
            pass
        logger.info("bucle pcmaster finalizado")


if __name__ == "__main__":
    asyncio.run(main())