import os
import sys
import json
import asyncio
import websockets
import requests
import time
import random
from playwright.async_api import async_playwright

BASE_DIR = os.path.join(os.environ["USERPROFILE"], "Desktop", "ROXYMASTER", "PCBOT")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

perfiles_abiertos = {}

def cargar_config():
    with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def get_workspace(api_url, token):
    try:
        r = requests.get(f"{api_url}/browser/workspace", headers={"token": token}, timeout=30)
        if r.status_code == 200 and r.json().get("code") == 0:
            rows = r.json().get("data", {}).get("rows", [])
            if rows:
                return rows[0].get("id")
    except:
        pass
    return "94706"

def get_perfiles(api_url, token, ws_id):
    perfiles = []
    try:
        r = requests.get(f"{api_url}/browser/list_v3?workspaceId={ws_id}", headers={"token": token}, timeout=30)
        if r.status_code == 200 and r.json().get("code") == 0:
            for p in r.json().get("data", {}).get("rows", []):
                nombre = p.get("windowName")
                dir_id = p.get("dirId")
                if nombre and dir_id:
                    perfiles.append({"name": nombre, "dirId": dir_id})
                    print(f"[DETECTADO] {nombre}")
    except Exception as e:
        print(f"Error listando perfiles: {e}")
    return perfiles

async def inyectar_comentario(page, comentario):
    try:
        await page.wait_for_timeout(2000)
        selectores = [
            'textarea[placeholder*="Message"]',
            'textarea[placeholder*="message"]',
            'div[role="textbox"][contenteditable="true"]',
            '.chat-input',
            '[data-testid="chat-input"]'
        ]
        for selector in selectores:
            if await page.locator(selector).count():
                await page.click(selector)
                await page.fill(selector, "")
                await page.type(selector, comentario, delay=random.uniform(30, 100))
                await page.keyboard.press("Enter")
                print(f"  ✅ Comentario enviado: {comentario[:50]}")
                return True
        print(f"  ❌ No se encontró selector de chat")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

async def abrir_url(page, url):
    try:
        await page.goto(url, timeout=30000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        print(f"  ✅ URL cargada: {url}")
        return True
    except Exception as e:
        print(f"  ❌ Error cargando URL: {e}")
        return False

async def abrir_o_reutilizar_perfil(api_url, token, ws_id, dir_id, url="", comentario=""):
    if dir_id in perfiles_abiertos:
        data = perfiles_abiertos[dir_id]
        page = data["page"]
        try:
            await page.evaluate("1")
            print(f"  Reutilizando perfil existente")
            if url and page.url != url:
                await abrir_url(page, url)
            if comentario:
                await inyectar_comentario(page, comentario)
            return True
        except:
            print(f"  Conexión perdida, abriendo nuevo...")
            del perfiles_abiertos[dir_id]
    
    print(f"  Abriendo nuevo perfil...")
    r = requests.post(
        f"{api_url}/browser/open",
        headers={"token": token, "Content-Type": "application/json"},
        json={"workspaceId": ws_id, "dirId": dir_id, "args": []},
        timeout=60
    )
    if r.status_code != 200:
        print(f"  Error HTTP: {r.status_code}")
        return False
    
    data = r.json()
    if data.get("code") != 0:
        print(f"  Error API: {data.get('msg')}")
        return False
    
    ws_endpoint = data.get("data", {}).get("ws")
    if not ws_endpoint:
        print(f"  No WebSocket endpoint")
        return False
    
    print(f"  Conectando a CDP...")
    
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(ws_endpoint, timeout=30000)
        page = browser.contexts[0].pages[0]
        perfiles_abiertos[dir_id] = {"browser": browser, "page": page}
        
        if url:
            await abrir_url(page, url)
        
        if comentario:
            await inyectar_comentario(page, comentario)
        
        print(f"  Perfil listo")
    
    return True

class PCBOTClient:
    def __init__(self):
        cfg = cargar_config()
        self.ip = cfg["pcmaster_ip"]
        self.port = cfg["pcmaster_port"]
        self.client_id = os.environ.get("COMPUTERNAME", "pcbot")
        api = cfg.get("roxy_api", {})
        self.api_url = api.get("url", "http://127.0.0.1:50000")
        self.token = api.get("token", "")
        
        print(f"[PCBOT] Conectando a API en {self.api_url}")
        self.ws_id = get_workspace(self.api_url, self.token)
        self.perfiles = get_perfiles(self.api_url, self.token, self.ws_id)
        print(f"[PCBOT] Total perfiles: {len(self.perfiles)}")
    
    async def conectar(self):
        uri = f"ws://{self.ip}:{self.port}"
        while True:
            try:
                async with websockets.connect(uri) as ws:
                    await ws.send(json.dumps({
                        "type": "identify",
                        "client_id": self.client_id,
                        "profiles": self.perfiles
                    }))
                    print(f"[PCBOT] Conectado a PCMASTER en {self.ip}:{self.port}")
                    
                    async for msg in ws:
                        data = json.loads(msg)
                        tipo = data.get("type")
                        d = data.get("data", {})
                        
                        if tipo == "open_url":
                            url = d.get("url", "")
                            profile = d.get("profile", "")
                            print(f"\n[ORDEN] Abrir {url} en {profile}")
                            
                            perfil = next((p for p in self.perfiles if p["name"] == profile), None)
                            if not perfil:
                                print(f"  Perfil '{profile}' no encontrado")
                                continue
                            
                            await abrir_o_reutilizar_perfil(
                                self.api_url, self.token, self.ws_id,
                                perfil["dirId"], url, ""
                            )
                            print(f"  [OK] Perfil {profile} listo")
                        
                        elif tipo == "comment":
                            texto = d.get("text", "")
                            profile = d.get("profile", "")
                            print(f"\n[COMENTARIO] '{texto}' para {profile}")
                            
                            perfil = next((p for p in self.perfiles if p["name"] == profile), None)
                            if not perfil:
                                print(f"  Perfil '{profile}' no encontrado")
                                continue
                            
                            await abrir_o_reutilizar_perfil(
                                self.api_url, self.token, self.ws_id,
                                perfil["dirId"], "", texto
                            )
                        
                        elif tipo == "ping":
                            await ws.send(json.dumps({"type": "pong", "timestamp": time.time()}))
                            
            except Exception as e:
                print(f"Error de conexión: {e}")
                await asyncio.sleep(5)

async def main():
    print("=" * 50)
    print("  ROXYMASTER v6.0 - PCBOT")
    print("=" * 50)
    client = PCBOTClient()
    await client.conectar()

if __name__ == "__main__":
    asyncio.run(main())