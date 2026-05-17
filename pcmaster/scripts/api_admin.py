# api_admin.py - rutas de administracion de roxymaster v8.3
# todas en minusculas, utf-8 sin bom
# solo accesible por usuarios con rol admin

import hashlib
import json
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth import (
    verificar_admin_dependencia,
    verificar_token_opcional,
)
from db import ejecutar_sql, ejecutar_sql_unico, init_db
from shs import firmar_payload as generar_firma
from variables_globales import restablecer_variables_predeterminadas

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# helpers internos
# ---------------------------------------------------------------------------
def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _hash_pbkdf2(password: str, salt: str = "") -> str:
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return h.hex()


# ---------------------------------------------------------------------------
# gestor de sesiones manuales (sin auth.py)
# ---------------------------------------------------------------------------
def _crear_sesion(email: str, usuario_id: int, rol: str) -> str:
    token = secrets.token_urlsafe(48)
    expiracion = _utc_now()
    ejecutar_sql(
        "insert into sesiones (token, usuario_id, email, rol, fecha_expiracion) "
        "values (?, ?, ?, ?, datetime('now', '+7 days'))",
        (token, usuario_id, email, rol),
    )
    return token


# ---------------------------------------------------------------------------
# endpoints publicos
# ---------------------------------------------------------------------------
@router.get("/health")
async def health():
    return {"status": "ok", "timestamp": _utc_now()}


# ---------------------------------------------------------------------------
# endpoints protegidos con verificar_admin_dependencia
# ---------------------------------------------------------------------------
@router.get("/usuarios")
async def api_listar_usuarios(
    q: Optional[str] = Query(None),
    rol: Optional[str] = Query(None),
    estado: Optional[str] = Query(None),
    sesion: dict = Depends(verificar_admin_dependencia),
):
    sql = "select id, email, username, rol, wallet, activo, referido_por, fecha_registro, ultimo_login, pcbot_id from usuarios"
    condiciones = []
    params = []
    if q:
        condiciones.append("(email like ? or username like ?)")
        params.extend([f"%{q}%", f"%{q}%"])
    if rol:
        condiciones.append("rol = ?")
        params.append(rol)
    if estado == "activo":
        condiciones.append("activo = 1")
    elif estado == "inactivo":
        condiciones.append("activo = 0")
    if condiciones:
        sql += " where " + " and ".join(condiciones)
    sql += " order by id"
    rows = ejecutar_sql(sql, tuple(params))
    return {"exito": True, "usuarios": [dict(r) for r in rows]}


@router.get("/usuarios/{usuario_id}")
async def api_detalle_usuario(
    usuario_id: int,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """devuelve detalle completo de un usuario con perfiles, pcs y transacciones."""
    u = ejecutar_sql_unico(
        "select u.*, w.balance, w.minado_total from usuarios u "
        "left join wallets w on u.id = w.usuario_id where u.id = ?",
        (usuario_id,),
    )
    if not u:
        raise HTTPException(status_code=404, detail="usuario no encontrado")
    perfiles = ejecutar_sql("select * from perfiles where usuario_id = ?", (usuario_id,))
    pcs = ejecutar_sql(
        "select * from usuarios where pcbot_id is not null and id = ?", (usuario_id,)
    )
    transacciones = ejecutar_sql(
        "select * from transacciones where comprador_id = ? or vendedor_id = ? order by fecha desc limit 50",
        (usuario_id, usuario_id),
    )
    return {
        "exito": True,
        "usuario": dict(u),
        "perfiles": [dict(p) for p in perfiles],
        "pcs": [dict(pc) for pc in pcs],
        "transacciones": [dict(t) for t in transacciones],
    }


# ------------------------------------------------
@router.get("/dashboard")
async def api_dashboard(
    sesion: dict = Depends(verificar_admin_dependencia),
):
    total_usuarios = ejecutar_sql_unico("select count(*) as c from usuarios")["c"]
    usuarios_activos = ejecutar_sql_unico(
        "select count(*) as c from usuarios where activo = 1"
    )["c"]
    perfiles_activos = ejecutar_sql_unico(
        "select count(*) as c from perfiles where estado = 'activo'"
    )["c"]
    total_wallet = ejecutar_sql_unico(
        "select coalesce(sum(balance), 0) as total from wallets"
    )["total"]
    return {
        "exito": True,
        "total_usuarios": total_usuarios,
        "usuarios_activos": usuarios_activos,
        "perfiles_activos": perfiles_activos,
        "total_wallet": total_wallet,
    }


# ------------------------------------------------
@router.post("/variables/restablecer")
async def api_admin_restablecer_variables(
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """restablece todas las variables economicas a sus valores predeterminados."""
    exito = restablecer_variables_predeterminadas()
    if not exito:
        raise HTTPException(status_code=500, detail="error al restablecer variables")
    return {"exito": True, "mensaje": "variables restablecidas a valores predeterminados"}


# enpoints para perfil admin
@router.post("/login")
async def api_login_admin(datos: dict):
    email = datos.get("email", "").strip().lower()
    password = datos.get("password", "")
    if not email or not password:
        raise HTTPException(status_code=400, detail="email y password requeridos")
    user = ejecutar_sql_unico(
        "select id, email, username, password_hash, rol from usuarios where email = ?",
        (email,),
    )
    if not user:
        raise HTTPException(status_code=401, detail="credenciales invalidas")
    expected_hash = _hash_pbkdf2(password, email)
    if user["password_hash"] != expected_hash:
        raise HTTPException(status_code=401, detail="credenciales invalidas")
    if user["rol"] != "admin":
        raise HTTPException(status_code=403, detail="acceso solo para administradores")
    token = _crear_sesion(email, user["id"], user["rol"])
    return {
        "exito": True,
        "token": token,
        "usuario": {
            "id": user["id"],
            "email": user["email"],
            "username": user["username"],
            "rol": user["rol"],
        },
    }


@router.get("/verificar")
async def api_verificar_admin(sesion: dict = Depends(verificar_admin_dependencia)):
    return {
        "exito": True,
        "usuario": {
            "id": sesion.get("usuario_id"),
            "email": sesion.get("email"),
            "rol": sesion.get("rol"),
        },
    }


# fin api_admin.py