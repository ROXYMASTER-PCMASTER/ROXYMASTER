from fastapi import APIRouter, Request
from marketplace import listar_ordenes_activas, crear_orden, ejecutar_orden, cancelar_orden, obtener_historial_ordenes
from tokenomics import obtener_wallet_por_usuario
from auth import verificar_token
router = APIRouter()

async def verificar_auth(request: Request):
    token = request.headers.get("x-token") or request.headers.get("authorization", "").replace("Bearer ", "")
    if not token:
        return None
    return verificar_token(token)

@router.get("/api/marketplace/ordenes")
async def api_ordenes(request: Request):
    return {"ok": True, "ordenes": listar_ordenes_activas()}

@router.post("/api/marketplace/crear")
async def api_crear(request: Request):
    auth = await verificar_auth(request)
    if not auth:
        return {"ok": False}
    data = await request.json()
    return crear_orden(data.get("tipo","venta"), obtener_wallet_por_usuario(auth[0]), auth[0], data.get("cantidad",0), data.get("precio", 0.0))

@router.post("/api/marketplace/cancelar")
async def api_cancelar(request: Request):
    data = await request.json()
    return cancelar_orden(data.get("orden_id",""))