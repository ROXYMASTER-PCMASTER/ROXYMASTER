import sys
import os
import json
import asyncio
import websockets
import socket
import threading
import time
import random
import requests
import logging
import secrets
from datetime import datetime
from collections import deque
from urllib.parse import urlparse
from jsonschema import validate, ValidationError
from concurrent.futures import ThreadPoolExecutor

BASE_DIR = os.path.join(os.environ["USERPROFILE"], "Desktop", "ROXYMASTER", "PCMASTER")
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))

from variables_globales import *
from jarvis_v61 import Jarvis

# ============================================================================
# LOGGING ESTRUCTURADO
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(BASE_DIR, "server.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("ROXYMASTER")

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

with open(os.path.join(BASE_DIR, "config.json"), "r", encoding="utf-8-sig") as f:
    config = json.load(f)

PUERTO = config["server"]["ws_port"]
IP = config["server"]["ip_servidor"]

pcbots = {}
perfiles_map = {}
grupos = {}
loop = None

# ============================================================================
# LOCKS Y SINCRONIZACIÓN (asyncio.Lock)
# ============================================================================
lock_perfiles = asyncio.Lock()
lock_grupos = asyncio.Lock()
lock_pcbots = asyncio.Lock()
tokens_autenticados = {}  # token -> {cid, tiempo}
TOKEN_TIMEOUT = 1800  # 30 minutos

# ============================================================================
# RATE LIMITING - TOKEN BUCKET (100 solicitudes/segundo)
# ============================================================================

class TokenBucket:
    """Rate limiter con algoritmo token bucket."""
    def __init__(self, rate=100, burst=120):
        self.rate = rate
        self.burst = burst
        self.tokens = burst
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def consume(self, tokens=1):
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_refill = now
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

rate_limiter = TokenBucket(rate=100, burst=120)

# ============================================================================
# JSON SCHEMA PARA MENSAJES WEBSOCKET
# ============================================================================

SCHEMA_IDENTIFY = {
    "type": "object",
    "required": ["type", "client_id"],
    "properties": {
        "type": {"type": "string", "enum": ["identify"]},
        "client_id": {"type": "string", "minLength": 1},
        "profiles": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "dirId"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "dirId": {"type": "string", "minLength": 1}
                }
            }
        }
    }
}

SCHEMA_COMMAND = {
    "type": "object",
    "required": ["type", "data"],
    "properties": {
        "type": {"type": "string"},
        "data": {"type": "object"}
    }
}

def validar_json_schema(data, schema):
    """Valida datos contra un JSON Schema. Retorna (bool, error_msg)."""
    try:
        validate(instance=data, schema=schema)
        return True, None
    except ValidationError as e:
        return False, str(e.message)

# ============================================================================
# UTILIDADES DE VALIDACIÓN
# ============================================================================

def validar_url(url):
    """Valida que la URL sea válida y HTTPS o HTTP"""
    try:
        result = urlparse(url)
        if result.scheme not in ['http', 'https']:
            return False
        if not result.netloc:
            return False
        return True
    except Exception:
        return False

def generar_token():
    """Genera un token seguro de autenticación"""
    return secrets.token_urlsafe(32)

def verificar_token(token):
    """Verifica si el token es válido y no ha expirado"""
    if token not in tokens_autenticados:
        return None

    token_info = tokens_autenticados[token]
    if time.time() - token_info["tiempo"] > TOKEN_TIMEOUT:
        del tokens_autenticados[token]
        return None

    return token_info["cid"]

# ============================================================================
# JARVIS (IMPORTADO de jarvis_v61.py)
# ============================================================================

jarvis = Jarvis(os.path.join(BASE_DIR, "prompts"))

# ============================================================================
# FUNCIONES BASE
# ============================================================================

async def enviar(pcbot_id, cmd, data):
    """Envía un comando a un PCBOT específico"""
    try:
        async with lock_pcbots:
            if pcbot_id not in pcbots:
                logger.warning(f"PCBOT {pcbot_id} no conectado")
                return False
            ws = pcbots[pcbot_id]

        try:
            msg = json.dumps({"type": cmd, "data": data})
            await ws.send(msg)
            return True
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"PCBOT {pcbot_id} desconectado durante envío")
            async with lock_pcbots:
                pcbots.pop(pcbot_id, None)
            return False
    except json.JSONEncodeError as e:
        logger.error(f"JSON inválido en enviar: {cmd} - {e}")
        return False
    except Exception as e:
        logger.error(f"Fallo enviando a {pcbot_id}: {e}")
        return False

