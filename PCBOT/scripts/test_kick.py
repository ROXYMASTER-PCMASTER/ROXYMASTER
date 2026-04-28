"""
TEST: Abrir https://kick.com/benjaz por 60s usando el sistema RoxyBrowser + Playwright.
Reutiliza la misma lógica que pcbot.py (chromium.connect_over_cdp).
"""
import asyncio
import json
import os
import requests
from playwright.async_api import async_playwright

# Config
API = "http://127.0.0.1:50000"
TOKEN = "8ce112f7ebbb0fba6e9e290194f8e117"
WORKSPACE_ID = "94706"
PERFIL_DIRID = "9713f2ca9fb3570bd20fc87c3507beb6"  # User1_1
TARGET_URL = "https://kick.com/benjaz"
WAIT_SECONDS = 60


def api_open_profile():
    """Abre perfil via Roxy API (misma lógica que pcbot.py)"""
    print(f"[TEST] Abriendo perfil {PERFIL_DIRID} via Roxy API...")
    r = requests.post(
        f"{API}/browser/open",
        headers={"token": TOKEN, "Content-Type": "application/json"},
        json={"workspaceId": int(WORKSPACE_ID), "dirId": PERFIL_DIRID, "args": []},
        timeout=60
    )
    if r.status_code != 200:
        print(f"[TEST] ERROR HTTP: {r.status_code}")
        return None

    data = r.json()
    if data.get("code") != 0:
        print(f"[TEST] ERROR API: {data.get('msg')}")
        return None

    ws_endpoint = data.get("data", {}).get("ws")
    if not ws_endpoint:
        print("[TEST] ERROR: No WebSocket endpoint en respuesta")
        return None

    print(f"[TEST] CDP endpoint: {ws_endpoint}")
    return ws_endpoint


async def main():
    # 1. Abrir perfil via API Roxy
    ws_endpoint = api_open_profile()
    if not ws_endpoint:
        print("[TEST] No se pudo abrir el perfil.")
        return

    # 2. Conectar via Playwright (misma lógica que pcbot.py)
    print("[TEST] Iniciando Playwright...")
    async with async_playwright() as p:
        print(f"[TEST] Conectando a CDP: {ws_endpoint[:50]}...")
        try:
            browser = await p.chromium.connect_over_cdp(ws_endpoint, timeout=30000)
        except Exception as e:
            print(f"[TEST] ERROR conectando CDP: {e}")
            return

        if not browser or not browser.contexts:
            print("[TEST] ERROR: Browser sin contextos")
            return

        page = browser.contexts[0].pages[0] if browser.contexts[0].pages else await browser.contexts[0].new_page()
        print(f"[TEST] Navegando a {TARGET_URL}...")

        # 3. Navegar
        try:
            await page.goto(TARGET_URL, timeout=30000, wait_until="domcontentloaded")
        except Exception as e:
            print(f"[TEST] ERROR navegando: {e}")
            return

        # 4. Esperar
        print(f"[TEST] Esperando {WAIT_SECONDS}s en la página...")
        await asyncio.sleep(WAIT_SECONDS)

        # 5. Verificar
        try:
            titulo = await page.title()
            print(f"[TEST] Título de la página: {titulo}")
        except Exception as e:
            print(f"[TEST] No se pudo obtener título: {e}")

        print(f"[TEST] ✅ PRUEBA EXITOSA — {TARGET_URL} abierto {WAIT_SECONDS}s en User1_1.")
        print("[TEST] Perfil sigue abierto en RoxyBrowser (no se cierra).")


if __name__ == "__main__":
    asyncio.run(main())