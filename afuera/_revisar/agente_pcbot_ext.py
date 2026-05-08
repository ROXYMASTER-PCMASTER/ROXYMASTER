# agente_pcbot_ext.py - manejadores de solicitudes y bucle principal
# roxymaster v8.3 - todos los nombres en minusculas, utf-8 sin bom
# no usa shs ni hmac, solo archivos de texto plano en carpeta compartida

import asyncio
import logging
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

# importar todo desde core
from agente_pcbot_core import (
    CARPETA_COMPARTIDA,
    RUTA_ROXYMASTER,
    RUTA_SCRIPTS,
    RUTA_DATA,
    RUTA_DB,
    RUTA_PORTAL,
    RUTA_PRIVADO,
    ERRORES_PENDIENTES,
    ERROR_REPETIDO,
    BUCLE_SIN_PROGRESO,
    conteo_errores_consecutivos,
    ciclos_sin_progreso,
    ultima_accion_real,
    ultima_verificacion_servicios,
    logger,
    leer_reporte,
    escribir_respuesta,
    escribir_alerta,
    parsear_reporte,
    obtener_solicitud,
    tiene_error,
    verificar_errores_repetidos,
    verificar_bucle_sin_progreso,
)

# ---------------------------------------------------------------------------
# manejadores de solicitudes
# ---------------------------------------------------------------------------

async def manejar_error(reporte):
    """maneja un reporte con error."""
    error_msg = reporte.get("error_detectado", "error desconocido")
    diagnostico = f"error reportado por pcbot: {error_msg}"
    accion = f"revisa el error: {error_msg}. si necesitas que genere un archivo de correccion, especifica el archivo exacto."

    if verificar_errores_repetidos(error_msg):
        diagnostico += " (3er error consecutivo, se genero alerta)"

    escribir_respuesta(diagnostico, "ninguno", accion, esperar_respuesta=True)
    return True


async def manejar_heartbeat(reporte):
    """maneja un reporte sin solicitud explicita (heartbeat)."""
    global conteo_errores_consecutivos, ciclos_sin_progreso
    conteo_errores_consecutivos = 0

    perfiles = reporte.get("perfiles_detectados", "0")
    diagnostico = f"heartbeat recibido. perfiles detectados: {perfiles}"
    accion = "pcbot operativo y monitoreado. continuar con operacion normal."

    escribir_respuesta(diagnostico, "ninguno", accion, esperar_respuesta=False)
    return True


async def manejar_solicitud_roxykey(reporte):
    """maneja solicitud de api key para roxybrowser."""
    try:
        sys.path.insert(0, RUTA_SCRIPTS)
        from db import ejecutar_sql
    except Exception as e:
        logger.error(f"error al importar db: {e}")
        diagnostico = "no se pudo consultar la base de datos para obtener api key de roxybrowser"
        accion = "se necesita la api key de roxybrowser. por favor, el usuario humano debe ingresar la api key en el dashboard publico (endpoint /api/registrar_api_roxy). una vez registrada, pcmaster te la enviara automaticamente."
        escribir_respuesta(diagnostico, "ninguno", accion, esperar_respuesta=True)
        return True

    try:
        rows = ejecutar_sql("select id, roxy_api_key, roxy_workspace_id from usuarios where roxy_api_key != '' and roxy_api_key is not null limit 1")
        if rows:
            usuario = rows[0]
            api_key = usuario.get("roxy_api_key", "")
            workspace_id = usuario.get("roxy_workspace_id", "")
            if api_key:
                diagnostico = "api key de roxybrowser encontrada en base de datos"
                accion = f"usa esta api key: {api_key} para consultar roxybrowser. workspace id: {workspace_id}. reporta los perfiles encontrados."
                escribir_respuesta(diagnostico, "ninguno", accion, esperar_respuesta=True)
                return True
    except Exception as e:
        logger.error(f"error al consultar api key en db: {e}")

    diagnostico = "no hay api key de roxybrowser registrada en la base de datos"
    accion = "el usuario humano debe ingresar la api key de roxybrowser en el dashboard publico (endpoint /api/registrar_api_roxy). una vez registrada, pcmaster te la enviara. mientras tanto, continua monitoreando."
    escribir_respuesta(diagnostico, "ninguno", accion, esperar_respuesta=False)
    return True


