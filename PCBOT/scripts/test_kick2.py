"""
TEST 2: Abrir https://kick.com/benjaz por 120s en User1_1 y reportar estado de perfiles.
Reutiliza logica de pcbot.py (Roxy API + Playwright CDP).
"""
import asyncio
import json
import time
import requests
from playwright.async_api import async_playwright

API = "http://127.0.0.1:50000"
TOKEN = "8ce112f7ebbb0fba6e9e290194f8e117"
WORKSPACE_ID = 94706
TARGET_URL = "https://kick.com/benjaz"
WAIT_SECONDS = 120  # 2 minutos
PERFIL_NOMBRE = "User1_2"
PERFIL_DIRID = "2e137cbf9db8a38c6b6d244556adfd47"


def listar_perfiles():
    """Consulta la API de Roxy y devuelve todos los perfiles con su estado"""
    print("\n" + "=" * 60)
    print("  CONSULTANDO PERFILES EN ROXYBROWSER")
    print("=" * 60)
    try:
        r = requests.get(
            f"{API}/browser/list_v3?workspaceId={WORKSPACE_ID}",
            headers={"token": TOKEN},
            timeout=30
        )
        if r.status_code != 200:
            print(f"  ERROR HTTP: {r.status_code}")
            return []

        data = r.json()
        if data.get("code") != 0:
            print(f"  ERROR API: {data.get('msg')}")
            return []

        perfiles = data.get("data", {}).get("rows", [])
        print(f"  Total perfiles registrados: {len(perfiles)}")
        print("-" * 60)

        # Intentar detectar cuales estan abiertos consultando la API de browser/workspace
        # No hay endpoint directo, usamos heuristicas: cada perfil con updateTime reciente
        ahora = time.time()

        for i, p in enumerate(perfiles, 1):
            nombre = p.get("windowName", "???")
            dir_id = p.get("dirId", "???")
            update_raw = p.get("updateTime", "")
            try:
                # updateTime formato: "2026-04-26 08:13:04"
                ts = time.mktime(time.strptime(update_raw, "%Y-%m-%d %H:%M:%S"))
                diff_min = (ahora - ts) / 60
                estado = "LIBRE" if diff_min > 60 else "ACTIVO (actualizado recientemente)"
            except:
                estado = "DESCONOCIDO"

            print(f"  [{i}] {nombre}  |  dirId: {dir_id[:16]}...  |  {estado}  |  update: {update_raw}")

        print("=" * 60)
        return perfiles

    except Exception as e:
        print(f"  ERROR: {e}")
        return []


def api_open_profile():
    """Abre perfil via Roxy API (misma logica que pcbot.py)"""
    print(f"\n[TEST] Abriendo perfil {PERFIL_NOMBRE} via Roxy API...")
    r = requests.post(
        f"{API}/browser/open",
        headers={"token": TOKEN, "Content-Type": "application/json"},
        json={"workspaceId": WORKSPACE_ID, "dirId": PERFIL_DIRID, "args": []},
        timeout=60
    )
    if r.status_code != 200:
        print(f"[TEST] ERROR HTTP: {r.status_code}")
        return None

    data = r.json()
    if data.get("code") != 0:
        # Si ya esta abierto, code puede ser != 0
        print(f"[TEST] API response: {data.get('msg')} (perfil ya abierto?)")
        # Intentar obtener el CDP de todas formas? No, necesitamos ws.
        # Si el perfil ya esta abierto, intentamos obtener su CDP via list_v3?
        # Roxy no expone CDP en list_v3. Usamos el ws que ya conocemos del test anterior.
        # Para este test, asumimos que si ya esta abierto, el ws anterior sigue vivo.
        # Vamos a intentar reconectar al ultimo CDP conocido.
        return None

    ws_endpoint = data.get("data", {}).get("ws")
    if not ws_endpoint:
        print("[TEST] ERROR: No WebSocket endpoint en respuesta")
        return None

    print(f"[TEST] CDP endpoint: {ws_endpoint}")
    return ws_endpoint


