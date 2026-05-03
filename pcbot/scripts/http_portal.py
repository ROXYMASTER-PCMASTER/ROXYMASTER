"""
http_portal.py - servidor http local para el portal del granjero
proxy inverso hacia pcmaster y endpoint de estado local.
puerto 8087.
"""
import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from aiohttp import web, ClientSession, ClientTimeout

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("http_portal")

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
SCRIPTS_DIR = BASE_DIR / "scripts"
PORTAL_HTML = BASE_DIR / "portal.html"
DATA_DIR = BASE_DIR / "data"

PCMASTER_WS = "ws://100.111.179.65:5006"
PCMASTER_API = "http://100.111.179.65:8086/api"
LOCAL_PORT = 8087

class StateManager:
    def __init__(self):
        self.pcbot_id = os.environ.get("COMPUTERNAME", "pcbot")
        self.username = os.environ.get("USERNAME", "cyber")
        self.ip_local = "127.0.0.1"
        self.ip_tailscale = "100.111.179.65"
        self.ip_wan = "0.0.0.0"
        self.modo = "pidiendo_ordenes"
        self.conectado = False
        self.perfiles = []
        self.tokens = {"kbt_acumulado": 0, "kbt_hoy": 0, "historial": []}
        self.ordenes_activas = []
        self.ultimo_heartbeat = None
        self.inicio = datetime.now()

    def to_dict(self):
        return {
            "pcbot_id": self.pcbot_id,
            "username": self.username,
            "ip_local": self.ip_local,
            "ip_tailscale": self.ip_tailscale,
            "ip_wan": self.ip_wan,
            "modo": self.modo,
            "conectado": self.conectado,
            "perfiles": self.perfiles,
            "tokens": self.tokens,
            "ordenes_activas": self.ordenes_activas,
            "ultimo_heartbeat": self.ultimo_heartbeat.isoformat() if self.ultimo_heartbeat else None,
            "uptime": str(datetime.now() - self.inicio).split(".")[0],
            "counts": {
                "total": len(self.perfiles),
                "active": sum(1 for p in self.perfiles if p.get("estado") == "active"),
                "inactive": sum(1 for p in self.perfiles if p.get("estado") == "inactive"),
                "hung": sum(1 for p in self.perfiles if p.get("estado") == "hung"),
            }
        }

state = StateManager()
_http_session = None

async def get_http_session():
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = ClientSession(timeout=ClientTimeout(total=30))
    return _http_session

async def proxy_to_pcmaster(request, endpoint_path):
    session = await get_http_session()
    url = f"{PCMASTER_API}{endpoint_path}"
    headers = {}
    for h in ("Content-Type", "Authorization", "Cookie", "X-Requested-With"):
        if h in request.headers:
            headers[h] = request.headers[h]
    try:
        body = await request.read()
        async with session.request(
            method=request.method, url=url, headers=headers,
            data=body if body else None, params=request.query,
        ) as resp:
            resp_body = await resp.read()
            return web.Response(
                status=resp.status, body=resp_body,
                content_type=resp.content_type or "application/json",
            )
    except asyncio.TimeoutError:
        log.warning(f"proxy timeout to {url}")
        return web.json_response({"error": "timeout"}, status=504)
    except Exception as e:
        log.warning(f"proxy error to {url}: {type(e).__name__}: {e}")
        return web.json_response({"error": str(e)}, status=502)

async def index_handler(request):
    if PORTAL_HTML.exists():
        return web.FileResponse(str(PORTAL_HTML))
    return web.Response(text="portal no encontrado", status=404)

async def static_handler(request):
    filename = request.match_info.get("filename", "")
    filepath = (STATIC_DIR / filename).resolve()
    try:
        if not str(filepath).startswith(str(STATIC_DIR.resolve())):
            return web.Response(text="acceso denegado", status=403)
    except Exception:
        return web.Response(text="ruta invalida", status=400)
    if filepath.exists() and filepath.is_file():
        return web.FileResponse(str(filepath))
    return web.Response(text="archivo no encontrado", status=404)

async def api_estado_handler(request):
    return web.json_response(state.to_dict())

