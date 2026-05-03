# server.py - punto de entrada fastapi + websocket. roxymaster v8.3
# utf-8 sin bom, nombres en minusculas, <= 400 lineas

import asyncio
import json
import logging
import sys
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from config_loader import cargar_configuracion
from db import init_db as inicializar_db, get_db, ejecutar_sql_unico
from shs import firmar_payload as firmar_mensaje, verificar_payload
import websockets
from orchestrator import (
    gestor_websockets,
    cola_comandos,
    procesar_mensaje_ws,
    manejar_conexion_pcbot,
)
from tasks import iniciar_tareas_periodicas, inicializar_registros_tareas
from tokenomics import inicializar_tokenomics, emitir_kbt_admin

from api_auth import router as router_auth
from api_kbt import router as router_kbt
from api_dashboard import router as router_dashboard
from api_marketplace import router as router_marketplace
from api_comandos import router as router_comandos
from api_admin import router as router_admin
from api_superadmin import router as router_superadmin
from api_mensajes import router as router_mensajes
from api_tokenomia import router as router_tokenomia
from api_pedidos import router as router_pedidos
from api_monitoreo import router as router_monitoreo
from api_encriptacion import router as router_encriptacion
from api_version import router as router_version

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s", handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger("roxymaster.server")

config = {}
tarea_fondo = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global tarea_fondo
    logger.info("iniciando roxymaster server v8.3...")
    config.update(cargar_configuracion())
    logger.info(f"configuracion cargada desde {config.get('archivo_config', 'config.json')}")
    db_path = config.get("db_path", "data/roxymaster.db")
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else "data", exist_ok=True)
    inicializar_db()
    logger.info(f"base de datos inicializada: {db_path}")
    inicializar_tokenomics()
    inicializar_registros_tareas()
    from auth import registrar_usuario
    admin_email = config.get("admin_email", "admin@roxymaster.local")
    admin_pass = config.get("admin_password", "admin123")
    existente = get_db().execute("select id from usuarios where email = ?", (admin_email,)).fetchone()
    if not existente:
        resultado = registrar_usuario(email=admin_email, password=admin_pass, username="admin", codigo_referido_externo=None, pcbot_id="pcmaster")
        if resultado.get("exito"):
            from db import ejecutar_sql
            ejecutar_sql("update usuarios set rol = 'admin' where email = ?", (admin_email,))
            logger.info(f"usuario admin creado: {admin_email}")
        else:
            logger.warning(f"no se pudo crear admin: {resultado.get('error')}")
    tarea_fondo = asyncio.create_task(iniciar_tareas_periodicas())
    logger.info("tareas periodicas iniciadas")
    yield
    logger.info("deteniendo servidor...")
    if tarea_fondo:
        tarea_fondo.cancel()
        try:
            await tarea_fondo
        except asyncio.CancelledError:
            pass