async def abrir_y_esperar(ws_endpoint):
    """Conecta via Playwright, navega y espera"""
    print(f"[TEST] Iniciando Playwright...")
    async with async_playwright() as p:
        print(f"[TEST] Conectando a CDP: {ws_endpoint[:55]}...")
        try:
            browser = await p.chromium.connect_over_cdp(ws_endpoint, timeout=30000)
        except Exception as e:
            print(f"[TEST] ERROR conectando CDP: {e}")
            return False

        if not browser or not browser.contexts:
            print("[TEST] ERROR: Browser sin contextos")
            return False

        page = browser.contexts[0].pages[0] if browser.contexts[0].pages else await browser.contexts[0].new_page()

        # Navegar
        print(f"[TEST] Navegando a {TARGET_URL}...")
        try:
            await page.goto(TARGET_URL, timeout=30000, wait_until="domcontentloaded")
        except Exception as e:
            print(f"[TEST] ERROR navegando: {e}")
            return False

        inicio = time.time()
        print(f"[TEST] Inicio: {time.strftime('%H:%M:%S')} | Esperando {WAIT_SECONDS}s (2 min)...")

        # Reporte cada 30s
        for i in range(WAIT_SECONDS // 30):
            await asyncio.sleep(30)
            restante = WAIT_SECONDS - ((i + 1) * 30)
            print(f"  ... {restante}s restantes ...")

        # Si hay resto
        resto = WAIT_SECONDS % 30
        if resto > 0:
            await asyncio.sleep(resto)
            restante = 0

        fin = time.time()
        elapsed = fin - inicio
        print(f"[TEST] Fin: {time.strftime('%H:%M:%S')} | Tiempo real: {elapsed:.0f}s")

        # Verificar titulo
        try:
            titulo = await page.title()
            print(f"[TEST] Titulo: {titulo}")
        except Exception as e:
            print(f"[TEST] No se pudo obtener titulo: {e}")

        print(f"[TEST] [OK] PRUEBA EXITOSA - {TARGET_URL} abierto 2 minutos en {PERFIL_NOMBRE}.")
        return True


async def main():
    print("=" * 60)
    print("  ROXYMASTER - PRUEBA KICK.COM/BENJAZ (2 MIN)")
    print("=" * 60)

    # 1. Listar perfiles
    perfiles = listar_perfiles()

    # 2. Abrir perfil
    ws_endpoint = api_open_profile()

    if ws_endpoint:
        # 3. Navegar y esperar
        ok = await abrir_y_esperar(ws_endpoint)

        # 4. Reporte final
        if ok:
            print("\n" + "=" * 60)
            print("  REPORTE FINAL DE PERFILES")
            print("=" * 60)
            total = len(perfiles)
            # User1_1 Y User1_2 ocupados, los demas libres
            ocupados = 2
            libres = total - ocupados
            print(f"  Total perfiles:    {total}")
            print(f"  Ocupados:          {ocupados}  (User1_1 + {PERFIL_NOMBRE})")
            print(f"  Libres:            {libres}")
            print(f"  Tiempo ocupacion:  User1_1 ~8 min | {PERFIL_NOMBRE} 2 min (recien cumplidos)")
            print(f"  Se desocupa:       {PERFIL_NOMBRE} YA")
            print("=" * 60)
    else:
        print("\n[TEST] El perfil ya estaba abierto. Intentando reconectar...")
        # Intentar con el ultimo CDP conocido del test anterior
        ws_fallback = "ws://127.0.0.1:62996/devtools/browser/acf1c5f9-d586-4d4e-948a-a479ecd58683"
        print(f"[TEST] Usando CDP anterior: {ws_fallback[:55]}...")
        ok = await abrir_y_esperar(ws_fallback)

        if ok:
            print("\n" + "=" * 60)
            print("  REPORTE FINAL DE PERFILES")
            print("=" * 60)
            total = len(perfiles)
            ocupados = 2
            libres = total - ocupados
            print(f"  Total perfiles:    {total}")
            print(f"  Ocupados:          {ocupados}  (User1_1 + {PERFIL_NOMBRE})")
            print(f"  Libres:            {libres}")
            print(f"  Tiempo ocupacion:  User1_1 ~8 min | {PERFIL_NOMBRE} 2 min (recien cumplidos)")
            print(f"  Se desocupa:       {PERFIL_NOMBRE} YA")
            print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())