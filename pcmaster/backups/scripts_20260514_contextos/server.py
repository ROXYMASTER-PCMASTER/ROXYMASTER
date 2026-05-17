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
)
from orchestrator_ext import procesar_mensaje_ws
from tasks import iniciar_tareas_periodicas, inicializar_registros_tareas
from tokenomics import inicializar_tokenomics, emitir_kbt_admin
from db_pedidos_vigilante import crear_tablas_vigilante
from pedidos_vigilante import monitorear_pedidos
from procesador_cola import ejecutar_ciclo_match

# routers api
from api_heartbeat import router as heartbeat_router
from api_auth import router as router_auth
from api_kbt import router as router_kbt
from api_dashboard_core import router as router_dashboard_core
from api_dashboard_ext import router as router_dashboard_ext
from api_marketplace import router as router_marketplace
from api_comandos import router as router_comandos
from api_admin import router as router_admin
from api_admin_usuarios import router as router_admin_usuarios
from api_admin_pedidos import router as router_admin_pedidos
from api_admin_perfiles import router as router_admin_perfiles
from api_admin_pcbots import router as router_admin_pcbots
from api_admin_config import router as router_admin_config
from api_admin_acciones import router as router_admin_acciones
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

# router para acciones de pedidos (eliminar, detener)
from api_pedidos_acciones import router as router_pedidos_acciones

# router para agendamiento de pedidos por hora
from api_pedidos_agendamiento import router as router_pedidos_agendamiento

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

    # agregar columnas de agendamiento si no existen
    try:
        from db_pedidos_ext import agregar_columnas_agendamiento, agregar_columna_timeout
        agregar_columnas_agendamiento()
        agregar_columna_timeout()
        logger.info("columnas de agendamiento y timeout verificadas/agregadas")
    except Exception as e:
        logger.warning(f"no se pudieron agregar columnas de agendamiento: {e}")
    # crear tabla contextos_streamer
    try:
        from db_pedidos_ext import crear_tabla_contextos_streamer
        crear_tabla_contextos_streamer()
        logger.info("tabla contextos_streamer verificada/creada")
    except Exception as e:
        logger.warning(f"no se pudo crear tabla contextos_streamer: {e}")
    # crear tablas del vigilante de pedidos
    try:
        await crear_tablas_vigilante()
        logger.info("tablas del vigilante de pedidos creadas")
    except Exception as e:
        logger.warning(f"no se pudieron crear tablas vigilante: {e}")

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
    # iniciar vigilante de pedidos
    tarea_vigilante = asyncio.create_task(monitorear_pedidos())
    logger.info("vigilante de pedidos iniciado")

    # procesador de cola: ahora se ejecuta bajo demanda tras heartbeats
    # no hay bucle continuo; el match se dispara desde orchestrator
    logger.info("procesador de cola (bajo demanda) listo - no hay bucle continuo")

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
app.include_router(router_pedidos_acciones)
app.include_router(router_pedidos_agendamiento)

# nuevos routers de admin superadmin
app.include_router(router_admin_usuarios)
app.include_router(router_admin_pedidos)
app.include_router(router_admin_perfiles)
app.include_router(router_admin_pcbots)
app.include_router(router_admin_config)
app.include_router(router_admin_acciones)

