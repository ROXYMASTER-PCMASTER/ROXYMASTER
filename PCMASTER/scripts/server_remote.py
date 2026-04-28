import sys
import os
import json
import asyncio
import websockets
import threading
import time
import random
import requests
import logging
import secrets
from datetime import datetime
from collections import deque
from urllib.parse import urlparse

BASE_DIR = os.path.join(os.environ["USERPROFILE"], "Desktop", "ROXYMASTER", "PCMASTER")
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))

from variables_globales import *

with open(os.path.join(BASE_DIR, "config.json"), "r", encoding="utf-8-sig") as f:
    config = json.load(f)

PUERTO = config["server"]["ws_port"]
IP = config["server"]["ip_servidor"]

pcbots = {}
perfiles_map = {}
grupos = {}
loop = None

# ============================================================================
# LOCKS Y SINCRONIZACIÓN
# ============================================================================
lock_perfiles = threading.Lock()
lock_grupos = threading.Lock()
lock_pcbots = threading.Lock()
tokens_autenticados = {}  # token -> {cid, tiempo}
TOKEN_TIMEOUT = 3600  # 1 hora

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
    except:
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
# JARVIS
# ============================================================================

class Jarvis:
    def __init__(self, prompts_dir):
        self.prompts_dir = prompts_dir
        self.prompt_maestro = self._cargar_prompt()
        self.memoria_por_url = {}
        self.stats = {"generados": 0}
        self.ultimos_comentarios = deque(maxlen=100)  # Aumentado a 100
        print(f"[JARVIS] Activado")
    
    def _cargar_prompt(self):
        path = os.path.join(self.prompts_dir, "maestro.txt")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8-sig") as f:
                return f.read()
        return "Eres un comentarista de streams."
    
    def _get_memoria(self, url):
        if url not in self.memoria_por_url:
            self.memoria_por_url[url] = deque(maxlen=50)
        return self.memoria_por_url[url]
    
    def aprender(self, texto, url):
        if texto and len(texto) > 5:
            memoria = self._get_memoria(url)
            memoria.append({"texto": texto, "ts": time.time()})
    
    def generar(self, url):
        memoria = self._get_memoria(url)
        contexto = ""
        ahora = time.time()
        contextos = [m["texto"] for m in memoria if ahora - m["ts"] <= 30]
        if contextos:
            contexto = "\n".join(list(contextos)[-10:])
        
        prompt = f"""{self.prompt_maestro}

CONTEXTO:
{contexto[:500] if contexto else "Stream en vivo"}

Genera UN comentario corto (max 60 caracteres). Se natural. Diferente a comentarios anteriores."""
        
        try:
            r = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3.2",
                    "prompt": prompt,
                    "stream": False,
                    "max_tokens": 80,
                    "temperature": 0.9
                },
                timeout=15
            )
            if r.status_code == 200:
                txt = r.json().get("response", "").strip()
                if txt and len(txt) > 2 and txt not in self.ultimos_comentarios:
                    self.ultimos_comentarios.append(txt)
                    self.stats["generados"] += 1
                    return txt[:60]
        except requests.exceptions.Timeout:
            print(f"[JARVIS] Timeout conectando a Ollama")
        except requests.exceptions.ConnectionError:
            print(f"[JARVIS] Error conectando a Ollama")
        except Exception as e:
            print(f"[JARVIS] Error: {e}")
        
        return random.choice(["no see 🔥", "vamooo 🔥", "oyeee 🔥"])
    
    def get_stats(self):
        return self.stats

jarvis = Jarvis(os.path.join(BASE_DIR, "prompts"))

# ============================================================================
# FUNCIONES BASE
# ============================================================================

