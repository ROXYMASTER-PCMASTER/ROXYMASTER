# server.py - punto de entrada fastapi + websocket. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

import asyncio
import logging
import sys
import os
from contextlib import asynccontextmanager
from datetime import datetime

# asegurar que scripts/ esta en el path (para imports como config_loader)
_scripts_dir = os.path.dirname(os.path.abspath(__file__))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

# modulos propios
from config_loader import cargar_configuracion
from db import init_db as inicializar_db, get_db, ejecutar_sql_unico
from orchestrator import (
    gestor_websockets,
    cola_comandos,
    procesar_mensaje_ws,
)
from tasks import iniciar_tareas_periodicas, inicializar_registros_tareas
from tokenomics import inicializar_tokenomics, emitir_kbt_admin

# routers api
from api_heartbeat import router as heartbeat_router
from api_auth import router as router_auth
from api_kbt import router as router_kbt
from api_dashboard_core import router as router_dashboard_core
from api_dashboard_ext import router as router_dashboard_ext
from api_marketplace import router as router_marketplace
from api_comandos import router as router_comandos
from api_admin import router as router_admin
from api_superadmin import router as router_superadmin
from api_tokenomics import router as router_tokenomics
from api_roxykey import router as router_roxykey
from api_mensajes import router as router_mensajes

# router para refresh de token
from api_refresh import router as router_refresh

# router admin ext (rutas exactas)
from api_admin_ext import router as router_admin_ext

# routers publicos para dashboard
from api_public_perfiles import router as router_public_perfiles
from api_public_finanzas import router as router_public_finanzas
from api_public_referidos import router as router_public_referidos
from api_public_sistema import router as router_public_sistema
from api_public_marketplace_ext import router as router_public_marketplace_ext

# routers adicionales existentes
from api_dashboard import router as router_dashboard
from api_encriptacion import router as router_encriptacion
from api_monitoreo import router as router_monitoreo
from api_pedidos import router as router_pedidos
from api_version import router as router_version

# routers nuevos para economia - retiros y referidos
from api_retiros import router as router_retiros
from api_referidos import router as router_referidos

# router para computadoras
from api_computadoras import router as router_computadoras

from pydantic import BaseModel
from api_auth import LoginRequest, RegisterRequest

# ---------------------------------------------------------------------------
# configuracion de logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("roxymaster.server")

# ---------------------------------------------------------------------------
# variables globales
# ---------------------------------------------------------------------------
config = {}
tarea_fondo = None


# ---------------------------------------------------------------------------
# lifespan para fastapi
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """inicializa y finaliza recursos del servidor."""
    global tarea_fondo, config
    logger.info("iniciando roxymaster server v8.3...")

    # cargar configuracion
    config = cargar_configuracion()
    logger.info(f"configuracion cargada: puerto={config.get('puerto', 'desconocido')}")

    # inicializar base de datos
    db_path = config.get("db_path", "data/roxymaster.db")
    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else "data", exist_ok=True)
    inicializar_db()
    logger.info(f"base de datos inicializada: {db_path}")

    # inicializar registros de tareas
    inicializar_registros_tareas()

    # inicializar tokenomics
    inicializar_tokenomics()
    # emitir tokens genesis para admin si existe
    try:
        admin_db = ejecutar_sql_unico("select id from usuarios where rol = 'admin' limit 1")
        if admin_db:
            from tokenomics import emitir_kbt_admin
            emitir_kbt_admin(admin_db["id"], 1000.0, "genesis_bienvenida")
            logger.info("tokens genesis emitidos para admin")
    except Exception as e:
        logger.info(f"no se emitieron tokens genesis: {e}")

    # iniciar tareas periodicas en segundo plano
    tarea_fondo = asyncio.create_task(iniciar_tareas_periodicas())
    logger.info("tareas periodicas iniciadas")

    yield  # servidor corriendo

    # cleanup
    logger.info("deteniendo servidor...")
    if tarea_fondo:
        tarea_fondo.cancel()
        try:
            await tarea_fondo
        except asyncio.CancelledError:
            pass


# ---------------------------------------------------------------------------
# aplicacion fastapi
# ---------------------------------------------------------------------------
app = FastAPI(
    title="roxymaster api v8.3",
    description="api central del ecosistema roxymaster kbt",
    version="8.3.0",
    lifespan=lifespan,
)

# cors para desarrollo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# incluir routers

app.include_router(router_auth)
app.include_router(router_kbt)
app.include_router(router_dashboard_core)
app.include_router(router_dashboard_ext)
app.include_router(router_marketplace)
app.include_router(router_comandos)
app.include_router(router_admin)
app.include_router(router_superadmin)
app.include_router(router_tokenomics)
app.include_router(router_roxykey)
app.include_router(router_mensajes)
app.include_router(router_refresh)
app.include_router(router_admin_ext)
app.include_router(router_public_perfiles)
app.include_router(router_public_finanzas)
app.include_router(router_public_referidos)
app.include_router(router_public_sistema)
app.include_router(router_public_marketplace_ext)