logger.info(
    "routers registrados: auth, kbt, dashboard_core, dashboard_ext, marketplace, "
    "comandos, admin, superadmin, tokenomics, roxykey, mensajes, "
    "public_perfiles, public_finanzas, public_referidos, public_sistema, "
    "public_marketplace_ext, dashboard, encriptacion, monitoreo, pedidos, "
    "retiros, referidos, version, computadoras, pedidos_acciones, pedidos_agendamiento, "
    "admin_usuarios, admin_pedidos, admin_perfiles, admin_pcbots, admin_config, admin_acciones"
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

# redirecciones de compatibilidad para rutas sin prefijo /publico/
@app.get("/dashboard_publico.html")
async def dashboard_publico_redirect():
    """redirige a la ruta correcta con prefijo /publico/."""
    dashboard_path = os.path.join(base_dir, "..", "publico", "dashboard_publico.html")
    if os.path.exists(dashboard_path):
        return FileResponse(dashboard_path, media_type="text/html")
    return RedirectResponse(url="/publico/dashboard_publico.html")

@app.get("/dashboard")
async def dashboard_redirect():
    """redirige a la ruta correcta con prefijo /publico/."""
    return RedirectResponse(url="/publico/dashboard_publico.html")

@app.get("/pedidos")
async def pedidos_page():
    """pagina de gestion de pedidos."""
    pedidos_path = os.path.join(base_dir, "..", "publico", "pedidos.html")
    if os.path.exists(pedidos_path):
        return FileResponse(pedidos_path, media_type="text/html")
    return RedirectResponse(url="/publico/pedidos.html")

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
# websocket para pcbots (sin hmac) - delegado a server_ws_handler.py
# ---------------------------------------------------------------------------
@app.websocket("/ws/{pcbot_id}")
async def websocket_pcbot(websocket: WebSocket, pcbot_id: str):
    """endpoint websocket para comunicacion con pcbots.
    delegado a server_ws_handler.py para mantener el limite de lineas."""
    from server_ws_handler import manejar_websocket_pcbot
    await manejar_websocket_pcbot(websocket, pcbot_id, gestor_websockets)


# ---------------------------------------------------------------------------
# diagnostic endpoint
# ---------------------------------------------------------------------------
@app.get("/api/diag_cola")
async def diag_cola():
    """diagnostico del procesador de cola"""
    import asyncio
    import json
    from ws_manager import listar_conexiones, obtener_pcbots_de_usuario, _conexiones_por_pcbot, _conexiones_por_usuario
    import heartbeat_cache

    resultado = {
        "conexiones_ws": listar_conexiones(),
        "claves_conexiones_por_usuario": list(_conexiones_por_usuario.keys()),
        "claves_conexiones_por_pcbot": list(_conexiones_por_pcbot.keys()),
        "heartbeat_cache_pcbots": list(heartbeat_cache._cache.keys()) if hasattr(heartbeat_cache, '_cache') else [],
        "timestamp": datetime.now().isoformat(),
    }

    # agregar detalle de cada pcbot en cache de heartbeat
    resultado["heartbeat_detalle"] = {}
    for pcbot_id in resultado["heartbeat_cache_pcbots"]:
        hb = heartbeat_cache.obtener_heartbeat(pcbot_id)
        resultado["heartbeat_detalle"][pcbot_id] = {
            "perfiles_activos": [p for p in hb.get("perfiles", []) if p.get("activo")],
            "perfiles_inactivos": [p for p in hb.get("perfiles", []) if not p.get("activo")],
            "recibido_en": hb.get("recibido_en", ""),
        }

    # detalle de cada conexion por pcbot
    resultado["conexiones_por_pcbot_detalle"] = {}
    for pid, info in _conexiones_por_pcbot.items():
        resultado["conexiones_por_pcbot_detalle"][pid] = {
            "usuario_id": info.get("usuario_id"),
            "conectado_desde": info.get("conectado_desde", ""),
        }

    # pedidos pendientes
    try:
        from db import ejecutar_sql
        pedidos = ejecutar_sql("select id, usuario_id, url, cantidad_perfiles, duracion_horas, estado, fecha_creacion from pedidos where estado in ('agendado','programado') order by fecha_creacion asc", fetchall=True)
        resultado["pedidos_pendientes"] = []
        for p in pedidos:
            resultado["pedidos_pendientes"].append({
                "id": p[0], "usuario_id": p[1], "url": p[2],
                "cantidad_perfiles": p[3], "duracion_horas": p[4],
                "estado": p[5], "fecha_creacion": p[6],
            })
    except Exception as e:
        resultado["error_pedidos"] = str(e)

    return resultado

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