async def enviar(pcbot_id, cmd, data):
    """Envía un comando a un PCBOT específico"""
    try:
        with lock_pcbots:
            if pcbot_id not in pcbots:
                print(f"[ADVERTENCIA] PCBOT {pcbot_id} no conectado")
                return False
            ws = pcbots[pcbot_id]
        
        try:
            msg = json.dumps({"type": cmd, "data": data})
            await ws.send(msg)
            return True
        except websockets.exceptions.ConnectionClosed:
            print(f"[-] PCBOT {pcbot_id} desconectado durante envío")
            with lock_pcbots:
                pcbots.pop(pcbot_id, None)
            return False
    except json.JSONEncodeError as e:
        print(f"[ERROR] JSON inválido en enviar: {cmd} - {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Fallo enviando a {pcbot_id}: {e}")
        return False

async def heartbeat(ws, cid, interval=30):
    """Envía ping periódicamente para mantener conexión viva"""
    try:
        while True:
            await asyncio.sleep(interval)
            try:
                await ws.ping()
            except websockets.exceptions.ConnectionClosed:
                print(f"[HEARTBEAT] Conexión cerrada: {cid}")
                break
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[HEARTBEAT] Error: {e}")

async def manejar_conexion(ws, path):
    cid = None
    token = None
    heartbeat_task = None
    
    try:
        # Esperar handshake con timeout
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=30)
        except asyncio.TimeoutError:
            print(f"[ERROR] Timeout en handshake - no recibió 'identify'")
            await ws.send(json.dumps({"type": "error", "data": "Timeout en handshake"}))
            return
        
        try:
            data = json.loads(msg)
        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON inválido en handshake: {e}")
            await ws.send(json.dumps({"type": "error", "data": "JSON inválido"}))
            return
        
        if data.get("type") != "identify":
            print(f"[ERROR] Primer mensaje no es 'identify'")
            await ws.send(json.dumps({"type": "error", "data": "Se requiere 'identify' primero"}))
            return
        
        cid = data.get("client_id")
        if not cid:
            print(f"[ERROR] 'client_id' faltante en identify")
            await ws.send(json.dumps({"type": "error", "data": "client_id requerido"}))
            return
        
        # Generar token de autenticación
        token = generar_token()
        tokens_autenticados[token] = {"cid": cid, "tiempo": time.time()}
        
        perfiles = data.get("profiles", [])
        
        with lock_pcbots:
            pcbots[cid] = ws
        
        with lock_perfiles:
            for p in perfiles:
                key = f"{cid}|{p['name']}"
                perfiles_map[key] = {
                    "pcbot": cid,
                    "name": p["name"],
                    "dirId": p["dirId"]
                }
        
        print(f"[+] PCBOT: {cid} | Perfiles: {len(perfiles)} | Token: {token[:8]}...")
        
        # Enviar confirmación con token
        await ws.send(json.dumps({"type": "connected", "data": {"token": token}}))
        
        # Iniciar heartbeat
        heartbeat_task = asyncio.create_task(heartbeat(ws, cid, interval=30))
        
        # Escuchar mensajes
        try:
            async for msg in ws:
                # Procesar mensajes del cliente (si es necesario)
                pass
        except websockets.exceptions.ConnectionClosed:
            print(f"[-] Conexión cerrada: {cid}")
        except Exception as e:
            print(f"[ERROR] Error procesando mensajes de {cid}: {e}")
    
    except Exception as e:
        print(f"[ERROR] Error en manejar_conexion: {e}")
    
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
            with lock_perfiles:
                keys = [k for k, v in list(perfiles_map.items()) if v["pcbot"] == cid]
                for k in keys:
                    del perfiles_map[k]
            
            with lock_pcbots:
                pcbots.pop(cid, None)
            
            print(f"[-] PCBOT {cid} limpiado (perfiles eliminados: {len(keys)})")
        
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
            with lock_grupos:
                grupos_copy = list(grupos.items())
            
            for url, grupo in grupos_copy:
                if not grupo.get("comentarios", False):
                    continue
                
                # Para CADA perfil del grupo, generar un comentario DIFERENTE
                for perfil_key in grupo["perfiles"]:
                    with lock_perfiles:
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
                        print(f"[JARVIS] {comentario} -> {perfil_key}")
                    
                    # Pausa entre comentarios de diferentes perfiles
                    await asyncio.sleep(random.randint(5, 10))
            
            # Pausa entre ciclos completos (15-25 segundos)
            await asyncio.sleep(random.randint(15, 25))
        except Exception as e:
            print(f"[ERROR] tarea_comentarios: {e}")
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
            with lock_grupos:
                urls_expiradas = []
                for url, grupo in list(grupos.items()):
                    duracion_minutos = (ahora - grupo.get("inicio", 0)) / 60
                    duracion_max = grupo.get("duracion", 999)
                    
                    if duracion_minutos > duracion_max:
                        urls_expiradas.append(url)
                
                for url in urls_expiradas:
                    await ejecutar_detener(url)
                    print(f"[TIMEOUT] Grupo {url} liberado automáticamente")
        
        except Exception as e:
            print(f"[ERROR] Limpieza de grupos: {e}")

