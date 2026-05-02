# server.py - orquestador principal roxymaster v8.3
import asyncio, sys, logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
import uvicorn, websockets

_base_dir = Path(__file__).parent.parent.absolute()
_scripts_dir = _base_dir / "scripts"
_data_dir = _base_dir / "data"
_portal_html = _base_dir / "portal.html"
sys.path.insert(0, str(_scripts_dir))

from variables_globales import WS_HOST, WS_PORT, HTTP_HOST, HTTP_PORT, SECRETO_SISTEMA
from database import init_all_databases
from tasks import tarea_quema_diaria, tarea_limpieza_pcbots
from ws_handler import manejar_conexion, _WebSocketServerProxy
from orchestrator import set_ws_server

# importar routers de API
from api_auth import router as auth_router
from api_dashboard import router as dashboard_router
from api_comandos import router as comandos_router
from api_kbt import router as kbt_router
from api_marketplace import router as marketplace_router
from api_admin import router as admin_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("roxymaster")

app = FastAPI(title="roxymaster api v8.3", version="8.3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# montar routers
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(comandos_router)
app.include_router(kbt_router)
app.include_router(marketplace_router)
app.include_router(admin_router)

@app.get("/")
async def raiz():
    if _portal_html.exists():
        return FileResponse(str(_portal_html), media_type="text/html")
    return HTMLResponse("<h1>roxymaster v8.3</h1>")

@app.get("/portal.html")
async def portal():
    if _portal_html.exists():
        return FileResponse(str(_portal_html), media_type="text/html")
    return HTMLResponse("<h1>portal no encontrado</h1>", status_code=404)

async def iniciar_websocket():
    logger.info(f"[ws] {WS_HOST}:{WS_PORT}")
    async with websockets.serve(manejar_conexion, WS_HOST, WS_PORT, ping_interval=30, ping_timeout=10, close_timeout=5, max_size=10*1024*1024):
        await asyncio.Future()

async def iniciar_http():
    config = uvicorn.Config(app, host=HTTP_HOST, port=HTTP_PORT, log_level="warning", access_log=False)
    await uvicorn.Server(config).serve()

async def main():
    init_all_databases()
    set_ws_server(_WebSocketServerProxy())
    asyncio.create_task(tarea_quema_diaria())
    asyncio.create_task(tarea_limpieza_pcbots())
    print(f'\n{"="*60}')
    print(f"  roxymaster v8.3 - pcmaster server")
    print(f"  ws:  {WS_HOST}:{WS_PORT}")
    print(f"  http: {HTTP_HOST}:{HTTP_PORT}")
    print(f'{"="*60}\n')
    await asyncio.gather(iniciar_websocket(), iniciar_http())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nservidor detenido.")
    except Exception as e:
        logger.error(f"error fatal: {e}")
        raise