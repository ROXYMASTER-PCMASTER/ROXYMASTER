# api_public_sistema.py - endpoints de sistema, notificaciones, estadisticas, config
# roxymaster v8.3 - todo en minusculas, utf-8 sin bom, <= 400 lineas

import json
import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from api_auth import verificar_token_dependencia
from db import ejecutar_sql_unico, ejecutar_sql, ejecutar_insercion

router = APIRouter(prefix="/api", tags=["public_sistema"])


# ---------------------------------------------------------------------------
# modelos
# ---------------------------------------------------------------------------
class ActualizarUsuarioRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    password_actual: Optional[str] = None


class ConfiguracionRequest(BaseModel):
    idioma: Optional[str] = None
    notificaciones_activas: Optional[bool] = None


# ---------------------------------------------------------------------------
# estadisticas globales (publico, sin auth)
# ---------------------------------------------------------------------------
@router.get("/estadisticas_globales")
async def api_estadisticas_globales():
    """resumen publico del sistema."""
    total_usuarios = ejecutar_sql_unico("select count(*) as c from usuarios")
    total_activos = ejecutar_sql_unico(
        "select count(*) as c from usuarios where activo = 1"
    )

    total_kbt_minado = ejecutar_sql_unico(
        "select coalesce(sum(minado_total), 0) as total from wallets"
    )

    reserva = ejecutar_sql_unico(
        "select tokens, soles from reserva where id = 1"
    )

    pcbots_conectados = ejecutar_sql_unico(
        "select count(*) as c from usuarios where modo = 'conectado'"
    )

    return {
        "exito": True,
        "total_usuarios": total_usuarios["c"] if total_usuarios else 0,
        "usuarios_activos": total_activos["c"] if total_activos else 0,
        "total_kbt_minado": float(total_kbt_minado["total"]) if total_kbt_minado else 0.0,
        "reserva_tokens": float(reserva["tokens"]) if reserva else 0.0,
        "reserva_soles": float(reserva["soles"]) if reserva else 0.0,
        "pcbots_conectados": pcbots_conectados["c"] if pcbots_conectados else 0,
    }