# ============================================================================
# COMANDOS
# ============================================================================

async def ejecutar_asignar(cant, url, dur):
    """Asigna perfiles a una URL específica"""
    if not validar_url(url):
        print(f"[ERROR] URL inválida: {url}")
        return
    
    with lock_perfiles:
        ocupados = set()
        with lock_grupos:
            for g in grupos.values():
                ocupados.update(g["perfiles"])
        
        libres = [k for k in perfiles_map.keys() if k not in ocupados]
    
    if len(libres) < cant:
        print(f"[ADVERTENCIA] Solo {len(libres)} perfiles libres, se requieren {cant}")
        return
    
    sel = libres[:cant]
    
    with lock_grupos:
        if url not in grupos:
            grupos[url] = {
                "perfiles": [],
                "comentarios": False,
                "inicio": time.time(),
                "duracion": dur
            }
        
        for key in sel:
            grupos[url]["perfiles"].append(key)
            
            with lock_perfiles:
                info = perfiles_map[key]
            
            await enviar(info["pcbot"], "open_url", {
                "url": url,
                "profile": info["name"],
                "dirId": info["dirId"]
            })
            print(f"  Abriendo {key} en {url}")
            await asyncio.sleep(2)
    
    print(f"[OK] Asignados {cant} perfiles a {url} por {dur} minutos")

async def ejecutar_comentarios_activar(url, nivel):
    """Activa generación de comentarios para un grupo"""
    if not validar_url(url):
        print(f"[ERROR] URL inválida: {url}")
        return
    
    with lock_grupos:
        if url in grupos:
            grupos[url]["comentarios"] = True
            print(f"[OK] Comentarios activados para {url} (nivel {nivel})")
        else:
            print(f"[ERROR] Grupo no encontrado: {url}")

async def ejecutar_comentarios_desactivar(url):
    """Desactiva generación de comentarios para un grupo"""
    if not validar_url(url):
        print(f"[ERROR] URL inválida: {url}")
        return
    
    with lock_grupos:
        if url in grupos:
            grupos[url]["comentarios"] = False
            print(f"[OK] Comentarios desactivados para {url}")
        else:
            print(f"[ERROR] Grupo no encontrado: {url}")

async def ejecutar_detener(url):
    """Detiene un grupo y libera sus perfiles"""
    with lock_grupos:
        if url in grupos:
            perfiles_liberados = len(grupos[url]["perfiles"])
            del grupos[url]
            print(f"[OK] Grupo detenido: {url} ({perfiles_liberados} perfiles liberados)")
        else:
            print(f"[ERROR] Grupo no encontrado: {url}")

# ============================================================================
# CONSOLA ADMIN
# ============================================================================

