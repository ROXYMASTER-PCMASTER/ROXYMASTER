# api_admin_usuarios.py - gestion de usuarios para panel superadmin. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional

from api_auth import verificar_admin_dependencia
from db import ejecutar_sql, ejecutar_sql_unico, ejecutar_insercion
from auth import encriptar_password as _hash_pw

router = APIRouter(prefix="/api/admin", tags=["admin_usuarios"])


class CrearUsuarioRequest(BaseModel):
    email: str
    password: str
    username: Optional[str] = None
    rol: str = "usuario"
    pcbot_id: Optional[str] = None


class EditarUsuarioRequest(BaseModel):
    email: Optional[str] = None
    rol: Optional[str] = None
    username: Optional[str] = None
    activo: Optional[int] = None
    password: Optional[str] = None
    nivel_fiabilidad: Optional[str] = None


# ---------------------------------------------------------------------------
# 1. listar usuarios con filtros
# ---------------------------------------------------------------------------
@router.get("/usuarios")
async def api_listar_usuarios(
    pagina: int = Query(1, ge=1),
    limite: int = Query(50, ge=1, le=200),
    busqueda: Optional[str] = Query(None),
    rol_filtro: Optional[str] = Query(None),
    activo: Optional[int] = Query(None),
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """lista usuarios con filtros opcionales. solo admin/superadmin."""
    condiciones = []
    params = []
    if busqueda:
        condiciones.append("(u.email like ? or u.username like ?)")
        params.extend([f"%{busqueda}%", f"%{busqueda}%"])
    if rol_filtro:
        condiciones.append("u.rol = ?")
        params.append(rol_filtro)
    if activo is not None:
        condiciones.append("u.activo = ?")
        params.append(activo)

    where = "where " + " and ".join(condiciones) if condiciones else ""
    offset = (pagina - 1) * limite

    # contar total
    count_sql = f"select count(*) as total from usuarios u {where}"
    total = ejecutar_sql_unico(count_sql, tuple(params))["total"]

    # listar
    data_sql = f"""
        select u.id, u.email, u.username, u.rol, u.activo, u.pcbot_id,
               u.nivel_fiabilidad, u.ultimo_login, u.fecha_registro,
               u.referido_por, u.modo
        from usuarios u {where}
        order by u.id desc
        limit ? offset ?
    """
    params.extend([limite, offset])
    usuarios = ejecutar_sql(data_sql, tuple(params))

    # obtener wallet de cada usuario
    for usr in usuarios:
        wallet = ejecutar_sql_unico(
            "select id, balance, minado_total from billeteras where usuario_id = ? and tipo = 'kbt'",
            (usr["id"],),
        )
        usr["wallet_kbt"] = wallet if wallet else {"balance": 0, "minado_total": 0}

    # normalizar para frontend
    usuarios_list = []
    for usr in usuarios:
        wallet_kbt = usr.get("wallet_kbt") or {}
        if isinstance(wallet_kbt, dict):
            wallet_kbt_balance = wallet_kbt.get("balance", 0) or 0
        else:
            wallet_kbt_balance = 0
        usuarios_list.append({
            "id": usr["id"],
            "email": usr.get("email", ""),
            "username": usr.get("username", ""),
            "rol": usr.get("rol", "user"),
            "estado": "activo" if usr.get("activo") else "suspendido",
            "activo": usr.get("activo", 0),
            "wallet_kbt": float(wallet_kbt_balance),
            "wallet_pen": 0.0,
            "fecha_creacion": usr.get("fecha_registro", ""),
            "pcbot_id": usr.get("pcbot_id", ""),
            "nivel_fiabilidad": usr.get("nivel_fiabilidad", ""),
            "ultimo_login": usr.get("ultimo_login", ""),
        })
    return {
        "exito": True,
        "total": total,
        "pagina": pagina,
        "limite": limite,
        "usuarios": usuarios_list,
    }


# ---------------------------------------------------------------------------
# 2. crear nuevo usuario
# ---------------------------------------------------------------------------
@router.post("/usuarios")
async def api_crear_usuario(
    req: CrearUsuarioRequest,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """crea un nuevo usuario manualmente desde el admin."""
    existente = ejecutar_sql_unico("select id from usuarios where email = ?", (req.email,))
    if existente:
        raise HTTPException(status_code=400, detail="el email ya esta registrado")

    password_hash = _hash_pw(req.password)
    wallet = f"kbt_{req.email.split('@')[0]}_{_ahora_str()[:10]}"

    user_id = ejecutar_insercion(
        "insert into usuarios (email, password_hash, username, rol, wallet, pcbot_id, activo) "
        "values (?, ?, ?, ?, ?, ?, 1)",
        (req.email, password_hash, req.username or "", req.rol, wallet, req.pcbot_id or ""),
    )

    # crear wallet kbt por defecto
    ejecutar_insercion(
        "insert into billeteras (usuario_id, tipo, balance) values (?, 'kbt', 0)",
        (user_id,),
    )

    return {"exito": True, "usuario_id": user_id, "email": req.email}


# ---------------------------------------------------------------------------
# 3. editar usuario
# ---------------------------------------------------------------------------
@router.put("/usuarios/{usuario_id}")
async def api_editar_usuario(
    usuario_id: int,
    req: EditarUsuarioRequest,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """edita los campos de un usuario (email, rol, activo, etc)."""
    existente = ejecutar_sql_unico("select id from usuarios where id = ?", (usuario_id,))
    if not existente:
        raise HTTPException(status_code=404, detail="usuario no encontrado")

    updates = []
    params = []
    if req.email is not None:
        # verificar que no haya duplicado
        dup = ejecutar_sql_unico("select id from usuarios where email = ? and id != ?", (req.email, usuario_id))
        if dup:
            raise HTTPException(status_code=400, detail="el email ya pertenece a otro usuario")
        updates.append("email = ?")
        params.append(req.email)
    if req.rol is not None:
        if req.rol not in ("usuario", "admin", "superadmin"):
            raise HTTPException(status_code=400, detail="rol invalido")
        updates.append("rol = ?")
        params.append(req.rol)
    if req.username is not None:
        updates.append("username = ?")
        params.append(req.username)
    if req.activo is not None:
        updates.append("activo = ?")
        params.append(req.activo)
    if req.password is not None:
        updates.append("password_hash = ?")
        params.append(_hash_pw(req.password))
    if req.nivel_fiabilidad is not None:
        updates.append("nivel_fiabilidad = ?")
        params.append(req.nivel_fiabilidad)

    if not updates:
        raise HTTPException(status_code=400, detail="no hay campos para actualizar")

    params.append(usuario_id)
    ejecutar_sql(
        f"update usuarios set {', '.join(updates)} where id = ?",
        tuple(params),
    )
    return {"exito": True, "mensaje": "usuario actualizado"}


# ---------------------------------------------------------------------------
# 4. eliminar usuario
# ---------------------------------------------------------------------------
@router.delete("/usuarios/{usuario_id}")
async def api_eliminar_usuario(
    usuario_id: int,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """elimina un usuario y sus datos asociados."""
    existente = ejecutar_sql_unico("select id from usuarios where id = ?", (usuario_id,))
    if not existente:
        raise HTTPException(status_code=404, detail="usuario no encontrado")

    ejecutar_sql("delete from billeteras where usuario_id = ?", (usuario_id,))
    ejecutar_sql("delete from sesiones where usuario_id = ?", (usuario_id,))
    ejecutar_sql("delete from transacciones where origen_id = ? or destino_id = ?", (usuario_id, usuario_id))
    ejecutar_sql("delete from pedidos where usuario_id = ?", (usuario_id,))
    ejecutar_sql("delete from computadoras where usuario_id = ?", (usuario_id,))
    ejecutar_sql("delete from mensajes where origen_id = ? or destino_id = ?", (usuario_id, usuario_id))
    ejecutar_sql("delete from usuarios where id = ?", (usuario_id,))

    return {"exito": True, "mensaje": "usuario eliminado"}


# ---------------------------------------------------------------------------
# 5. ver wallet de un usuario
# ---------------------------------------------------------------------------
@router.get("/usuarios/{usuario_id}/wallet")
async def api_ver_wallet_usuario(
    usuario_id: int,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """devuelve las wallets de un usuario especifico."""
    wallets = ejecutar_sql(
        "select id, tipo, balance, minado_total, recolectado_total, "
        "comprado_total, retirado_total, staking_total "
        "from billeteras where usuario_id = ?",
        (usuario_id,),
    )
    return {"exito": True, "datos": wallets}


# ---------------------------------------------------------------------------
# 6. historial de pedidos de un usuario
# ---------------------------------------------------------------------------
@router.get("/usuarios/{usuario_id}/pedidos")
async def api_pedidos_usuario(
    usuario_id: int,
    limite: int = Query(50, ge=1, le=200),
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """devuelve el historial de pedidos de un usuario."""
    pedidos = ejecutar_sql(
        "select id, url, estado, tipo_pedido, cantidad_perfiles, duracion_horas, "
        "costo_tokens, fecha_creacion from pedidos where usuario_id = ? "
        "order by fecha_creacion desc limit ?",
        (usuario_id, limite),
    )
    return {"exito": True, "datos": pedidos}


# ---------------------------------------------------------------------------
# 7. suspender usuario
# ---------------------------------------------------------------------------
@router.post("/usuarios/{usuario_id}/suspender")
async def api_suspender_usuario(
    usuario_id: int,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """suspende un usuario (activo=0)."""
    existente = ejecutar_sql_unico("select id, activo from usuarios where id = ?", (usuario_id,))
    if not existente:
        raise HTTPException(status_code=404, detail="usuario no encontrado")
    if existente["activo"] == 0:
        raise HTTPException(status_code=400, detail="el usuario ya esta suspendido")

    ejecutar_sql("update usuarios set activo = 0 where id = ?", (usuario_id,))
    return {"exito": True, "mensaje": "usuario suspendido"}


# ---------------------------------------------------------------------------
# 8. reactivar usuario
# ---------------------------------------------------------------------------
@router.post("/usuarios/{usuario_id}/reactivar")
async def api_reactivar_usuario(
    usuario_id: int,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """reactiva un usuario (activo=1)."""
    existente = ejecutar_sql_unico("select id, activo from usuarios where id = ?", (usuario_id,))
    if not existente:
        raise HTTPException(status_code=404, detail="usuario no encontrado")
    if existente["activo"] == 1:
        raise HTTPException(status_code=400, detail="el usuario ya esta activo")

    ejecutar_sql("update usuarios set activo = 1 where id = ?", (usuario_id,))
    return {"exito": True, "mensaje": "usuario reactivado"}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _ahora_str() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")