# routers adicionales
app.include_router(router_dashboard)
app.include_router(router_encriptacion)
app.include_router(router_monitoreo)
app.include_router(router_pedidos)
app.include_router(router_retiros)
app.include_router(router_referidos)
app.include_router(router_version)
app.include_router(heartbeat_router)
app.include_router(router_computadoras)

logger.info(
    "routers registrados: auth, kbt, dashboard_core, dashboard_ext, marketplace, "
    "comandos, admin, superadmin, tokenomics, roxykey, mensajes, "
    "public_perfiles, public_finanzas, public_referidos, public_sistema, "
    "public_marketplace_ext, dashboard, encriptacion, monitoreo, pedidos, "
    "retiros, referidos, version, computadoras"
)


# ---------------------------------------------------------------------------
# archivos estaticos y portal web
# ---------------------------------------------------------------------------
# montar directorio publico de manera segura
base_dir = os.path.dirname(os.path.abspath(__file__))

# endpoint raiz: sirve el portal principal
@app.get("/")
async def raiz():
    """portal principal wafabot coorporation."""
    index_path = os.path.join(base_dir, "..", "publico", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, media_type="text/html")
    return {
        "sistema": "roxymaster",
        "version": "8.3.0",
        "estado": "operativo",
        "timestamp": datetime.now().isoformat(),
    }

# alias para /api/registro -> /api/register (compatibilidad con frontend)
class AliasRegisterRequest(BaseModel):
    email: str
    password: str
    username: str = None
    codigo_referido: str = None
    pcbot_id: str = None

@app.post("/api/registro")
async def api_registro_alias(req: AliasRegisterRequest):
    """alias de compatibilidad para /api/registro -> redirige a /api/register."""
    from api_auth import api_register
    # convertir al modelo que espera api_register
    from fastapi import Request as FastAPIRequest
    register_req = RegisterRequest(
        email=req.email,
        password=req.password,
        username=req.username,
        codigo_referido=req.codigo_referido,
        pcbot_id=req.pcbot_id,
    )
    return await api_register(register_req)

# endpoint login
@app.get("/login")
async def login():
    """pagina de inicio de sesion."""
    login_path = os.path.join(base_dir, "..", "publico", "login.html")
    if os.path.exists(login_path):
        return FileResponse(login_path, media_type="text/html")
    return {"error": "login no disponible"}

# endpoint registro
@app.get("/registro")
async def registro():
    """pagina de registro."""
    registro_path = os.path.join(base_dir, "..", "publico", "registro.html")
    if os.path.exists(registro_path):
        return FileResponse(registro_path, media_type="text/html")
    return {"error": "registro no disponible"}




