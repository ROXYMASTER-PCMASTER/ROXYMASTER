from fastapi import APIRouter, Request
from auth import verificar_token, listar_usuarios, cambiar_rol
from tokenomics import acreditar_tokens, debitar_tokens, ejecutar_quema_inactividad
from shs import obtener_eventos_seguridad
from variables_globales import obtener_variables, actualizar_variable, restablecer_variables_predeterminadas as restablecer_variables
router = APIRouter()

async def verificar_admin(request: Request):
    token = request.headers.get("x-token") or request.headers.get("authorization", "").replace("Bearer ", "")
    if not token:
        return None
    auth = verificar_token(token)
    if auth and auth[2] == "admin":
        return auth
    return None

@router.get("/api/admin/variables")
async def api_admin_variables(request: Request):
    if not await verificar_admin(request):
        return {"ok": False, "error": "acceso denegado"}
    return {"ok": True, "variables": obtener_variables()}

@router.post("/api/admin/variables")
async def api_admin_actualizar(request: Request):
    if not await verificar_admin(request):
        return {"ok": False}
    data = await request.json()
    return actualizar_variable(data.get("nombre",""), data.get("valor"))

@router.post("/api/admin/variables/restablecer")
async def api_admin_restablecer(request: Request):
    if not await verificar_admin(request):
        return {"ok": False}
    return restablecer_variables()

@router.get("/api/admin/usuarios")
async def api_admin_usuarios(request: Request):
    if not await verificar_admin(request):
        return {"ok": False}
    return {"ok": True, "usuarios": listar_usuarios()}

@router.post("/api/admin/kbt/emitir")
async def api_admin_emitir(request: Request):
    if not await verificar_admin(request):
        return {"ok": False}
    data = await request.json()
    acreditar_tokens(data.get("uid",""), data.get("cantidad",0), data.get("concepto","emision_manual"))
    return {"ok": True}