async def manejar_correccion(reporte, solicitud):
    """maneja solicitud de correccion de un archivo."""
    palabras = solicitud.split()
    archivo = "ninguno"
    for i, p in enumerate(palabras):
        if p in ("archivo", "script", "fichero") and i + 1 < len(palabras):
            archivo = palabras[i + 1].strip(".:,;")
            break

    diagnostico = f"solicitud de correccion recibida para archivo: {archivo}"
    accion = f"para corregir {archivo}, envia el contenido actual del archivo en el proximo reporte para que pueda generar la version corregida."
    escribir_respuesta(diagnostico, archivo, accion, esperar_respuesta=True)
    return True


async def manejar_prueba_visual(reporte, solicitud):
    """maneja solicitud de prueba visual o captura."""
    diagnostico = "solicitud de prueba visual recibida"
    accion = "ejecuta una prueba visual del dashboard publico en http://localhost:8086 y envia el resultado o captura en el proximo reporte."
    escribir_respuesta(diagnostico, "ninguno", accion, esperar_respuesta=True)
    return True


def manejar_operativo(reporte):
    """maneja reporte de estado operativo."""
    global conteo_errores_consecutivos, ciclos_sin_progreso
    conteo_errores_consecutivos = 0
    ciclos_sin_progreso = 0

    diagnostico = "pcbot reporta estado operativo. sin incidencias."
    accion = "continua con la operacion normal. reporta cualquier novedad."
    escribir_respuesta(diagnostico, "ninguno", accion, esperar_respuesta=False)
    return True


def manejar_no_reconocida(reporte, solicitud):
    """maneja una solicitud no reconocida."""
    global ultima_accion_real

    diagnostico = f"solicitud no reconocida: {solicitud[:100]}"
    accion = "no reconozco esta solicitud. por favor, especifica claramente que necesitas: 'api key para roxybrowser', 'corregir [archivo]', o 'prueba visual'."

    if verificar_bucle_sin_progreso(solicitud):
        diagnostico += " (bucle sin progreso detectado)"

    escribir_respuesta(diagnostico, "ninguno", accion, esperar_respuesta=False)
    return True


# ---------------------------------------------------------------------------
# procesamiento de reportes
# ---------------------------------------------------------------------------

async def procesar_reporte(contenido):
    """procesa el contenido de un reporte y genera la respuesta adecuada."""
    global conteo_errores_consecutivos, ciclos_sin_progreso, ultima_accion_real

    reporte = parsear_reporte(contenido)
    solicitud = obtener_solicitud(reporte)

    logger.info(f"procesando reporte. solicitud: {solicitud[:80] if solicitud else 'vacia'}")

    if tiene_error(reporte):
        logger.warning(f"error detectado en reporte: {reporte.get('error_detectado')}")
        return await manejar_error(reporte)

    if not solicitud:
        return await manejar_heartbeat(reporte)

    if "roxy" in solicitud and ("api" in solicitud or "key" in solicitud):
        return await manejar_solicitud_roxykey(reporte)

    if "corregir" in solicitud or "arreglar" in solicitud:
        return await manejar_correccion(reporte, solicitud)

    if "prueba" in solicitud or "visual" in solicitud or "captura" in solicitud:
        return await manejar_prueba_visual(reporte, solicitud)

    if "operativo" in solicitud or "esperando" in solicitud:
        return manejar_operativo(reporte)

    return manejar_no_reconocida(reporte, solicitud)


# ---------------------------------------------------------------------------
# monitoreo de respuesta (esperar hasta 7 minutos)
# ---------------------------------------------------------------------------

async def esperar_respuesta_pcbot(timeout_minutos=7):
    """monitorea la carpeta compartida esperando un nuevo pcbot_report.txt."""
    logger.info(f"esperando respuesta de pcbot (timeout: {timeout_minutos} minutos)...")
    inicio = time.time()
    timeout_segundos = timeout_minutos * 60

    while time.time() - inicio < timeout_segundos:
        ruta = os.path.join(CARPETA_COMPARTIDA, "pcbot_report.txt")
        if os.path.exists(ruta):
            logger.info("nuevo reporte recibido durante espera")
            return True
        await asyncio.sleep(30)

    logger.warning(f"timeout: pcbot no respondio en {timeout_minutos} minutos")
    contenido_timeout = (
        f"tiempo_agotado: {datetime.now().isoformat()}\n"
        f"timeout_minutos: {timeout_minutos}\n"
        f"detalle: pcbot no respondio dentro del tiempo limite\n"
    )
    ruta_timeout = os.path.join(CARPETA_COMPARTIDA, "tiempo_agotado_pcbot.txt")
    with open(ruta_timeout, "w", encoding="utf-8-sig") as f:
        f.write(contenido_timeout)
    logger.info("archivo tiempo_agotado_pcbot.txt escrito")
    return False


