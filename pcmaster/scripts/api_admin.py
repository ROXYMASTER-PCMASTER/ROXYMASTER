# api_admin.py - router fastapi para administracion: usuarios, perfiles, pcs, sesiones, retiros, mensajes, seguridad. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

import os
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
from api_auth import verificar_admin_dependencia
from db import ejecutar_sql, ejecutar_sql_unico, ejecutar_insercion

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# modelos pydantic
# ---------------------------------------------------------------------------
class UsuarioUpdateRequest(BaseModel):
    email: Optional[str] = None
    username: Optional[str] = None
    rol: Optional[str] = None
    wallet: Optional[str] = None
    saldo: Optional[float] = None
    estado: Optional[str] = None
    activo: Optional[int] = None

class RolRequest(BaseModel):
    rol: str

class PerfilUpdateRequest(BaseModel):
    nombre: Optional[str] = None
    estado: Optional[str] = None
    usuario_id: Optional[int] = None
    ip_wan: Optional[str] = None

class PerfilCrearRequest(BaseModel):
    usuario_id: int
    nombre_perfil: str
    tipo: str = "local"
    hash_id: Optional[str] = None

class PcUpdateRequest(BaseModel):
    modo: Optional[str] = None

class RetiroProcesarRequest(BaseModel):
    retiro_id: int
    accion: str

class MensajeEnviarRequest(BaseModel):
    texto: str
    alcance: str
    rol: Optional[str] = None
    user_ids: Optional[List[int]] = None

class ToggleRequest(BaseModel):
    activo: int


# ---------------------------------------------------------------------------
# usuarios
# ---------------------------------------------------------------------------
@router.get("/usuarios")
async def api_listar_usuarios(
    q: str = Query(""),
    rol: str = Query(""),
    estado: str = Query(""),
    sesion: dict = Depends(verificar_admin_dependencia),
):
    sql = "select id, email, username, rol, wallet, balance, activo, referido_por, fecha_registro, ultimo_login, pcbot_id from usuarios"
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
        "pcs": [dict(p) for p in pcs],
        "transacciones": [dict(t) for t in transacciones],
    }


