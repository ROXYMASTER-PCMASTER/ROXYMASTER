import os
import sys
import json
import asyncio
import websockets
import requests
import time
import random
import logging
from datetime import datetime
from urllib.parse import urlparse
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.environ["USERPROFILE"], "Desktop", "ROXYMASTER", "PCBOT", "pcbot.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.join(os.environ["USERPROFILE"], "Desktop", "ROXYMASTER", "PCBOT")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

perfiles_abiertos = {}
clientes_ui = set()

# ============================================================================
# CONFIGURACIÓN Y VALIDACIÓN
# ============================================================================

def cargar_config():
    """Carga configuración de forma segura"""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error cargando config: {e}")
        return {}

def validar_url(url):
    """Valida URL antes de navegar"""
    try:
        if not isinstance(url, str) or len(url) > 2048:
            return False
        result = urlparse(url)
        if result.scheme not in ['http', 'https']:
            return False
        if not result.netloc:
            return False
        return True
    except Exception as e:
        logger.error(f"Error validando URL: {e}")
        return False

def sanitizar_comentario(texto, max_length=60):
    """Sanitiza comentario para evitar inyecciones"""
    try:
        if not isinstance(texto, str):
            return ""
        texto = ''.join(c for c in texto if ord(c) >= 32)
        return texto[:max_length]
    except Exception as e:
        logger.error(f"Error sanitizando comentario: {e}")
        return ""

# ============================================================================
# FUNCIONES ROXY API
# ============================================================================

async def get_workspace(api_url, token):
    """Obtiene workspace ID"""
    try:
        r = requests.get(f"{api_url}/browser/workspace", headers={"token": token}, timeout=30)
        if r.status_code == 200:
            data = r.json()
            if data.get("code") == 0:
                rows = data.get("data", {}).get("rows", [])
                if rows:
                    return rows[0].get("id")
        logger.warning(f"No workspace encontrado")
    except requests.exceptions.Timeout:
        logger.error("Timeout obteniendo workspace")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error en API workspace: {type(e).__name__}")
    except Exception as e:
        logger.error(f"Error inesperado en get_workspace: {e}")
    
    return "94706"

async def get_perfiles(api_url, token, ws_id):
    """Obtiene perfiles disponibles"""
    perfiles = []
    try:
        r = requests.get(f"{api_url}/browser/list_v3?workspaceId={ws_id}", headers={"token": token}, timeout=30)
        if r.status_code == 200:
            data = r.json()
            if data.get("code") == 0:
                for p in data.get("data", {}).get("rows", []):
                    nombre = p.get("windowName", "")
                    dir_id = p.get("dirId", "")
                    if nombre and dir_id:
                        perfiles.append({"name": nombre, "dirId": dir_id})
                        logger.info(f"[PERFIL DETECTADO] {nombre}")
        logger.info(f"Total de perfiles: {len(perfiles)}")
    except requests.exceptions.Timeout:
        logger.error("Timeout obteniendo perfiles")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error en API perfiles: {type(e).__name__}")
    except Exception as e:
        logger.error(f"Error inesperado en get_perfiles: {e}")
    
    return perfiles

# ============================================================================
# UI WEBSOCKET
# ============================================================================

async def enviar_a_ui(mensaje):
    """Envía mensaje a interfaces UI conectadas"""
    clientes_desconectados = set()
    
    for ws in list(clientes_ui):
        try:
            await ws.send(json.dumps(mensaje))
        except websockets.exceptions.ConnectionClosed:
            clientes_desconectados.add(ws)
        except Exception as e:
            logger.error(f"Error enviando a UI: {type(e).__name__}")
            clientes_desconectados.add(ws)
    
    for ws in clientes_desconectados:
        clientes_ui.discard(ws)