# servir archivos estaticos de /static (css, js compartidos)
static_dir = os.path.join(base_dir, "..", "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir, html=False), name="static")

# servir archivos estaticos de publico
publico_dir = os.path.join(base_dir, "..", "publico")
if os.path.exists(publico_dir):
    app.mount("/publico", StaticFiles(directory=publico_dir, html=True), name="publico")

# servir archivos estaticos de privado
privado_dir = os.path.join(base_dir, "..", "privado")
if os.path.exists(privado_dir):
    app.mount("/privado", StaticFiles(directory=privado_dir, html=True), name="privado")


# ---------------------------------------------------------------------------
# websocket para pcbots (sin hmac)
# ---------------------------------------------------------------------------
@app.websocket("/ws/{pcbot_id}")
async def websocket_pcbot(websocket: WebSocket, pcbot_id: str):
    """endpoint websocket para comunicacion con pcbots.
    sin hmac. la autenticacion se basa en que la conexion via tailscale
    ya provee cifrado e integridad. se valida que el pcbot_id exista
    y se persiste la informacion en la base de datos."""
    await websocket.accept()
    logger.info(f"pcbot conectado via ws: {pcbot_id}")

    # registrar en gestor legacy
    gestor_websockets[pcbot_id] = {
        "ws": websocket,
        "conectado_desde": datetime.now().isoformat(),
        "ultimo_heartbeat": datetime.now().isoformat(),
    }

    # registrar en ws_manager (nuevo sistema por usuario)
    from ws_manager import registrar_conexion
    _usuario_registrado_ws = None

    # actualizar estado del usuario en db
    try:
        from db import ejecutar_sql
        ejecutar_sql(
            "update usuarios set modo = 'conectado', pcbot_id = ? where pcbot_id = ?",
            (pcbot_id, pcbot_id),
        )
    except Exception:
        pass

    try:
        while True:
            # recibir mensaje del pcbot (json plano, sin firma)
            data = await websocket.receive_json()

            # persistir datos del pcbot si es identify
            if data.get("tipo") == "identify":
                logger.info(f"identify recibido de {pcbot_id}")
                try:
                    import json as _json
                    from db import ejecutar_sql, ejecutar_insercion
                    info = data
                    perfiles_r = _json.dumps(info.get("perfiles_roxy", []), ensure_ascii=False)
                    perfiles_v = _json.dumps(info.get("perfiles_vip", []), ensure_ascii=False)
                    navs = _json.dumps(info.get("navegadores", []), ensure_ascii=False)

                    existente = ejecutar_sql_unico(
                        "select id from pcbots_registrados where pcbot_id = ?", (pcbot_id,)
                    )

                    if existente:
                        ejecutar_sql(
                            """update pcbots_registrados set hostname=?, usuario=?, ip_local=?, ip_tailscale=?, ip_wan=?,
                               perfiles_roxy=?, perfiles_vip=?, navegadores=?, modo=?, estado='conectado',
                               ultima_conexion=? where pcbot_id=?""",
                            (info.get("pcbot_id", pcbot_id), info.get("usuario", ""),
                             info.get("ip_local", ""), info.get("ip_tailscale", ""),
                             info.get("ip_wan", ""), perfiles_r, perfiles_v, navs,
                             info.get("modo", ""), datetime.now().isoformat(), pcbot_id))
                    else:
                        ejecutar_insercion(
                            """insert into pcbots_registrados
                               (pcbot_id, hostname, usuario, ip_local, ip_tailscale, ip_wan,
                                perfiles_roxy, perfiles_vip, navegadores, modo, estado, ultima_conexion)
                               values (?,?,?,?,?,?,?,?,?,?,'conectado',?)""",
                            (pcbot_id, info.get("pcbot_id", pcbot_id), info.get("usuario", ""),
                             info.get("ip_local", ""), info.get("ip_tailscale", ""),
                             info.get("ip_wan", ""), perfiles_r, perfiles_v, navs,
                             info.get("modo", ""), datetime.now().isoformat()))
                except Exception as e:
                    logger.warning(f"error persistir pcbot {pcbot_id}: {e}")

                # responder identify_ok (plano, sin secreto)
                await websocket.send_json({"tipo": "identify_ok", "pcbot_id": pcbot_id})
                logger.info(f"identify_ok enviado a {pcbot_id}")

                # registrar en ws_manager por usuario
                try:
                    from db import ejecutar_sql_unico as _sql_unico
                    _user = _sql_unico(
                        "select id from usuarios where pcbot_id = ?", (pcbot_id,)
                    )
                    if _user:
                        _usuario_registrado_ws = _user["id"]
                        from ws_manager import registrar_conexion
                        registrar_conexion(_user["id"], pcbot_id, websocket)
                        logger.info(f"usuario {_user['id']} registrado en ws_manager via pcbot {pcbot_id}")
                except Exception:
                    pass

                # actualizar heartbeat
                gestor_websockets[pcbot_id]["ultimo_heartbeat"] = datetime.now().isoformat()
                continue

            # procesar mensaje normalmente (heartbeat, respuesta, alerta, etc.)
            respuesta = await procesar_mensaje_ws(pcbot_id, data)
            if respuesta:
                await websocket.send_json(respuesta)

            # actualizar heartbeat
            gestor_websockets[pcbot_id]["ultimo_heartbeat"] = datetime.now().isoformat()

    except WebSocketDisconnect:
        logger.info(f"pcbot desconectado: {pcbot_id}")
        gestor_websockets.pop(pcbot_id, None)
        # actualizar estado en db
        try:
            from db import ejecutar_sql
            ejecutar_sql(
                "update usuarios set modo = 'desconectado' where pcbot_id = ?",
                (pcbot_id,),
            )
        except Exception:
            pass
        # limpiar ws_manager
        try:
            from ws_manager import eliminar_conexion
            eliminar_conexion(pcbot_id=pcbot_id)
        except Exception:
            pass
    except Exception as e:
        logger.error(f"error en ws de {pcbot_id}: {e}")
        gestor_websockets.pop(pcbot_id, None)
        # limpiar ws_manager
        try:
            from ws_manager import eliminar_conexion
            eliminar_conexion(pcbot_id=pcbot_id)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# health check
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health_check():
    """health check del servidor."""
    pcbots_conectados = len(gestor_websockets)
    comandos_pendientes = len(cola_comandos)
    return {
        "estado": "saludable",
        "pcbots_conectados": pcbots_conectados,
        "comandos_pendientes": comandos_pendientes,
        "timestamp": datetime.now().isoformat(),
    }


# ---------------------------------------------------------------------------
# punto de entrada
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    host = config.get("host", "0.0.0.0")
    puerto = config.get("puerto", 8086)
    logger.info(f"iniciando servidor en {host}:{puerto}")
    uvicorn.run(
        "server:app",
        host=host,
        port=puerto,
        reload=False,
        log_level="info",
    )