# api_auth.py - router fastapi para login, register, verify. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel
from typing import Optional

from auth import registrar_usuario, iniciar_sesion, verificar_token, cerrar_sesion

router = APIRouter(prefix="/api", tags=["auth"])


# ---------------------------------------------------------------------------
# modelos de peticion
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    username: Optional[str] = None
    codigo_referido: Optional[str] = None
    pcbot_id: Optional[str] = None


# ---------------------------------------------------------------------------
# dependencia comun para verificar token (usada por todos los routers)
# ---------------------------------------------------------------------------
async def verificar_token_dependencia(authorization: str = Header(None)) -> dict:
    """dependencia fastapi para verificar token de sesion desde header authorization."""
    if not authorization:
        raise HTTPException(status_code=401, detail="token no proporcionado")

    # extraer bearer token
    token = authorization
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="token no proporcionado")

    sesion = verificar_token(token)
    if not sesion:
        raise HTTPException(status_code=401, detail="token invalido o expirado")
    return sesion


async def verificar_admin_dependencia(authorization: str = Header(None)) -> dict:
    """dependencia que verifica token y ademas que el rol sea admin."""
    sesion = await verificar_token_dependencia(authorization)
    if sesion.get("rol") != "admin":
        raise HTTPException(status_code=403, detail="acceso restringido a administradores")
    return sesion


# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------
@router.post("/login")
async def api_login(req: LoginRequest):
    """inicia sesion y devuelve token."""
    resultado = iniciar_sesion(req.email, req.password)
    if not resultado.get("exito"):
        raise HTTPException(status_code=401, detail=resultado.get("error", "error de autenticacion"))
    return resultado


@router.post("/register")
async def api_register(req: RegisterRequest):
    """registra un nuevo usuario."""
    resultado = registrar_usuario(
        email=req.email,
        password=req.password,
        username=req.username,
        codigo_referido_externo=req.codigo_referido,
        pcbot_id=req.pcbot_id,
    )
    if not resultado.get("exito"):
        raise HTTPException(status_code=400, detail=resultado.get("error", "error al registrar"))
    return resultado


@router.get("/verify")
async def api_verify(sesion: dict = Depends(verificar_token_dependencia)):
    """verifica un token de sesion y devuelve datos del usuario."""
    return {"exito": True, "sesion": sesion}


@router.post("/verify")
async def api_verify_post(sesion: dict = None):
    """verifica un token de sesion (post)."""
    return {"exito": True, "sesion": sesion}


@router.post("/logout")
async def api_logout(authorization: str = Header(None)):
    """cierra sesion."""
    if authorization:
        token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else authorization
        cerrar_sesion(token)
    return {"exito": True, "mensaje": "sesion cerrada"}