async def api_dashboard_handler(request):
    pcmaster_data = {}
    session = await get_http_session()
    hdrs = {}
    if "Authorization" in request.headers:
        hdrs["Authorization"] = request.headers["Authorization"]
    if "Cookie" in request.headers:
        hdrs["Cookie"] = request.headers["Cookie"]
    try:
        async with session.get(f"{PCMASTER_API}/dashboard", timeout=10, headers=hdrs) as resp:
            if resp.status == 200:
                pcmaster_data = await resp.json()
    except Exception as e:
        log.warning(f"no se pudo obtener dashboard de pcmaster: {e}")
    local = state.to_dict()
    result = {
        "server_ok": bool(pcmaster_data),
        "balance": pcmaster_data.get("balance", state.tokens.get("kbt_acumulado", 0)),
        "kbt_hoy": state.tokens.get("kbt_hoy", 0),
        "perfiles_activos": local["counts"]["active"],
        "modo": local["modo"],
        "server_uptime": local["uptime"],
        "ultimo_heartbeat": local["ultimo_heartbeat"],
        "uptime": local["uptime"],
        "codigo_referido": pcmaster_data.get("codigo_referido"),
        "referido_por": pcmaster_data.get("referido_por"),
        "comisiones_referidos": pcmaster_data.get("comisiones_referidos", 0),
        "referido_cambiado": pcmaster_data.get("referido_cambiado", False),
    }
    return web.json_response(result)

async def api_profiles_handler(request):
    profiles = []
    for p in state.perfiles:
        pct = 0
        time_str = "0m"
        url = p.get("url", "")
        if p.get("estado") == "active" and p.get("inicio"):
            try:
                inicio = datetime.fromisoformat(p["inicio"])
                now = datetime.now()
                elapsed = (now - inicio).total_seconds() / 60
                pct = min(100, int((elapsed / 62) * 100))
                time_str = f"{int(elapsed)}m"
            except Exception:
                pass
        profiles.append({
            "perfil_id": p.get("perfil_id", ""),
            "nombre": p.get("nombre", p.get("perfil_id", "")),
            "tipo": p.get("tipo", "local"),
            "estado": p.get("estado", "inactive"),
            "url": url,
            "tiempo": time_str,
            "progreso_pct": pct,
        })
    return web.json_response({"profiles": profiles, "counts": state.to_dict()["counts"]})

async def api_recargar_perfiles_handler(request):
    try:
        from roxybrowser_api import RoxyBrowserAPI
        api = RoxyBrowserAPI()
        perfiles = await api.get_profiles()
        if perfiles:
            state.perfiles = perfiles
            log.info(f"perfiles recargados: {len(perfiles)}")
            return web.json_response({"ok": True, "count": len(perfiles)})
    except Exception as e:
        log.warning(f"error recargando perfiles: {e}")
    return web.json_response({"ok": False, "error": "no se pudieron recargar perfiles"})

async def api_modo_handler(request):
    try:
        data = await request.json()
        modo = data.get("modo", "pidiendo_ordenes")
        if modo not in ("pidiendo_ordenes", "uso_personal"):
            return web.json_response({"error": "modo invalido"}, status=400)
        state.modo = modo
        log.info(f"modo cambiado a: {modo}")
        return web.json_response({"ok": True, "modo": modo})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=400)

async def api_ordenes_activas_handler(request):
    return web.json_response({"ordenes": state.ordenes_activas})

async def proxy_handler(request):
    path = request.match_info.get("path", "")
    return await proxy_to_pcmaster(request, "/" + path)

def create_app():
    app = web.Application()
    app.router.add_get("/", index_handler)
    app.router.add_get("/portal.html", index_handler)
    app.router.add_get("/static/{filename:.*}", static_handler)
    app.router.add_get("/api/estado", api_estado_handler)
    app.router.add_get("/api/dashboard", api_dashboard_handler)
    app.router.add_get("/api/profiles", api_profiles_handler)
    app.router.add_post("/api/recargar_perfiles", api_recargar_perfiles_handler)
    app.router.add_post("/api/modo", api_modo_handler)
    app.router.add_get("/api/ordenes_activas", api_ordenes_activas_handler)
    app.router.add_route("*", "/api/{path:.*}", proxy_handler)
    return app

async def start_portal(pcmaster_ws=None, pcmaster_api=None, local_port=None):
    global PCMASTER_WS, PCMASTER_API, LOCAL_PORT
    if pcmaster_ws:
        PCMASTER_WS = pcmaster_ws
    if pcmaster_api:
        PCMASTER_API = pcmaster_api
    if local_port:
        LOCAL_PORT = local_port
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", LOCAL_PORT)
    await site.start()
    log.info(f"portal http iniciado en http://0.0.0.0:{LOCAL_PORT}")
    return runner

async def stop_portal(runner):
    await runner.cleanup()
    global _http_session
    if _http_session and not _http_session.closed:
        await _http_session.close()

if __name__ == "__main__":
    async def main():
        await start_portal()
        while True:
            await asyncio.sleep(3600)
    asyncio.run(main())