def admin_console():
    print("\n" + "=" * 60)
    print("  ROXYMASTER v6.1 - CONSOLA ADMIN (CON SEGURIDAD)")
    print("=" * 60)
    print("  COMANDOS:")
    print("  perfiles")
    print("  asignar <cant> url <URL> duracion <min>")
    print("  comentarios_activar url <URL> nivel <bajo/medio/alto>")
    print("  comentarios_desactivar url <URL>")
    print("  detener url <URL>")
    print("  estado")
    print("  salir")
    print("-" * 60)
    
    while True:
        try:
            cmd = input("\n[ADMIN] > ").strip().split()
            if not cmd:
                continue
            
            if cmd[0] == "perfiles":
                with lock_perfiles:
                    total = len(perfiles_map)
                    ocupados = set()
                    with lock_grupos:
                        for g in grupos.values():
                            ocupados.update(g["perfiles"])
                
                print(f"\n[PERFILES] Total: {total}")
                with lock_perfiles:
                    for key in list(perfiles_map.keys())[:20]:
                        estado = "🔥 OCUPADO" if key in ocupados else "✅ LIBRE"
                        print(f"  {key} : {estado}")
            
            elif cmd[0] == "asignar":
                try:
                    cant = int(cmd[1])
                    url = cmd[3]
                    dur = int(cmd[5])
                    asyncio.run_coroutine_threadsafe(ejecutar_asignar(cant, url, dur), loop)
                except (IndexError, ValueError):
                    print("Uso: asignar 2 url https://kick.com/xxx duracion 10")
            
            elif cmd[0] == "comentarios_activar":
                try:
                    url = cmd[2]
                    nivel = cmd[4] if len(cmd) > 4 else "medio"
                    asyncio.run_coroutine_threadsafe(ejecutar_comentarios_activar(url, nivel), loop)
                except (IndexError, ValueError):
                    print("Uso: comentarios_activar url https://kick.com/xxx nivel medio")
            
            elif cmd[0] == "comentarios_desactivar":
                try:
                    url = cmd[2]
                    asyncio.run_coroutine_threadsafe(ejecutar_comentarios_desactivar(url), loop)
                except (IndexError, ValueError):
                    print("Uso: comentarios_desactivar url https://kick.com/xxx")
            
            elif cmd[0] == "detener":
                try:
                    url = cmd[2]
                    asyncio.run_coroutine_threadsafe(ejecutar_detener(url), loop)
                except (IndexError, ValueError):
                    print("Uso: detener url https://kick.com/xxx")
            
            elif cmd[0] == "estado":
                with lock_perfiles:
                    total = len(perfiles_map)
                
                with lock_pcbots:
                    pcbots_conectados = len(pcbots)
                
                with lock_grupos:
                    ocupados = sum(len(g.get("perfiles", [])) for g in grupos.values())
                    grupos_activos = len(grupos)
                
                print(f"\n[ESTADO]")
                print(f"  Servidor: {IP}:{PUERTO}")
                print(f"  PCBOTs conectados: {pcbots_conectados}")
                print(f"  Perfiles totales: {total}")
                print(f"  Perfiles ocupados: {ocupados}")
                print(f"  Perfiles libres: {total - ocupados}")
                print(f"  Grupos activos: {grupos_activos}")
                print(f"  JARVIS comentarios generados: {jarvis.get_stats()['generados']}")
                print(f"  Sesiones autenticadas: {len(tokens_autenticados)}")
            
            elif cmd[0] == "salir":
                print("Deteniendo servidor...")
                os._exit(0)
            
            else:
                print("Comando no reconocido")
        except Exception as e:
            print(f"Error: {e}")

# ============================================================================
# MAIN
# ============================================================================

async def main():
    global loop
    loop = asyncio.get_event_loop()
    
    # Iniciar tareas de fondo
    asyncio.create_task(tarea_enviar_comentarios())
    asyncio.create_task(limpiar_grupos_expirados())
    
    # Iniciar consola admin en thread separado
    threading.Thread(target=admin_console, daemon=True).start()
    
    print(f"SERVIDOR ACTIVO en {IP}:{PUERTO}")
    print(f"Versión: 6.1 (Con manejo de conexiones mejorado)")
    print("-" * 50)
    
    async with websockets.serve(manejar_conexion, IP, PUERTO):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
