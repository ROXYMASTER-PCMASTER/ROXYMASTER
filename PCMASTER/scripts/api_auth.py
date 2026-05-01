from fastapi import APIRouter, Request
from auth import autenticar_usuario, registrar_usuario, generar_token, verificar_token
router = APIRouter()

@router.post("/api/login")
async def api_login(request: Request):
    data = await request.json()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    resultado = autenticar_usuario(email, password)
    if not resultado:
        return {"ok": False, "error": "credenciales invalidas"}
    uid, username, rol = resultado
    token = generar_token(uid, username, rol)
    return {"ok": True, "token": token, "uid": uid, "username": username, "rol": rol}

@router.post("/api/register")
async def api_register(request: Request):
    data = await request.json()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    codigo_referido = data.get("codigo_referido", "pcmaster")
    resultado = registrar_usuario(email, password, email.split("@")[0] if "@" in email else email, codigo_referido)
    if not resultado["ok"]:
        return {"ok": False, "error": resultado.get("error")}
    uid = resultado["uid"]
    token = generar_token(uid, email.split("@")[0] if "@" in email else email, "usuario")
    return {"ok": True, "token": token, "uid": uid, "username": email.split("@")[0] if "@" in email else email, "rol": "usuario"}

@router.get("/api/verify")
async def api_verify(request: Request):
    token = request.headers.get("x-token") or request.headers.get("authorization", "").replace("Bearer ", "")
    if not token:
        token = request.query_params.get("token", "")
    usuario = verificar_token(token)
    if usuario:
        return {"ok": True, "uid": usuario[0], "username": usuario[1], "rol": usuario[2]}
    return {"ok": False, "error": "token invalido"}