async def heartbeat(ws, cid, interval=30):
    """Envía ping periódicamente para mantener conexión viva"""
    try:
        while True:
            await asyncio.sleep(interval)
            try:
                await ws.ping()
            except websockets.exceptions.ConnectionClosed:
                logger.info(f"Heartbeat: Conexión cerrada: {cid}")
                break
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Heartbeat: Error: {e}")

async def manejar_conexion(ws):
    cid = None
    token = None
    heartbeat_task = None
    keys = []

    try:
        # Esperar handshake con timeout
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=30)
        except asyncio.TimeoutError:
            logger.error("Timeout en handshake - no recibió 'identify'")
            await ws.send(json.dumps({"type": "error", "data": "Timeout en handshake"}))
            return

        try:
            data = json.loads(msg)
        except json.JSONDecodeError as e:
            logger.error(f"JSON inválido en handshake: {e}")
            await ws.send(json.dumps({"type": "error", "data": "JSON inválido"}))
            return

        # Validar con JSON Schema
        valido, err = validar_json_schema(data, SCHEMA_IDENTIFY)
        if not valido:
            logger.error(f"Schema inválido en identify: {err}")
            await ws.send(json.dumps({"type": "error", "data": f"Schema inválido: {err}"}))
            return

        if data.get("type") != "identify":
            logger.error("Primer mensaje no es 'identify'")
            await ws.send(json.dumps({"type": "error", "data": "Se requiere 'identify' primero"}))
            return

        cid = data.get("client_id")

        # Generar token de autenticación
        token = generar_token()
        tokens_autenticados[token] = {"cid": cid, "tiempo": time.time()}

        perfiles = data.get("profiles", [])

        async with lock_pcbots:
            pcbots[cid] = ws

        async with lock_perfiles:
            for p in perfiles:
                key = f"{cid}|{p['name']}"
                perfiles_map[key] = {
                    "pcbot": cid,
                    "name": p["name"],
                    "dirId": p["dirId"]
                }

        logger.info(f"PCBOT conectado: {cid} | Perfiles: {len(perfiles)} | Token: {token[:8]}...")

        # Enviar confirmación con token
        await ws.send(json.dumps({"type": "connected", "data": {"token": token}}))

        # Iniciar heartbeat
        heartbeat_task = asyncio.create_task(heartbeat(ws, cid, interval=30))

        # Escuchar mensajes
        try:
            async for msg in ws:
                # Rate limiting
                if not await rate_limiter.consume(1):
                    logger.warning(f"Rate limit excedido para {cid}")
                    continue

                try:
                    msg_data = json.loads(msg)
                except json.JSONDecodeError:
                    logger.warning(f"Mensaje no-JSON de {cid}")
                    continue

                valido, err = validar_json_schema(msg_data, SCHEMA_COMMAND)
                if not valido:
                    logger.warning(f"Schema inválido de {cid}: {err}")
                    continue

                # Procesar mensajes del cliente (si es necesario)
                pass
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Conexión cerrada: {cid}")
        except Exception as e:
            logger.error(f"Error procesando mensajes de {cid}: {e}")

    except Exception as e:
        logger.error(f"Error en manejar_conexion: {e}")

    finally:
        # Limpiar heartbeat
        if heartbeat_task:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

        # Limpiar referencias del PCBOT
        if cid:
            async with lock_perfiles:
                keys = [k for k, v in list(perfiles_map.items()) if v["pcbot"] == cid]
                for k in keys:
                    del perfiles_map[k]

            async with lock_pcbots:
                pcbots.pop(cid, None)

            logger.info(f"PCBOT {cid} limpiado (perfiles eliminados: {len(keys)})")

        # Limpiar token
        if token and token in tokens_autenticados:
            del tokens_autenticados[token]

# ============================================================================
# TAREA: COMENTARIOS ÚNICOS POR PERFIL
# ============================================================================

