# api_refresh.py - endpoint para refrescar token. roxymaster v8.3
# utf-8 sin bom, todo en minusculas, <= 400 lineas

from fastapi import APIRouter, HTTPException, Header
from auth import generar_token, verificar_token

router = APIRouter(prefix="/api", tags=["refresh"])


@router.post("/refresh")
async def api_refresh(authorization: str = Header(None)):
    """refresca un token jwt: genera uno nuevo si el actual es valido."""
    if not authorization:
        raise HTTPException(status_code=401, detail="token no proporcionado")

    token = authorization
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="token no proporcionado")

    # verificar que el token actual sea valido
    sesion = verificar_token(token)
    if not sesion:
        raise HTTPException(status_code=401, detail="token invalido o expirado")

    # generar nuevo token con los mismos datos
    email = sesion.get("email", "")
    usuario_id = sesion.get("usuario_id", 0)
    rol = sesion.get("rol", "usuario")
    nuevo_token = generar_token()

    # registrar nueva sesion en db
    from datetime import datetime, timedelta
    from db import ejecutar_insercion
    ahora = datetime.now()
    expiracion = ahora + timedelta(days=7)
    ejecutar_insercion(
        "insert into sesiones (token, usuario_id, email, rol, fecha_creacion, fecha_expiracion) "
        "values (?, ?, ?, ?, ?, ?)",
        (nuevo_token, usuario_id, email, rol,
         ahora.strftime("%Y-%m-%d %H:%M:%S"),
         expiracion.strftime("%Y-%m-%d %H:%M:%S")),
    )

    return {
        "exito": True,
        "token": nuevo_token,
        "email": email,
        "usuario_id": usuario_id,
        "rol": rol,
        "expiracion": expiracion.strftime("%Y-%m-%d %H:%M:%S"),
        "mensaje": "token refrescado",
    }