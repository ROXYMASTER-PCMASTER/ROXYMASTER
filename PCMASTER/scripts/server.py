import os
import sys
import json
import asyncio
import websockets
import time
import random
import requests
import logging
import secrets
from datetime import datetime, timedelta
from collections import deque
from urllib.parse import urlparse
import jsonschema

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.environ["USERPROFILE"], "Desktop", "ROXYMASTER", "PCMASTER", "server.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.join(os.environ["USERPROFILE"], "Desktop", "ROXYMASTER", "PCMASTER")

# Cargar configuración de forma segura
def cargar_config():
    try:
        with open(os.path.join(BASE_DIR, "config.json"), "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error cargando config.json: {e}")
        return {"server": {"ws_port": 5006, "ip_servidor": "0.0.0.0"}}

config = cargar_config()
PUERTO = config.get("server", {}).get("ws_port", 5006)
IP = config.get("server", {}).get("ip_servidor", "0.0.0.0")

# Estado global con locks asyncio (no threading)
pcbots = {}
perfiles_map = {}
grupos = {}
lock_perfiles = asyncio.Lock()
lock_grupos = asyncio.Lock()
lock_pcbots = asyncio.Lock()

# Tokens con expiración automática
tokens_autenticados = {}
TOKEN_TIMEOUT = 1800  # 30 minutos
RECONEXION_BACKOFF_MIN = 2
RECONEXION_BACKOFF_MAX = 32

# Rate limiting con token bucket
class TokenBucket:
    def __init__(self, capacity=100, refill_rate=10):
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()
    
    def consume(self, tokens=1):
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

rate_limiters = {}

# ============================================================================
# VALIDACIÓN DE ENTRADA (CRÍTICA)
# ============================================================================

SCHEMA_IDENTIFY = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": ["identify"]},
        "client_id": {"type": "string", "minLength": 1, "maxLength": 255},
        "profiles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "minLength": 1, "maxLength": 255},
                    "dirId": {"type": "string", "minLength": 1, "maxLength": 255}
                },
                "required": ["name", "dirId"]
            }
        }
    },
    "required": ["type", "client_id"]
}

def validar_url(url):
    """Valida URL y previene inyección"""
    try:
        if not isinstance(url, str):
            return False
        if len(url) > 2048:
            return False
        result = urlparse(url)
        if result.scheme not in ['http', 'https']:
            return False
        if not result.netloc:
            return False
        return True
    except Exception:
        return False

def validar_handshake(data):
    """Valida schema de handshake"""
    try:
        jsonschema.validate(instance=data, schema=SCHEMA_IDENTIFY)
        return True
    except jsonschema.ValidationError as e:
        logger.warning(f"Validación fallida: {e.message}")
        return False

def generar_token():
    """Token seguro con alta entropía"""
    return secrets.token_urlsafe(32)

def verificar_token(token):
    """Verifica y renueva token si es válido"""
    try:
        if not isinstance(token, str) or len(token) < 10:
            return None
        
        if token not in tokens_autenticados:
            return None
        
        token_info = tokens_autenticados[token]
        edad = time.time() - token_info["tiempo"]
        
        if edad > TOKEN_TIMEOUT:
            del tokens_autenticados[token]
            return None
        
        # Renovar tiempo de vida
        token_info["tiempo"] = time.time()
        return token_info["cid"]
    except Exception as e:
        logger.error(f"Error verificando token: {e}")
        return None

# ============================================================================
# HEARTBEAT CON EXCEPCIONES ESPECÍFICAS
# ============================================================================

async def heartbeat(ws, cid, interval=30):
    """Heartbeat robusto con manejo de excepciones específicas"""
    intento_fallido = 0
    
    try:
        while True:
            await asyncio.sleep(interval)
            try:
                await ws.ping()
                intento_fallido = 0
            except websockets.exceptions.ConnectionClosed:
                logger.info(f"[HEARTBEAT] Conexión cerrada: {cid}")
                break
            except asyncio.TimeoutError:
                intento_fallido += 1
                logger.warning(f"[HEARTBEAT] Timeout en {cid} ({intento_fallido})")
                if intento_fallido > 3:
                    break
            except Exception as e:
                logger.error(f"[HEARTBEAT] Error inesperado en {cid}: {type(e).__name__} - {e}")
                break
    except asyncio.CancelledError:
        logger.debug(f"[HEARTBEAT] Cancelado para {cid}")
    except Exception as e:
        logger.error(f"[HEARTBEAT] Error crítico: {e}")