async def tarea_enviar_comentarios():
    """Genera y envía un comentario ÚNICO por perfil, no el mismo para todos"""
    while True:
        try:
            async with lock_grupos:
                grupos_copy = list(grupos.items())

            for url, grupo in grupos_copy:
                if not grupo.get("comentarios", False):
                    continue

                # Para CADA perfil del grupo, generar un comentario DIFERENTE
                for perfil_key in grupo["perfiles"]:
                    async with lock_perfiles:
                        if perfil_key not in perfiles_map:
                            continue
                        info = perfiles_map[perfil_key]

                    # Generar comentario NUEVO para este perfil
                    comentario = jarvis.generar(url)

                    if comentario:
                        await enviar(info["pcbot"], "comment", {
                            "profile": info["name"],
                            "dirId": info["dirId"],
                            "text": comentario,
                            "url": url
                        })
                        logger.info(f"JARVIS: {comentario} -> {perfil_key}")

                    # Pausa entre comentarios de diferentes perfiles
                    await asyncio.sleep(random.randint(5, 10))

            # Pausa entre ciclos completos (15-25 segundos)
            await asyncio.sleep(random.randint(15, 25))
        except Exception as e:
            logger.error(f"Error en tarea_comentarios: {e}")
            await asyncio.sleep(5)

# ============================================================================
# TAREA: LIMPIAR GRUPOS EXPIRADOS POR TIMEOUT
# ============================================================================

async def limpiar_grupos_expirados():
    """Libera perfiles de grupos que han superado su duración"""
    while True:
        try:
            await asyncio.sleep(300)  # Verificar cada 5 minutos

            ahora = time.time()
            async with lock_grupos:
                urls_expiradas = []
                for url, grupo in list(grupos.items()):
                    duracion_minutos = (ahora - grupo.get("inicio", 0)) / 60
                    duracion_max = grupo.get("duracion", 999)

                    if duracion_minutos > duracion_max:
                        urls_expiradas.append(url)

                for url in urls_expiradas:
                    await ejecutar_detener(url)
                    logger.info(f"TIMEOUT: Grupo {url} liberado automáticamente")

        except Exception as e:
            logger.error(f"Error en limpieza de grupos: {e}")

# ============================================================================
# COMANDOS
# ============================================================================

async def ejecutar_asignar(cant, url, dur):
    """Asigna perfiles a una URL específica"""
    if not validar_url(url):
        logger.error(f"URL inválida: {url}")
        return

    async with lock_perfiles:
        ocupados = set()
        async with lock_grupos:
            for g in grupos.values():
                ocupados.update(g["perfiles"])

        libres = [k for k in perfiles_map.keys() if k not in ocupados]

    if len(libres) < cant:
        logger.warning(f"Solo {len(libres)} perfiles libres, se requieren {cant}")
        return

    sel = libres[:cant]

    async with lock_grupos:
        if url not in grupos:
            grupos[url] = {
                "perfiles": [],
                "comentarios": False,
                "inicio": time.time(),
                "duracion": dur
            }

        for key in sel:
            grupos[url]["perfiles"].append(key)

            async with lock_perfiles:
                info = perfiles_map[key]

            await enviar(info["pcbot"], "open_url", {
                "url": url,
                "profile": info["name"],
                "dirId": info["dirId"]
            })
            logger.info(f"  Abriendo {key} en {url}")
            await asyncio.sleep(2)

    logger.info(f"Asignados {cant} perfiles a {url} por {dur} minutos")

async def ejecutar_comentarios_activar(url, nivel):
    """Activa generación de comentarios para un grupo"""
    if not validar_url(url):
        logger.error(f"URL inválida: {url}")
        return

    async with lock_grupos:
        if url in grupos:
            grupos[url]["comentarios"] = True
            logger.info(f"Comentarios activados para {url} (nivel {nivel})")
        else:
            logger.error(f"Grupo no encontrado: {url}")

async def ejecutar_comentarios_desactivar(url):
    """Desactiva generación de comentarios para un grupo"""
    if not validar_url(url):
        logger.error(f"URL inválida: {url}")
        return

    async with lock_grupos:
        if url in grupos:
            grupos[url]["comentarios"] = False
            logger.info(f"Comentarios desactivados para {url}")
        else:
            logger.error(f"Grupo no encontrado: {url}")

async def ejecutar_detener(url):
    """Detiene un grupo y libera sus perfiles"""
    async with lock_grupos:
        if url in grupos:
            perfiles_liberados = len(grupos[url]["perfiles"])
            del grupos[url]
            logger.info(f"Grupo detenido: {url} ({perfiles_liberados} perfiles liberados)")
        else:
            logger.error(f"Grupo no encontrado: {url}")

# ============================================================================
# CONSOLA ADMIN
# ============================================================================

