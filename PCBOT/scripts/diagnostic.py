"""
DIAGNOSTICO: Listar perfiles, detectar ocupados, URL actual, tiempo restante.
"""
import asyncio
import json
import time
import requests
from playwright.async_api import async_playwright

API = "http://127.0.0.1:50000"
TOKEN = "8ce112f7ebbb0fba6e9e290194f8e117"
WORKSPACE_ID = 94706

# Registro manual de aperturas (para estimar tiempo restante)
# Formato: {dirId: (hora_apertura, duracion_segundos, url)}
REGISTRO = {
    "9713f2ca9fb3570bd20fc87c3507beb6": (time.time() - 600, 600, "https://kick.com/benjaz"),  # User1_1 ~10min atras
    "2e137cbf9db8a38c6b6d244556adfd47": (time.time() - 120, 120, "https://kick.com/benjaz"),  # User1_2 ~2min atras
}


def listar_perfiles():
    """Obtiene todos los perfiles del workspace"""
    try:
        r = requests.get(
            f"{API}/browser/list_v3?workspaceId={WORKSPACE_ID}",
            headers={"token": TOKEN},
            timeout=30
        )
        if r.status_code != 200 or r.json().get("code") != 0:
            return []
        return r.json().get("data", {}).get("rows", [])
    except Exception as e:
        print(f"  ERROR listando perfiles: {e}")
        return []


def intentar_abrir_perfil(dir_id):
    """Intenta abrir perfil. Si ya esta abierto, puede devolver o no el CDP endpoint."""
    try:
        r = requests.post(
            f"{API}/browser/open",
            headers={"token": TOKEN, "Content-Type": "application/json"},
            json={"workspaceId": WORKSPACE_ID, "dirId": dir_id, "args": []},
            timeout=30
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("code") == 0:
                ws = data.get("data", {}).get("ws")
                if ws:
                    return True, ws
        # code != 0 puede significar "ya abierto" u otro error
        return False, r.json().get("msg", "desconocido") if r.status_code == 200 else f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)


async def obtener_url_cdp(ws_endpoint):
    """Conecta via CDP y obtiene la URL actual del perfil"""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(ws_endpoint, timeout=10000)
            if browser and browser.contexts and browser.contexts[0].pages:
                page = browser.contexts[0].pages[0]
                url = await page.evaluate("window.location.href")
                titulo = await page.title()
                return url, titulo
    except Exception as e:
        return None, f"Error: {type(e).__name__}"
    return None, "Sin paginas"


async def diagnosticar():
    print("=" * 65)
    print("  ROXYMASTER - DIAGNOSTICO DE PERFILES")
    print("=" * 65)

    perfiles = listar_perfiles()
    if not perfiles:
        print("  No se pudieron obtener perfiles.")
        return

    total = len(perfiles)
    abiertos = 0
    libres = 0
    resultados = []

    print(f"  Total perfiles en workspace: {total}")
    print("-" * 65)

    for i, p in enumerate(perfiles, 1):
        nombre = p.get("windowName", "???")
        dir_id = p.get("dirId", "")
        print(f"\n  [{i}] {nombre} (dirId: {dir_id})")

        # Intentar obtener CDP
        ok, ws = intentar_abrir_perfil(dir_id)

        if ok and ws:
            # Perfil abierto, inspeccionar
            abiertos += 1
            print(f"      Estado: ABIERTO")
            print(f"      CDP: {ws[:55]}...")

            url, titulo = await obtener_url_cdp(ws)
            print(f"      URL: {url or 'N/D'}")
            print(f"      Titulo: {titulo or 'N/D'}")

            # Tiempo restante
            registro = REGISTRO.get(dir_id)
            if registro:
                hora_ini, duracion, url_reg = registro
                transcurrido = time.time() - hora_ini
                restante = max(0, duracion - transcurrido)
                minutos = int(restante // 60)
                segundos = int(restante % 60)
                print(f"      Tiempo asignado: {duracion // 60} min")
                print(f"      Tiempo restante: {minutos}m {segundos}s")
            else:
                print(f"      Tiempo restante: DESCONOCIDO (sin registro)")

            resultados.append({
                "nombre": nombre, "dirId": dir_id, "url": url,
                "abierto": True, "restante": restante if registro else None
            })
        else:
            libres += 1
            print(f"      Estado: LIBRE (respuesta API: {ws})")
            resultados.append({
                "nombre": nombre, "dirId": dir_id,
                "abierto": False, "url": None, "restante": None
            })

    # RESUMEN
    print("\n" + "=" * 65)
    print("  RESUMEN FINAL")
    print("=" * 65)
    print(f"  Total perfiles:    {total}")
    print(f"  Abiertos (ocupados): {abiertos}")
    print(f"  Libres (disponibles): {libres}")
    print("-" * 65)

    for r in resultados:
        if r["abierto"]:
            restante = r.get("restante")
            if restante is not None:
                m = int(restante // 60)
                s = int(restante % 60)
                print(f"  [{r['nombre']}] OCUPADO | URL: {r['url']} | Restante: {m}m {s}s")
            else:
                print(f"  [{r['nombre']}] OCUPADO | URL: {r['url']} | Restante: ?")
        else:
            print(f"  [{r['nombre']}] LIBRE | Disponible para usar")

    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(diagnosticar())