@router.put("/usuarios/{usuario_id}")
async def api_actualizar_usuario(
    usuario_id: int,
    req: UsuarioUpdateRequest,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """actualiza campos editables de un usuario."""
    updates = {}
    if req.email is not None:
        updates["email"] = req.email
    if req.username is not None:
        updates["username"] = req.username
    if req.rol is not None:
        updates["rol"] = req.rol
    if req.wallet is not None:
        updates["wallet"] = req.wallet
    if req.estado is not None:
        updates["estado"] = req.estado
    if req.activo is not None:
        updates["activo"] = req.activo
    if updates:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        valores = list(updates.values()) + [usuario_id]
        ejecutar_sql(f"update usuarios set {set_clause} where id = ?", tuple(valores))
    # saldo va en tabla wallets, no en usuarios
    if req.saldo is not None:
        existente = ejecutar_sql_unico("select id from wallets where usuario_id = ?", (usuario_id,))
        if existente:
            ejecutar_sql("update wallets set balance = ? where usuario_id = ?", (req.saldo, usuario_id))
        else:
            ejecutar_insercion("insert into wallets (usuario_id, balance, minado_total) values (?, ?, 0)", (usuario_id, req.saldo))
    if not updates and req.saldo is None:
        raise HTTPException(status_code=400, detail="sin campos para actualizar")
    return {"exito": True, "mensaje": "usuario actualizado"}


@router.post("/usuarios/{usuario_id}/rol")
async def api_cambiar_rol(
    usuario_id: int,
    req: RolRequest,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    roles_validos = {"admin", "granjero", "usuario"}
    if req.rol not in roles_validos:
        raise HTTPException(status_code=400, detail="rol invalido")
    ejecutar_sql("update usuarios set rol = ? where id = ?", (req.rol, usuario_id))
    return {"exito": True, "mensaje": f"rol cambiado a {req.rol}"}


@router.post("/usuarios/{usuario_id}/toggle")
async def api_toggle_usuario(
    usuario_id: int,
    req: ToggleRequest,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """activa o desactiva un usuario."""
    ejecutar_sql("update usuarios set activo = ? where id = ?", (req.activo, usuario_id))
    return {"exito": True, "mensaje": "usuario " + ("activado" if req.activo else "desactivado")}


@router.delete("/usuarios/{usuario_id}")
async def api_eliminar_usuario(
    usuario_id: int,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """elimina un usuario y sus datos asociados (confirmacion requerida)."""
    existente = ejecutar_sql_unico("select id from usuarios where id = ?", (usuario_id,))
    if not existente:
        raise HTTPException(status_code=404, detail="usuario no encontrado")
    ejecutar_sql("delete from sesiones where usuario_id = ?", (usuario_id,))
    ejecutar_sql("delete from wallets where usuario_id = ?", (usuario_id,))
    ejecutar_sql("delete from perfiles where usuario_id = ?", (usuario_id,))
    ejecutar_sql("delete from mensajes where origen_id = ? or destino_id = ?", (usuario_id, usuario_id))
    ejecutar_sql("delete from usuarios where id = ?", (usuario_id,))
    return {"exito": True, "mensaje": "usuario eliminado"}


# ---------------------------------------------------------------------------
# perfiles
# ---------------------------------------------------------------------------
@router.get("/perfiles")
async def api_listar_perfiles(
    q: str = Query(""),
    estado: str = Query(""),
    dueno: str = Query(""),
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """lista todos los perfiles con filtros opcionales."""
    sql = (
        "select p.*, u.email as dueno_email, u.username as dueno_username "
        "from perfiles p join usuarios u on p.usuario_id = u.id"
    )
    condiciones = []
    params = []
    if q:
        condiciones.append("p.nombre like ?")
        params.append(f"%{q}%")
    if estado:
        condiciones.append("p.estado = ?")
        params.append(estado)
    if dueno:
        condiciones.append("(u.email like ? or u.username like ?)")
        params.extend([f"%{dueno}%", f"%{dueno}%"])
    if condiciones:
        sql += " where " + " and ".join(condiciones)
    sql += " order by p.id"
    rows = ejecutar_sql(sql, tuple(params))
    return {"exito": True, "perfiles": [dict(r) for r in rows]}


@router.post("/perfiles")
async def api_crear_perfil(
    req: PerfilCrearRequest,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """crea un nuevo perfil para un usuario."""
    # verificar que el usuario existe
    usuario = ejecutar_sql_unico("select id from usuarios where id = ?", (req.usuario_id,))
    if not usuario:
        raise HTTPException(status_code=404, detail="usuario no encontrado")
    perfil_id = ejecutar_insercion(
        "insert into perfiles (usuario_id, nombre_perfil, tipo, estado, horas_conexion, horas_en_uso, horas_hh) values (?, ?, ?, 'inactivo', 0, 0, 0)",
        (req.usuario_id, req.nombre_perfil, req.tipo),
    )
    return {"exito": True, "perfil_id": perfil_id, "hash_id": ""}


@router.get("/perfiles/historial_fallos/{perfil_id}")
async def api_historial_fallos_perfil(
    perfil_id: int,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """devuelve el historial de fallos/cortes/interrupciones de un perfil."""
    rows = ejecutar_sql(
        "select * from fallos_perfil where perfil_id = ? order by fecha_inicio desc limit 100",
        (perfil_id,),
    )
    return {"exito": True, "fallos": [dict(r) for r in rows]}


@router.put("/perfiles/{perfil_id}")
async def api_actualizar_perfil(
    perfil_id: int,
    req: PerfilUpdateRequest,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """actualiza campos editables de un perfil."""
    updates = {}
    if req.nombre is not None:
        updates["nombre"] = req.nombre
    if req.estado is not None:
        updates["estado"] = req.estado
    if req.usuario_id is not None:
        updates["usuario_id"] = req.usuario_id
    if req.ip_wan is not None:
        updates["ip_wan"] = req.ip_wan
    if not updates:
        raise HTTPException(status_code=400, detail="sin campos para actualizar")
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    valores = list(updates.values()) + [perfil_id]
    ejecutar_sql(f"update perfiles set {set_clause} where id = ?", tuple(valores))
    return {"exito": True, "mensaje": "perfil actualizado"}


@router.post("/perfiles/{perfil_id}/desconectar")
async def api_desconectar_perfil(
    perfil_id: int,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """fuerza la desconexion de un perfil."""
    ejecutar_sql("update perfiles set estado = 'desconectado' where id = ?", (perfil_id,))
    return {"exito": True, "mensaje": "perfil desconectado"}


# ---------------------------------------------------------------------------
# pcs (pcbots)
# ---------------------------------------------------------------------------
@router.get("/pcs")
async def api_listar_pcs(
    q: str = Query(""),
    modo: str = Query(""),
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """lista todos los pcbots registrados."""
    sql = (
        "select u.id, u.email, u.pcbot_id, u.modo, "
        "(select count(*) from perfiles p where p.usuario_id = u.id) as perfiles_asociados, "
        "u.ultimo_login "
        "from usuarios u where u.pcbot_id is not null"
    )
    params = []
    if q:
        sql += " and u.email like ?"
        params.append(f"%{q}%")
    if modo:
        sql += " and u.modo = ?"
        params.append(modo)
    sql += " order by u.id"
    rows = ejecutar_sql(sql, tuple(params))
    return {"exito": True, "pcs": [dict(r) for r in rows]}


@router.put("/pcs/{usuario_id}")
async def api_actualizar_pc(
    usuario_id: int,
    req: PcUpdateRequest,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """actualiza modo de un pcbot."""
    updates = {}
    if req.modo is not None:
        updates["modo"] = req.modo
    if not updates:
        raise HTTPException(status_code=400, detail="sin campos para actualizar")
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    valores = list(updates.values()) + [usuario_id]
    ejecutar_sql(f"update usuarios set {set_clause} where id = ?", tuple(valores))
    return {"exito": True, "mensaje": "pc actualizada"}


# ---------------------------------------------------------------------------
# sesiones
# ---------------------------------------------------------------------------
@router.get("/sesiones")
async def api_listar_sesiones(sesion: dict = Depends(verificar_admin_dependencia)):
    """lista todas las sesiones activas."""
    rows = ejecutar_sql(
        "select s.token, s.usuario_id, s.email, s.rol, s.fecha_creacion, "
        "s.fecha_expiracion, u.pcbot_id from sesiones s "
        "left join usuarios u on s.usuario_id = u.id order by s.fecha_creacion desc"
    )
    return {"exito": True, "sesiones": [dict(r) for r in rows]}


@router.delete("/sesiones/{token}")
async def api_cerrar_sesion(
    token: str,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """cierra una sesion especifica por token."""
    ejecutar_sql("delete from sesiones where token = ?", (token,))
    return {"exito": True, "mensaje": "sesion cerrada"}


# ---------------------------------------------------------------------------
# retiros
# ---------------------------------------------------------------------------
@router.get("/retiros")
async def api_listar_retiros(
    estado: str = Query("pendiente"),
    q: str = Query(""),
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """lista solicitudes de retiro con filtros."""
    sql = (
        "select r.*, u.email as usuario_email, u.username as usuario_username "
        "from retiros r join usuarios u on r.usuario_id = u.id"
    )
    condiciones = []
    params = []
    if estado:
        condiciones.append("r.estado = ?")
        params.append(estado)
    if q:
        condiciones.append("(u.email like ? or u.username like ?)")
        params.extend([f"%{q}%", f"%{q}%"])
    if condiciones:
        sql += " where " + " and ".join(condiciones)
    sql += " order by r.fecha_solicitud desc"
    rows = ejecutar_sql(sql, tuple(params))
    return {"exito": True, "retiros": [dict(r) for r in rows]}


@router.post("/retiros/procesar")
async def api_procesar_retiro(
    req: RetiroProcesarRequest,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """aprueba, rechaza o marca como procesado un retiro."""
    estados_validos = {"aprobar": "aprobado", "rechazar": "rechazado", "procesado": "procesado"}
    nuevo_estado = estados_validos.get(req.accion)
    if not nuevo_estado:
        raise HTTPException(status_code=400, detail="accion invalida: usar aprobar, rechazar o procesado")
    ejecutar_sql(
        "update retiros set estado = ?, fecha_procesado = datetime('now','localtime') where id = ?",
        (nuevo_estado, req.retiro_id),
    )
    return {"exito": True, "mensaje": f"retiro {nuevo_estado}"}


# ---------------------------------------------------------------------------
# mensajes administrativos
# ---------------------------------------------------------------------------
@router.post("/mensajes/enviar")
async def api_enviar_mensaje_admin(
    req: MensajeEnviarRequest,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """envia un mensaje global, por rol o a usuarios especificos."""
    admin_id = sesion["usuario_id"]
    destinatarios = []
    if req.alcance == "todos":
        rows = ejecutar_sql("select id from usuarios")
        destinatarios = [r["id"] for r in rows]
    elif req.alcance == "por_rol" and req.rol:
        rows = ejecutar_sql("select id from usuarios where rol = ?", (req.rol,))
        destinatarios = [r["id"] for r in rows]
    elif req.alcance == "especificos" and req.user_ids:
        destinatarios = req.user_ids
    else:
        raise HTTPException(status_code=400, detail="alcance invalido o faltan parametros")
    if not destinatarios:
        raise HTTPException(status_code=400, detail="no hay destinatarios para este alcance")
    for destino_id in destinatarios:
        if destino_id != admin_id:
            ejecutar_insercion(
                "insert into mensajes (origen_id, destino_id, texto, leido, fecha) values (?, ?, ?, 0, datetime('now','localtime'))",
                (admin_id, destino_id, req.texto),
            )
    return {"exito": True, "mensaje": f"mensaje enviado a {len(destinatarios)} usuarios"}


@router.get("/mensajes/historial")
async def api_historial_mensajes(sesion: dict = Depends(verificar_admin_dependencia)):
    """devuelve el historial de mensajes enviados por admins."""
    rows = ejecutar_sql(
        "select m.*, o.email as origen_email, d.email as destino_email "
        "from mensajes m "
        "join usuarios o on m.origen_id = o.id "
        "join usuarios d on m.destino_id = d.id "
        "order by m.fecha desc limit 200"
    )
    return {"exito": True, "mensajes": [dict(r) for r in rows]}


# ---------------------------------------------------------------------------
# seguridad
# ---------------------------------------------------------------------------
@router.get("/seguridad")
async def api_listar_seguridad(
    tipo: str = Query(""),
    pcbot_id: str = Query(""),
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """lista eventos de seguridad con filtros opcionales."""
    sql = "select * from eventos_seguridad"
    condiciones = []
    params = []
    if tipo:
        condiciones.append("tipo = ?")
        params.append(tipo)
    if pcbot_id:
        condiciones.append("pcbot_id = ?")
        params.append(pcbot_id)
    if condiciones:
        sql += " where " + " and ".join(condiciones)
    sql += " order by fecha desc limit 200"
    rows = ejecutar_sql(sql, tuple(params))
    return {"exito": True, "eventos": [dict(r) for r in rows]}


# ---------------------------------------------------------------------------
# sistema
# ---------------------------------------------------------------------------
@router.get("/sistema/estado")
async def api_estado_sistema(sesion: dict = Depends(verificar_admin_dependencia)):
    """devuelve el estado general del sistema."""
    total_usuarios = ejecutar_sql_unico("select count(*) as total from usuarios")
    total_sesiones = ejecutar_sql_unico("select count(*) as total from sesiones")
    total_kbt = ejecutar_sql_unico("select sum(balance) as total from wallets")
    reserva = ejecutar_sql_unico("select * from reserva where id = 1")
    comandos_pendientes = ejecutar_sql_unico(
        "select count(*) as total from comandos where estado = 'pendiente'"
    )
    return {
        "exito": True,
        "total_usuarios": total_usuarios["total"] if total_usuarios else 0,
        "sesiones_activas": total_sesiones["total"] if total_sesiones else 0,
        "kbt_circulando": total_kbt["total"] or 0 if total_kbt else 0,
        "reserva": dict(reserva) if reserva else {},
        "comandos_pendientes": comandos_pendientes["total"] if comandos_pendientes else 0,
    }