# ============================================================================
# PROCESADOR DE COMANDOS ADMIN (compartido por consola y TCP)
# ============================================================================

def procesar_comando_admin(cmd_str, writer=None):
    """Procesa un comando admin y devuelve la respuesta como string."""
    cmd = cmd_str.strip().split()
    if not cmd:
        return ""

    def send(msg):
        if writer:
            writer.write((msg + "\n").encode())
        else:
            print(msg)

    if cmd[0] == "perfiles":
        async def _perfiles():
            async with lock_perfiles:
                total = len(perfiles_map)
                ocupados = set()
                async with lock_grupos:
                    for g in grupos.values():
                        ocupados.update(g["perfiles"])

                send(f"\n[PERFILES] Total: {total}")
                keys_list = list(perfiles_map.keys())[:20]
                for key in keys_list:
                    estado_ = "OCUPADO" if key in ocupados else "LIBRE"
                    send(f"  {key} : {estado_}")

        asyncio.run_coroutine_threadsafe(_perfiles(), loop)
        return "Consultando perfiles..."

    elif cmd[0] == "asignar":
        try:
            cant = int(cmd[1])
            url = cmd[3]
            dur = int(cmd[5])
            asyncio.run_coroutine_threadsafe(ejecutar_asignar(cant, url, dur), loop)
            return f"Asignando {cant} perfil(es) a {url} por {dur} min..."
        except (IndexError, ValueError):
            return "Uso: asignar <cant> url <URL> duracion <min>"

    elif cmd[0] == "comentarios_activar":
        try:
            url = cmd[2]
            nivel = cmd[4] if len(cmd) > 4 else "medio"
            asyncio.run_coroutine_threadsafe(ejecutar_comentarios_activar(url, nivel), loop)
            return f"Comentarios activados para {url} (nivel {nivel})"
        except (IndexError, ValueError):
            return "Uso: comentarios_activar url <URL> nivel <bajo/medio/alto>"

    elif cmd[0] == "comentarios_desactivar":
        try:
            url = cmd[2]
            asyncio.run_coroutine_threadsafe(ejecutar_comentarios_desactivar(url), loop)
            return f"Comentarios desactivados para {url}"
        except (IndexError, ValueError):
            return "Uso: comentarios_desactivar url <URL>"

    elif cmd[0] == "detener":
        try:
            url = cmd[2]
            asyncio.run_coroutine_threadsafe(ejecutar_detener(url), loop)
            return f"Deteniendo grupo en {url}"
        except (IndexError, ValueError):
            return "Uso: detener url <URL>"

    elif cmd[0] == "estado":
        async def _estado():
            async with lock_perfiles:
                total = len(perfiles_map)

            async with lock_pcbots:
                pcbots_conectados = len(pcbots)

            async with lock_grupos:
                ocupados = sum(len(g.get("perfiles", [])) for g in grupos.values())
                grupos_activos = len(grupos)

            lines = []
            lines.append(f"[ESTADO]")
            lines.append(f"  Servidor: {IP}:{PUERTO}")
            lines.append(f"  PCBOTs conectados: {pcbots_conectados}")
            lines.append(f"  Perfiles totales: {total}")
            lines.append(f"  Perfiles ocupados: {ocupados}")
            lines.append(f"  Perfiles libres: {total - ocupados}")
            lines.append(f"  Grupos activos: {grupos_activos}")
            lines.append(f"  JARVIS comentarios generados: {jarvis.get_stats()['generados']}")
            lines.append(f"  Sesiones autenticadas: {len(tokens_autenticados)}")
            send("\n".join(lines))

        asyncio.run_coroutine_threadsafe(_estado(), loop)
        return "OK"

    elif cmd[0] == "salir":
        return "__EXIT__"

    else:
        return "Comando no reconocido. Comandos: perfiles, asignar, estado, comentarios_activar, comentarios_desactivar, detener, salir"


# ============================================================================
# LISTENER TCP PARA ADMINISTRACIÓN REMOTA (puerto 5007)
# ============================================================================

TCP_ADMIN_PORT = 5007