async def manejar_ui(websocket, path):
    """Maneja conexiones de la interfaz UI local"""
    clientes_ui.add(websocket)
    logger.info("Cliente UI conectado")
    
    try:
        async for mensaje in websocket:
            try:
                data = json.loads(mensaje)
                if data.get("type") == "get_status":
                    await websocket.send(json.dumps({
                        "type": "status",
                        "perfiles": list(perfiles_abiertos.keys()),
                        "estado": "conectado"
                    }))
            except json.JSONDecodeError:
                logger.warning("Mensaje JSON inválido de UI")
            except Exception as e:
                logger.error(f"Error procesando mensaje UI: {type(e).__name__}")
    
    except websockets.exceptions.ConnectionClosed:
        logger.info("Cliente UI desconectado")
    except Exception as e:
        logger.error(f"Error en manejar_ui: {type(e).__name__}")
    
    finally:
        clientes_ui.discard(websocket)

# ============================================================================
# PLAYWRIGHT - INYECCIÓN DE COMENTARIOS
# ============================================================================

async def inyectar_comentario(page, comentario):
    """Inyecta comentario en página"""
    try:
        comentario = sanitizar_comentario(comentario)
        if not comentario:
            logger.warning("Comentario vacío después de sanitización")
            return False
        
        await page.wait_for_timeout(2000)
        
        selectores = [
            'textarea[placeholder*="Message"]',
            'textarea[placeholder*="message"]',
            'div[role="textbox"][contenteditable="true"]',
            '.chat-input'
        ]
        
        for selector in selectores:
            try:
                count = await page.locator(selector).count()
                if count > 0:
                    await page.click(selector)
                    await page.fill(selector, "")
                    await page.type(selector, comentario, delay=random.uniform(30, 100))
                    await page.keyboard.press("Enter")
                    logger.info(f"Comentario enviado: {comentario[:40]}")
                    return True
            except Exception as e:
                logger.debug(f"Selector no encontrado: {selector} - {type(e).__name__}")
                continue
        
        logger.warning("No se encontró selector de chat")
        return False
    
    except PlaywrightTimeoutError:
        logger.error("Timeout esperando elemento para comentario")
        return False
    except Exception as e:
        logger.error(f"Error inyectando comentario: {type(e).__name__} - {e}")
        return False

