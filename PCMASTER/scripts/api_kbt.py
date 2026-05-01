from fastapi import APIRouter, Request
from tokenomics import obtener_balance, obtener_wallet_por_usuario, obtener_historial_token, obtener_estadisticas_kbt
from auth import verificar_token
router = APIRouter()

async def verificar_auth(request: Request):
    token = request.headers.get("x-token") or request.headers.get("authorization", "").replace("Bearer ", "")
    if not token:
        return None
    return verificar_token(token)

@router.get("/api/kbt/balance")
async def api_kbt_balance(request: Request):
    auth = await verificar_auth(request)
    if not auth:
        return {"ok": False}
    uid, _, _ = auth
    balance = obtener_balance(uid)
    wallet = obtener_wallet_por_usuario(uid)
    return {"ok": True, "balance": balance, "wallet": wallet}

@router.get("/api/kbt/estadisticas")
async def api_kbt_estadisticas(request: Request):
    return {"ok": True, "estadisticas": obtener_estadisticas_kbt()}