async def tcp_admin_listener():
    """Servidor TCP para comandos admin (usado por SSH + nc)."""
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(("0.0.0.0", TCP_ADMIN_PORT))
    server_sock.listen(5)
    server_sock.setblocking(False)
    logger.info(f"ADMIN TCP activo en puerto {TCP_ADMIN_PORT} (usa: echo comando | nc {IP} {TCP_ADMIN_PORT})")

    loop_local = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=4)

    while True:
        client, addr = await loop_local.sock_accept(server_sock)
        logger.info(f"Admin TCP conectado: {addr}")

        async def handle_client(cli_sock, cli_addr):
            try:
                cli_sock.setblocking(False)
                data = b""
                while True:
                    try:
                        chunk = await loop_local.sock_recv(cli_sock, 4096)
                        if not chunk:
                            break
                        data += chunk
                        if b"\n" in data:
                            break
                    except:
                        break

                cmd_str = data.decode("utf-8", errors="replace").strip()
                if cmd_str:
                    future = loop_local.run_in_executor(executor, procesar_comando_admin, cmd_str, None)
                    respuesta = await future
                    if respuesta:
                        try:
                            await loop_local.sock_sendall(cli_sock, (respuesta + "\n").encode())
                        except:
                            pass

                    # Después de estado, esperar un poco para que se ejecute
                    await asyncio.sleep(0.3)

                    # Reconsultar estado si era comando estado
                    if cmd_str == "estado":
                        async def reconsulta():
                            async with lock_perfiles:
                                total = len(perfiles_map)
                            async with lock_pcbots:
                                pcbots_conectados = len(pcbots)
                            async with lock_grupos:
                                ocupados = sum(len(g.get("perfiles", [])) for g in grupos.values())
                                grupos_activos = len(grupos)

                            lines = [
                                f"  Servidor: {IP}:{PUERTO}",
                                f"  PCBOTs conectados: {pcbots_conectados}",
                                f"  Perfiles totales: {total}",
                                f"  Perfiles ocupados: {ocupados}",
                                f"  Perfiles libres: {total - ocupados}",
                                f"  Grupos activos: {grupos_activos}",
                                f"  JARVIS: {jarvis.get_stats()['generados']} generados",
                                f"  Sesiones: {len(tokens_autenticados)}",
                            ]
                            try:
                                await loop_local.sock_sendall(cli_sock, ("\n".join(lines) + "\n").encode())
                            except:
                                pass

                        await reconsulta()

                    if cmd_str == "salir":
                        os._exit(0)

            except Exception as e:
                logger.error(f"TCP admin error: {e}")
            finally:
                try:
                    cli_sock.close()
                except:
                    pass

        asyncio.create_task(handle_client(client, addr))


# ============================================================================
# CONSOLA ADMIN LOCAL (opcional, solo si hay TTY)
# ============================================================================

def admin_console():
    logger.info("=" * 60)
    logger.info("  ROXYMASTER v6.1 - CONSOLA ADMIN (opcional)")
    logger.info("=" * 60)

    try:
        print("\n" + "=" * 60)
        print("  ROXYMASTER v6.1 - CONSOLA ADMIN")
        print("=" * 60)
        print("  COMANDOS: perfiles | asignar | estado | comentarios_activar")
        print("            comentarios_desactivar | detener | salir")
        print("-" * 60)

        while True:
            try:
                cmd = input("\n[ADMIN] > ").strip()
                if not cmd:
                    continue
                respuesta = procesar_comando_admin(cmd, writer=None)
                if respuesta == "__EXIT__":
                    print("Deteniendo servidor...")
                    os._exit(0)
                elif respuesta:
                    print(respuesta)
            except EOFError:
                logger.info("Consola admin omitida (sin TTY/STDIN)")
                return
    except Exception as e:
        logger.info(f"Consola admin omitida: {e}")

# ============================================================================
# MAIN
# ============================================================================

async def main():
    global loop
    loop = asyncio.get_event_loop()

    # Iniciar tareas de fondo
    asyncio.create_task(tarea_enviar_comentarios())
    asyncio.create_task(limpiar_grupos_expirados())

    # Iniciar consola admin en thread separado (sobrevive sin TTY)
    threading.Thread(target=admin_console, daemon=True).start()

    # Iniciar listener TCP para admin remoto
    asyncio.create_task(tcp_admin_listener())

    logger.info(f"SERVIDOR ACTIVO en {IP}:{PUERTO}")
    logger.info(f"ADMIN TCP: echo comando | nc {IP} {TCP_ADMIN_PORT}")
    logger.info(f"Versión: 6.2 (v61 + TCP admin + sin TTY)")
    logger.info("-" * 50)

    async with websockets.serve(manejar_conexion, IP, PUERTO):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())