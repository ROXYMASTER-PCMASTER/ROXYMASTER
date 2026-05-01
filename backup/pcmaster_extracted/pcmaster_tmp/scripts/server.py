import sys
import os
import json
import asyncio
import websockets
import threading
import time
import random
import requests
from datetime import datetime
from collections import deque

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
pool_comentarios = {}  # url -> lista de comentarios
loop = None

# ============================================================================
# JARVIS
# ============================================================================

class Jarvis:
    def __init__(self, prompts_dir):
        self.prompts_dir = prompts_dir
        self.prompt_maestro = self._cargar_prompt()
        self.memoria_por_url = {}
        self.stats = {"generados": 0}
        self.ultimos_comentarios = deque(maxlen=20)  # Evitar repeticiones exactas
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
                if txt and txt not in self.ultimos_comentarios:
                    self.ultimos_comentarios.append(txt)
                    self.stats["generados"] += 1
                    return txt[:60]
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
    if pcbot_id in pcbots:
        try:
            await pcbots[pcbot_id].send(json.dumps({"type": cmd, "data": data}))
            return True
        except:
            pass
    return False

async def manejar_conexion(ws):
    cid = None
    try:
        msg = await asyncio.wait_for(ws.recv(), timeout=30)
        data = json.loads(msg)
        if data.get("type") == "identify":
            cid = data.get("client_id")
            perfiles = data.get("profiles", [])
            pcbots[cid] = ws
            for p in perfiles:
                key = f"{cid}|{p['name']}"
                perfiles_map[key] = {"pcbot": cid, "name": p["name"], "dirId": p["dirId"]}
            print(f"[+] PCBOT: {cid} | Perfiles: {len(perfiles)}")
            await ws.send(json.dumps({"type": "connected"}))
            async for _ in ws:
                pass
    except:
        pass
    finally:
        if cid:
            keys = [k for k, v in perfiles_map.items() if v["pcbot"] == cid]
            for k in keys:
                del perfiles_map[k]
            pcbots.pop(cid, None)
            print(f"[-] PCBOT: {cid}")

# ============================================================================
# TAREA: COMENTARIOS ÚNICOS POR PERFIL
# ============================================================================

async def tarea_enviar_comentarios():
    """Genera y envía un comentario ÚNICO por perfil, no el mismo para todos"""
    while True:
        try:
            for url, grupo in list(grupos.items()):
                if not grupo.get("comentarios", False):
                    continue
                
                # Para CADA perfil del grupo, generar un comentario DIFERENTE
                for perfil_key in grupo["perfiles"]:
                    if perfil_key not in perfiles_map:
                        continue
                    
                    # Generar comentario NUEVO para este perfil
                    comentario = jarvis.generar(url)
                    
                    if comentario:
                        info = perfiles_map[perfil_key]
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
# COMANDOS
# ============================================================================

async def ejecutar_asignar(cant, url, dur):
    ocupados = set()
    for g in grupos.values():
        ocupados.update(g["perfiles"])
    libres = [k for k in perfiles_map.keys() if k not in ocupados]
    
    if len(libres) < cant:
        print(f"Solo {len(libres)} perfiles libres")
        return
    
    sel = libres[:cant]
    
    if url not in grupos:
        grupos[url] = {"perfiles": [], "comentarios": False, "inicio": time.time()}
    
    for key in sel:
        grupos[url]["perfiles"].append(key)
        info = perfiles_map[key]
        await enviar(info["pcbot"], "open_url", {"url": url, "profile": info["name"], "dirId": info["dirId"]})
        print(f"  Abriendo {key} en {url}")
        await asyncio.sleep(2)
    
    print(f"Asignados {cant} perfiles a {url} por {dur} minutos")

async def ejecutar_comentarios_activar(url, nivel):
    if url in grupos:
        grupos[url]["comentarios"] = True
        print(f"Comentarios activados para {url} (nivel {nivel})")
    else:
        print(f"Grupo no encontrado: {url}")

async def ejecutar_comentarios_desactivar(url):
    if url in grupos:
        grupos[url]["comentarios"] = False
        print(f"Comentarios desactivados para {url}")
    else:
        print(f"Grupo no encontrado: {url}")

async def ejecutar_detener(url):
    if url in grupos:
        del grupos[url]
        print(f"Grupo detenido: {url}")
    else:
        print(f"Grupo no encontrado: {url}")

# ============================================================================
# CONSOLA ADMIN
# ============================================================================

def admin_console():
    print("\n" + "=" * 60)
    print("  ROXYMASTER v6.0 - CONSOLA ADMIN")
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
                print(f"\n[PERFILES] Total: {len(perfiles_map)}")
                ocupados = set()
                for g in grupos.values():
                    ocupados.update(g["perfiles"])
                for key in list(perfiles_map.keys())[:20]:
                    estado = "🔥 OCUPADO" if key in ocupados else "✅ LIBRE"
                    print(f"  {key} : {estado}")
            
            elif cmd[0] == "asignar":
                try:
                    cant = int(cmd[1])
                    url = cmd[3]
                    dur = int(cmd[5])
                    asyncio.run_coroutine_threadsafe(ejecutar_asignar(cant, url, dur), loop)
                except:
                    print("Uso: asignar 2 url https://kick.com/xxx duracion 10")
            
            elif cmd[0] == "comentarios_activar":
                try:
                    url = cmd[2]
                    nivel = cmd[4] if len(cmd) > 4 else "medio"
                    asyncio.run_coroutine_threadsafe(ejecutar_comentarios_activar(url, nivel), loop)
                except:
                    print("Uso: comentarios_activar url https://kick.com/xxx nivel medio")
            
            elif cmd[0] == "comentarios_desactivar":
                try:
                    url = cmd[2]
                    asyncio.run_coroutine_threadsafe(ejecutar_comentarios_desactivar(url), loop)
                except:
                    print("Uso: comentarios_desactivar url https://kick.com/xxx")
            
            elif cmd[0] == "detener":
                try:
                    url = cmd[2]
                    asyncio.run_coroutine_threadsafe(ejecutar_detener(url), loop)
                except:
                    print("Uso: detener url https://kick.com/xxx")
            
            elif cmd[0] == "estado":
                total = len(perfiles_map)
                ocupados = sum(len(g.get("perfiles", [])) for g in grupos.values())
                print(f"\n[ESTADO]")
                print(f"  Servidor: {IP}:{PUERTO}")
                print(f"  PCBOTs conectados: {len(pcbots)}")
                print(f"  Perfiles totales: {total}")
                print(f"  Perfiles ocupados: {ocupados}")
                print(f"  Perfiles libres: {total - ocupados}")
                print(f"  Grupos activos: {len(grupos)}")
                print(f"  JARVIS comentarios: {jarvis.get_stats()['generados']}")
            
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
    
    asyncio.create_task(tarea_enviar_comentarios())
    
    threading.Thread(target=admin_console, daemon=True).start()
    
    print(f"SERVIDOR ACTIVO en {IP}:{PUERTO}")
    print("-" * 50)
    
    async with websockets.serve(manejar_conexion, IP, PUERTO):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())