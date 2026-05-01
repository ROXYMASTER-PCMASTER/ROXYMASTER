from fastapi import APIRouter, Request
from ws_handler import _pcbots_conectados, _perfiles_globales
from tokenomics import obtener_balance, obtener_wallet_por_usuario, obtener_estadisticas_kbt
from orchestrator import obtener_urls_asignadas, obtener_historial_comandos
from shs import obtener_eventos_seguridad
from auth import verificar_token
router = APIRouter()

async def verificar_auth(request: Request):
    token = request.headers.get("x-token") or request.headers.get("authorization", "").replace("Bearer ", "")
    if not token:
        return None
    return verificar_token(token)

@router.get("/api/dashboard")
async def api_dashboard(request: Request):
    auth = await verificar_auth(request)
    if not auth:
        return {"ok": False, "error": "no autenticado"}
    uid, username, rol = auth
    total_pcbots = len(_pcbots_conectados)
    total_perfiles = len(_perfiles_globales)
    activos = sum(1 for p in _perfiles_globales.values() if p.get("estado") == "activo_en_uso")
    base = {
        "ok": True, "uid": uid, "username": username, "rol": rol,
        "total_pcbots": total_pcbots, "total_perfiles": total_perfiles,
        "perfiles_activos": activos,
    }
    wallet = obtener_wallet_por_usuario(uid)
    balance = obtener_balance(uid) if wallet else 0
    base["balance"] = balance
    if rol == "admin":
        base["stats_kbt"] = obtener_estadisticas_kbt()
        base["urls_asignadas"] = obtener_urls_asignadas()
        base["comandos_recientes"] = obtener_historial_comandos(50)
        base["eventos_seguridad"] = obtener_eventos_seguridad(50)
    return base

@router.get("/api/mi_estado")
async def api_mi_estado(request: Request):
    auth = await verificar_auth(request)
    if not auth:
        return {"ok": False, "error": "no autenticado"}
    uid, username, rol = auth
    wallet = obtener_wallet_por_usuario(uid)
    balance = obtener_balance(uid) if wallet else 0
    return {"ok": True, "uid": uid, "username": username, "rol": rol, "balance": balance, "wallet": wallet}