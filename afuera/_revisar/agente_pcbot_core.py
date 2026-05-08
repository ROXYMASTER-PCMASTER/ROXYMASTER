# agente_pcbot_core.py - utilidades base para comunicacion con pcbot via archivos
# roxymaster v8.3 - todos los nombres en minusculas, utf-8 sin bom
# no usa shs ni hmac, solo archivos de texto plano en carpeta compartida

import asyncio
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# configuracion de logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [agente_pcbot] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("agente_pcbot")

# ---------------------------------------------------------------------------
# rutas absolutas (no cambiar)
# ---------------------------------------------------------------------------
CARPETA_COMPARTIDA = r"C:\Users\PCMASTER\Desktop\pcbot_clon"
RUTA_ROXYMASTER = r"C:\Users\PCMASTER\Desktop\roxymaster"
RUTA_SCRIPTS = os.path.join(RUTA_ROXYMASTER, "pcmaster", "scripts")
RUTA_DATA = os.path.join(RUTA_ROXYMASTER, "pcmaster", "data")
RUTA_DB = os.path.join(RUTA_DATA, "roxymaster.db")
RUTA_PORTAL = os.path.join(RUTA_ROXYMASTER, "portal_publico")
RUTA_PRIVADO = os.path.join(RUTA_ROXYMASTER, "privado")
ERRORES_PENDIENTES = os.path.join(RUTA_ROXYMASTER, "errores_pendientes.txt")
ERROR_REPETIDO = os.path.join(RUTA_ROXYMASTER, "error_repetido.md")
BUCLE_SIN_PROGRESO = os.path.join(RUTA_ROXYMASTER, "bucle_sin_progreso.txt")

# ---------------------------------------------------------------------------
# variables de estado global
# ---------------------------------------------------------------------------
ultimo_reporte_timestamp = None
conteo_errores_consecutivos = 0
ciclos_sin_progreso = 0
ultima_accion_real = ""
ultima_verificacion_servicios = 0


# ---------------------------------------------------------------------------
# utilidades de archivos
# ---------------------------------------------------------------------------

def leer_reporte():
    """lee pcbot_report.txt de la carpeta compartida y lo borra."""
    ruta = os.path.join(CARPETA_COMPARTIDA, "pcbot_report.txt")
    if not os.path.exists(ruta):
        return None
    try:
        with open(ruta, "r", encoding="utf-8-sig") as f:
            contenido = f.read()
        # borrar el archivo inmediatamente despues de leerlo
        os.remove(ruta)
        logger.info("reporte leido y borrado exitosamente")
        return contenido
    except Exception as e:
        logger.error(f"error al leer/borrar reporte: {e}")
        # si el archivo esta corrupto, renombrarlo
        try:
            if os.path.exists(ruta):
                os.rename(ruta, ruta + ".corrupto")
                logger.info("reporte corrupto renombrado a .corrupto")
        except Exception:
            pass
        return None


def escribir_respuesta(diagnostico, archivo_corregido, accion_pcbot, esperar_respuesta=False):
    """escribe pcmaster_fix.txt en la carpeta compartida."""
    ruta = os.path.join(CARPETA_COMPARTIDA, "pcmaster_fix.txt")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    espero = "true" if esperar_respuesta else "false"
    contenido = (
        f"timestamp: {timestamp}\n"
        f"diagnostico: {diagnostico}\n"
        f"archivo_corregido: {archivo_corregido}\n"
        f"accion_para_pcbot: {accion_pcbot}\n"
        f"espero_respuesta: {espero}\n"
    )
    try:
        with open(ruta, "w", encoding="utf-8-sig") as f:
            f.write(contenido)
        logger.info(f"respuesta escrita: {ruta}")
        return True
    except Exception as e:
        logger.error(f"error al escribir respuesta: {e}")
        return False


def escribir_alerta(nombre_archivo, contenido):
    """escribe un archivo de alerta en la carpeta compartida."""
    ruta = os.path.join(CARPETA_COMPARTIDA, nombre_archivo)
    try:
        with open(ruta, "w", encoding="utf-8-sig") as f:
            f.write(contenido)
        logger.info(f"alerta escrita: {ruta}")
        return True
    except Exception as e:
        logger.error(f"error al escribir alerta: {e}")
        return False


# ---------------------------------------------------------------------------
# parseo de reporte
# ---------------------------------------------------------------------------

def parsear_reporte(contenido):
    """convierte el texto del reporte en un diccionario."""
    reporte = {}
    if not contenido:
        return reporte
    for linea in contenido.strip().split("\n"):
        if ":" in linea:
            clave, _, valor = linea.partition(":")
            reporte[clave.strip()] = valor.strip()
    return reporte


def obtener_solicitud(reporte):
    """extrae la solicitud del reporte."""
    return reporte.get("solicitud", "").strip().lower()


def tiene_error(reporte):
    """verifica si el reporte contiene un error."""
    error = reporte.get("error_detectado", "").strip().lower()
    return error != "ninguno" and error != ""


# ---------------------------------------------------------------------------
# gestor de errores repetidos y bucles
# ---------------------------------------------------------------------------

def verificar_errores_repetidos(error_msg):
    """incrementa contador y escribe error_repetido.md si llega a 3."""
    global conteo_errores_consecutivos
    conteo_errores_consecutivos += 1
    if conteo_errores_consecutivos >= 3:
        contenido = (
            f"# error repetido detectado\n"
            f"fecha: {datetime.now().isoformat()}\n"
            f"accion intentada: procesar reporte con error\n"
            f"mensaje de error: {error_msg}\n"
            f"razon probable: error persistente en pcbot\n"
            f"caminos alternativos:\n"
            f"1. pedir al usuario que verifique pcbot manualmente\n"
            f"2. reiniciar el servicio de pcbot\n"
            f"3. verificar la conexion tailscale\n"
        )
        with open(ERROR_REPETIDO, "w", encoding="utf-8-sig") as f:
            f.write(contenido)
        logger.warning("error repetido 3 veces, escrito error_repetido.md")
        conteo_errores_consecutivos = 0
        return True
    return False


def verificar_bucle_sin_progreso(solicitud):
    """incrementa contador y escribe alerta si llega a 4."""
    global ciclos_sin_progreso
    ciclos_sin_progreso += 1
    if ciclos_sin_progreso >= 4:
        contenido = (
            f"# bucle sin progreso detectado\n"
            f"fecha: {datetime.now().isoformat()}\n"
            f"ultima solicitud: {solicitud[:100]}\n"
            f"ultima accion: {ultima_accion_real}\n"
            f"se han intentado {ciclos_sin_progreso} ciclos sin progreso visible\n"
        )
        with open(BUCLE_SIN_PROGRESO, "w", encoding="utf-8-sig") as f:
            f.write(contenido)
        escribir_alerta("bucle_sin_progreso_pcmaster.txt", contenido)
        logger.warning("bucle sin progreso detectado, archivos de alerta generados")
        return True
    return False