# ---------------------------------------------------------------------------
# verificacion de servicios
# ---------------------------------------------------------------------------

async def verificar_estado_servicios():
    """verifica que los servicios (api, ws) esten operativos."""
    global ultima_verificacion_servicios

    ahora = time.time()
    if ahora - ultima_verificacion_servicios < 300:
        return True

    ultima_verificacion_servicios = ahora
    logger.info("verificando estado de servicios...")

    try:
        req = urllib.request.Request("http://localhost:8086/api/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                logger.info("servicio fastapi en puerto 8086: OK")
            else:
                logger.warning(f"servicio fastapi respondio con status {resp.status}")
    except Exception as e:
        logger.error(f"servicio fastapi no responde: {e}")
        logger.info("intentando iniciar servidor fastapi...")
        ruta_server = os.path.join(RUTA_SCRIPTS, "server.py")
        if os.path.exists(ruta_server):
            try:
                ps_script = os.path.join(RUTA_ROXYMASTER, "run_server_ps.ps1")
                if os.path.exists(ps_script):
                    subprocess.Popen(
                        ["powershell", "-File", ps_script],
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    logger.info("servidor iniciado via run_server_ps.ps1")
                else:
                    subprocess.Popen(
                        ["python", ruta_server],
                        cwd=RUTA_SCRIPTS,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    logger.info("servidor iniciado directamente")
            except Exception as e2:
                logger.error(f"error al iniciar servidor: {e2}")
                contenido_error = (
                    f"error al iniciar servidor fastapi\n"
                    f"traceback: {e2}\n"
                    f"fecha: {datetime.now().isoformat()}\n"
                    f"soluciones intentadas: run_server_ps.ps1, python server.py\n"
                )
                with open(ERRORES_PENDIENTES, "w", encoding="utf-8-sig") as f:
                    f.write(contenido_error)
        return False

    return True


async def verificar_base_datos():
    """verifica que la base de datos sea accesible."""
    try:
        if not os.path.exists(RUTA_DB):
            logger.warning(f"base de datos no encontrada en {RUTA_DB}")
            sys.path.insert(0, RUTA_SCRIPTS)
            from db import init_db
            init_db()
            logger.info("base de datos inicializada desde cero")
            return True

        import sqlite3
        conn = sqlite3.connect(RUTA_DB)
        conn.execute("select 1")
        conn.close()
        logger.info("base de datos: OK")
        return True
    except Exception as e:
        logger.error(f"error al verificar base de datos: {e}")
        return False


# ---------------------------------------------------------------------------
# bucle principal
# ---------------------------------------------------------------------------

async def bucle_principal():
    """bucle infinito de procesamiento de reportes."""
    global conteo_errores_consecutivos, ciclos_sin_progreso, ultima_accion_real

    logger.info("=" * 60)
    logger.info("agente pcmaster iniciado")
    logger.info(f"carpeta compartida: {CARPETA_COMPARTIDA}")
    logger.info(f"base de datos: {RUTA_DB}")
    logger.info(f"scripts: {RUTA_SCRIPTS}")
    logger.info("=" * 60)

    os.makedirs(CARPETA_COMPARTIDA, exist_ok=True)
    logger.info("carpeta compartida verificada/creada")

    await verificar_estado_servicios()
    await verificar_base_datos()

    contador_ciclos = 0

    while True:
        try:
            contador_ciclos += 1

            contenido = leer_reporte()

            if contenido:
                ciclos_sin_progreso = 0
                await procesar_reporte(contenido)
            else:
                await asyncio.sleep(5)

            if contador_ciclos % 100 == 0:
                await verificar_estado_servicios()
                await verificar_base_datos()
                contador_ciclos = 0

            if ciclos_sin_progreso >= 4:
                logger.warning("bucle sin progreso detectado, deteniendo")
                break

        except KeyboardInterrupt:
            logger.info("agente detenido por el usuario")
            break
        except Exception as e:
            logger.error(f"error en bucle principal: {e}")
            conteo_errores_consecutivos += 1
            if conteo_errores_consecutivos >= 3:
                logger.critical("3 errores consecutivos en bucle principal")
                break
            await asyncio.sleep(5)


def main():
    """punto de entrada."""
    try:
        asyncio.run(bucle_principal())
    except KeyboardInterrupt:
        logger.info("agente detenido por el usuario")
    except Exception as e:
        logger.error(f"error fatal: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()