# ---------------------------------------------------------------------------
# ranking
# ---------------------------------------------------------------------------
@router.get("/ranking")
async def api_ranking(
    tipo: str = "minado",
    limite: int = 20,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """top usuarios por minado, referidos o comisiones."""
    if tipo == "minado":
        rows = ejecutar_sql(
            "select u.id, u.username, w.minado_total "
            "from usuarios u join wallets w on u.id = w.usuario_id "
            "where u.activo = 1 order by w.minado_total desc limit ?",
            (limite,),
        )
        ranking = [
            {"posicion": i + 1, "usuario_id": r["id"],
             "username": r.get("username", ""), "valor": float(r["minado_total"])}
            for i, r in enumerate(rows)
        ]
    elif tipo == "referidos":
        rows = ejecutar_sql(
            "select u.id, u.username, count(r.id) as total "
            "from usuarios u left join referidos r on r.referidor_id = u.id "
            "where u.activo = 1 group by u.id order by total desc limit ?",
            (limite,),
        )
        ranking = [
            {"posicion": i + 1, "usuario_id": r["id"],
             "username": r.get("username", ""), "valor": r["total"]}
            for i, r in enumerate(rows)
        ]
    elif tipo == "comisiones":
        rows = ejecutar_sql(
            "select u.id, u.username, coalesce(sum(r.comisiones_generadas), 0) as total "
            "from usuarios u left join referidos r on r.referidor_id = u.id "
            "where u.activo = 1 group by u.id order by total desc limit ?",
            (limite,),
        )
        ranking = [
            {"posicion": i + 1, "usuario_id": r["id"],
             "username": r.get("username", ""), "valor": float(r["total"])}
            for i, r in enumerate(rows)
        ]
    else:
        return {"exito": False, "mensaje": "tipo invalido: usar minado, referidos o comisiones"}

    return {"exito": True, "tipo": tipo, "ranking": ranking}


# ---------------------------------------------------------------------------
# sistema
# ---------------------------------------------------------------------------
@router.get("/sistema/version")
async def api_sistema_version():
    """version actual del servidor y estado de servicios."""
    return {
        "exito": True,
        "sistema": "roxymaster",
        "version": "8.3.0",
        "estado": "operativo",
        "api_version": "v1",
    }


@router.get("/endpoints")
async def api_endpoints():
    """devuelve el indice maestro de endpoints para clientes web."""
    indice_path = os.path.join(os.path.dirname(__file__), "indice_endpoints.json")
    if not os.path.exists(indice_path):
        return {"exito": False, "mensaje": "indice_endpoints.json no encontrado", "categorias": []}
    with open(indice_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    categorias = data.get("categorias", [])
    total = 0
    for c in categorias:
        total += len(c.get("endpoints", []))
    return {
        "exito": True,
        "documentacion": data.get("documentacion", {}),
        "categorias": categorias,
        "total_endpoints": total,
    }


# ---------------------------------------------------------------------------
# notificaciones
# ---------------------------------------------------------------------------
@router.get("/notificaciones")
async def api_listar_notificaciones(sesion: dict = Depends(verificar_token_dependencia)):
    """lista notificaciones del sistema para el usuario."""
    usuario_id = sesion["usuario_id"]

    # las notificaciones son eventos dirigidos al usuario (por ahora se usa eventos_seguridad
    # y mensajes como notificaciones)
    rows = ejecutar_sql(
        "select id, tipo, detalle, fecha from eventos_seguridad "
        "where pcbot_id = (select pcbot_id from usuarios where id = ?) "
        "order by id desc limit 50",
        (usuario_id,),
    )

    # mensajes no leidos como notificaciones
    mensajes = ejecutar_sql(
        "select id, texto, fecha from mensajes "
        "where destino_id = ? and leido = 0 order by id desc limit 20",
        (usuario_id,),
    )

    eventos = [
        {
            "id": r["id"],
            "tipo": r["tipo"],
            "mensaje": r.get("detalle", ""),
            "fecha": r["fecha"],
            "leido": False,
        }
        for r in rows
    ]

    notificaciones_mensajes = [
        {
            "id": r["id"],
            "tipo": "mensaje",
            "mensaje": r.get("texto", ""),
            "fecha": r["fecha"],
            "leido": False,
        }
        for r in mensajes
    ]

    todas = eventos + notificaciones_mensajes
    todas.sort(key=lambda x: x.get("fecha", ""), reverse=True)

    return {"exito": True, "notificaciones": todas[:50]}


@router.post("/notificaciones/marcar_leida/{notificacion_id}")
async def api_marcar_notificacion_leida(
    notificacion_id: int,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """marca una notificacion como leida."""
    # intentar marcar en mensajes
    ejecutar_sql(
        "update mensajes set leido = 1 where id = ? and destino_id = ?",
        (notificacion_id, sesion["usuario_id"]),
    )
    return {"exito": True, "mensaje": "notificacion marcada como leida"}


# ---------------------------------------------------------------------------
# usuario config
# ---------------------------------------------------------------------------
@router.put("/usuario")
async def api_actualizar_usuario(
    req: ActualizarUsuarioRequest,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """actualiza datos del usuario (username, email, password)."""
    usuario_id = sesion["usuario_id"]

    import hashlib

    campos = []
    params = []

    if req.username is not None:
        campos.append("username = ?")
        params.append(req.username.strip())

    if req.email is not None:
        # verificar que no exista
        existente = ejecutar_sql_unico(
            "select id from usuarios where email = ? and id != ?",
            (req.email.strip().lower(), usuario_id),
        )
        if existente:
            return {"exito": False, "mensaje": "el email ya esta en uso"}
        campos.append("email = ?")
        params.append(req.email.strip().lower())

    if req.password is not None and req.password_actual is not None:
        # verificar password actual
        usuario = ejecutar_sql_unico(
            "select password_hash from usuarios where id = ?",
            (usuario_id,),
        )
        if usuario:
            email_usuario = sesion.get("email", "")
            hash_actual = hashlib.pbkdf2_hmac(
                "sha256", req.password_actual.encode(), email_usuario.encode(), 100000
            ).hex()
            if usuario["password_hash"] != hash_actual:
                return {"exito": False, "mensaje": "password actual incorrecto"}

            nuevo_hash = hashlib.pbkdf2_hmac(
                "sha256", req.password.encode(), (req.email or email_usuario).encode(), 100000
            ).hex()
            campos.append("password_hash = ?")
            params.append(nuevo_hash)

    if campos:
        params.append(usuario_id)
        ejecutar_sql(
            f"update usuarios set {', '.join(campos)} where id = ?",
            tuple(params),
        )

    return {"exito": True, "mensaje": "datos actualizados"}


@router.get("/usuario/configuracion")
async def api_obtener_configuracion(sesion: dict = Depends(verificar_token_dependencia)):
    """obtiene configuracion personal del usuario."""
    usuario_id = sesion["usuario_id"]

    # cargar config desde variables_globales con prefijo cfg_usuario_{id}
    config_raw = ejecutar_sql_unico(
        "select valor from variables_globales where clave = ?",
        (f"cfg_usuario_{usuario_id}",),
    )

    config_default = {
        "idioma": "es",
        "notificaciones_activas": True,
        "tema": "oscuro",
    }

    if config_raw:
        import json as _json
        try:
            config_personal = _json.loads(config_raw["valor"])
            config_default.update(config_personal)
        except (_json.JSONDecodeError, TypeError):
            pass

    return {"exito": True, "configuracion": config_default}


@router.post("/usuario/configuracion")
async def api_guardar_configuracion(
    req: ConfiguracionRequest,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """guarda configuracion personal del usuario."""
    usuario_id = sesion["usuario_id"]

    import json as _json

    # cargar config existente o empezar con default
    config_raw = ejecutar_sql_unico(
        "select valor from variables_globales where clave = ?",
        (f"cfg_usuario_{usuario_id}",),
    )

    config = {}
    if config_raw:
        try:
            config.update(_json.loads(config_raw["valor"]))
        except (_json.JSONDecodeError, TypeError):
            pass

    if req.idioma is not None:
        config["idioma"] = req.idioma
    if req.notificaciones_activas is not None:
        config["notificaciones_activas"] = req.notificaciones_activas

    ejecutar_sql(
        "insert or replace into variables_globales (clave, valor) values (?, ?)",
        (f"cfg_usuario_{usuario_id}", _json.dumps(config, ensure_ascii=False)),
    )

    return {"exito": True, "configuracion": config, "mensaje": "configuracion guardada"}