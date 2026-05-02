from fastapi import APIRouter, Request
from ws_handler import _pcbots_conectados, _perfiles_globales
from orchestrator import asignar_url, activar_comentarios, detener_url, broadcast_comando, cancelar_comando, obtener_comandos_pendientes, obtener_historial_comandos, obtener_urls_asignadas, obtener_sesiones_activas
from auth import verificar_token
router = APIRouter()

async def verificar_auth(request: Request):
    token = request.headers.get("x-token") or request.headers.get("authorization", "").replace("Bearer ", "")
    if not token:
        return None
    return verificar_token(token)

@router.post("/api/comando")
async def api_comando(request: Request):
    auth = await verificar_auth(request)
    if not auth:
        return {"ok": False, "error": "no autenticado"}
    data = await request.json()
    accion = data.get("accion", "")
    params = data.get("params", {})
    if accion == "asignar_url":
        return await asignar_url(url=params.get("url",""), perfiles=params.get("perfiles",1), duracion=params.get("duracion",60))
    elif accion == "activar_comentarios":
        return await activar_comentarios(params.get("url",""), auth[1])
    elif accion == "detener":
        return await detener_url(params.get("url",""))
    else:
        return {"ok": False, "error": f"accion desconocida: {accion}"}

@router.get("/api/urls")
async def api_urls(request: Request):
    return {"ok": True, "urls": obtener_urls_asignadas()}