app = FastAPI(title="roxymaster api v8.3", description="api central del ecosistema roxymaster kbt", version="8.3.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(router_auth)
app.include_router(router_kbt)
app.include_router(router_dashboard)
app.include_router(router_marketplace)
app.include_router(router_comandos)
app.include_router(router_admin)
app.include_router(router_superadmin)
app.include_router(router_mensajes)
app.include_router(router_tokenomia)
app.include_router(router_pedidos)
app.include_router(router_monitoreo)
app.include_router(router_encriptacion)
app.include_router(router_version)

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    logger.info("archivos estaticos servidos desde %s", static_dir)

logger.info("routers registrados: auth, kbt, dashboard, marketplace, comandos, admin, superadmin, mensajes, tokenomia, pedidos, monitoreo, encriptacion, version")


@app.get("/")
async def raiz():
    portal_path = os.path.join(os.path.dirname(__file__), "portal.html")
    if os.path.exists(portal_path):
        return FileResponse(portal_path, media_type="text/html")
    return {"sistema": "roxymaster", "version": "8.3.0", "estado": "operativo", "timestamp": datetime.now().isoformat()}


# ===== websocket de monitoreo admin =====
conexiones_monitoreo: dict = {}


@app.websocket("/ws/admin/monitor")
async def websocket_monitoreo(websocket: WebSocket):
    """websocket que transmite metricas del sistema a paneles admin."""
    await websocket.accept()
    conexion_id = f"monitor_{datetime.now().timestamp()}"
    conexiones_monitoreo[conexion_id] = websocket
    logger.info("cliente de monitoreo conectado")
    try:
        while True:
            try:
                usuarios_hoy = ejecutar_sql_unico("select count(*) as total from sesiones where date(fecha_creacion) = date('now','localtime')")
                usuarios_hoy = usuarios_hoy["total"] if usuarios_hoy else 0
                pcs = ejecutar_sql_unico("select count(*) as total from usuarios where pcbot_id is not null")
                pcs = pcs["total"] if pcs else 0
                pcs_online = ejecutar_sql_unico("select count(*) as total from usuarios where pcbot_id is not null and modo = 'conectado'")
                pcs_online = pcs_online["total"] if pcs_online else 0
                metricas = {
                    "tipo": "monitoreo",
                    "timestamp": datetime.now().isoformat(),
                    "pcbots_conectados": len(gestor_websockets),
                    "comandos_pendientes": len(cola_comandos),
                    "usuarios_conectados_hoy": usuarios_hoy,
                    "pcs_registradas": pcs,
                    "pcs_online": pcs_online,
                }
                await websocket.send_json(metricas)
            except Exception as e:
                logger.warning(f"error enviando metricas monitoreo: {e}")
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        logger.info("cliente de monitoreo desconectado")
    except Exception as e:
        logger.error(f"error en monitoreo ws: {e}")
    finally:
        conexiones_monitoreo.pop(conexion_id, None)


@app.websocket("/ws/{pcbot_id}")
async def websocket_pcbot(websocket: WebSocket, pcbot_id: str):
    await websocket.accept()
    logger.info(f"pcbot conectado via ws: {pcbot_id}")
    gestor_websockets[pcbot_id] = {"ws": websocket, "conectado_desde": datetime.now().isoformat(), "ultimo_heartbeat": datetime.now().isoformat()}
    handshake = firmar_mensaje({"tipo": "handshake", "servidor": "pcmaster", "version": "8.3.0"})
    await websocket.send_json(handshake)
    try:
        from db import ejecutar_sql
        ejecutar_sql("update usuarios set modo = 'conectado', pcbot_id = ? where pcbot_id = ?", (pcbot_id, pcbot_id))
    except Exception:
        pass
    try:
        while True:
            data = await websocket.receive_json()
            if not verificar_payload(data):
                logger.warning(f"firma invalida de {pcbot_id}")
                await websocket.send_json({"tipo": "error", "mensaje": "firma invalida"})
                continue
            mensaje = {k: v for k, v in data.items() if k not in ("timestamp", "signature")}
            respuesta = await procesar_mensaje_ws(pcbot_id, mensaje)
            if respuesta:
                await websocket.send_json(firmar_mensaje(respuesta))
            gestor_websockets[pcbot_id]["ultimo_heartbeat"] = datetime.now().isoformat()
    except WebSocketDisconnect:
        logger.info(f"pcbot desconectado: {pcbot_id}")
        gestor_websockets.pop(pcbot_id, None)
        try:
            from db import ejecutar_sql
            ejecutar_sql("update usuarios set modo = 'desconectado' where pcbot_id = ?", (pcbot_id,))
        except Exception:
            pass
    except Exception as e:
        logger.error(f"error en ws de {pcbot_id}: {e}")
        gestor_websockets.pop(pcbot_id, None)


@app.get("/api/health")
async def health_check():
    return {"estado": "saludable", "pcbots_conectados": len(gestor_websockets), "comandos_pendientes": len(cola_comandos), "timestamp": datetime.now().isoformat()}


class _WsAdapter:
    def __init__(self, ws):
        self._ws = ws

    async def receive_text(self):
        return await self._ws.recv()

    async def send_json(self, data):
        await self._ws.send(json.dumps(data))

    async def close(self):
        await self._ws.close()


async def iniciar_ws_externo():
    async def handler(websocket):
        await manejar_conexion_pcbot(_WsAdapter(websocket), "anonimo")
    logger.info("websocket externo iniciado en 0.0.0.0:5006")
    await websockets.serve(handler, "0.0.0.0", 5006)


if __name__ == "__main__":
    _cfg = cargar_configuracion()
    host = _cfg.get("host", "0.0.0.0")
    puerto = _cfg.get("puerto", 8086)

    async def main():
        ws_task = asyncio.create_task(iniciar_ws_externo())
        logger.info(f"iniciando fastapi en {host}:{puerto}")
        uvicorn_config = uvicorn.Config("server:app", host=host, port=puerto, reload=False, log_level="info")
        uvicorn_server = uvicorn.Server(uvicorn_config)
        await uvicorn_server.serve()

    asyncio.run(main())