# ============================================================================
# RECONEXIÓN CON BACKOFF EXPONENCIAL
# ============================================================================

async def enviar_con_retry(pcbot_id, cmd, data, max_intentos=3):
    """Envía mensaje con reintentos"""
    for intento in range(max_intentos):
        try:
            async with lock_pcbots:
                if pcbot_id not in pcbots:
                    logger.warning(f"PCBOT {pcbot_id} no encontrado")
                    return False
                ws = pcbots[pcbot_id]
            
            try:
                msg = json.dumps({"type": cmd, "data": data})
                await ws.send(msg)
                return True
            except websockets.exceptions.ConnectionClosed:
                logger.error(f"Conexión cerrada para {pcbot_id}")
                async with lock_pcbots:
                    pcbots.pop(pcbot_id, None)
                return False
            except json.JSONEncodeError as e:
                logger.error(f"JSON inválido: {cmd} - {e}")
                return False
            except Exception as e:
                logger.error(f"Error enviando: {type(e).__name__} - {e}")
                if intento < max_intentos - 1:
                    await asyncio.sleep(0.5 * (2 ** intento))
                    continue
                return False
        
        except Exception as e:
            logger.error(f"Error crítico en enviar_con_retry: {e}")
            return False
    
    return False

# ============================================================================
# MANEJO DE CONEXIÓN (MEJORADO)
# ============================================================================

async def manejar_conexion(ws, path):
    """Manejo robusto de conexiones con validación completa"""
    cid = None
    token = None
    heartbeat_task = None
    
    try:
        # Handshake con timeout y validación
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=30)
        except asyncio.TimeoutError:
            logger.error("Timeout en handshake")
            try:
                await ws.send(json.dumps({"type": "error", "data": "Timeout en handshake"}))
            except:
                pass
            return
        except websockets.exceptions.ConnectionClosed:
            logger.debug("Conexión cerrada antes de handshake")
            return
        except Exception as e:
            logger.error(f"Error recibiendo handshake: {type(e).__name__} - {e}")
            return
        
        # Validar JSON
        try:
            data = json.loads(msg)
        except json.JSONDecodeError as e:
            logger.error(f"JSON inválido en handshake: {e}")
            try:
                await ws.send(json.dumps({"type": "error", "data": "JSON inválido"}))
            except:
                pass
            return
        
        # Validar schema
        if not validar_handshake(data):
            logger.error("Handshake no cumple schema")
            try:
                await ws.send(json.dumps({"type": "error", "data": "Schema inválido"}))
            except:
                pass
            return
        
        cid = data["client_id"]
        perfiles = data.get("profiles", [])
        
        # Generar token
        token = generar_token()
        tokens_autenticados[token] = {"cid": cid, "tiempo": time.time()}
        
        # Registrar PCBOT
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
        
        logger.info(f"[+] PCBOT conectado: {cid} | Perfiles: {len(perfiles)}")
        
        # Rate limiter para este cliente
        rate_limiters[cid] = TokenBucket(capacity=100, refill_rate=10)
        
        # Enviar confirmación
        try:
            await ws.send(json.dumps({"type": "connected", "data": {"token": token}}))
        except Exception as e:
            logger.error(f"Error enviando confirmación: {e}")
            return
        
        # Iniciar heartbeat
        heartbeat_task = asyncio.create_task(heartbeat(ws, cid, interval=30))
        
        # Escuchar mensajes
        try:
            async for msg in ws:
                try:
                    # Rate limiting
                    if cid in rate_limiters:
                        if not rate_limiters[cid].consume(1):
                            logger.warning(f"Rate limit excedido para {cid}")
                            continue
                    
                    # Procesar mensajes
                    data = json.loads(msg)
                    msg_type = data.get("type", "")
                    
                    if msg_type == "pong":
                        logger.debug(f"Pong recibido de {cid}")
                    elif msg_type == "heartbeat":
                        logger.debug(f"Heartbeat recibido de {cid}")
                except json.JSONDecodeError:
                    logger.debug(f"Mensaje no-JSON de {cid}")
                except Exception as e:
                    logger.error(f"Error procesando mensaje: {type(e).__name__} - {e}")
        
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"[-] Conexión cerrada: {cid}")
        except Exception as e:
            logger.error(f"Error en loop de mensajes: {type(e).__name__} - {e}")
    
    except Exception as e:
        logger.error(f"Error en manejar_conexion: {type(e).__name__} - {e}")
    
    finally:
        # Limpiar heartbeat
        if heartbeat_task:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                logger.debug(f"Heartbeat cancelado para {cid}")
            except Exception as e:
                logger.error(f"Error cancelando heartbeat: {e}")
        
        # Limpiar PCBOT
        if cid:
            try:
                async with lock_perfiles:
                    keys = [k for k, v in list(perfiles_map.items()) if v["pcbot"] == cid]
                    for k in keys:
                        del perfiles_map[k]
                
                async with lock_pcbots:
                    pcbots.pop(cid, None)
                
                if cid in rate_limiters:
                    del rate_limiters[cid]
                
                logger.info(f"[-] PCBOT limpiado: {cid} (perfiles: {len(keys)})")
            except Exception as e:
                logger.error(f"Error en cleanup: {e}")
        
        # Limpiar token
        if token and token in tokens_autenticados:
            del tokens_autenticados[token]