async def abrir_url(page, url):
    """Abre URL con timeout"""
    try:
        if not validar_url(url):
            logger.error(f"URL inválida: {url}")
            return False
        
        logger.info(f"Navegando a: {url}")
        await page.goto(url, timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        logger.info(f"URL cargada exitosamente: {url}")
        return True
    
    except PlaywrightTimeoutError:
        logger.error(f"Timeout cargando URL: {url}")
        return False
    except Exception as e:
        logger.error(f"Error cargando URL: {type(e).__name__} - {e}")
        return False

async def limpiar_perfil(dir_id):
    """Limpia perfil abierto"""
    try:
        if dir_id not in perfiles_abiertos:
            return
        
        data = perfiles_abiertos[dir_id]
        browser = data.get("browser")
        
        if browser:
            try:
                await browser.close()
                logger.info(f"Browser cerrado para perfil: {dir_id}")
            except Exception as e:
                logger.error(f"Error cerrando browser: {type(e).__name__}")
        
        del perfiles_abiertos[dir_id]
    
    except Exception as e:
        logger.error(f"Error limpiando perfil: {type(e).__name__} - {e}")

async def abrir_o_reutilizar_perfil(api_url, token, ws_id, dir_id, url="", comentario=""):
    """Abre o reutiliza perfil"""
    try:
        # Intentar reutilizar perfil existente
        if dir_id in perfiles_abiertos:
            data = perfiles_abiertos[dir_id]
            page = data.get("page")
            
            if page:
                try:
                    await page.evaluate("1")
                    logger.info("Reutilizando perfil existente")
                    
                    if url:
                        await abrir_url(page, url)
                    if comentario:
                        await inyectar_comentario(page, comentario)
                    
                    return True
                except Exception as e:
                    logger.warning(f"Conexión perdida con perfil: {type(e).__name__}")
                    await limpiar_perfil(dir_id)
        
        # Abrir nuevo perfil
        logger.info(f"Abriendo nuevo perfil: {dir_id}")
        
        try:
            r = requests.post(
                f"{api_url}/browser/open",
                headers={"token": token, "Content-Type": "application/json"},
                json={"workspaceId": ws_id, "dirId": dir_id, "args": []},
                timeout=60
            )
            
            if r.status_code != 200:
                logger.error(f"Error HTTP en API: {r.status_code}")
                return False
            
            data = r.json()
            if data.get("code") != 0:
                logger.error(f"Error API: {data.get('msg')}")
                return False
            
            ws_endpoint = data.get("data", {}).get("ws")
            if not ws_endpoint:
                logger.error("No WebSocket endpoint en respuesta")
                return False
            
            logger.info(f"Conectando a CDP...")
            
            # Reutilizar playwright como variable de módulo en vez de context manager
            # para mantener el navegador vivo entre llamadas
            global playwright_inst
            try:
                browser = await playwright_inst.chromium.connect_over_cdp(ws_endpoint, timeout=30000)
                
                if not browser or not browser.contexts or not browser.contexts[0].pages:
                    logger.error("Browser o page no disponible")
                    return False
                
                page = browser.contexts[0].pages[0]
                perfiles_abiertos[dir_id] = {"browser": browser, "page": page}
                
                if url:
                    await abrir_url(page, url)
                
                if comentario:
                    await inyectar_comentario(page, comentario)
                
                logger.info(f"Perfil listo: {dir_id}")
                return True
            
            except PlaywrightTimeoutError:
                logger.error(f"Timeout conectando a CDP")
                return False
            except Exception as e:
                logger.error(f"Error con Playwright: {type(e).__name__} - {e}")
                return False
        
        except requests.exceptions.Timeout:
            logger.error("Timeout en API de Roxy")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Error en API de Roxy: {type(e).__name__}")
            return False
        except Exception as e:
            logger.error(f"Error inesperado: {type(e).__name__} - {e}")
            return False
    
    except Exception as e:
        logger.error(f"Error en abrir_o_reutilizar_perfil: {type(e).__name__} - {e}")
        return False

# ============================================================================
# CLIENTE PCBOT CON RECONEXIÓN EXPONENCIAL
# ============================================================================

class PCBOTClient:
    RECONEXION_BACKOFF_MIN = 2
    RECONEXION_BACKOFF_MAX = 32
    
    def __init__(self):
        cfg = cargar_config()
        self.ip = cfg.get("pcmaster_ip", "100.111.179.65")
        self.port = cfg.get("pcmaster_port", 5006)
        self.client_id = os.environ.get("COMPUTERNAME", "pcbot-default")
        
        api = cfg.get("roxy_api", {})
        self.api_url = api.get("url", "http://127.0.0.1:50000")
        self.token = api.get("token", "")
        
        self.ws_id = None
        self.perfiles = []
        self.reconexion_intento = 0
        
        logger.info(f"PCBOT inicializado: {self.client_id}")
    
    async def inicializar(self):
        """Inicializa cliente obteniendo perfiles"""
        try:
            logger.info(f"Conectando a API en {self.api_url}")
            self.ws_id = await get_workspace(self.api_url, self.token)
            self.perfiles = await get_perfiles(self.api_url, self.token, self.ws_id)
            logger.info(f"Total perfiles disponibles: {len(self.perfiles)}")
        except Exception as e:
            logger.error(f"Error en inicialización: {type(e).__name__} - {e}")
    
    async def conectar_pcmaster(self):
        """Conecta a PCMASTER con backoff exponencial"""
        while True:
            try:
                backoff = min(
                    self.RECONEXION_BACKOFF_MIN * (2 ** self.reconexion_intento),
                    self.RECONEXION_BACKOFF_MAX
                )
                
                if self.reconexion_intento > 0:
                    logger.info(f"Reintentando en {backoff} segundos...")
                    await asyncio.sleep(backoff)
                
                uri = f"ws://{self.ip}:{self.port}"
                logger.info(f"Conectando a PCMASTER en {uri}")
                
                async with websockets.connect(uri, timeout=10) as ws:
                    self.reconexion_intento = 0
                    logger.info(f"[PCBOT] Conectado a PCMASTER")
                    
                    # Enviar identificación
                    try:
                        await ws.send(json.dumps({
                            "type": "identify",
                            "client_id": self.client_id,
                            "profiles": self.perfiles
                        }))
                    except Exception as e:
                        logger.error(f"Error enviando identify: {type(e).__name__}")
                        continue
                    
                    # Escuchar comandos
                    try:
                        async for msg in ws:
                            try:
                                data = json.loads(msg)
                                await self.procesar_comando(data)
                            except json.JSONDecodeError:
                                logger.warning("Mensaje no-JSON recibido")
                            except Exception as e:
                                logger.error(f"Error procesando comando: {type(e).__name__}")
                    
                    except websockets.exceptions.ConnectionClosed:
                        logger.info("Conexión cerrada por servidor")
                        self.reconexion_intento += 1
                    except asyncio.TimeoutError:
                        logger.error("Timeout en conexión")
                        self.reconexion_intento += 1
            
            except (websockets.exceptions.WebSocketException, asyncio.TimeoutError) as e:
                self.reconexion_intento += 1
                logger.error(f"Error conexión: {type(e).__name__} (intento {self.reconexion_intento})")
                # Reconexión infinita — sin límite
            
            except Exception as e:
                logger.error(f"Error inesperado en conectar: {type(e).__name__} - {e}")
                self.reconexion_intento += 1
    
    async def procesar_comando(self, data):
        """Procesa comandos del servidor"""
        try:
            tipo = data.get("type", "")
            d = data.get("data", {})
            
            if tipo == "open_url":
                url = d.get("url", "")
                profile = d.get("profile", "")
                logger.info(f"[ORDEN] Abrir {url} en {profile}")
                
                perfil = next((p for p in self.perfiles if p["name"] == profile), None)
                if not perfil:
                    logger.error(f"Perfil no encontrado: {profile}")
                    return
                
                await abrir_o_reutilizar_perfil(
                    self.api_url, self.token, self.ws_id,
                    perfil["dirId"], url, ""
                )
                logger.info(f"[OK] Perfil {profile} listo")
            
            elif tipo == "comment":
                texto = d.get("text", "")
                profile = d.get("profile", "")
                url = d.get("url", "")
                logger.info(f"[COMENTARIO] '{texto[:40]}...' para {profile}")
                
                perfil = next((p for p in self.perfiles if p["name"] == profile), None)
                if not perfil:
                    logger.error(f"Perfil no encontrado: {profile}")
                    return
                
                await abrir_o_reutilizar_perfil(
                    self.api_url, self.token, self.ws_id,
                    perfil["dirId"], url, texto
                )
            
            elif tipo == "ping":
                logger.debug("Ping recibido")
        
        except Exception as e:
            logger.error(f"Error procesando comando: {type(e).__name__} - {e}")
    
    async def iniciar_servidor_ui(self):
        """Inicia servidor WebSocket local para UI"""
        try:
            async with websockets.serve(manejar_ui, "127.0.0.1", 8085):
                logger.info("Servidor UI iniciado en puerto 8085")
                await asyncio.Future()
        except Exception as e:
            logger.error(f"Error en servidor UI: {type(e).__name__} - {e}")

async def main():
    """Función principal"""
    logger.info("=" * 60)
    logger.info("ROXYMASTER v6.1 - PCBOT CLIENTE")
    logger.info("=" * 60)
    
    client = PCBOTClient()
    await client.inicializar()
    
    # Tareas en paralelo
    ui_task = asyncio.create_task(client.iniciar_servidor_ui())
    pcmaster_task = asyncio.create_task(client.conectar_pcmaster())
    
    try:
        await asyncio.gather(ui_task, pcmaster_task)
    except KeyboardInterrupt:
        logger.info("Cliente interrumpido por usuario")
        ui_task.cancel()
        pcmaster_task.cancel()
    except Exception as e:
        logger.error(f"Error en main: {type(e).__name__} - {e}")

# Instancia global de playwright (se inicia una vez y se reutiliza)
playwright_inst = None

async def inicializar_playwright():
    """Inicia playwright una sola vez para todo el ciclo de vida del cliente"""
    global playwright_inst
    p = await async_playwright().start()
    playwright_inst = p
    logger.info("Playwright iniciado (instancia global)")

if __name__ == "__main__":
    try:
        asyncio.run(inicializar_playwright())
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Error fatal: {e}")
        sys.exit(1)