# ============================================================================
# TAREA: ENVIAR COMENTARIOS ÚNICOS
# ============================================================================

async def tarea_enviar_comentarios():
    """Genera comentarios únicos por perfil"""
    while True:
        try:
            await asyncio.sleep(random.randint(15, 25))
            
            async with lock_grupos:
                grupos_copy = list(grupos.items())
            
            for url, grupo in grupos_copy:
                if not grupo.get("comentarios", False):
                    continue
                
                for perfil_key in grupo.get("perfiles", []):
                    try:
                        async with lock_perfiles:
                            if perfil_key not in perfiles_map:
                                continue
                            info = perfiles_map[perfil_key]
                        
                        # Enviar comentario (simulado sin Ollama por defecto)
                        comentario = f"Comentario único para {perfil_key}"
                        await enviar_con_retry(info["pcbot"], "comment", {
                            "profile": info["name"],
                            "dirId": info["dirId"],
                            "text": comentario,
                            "url": url
                        })
                        
                        await asyncio.sleep(random.randint(5, 10))
                    except Exception as e:
                        logger.error(f"Error enviando comentario: {e}")
        
        except asyncio.CancelledError:
            logger.info("Tarea de comentarios cancelada")
            break
        except Exception as e:
            logger.error(f"Error en tarea_comentarios: {type(e).__name__} - {e}")
            await asyncio.sleep(5)

# ============================================================================
# TAREA: LIMPIAR GRUPOS EXPIRADOS
# ============================================================================

async def limpiar_grupos_expirados():
    """Libera perfiles después de timeout"""
    while True:
        try:
            await asyncio.sleep(300)
            
            ahora = time.time()
            async with lock_grupos:
                urls_expiradas = []
                for url, grupo in list(grupos.items()):
                    duracion_seg = ahora - grupo.get("inicio", 0)
                    duracion_max_seg = grupo.get("duracion", 999) * 60
                    
                    if duracion_seg > duracion_max_seg:
                        urls_expiradas.append(url)
                
                for url in urls_expiradas:
                    if url in grupos:
                        del grupos[url]
                        logger.info(f"Grupo expirado liberado: {url}")
        
        except asyncio.CancelledError:
            logger.info("Limpieza de grupos cancelada")
            break
        except Exception as e:
            logger.error(f"Error limpiando grupos: {type(e).__name__} - {e}")

# ============================================================================
# INICIO DEL SERVIDOR
# ============================================================================

async def main():
    """Función principal del servidor"""
    logger.info("=" * 60)
    logger.info("ROXYMASTER v6.1 - SERVIDOR MEJORADO")
    logger.info("=" * 60)
    logger.info(f"Escuchando en {IP}:{PUERTO}")
    
    # Crear tareas de background
    comentarios_task = asyncio.create_task(tarea_enviar_comentarios())
    limpieza_task = asyncio.create_task(limpiar_grupos_expirados())
    
    # Iniciar servidor WebSocket
    async with websockets.serve(manejar_conexion, IP, PUERTO):
        logger.info("Servidor WebSocket iniciado")
        try:
            await asyncio.Future()
        except KeyboardInterrupt:
            logger.info("Servidor interrumpido por usuario")
        finally:
            comentarios_task.cancel()
            limpieza_task.cancel()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Error fatal: {e}")
        sys.exit(1)
