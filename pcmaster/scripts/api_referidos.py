# api_referidos.py - router de referidos (codigos, registro, recompensas).
# roxymaster v8.3 - utf-8 sin bom, nombres en minusculas, <= 400 lineas

import logging
import random
import string
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from db import ejecutar_sql, ejecutar_sql_unico, ejecutar_insercion
from auth import verificar_token_opcional, generar_codigo_referido

logger = logging.getLogger("roxymaster.api_referidos")

router = APIRouter(prefix="/api/referidos", tags=["referidos"])


def _usuario_requerido(sesion: dict) -> int:
    if not sesion:
        raise HTTPException(status_code=401, detail="autenticacion requerida")
    uid = sesion.get("usuario_id")
    if not uid:
        raise HTTPException(status_code=401, detail="token invalido")
    return uid


# ---------------------------------------------------------------------------
# post /api/referidos/generar_codigo
# ---------------------------------------------------------------------------
@router.post("/generar_codigo")
async def generar_codigo(sesion: dict = Depends(verificar_token_opcional)):
    """genera un codigo de referido unico para el usuario si no tiene uno."""
    uid = _usuario_requerido(sesion)

    # verificar si ya tiene codigo
    existente = ejecutar_sql_unico(
        "select codigo from referidos where usuario_id = ?", (uid,)
    )
    if existente:
        return {"exito": True, "codigo": existente["codigo"], "mensaje": "codigo ya existente"}

    # verificar en usuarios
    usuario = ejecutar_sql_unico(
        "select codigo_referido from usuarios where id = ?", (uid,)
    )
    if usuario and usuario.get("codigo_referido"):
        codigo = usuario["codigo_referido"]
        # asegurar que exista en tabla referidos
        ejecutar_insercion(
            "insert or ignore into referidos (usuario_id, codigo) values (?, ?)",
            (uid, codigo),
        )
        return {"exito": True, "codigo": codigo, "mensaje": "codigo recuperado de usuarios"}

    # generar nuevo codigo unico
    intentos = 0
    while intentos < 10:
        codigo = generar_codigo_referido()
        existe = ejecutar_sql_unico(
            "select id from referidos where codigo = ?", (codigo,)
        )
        if not existe:
            break
        intentos += 1
    else:
        raise HTTPException(status_code=500, detail="no se pudo generar codigo unico")

    # guardar en tabla referidos y actualizar usuario
    ejecutar_insercion(
        "insert into referidos (usuario_id, codigo) values (?, ?)",
        (uid, codigo),
    )
    ejecutar_sql(
        "update usuarios set codigo_referido = ? where id = ?",
        (codigo, uid),
    )

    logger.info(f"codigo referido generado: usuario={uid} codigo={codigo}")
    return {"exito": True, "codigo": codigo, "mensaje": "codigo generado exitosamente"}


# ---------------------------------------------------------------------------
# post /api/referidos/registrar
# ---------------------------------------------------------------------------
@router.post("/registrar")
async def registrar_referido(request: Request, sesion: dict = Depends(verificar_token_opcional)):
    """asocia el usuario autenticado (o su perfil) a un codigo de referido.
    body: {codigo}"""
    uid = _usuario_requerido(sesion)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="cuerpo invalido")

    codigo = body.get("codigo", "").strip()
    if not codigo:
        raise HTTPException(status_code=400, detail="codigo de referido requerido")

    # buscar el codigo en la tabla referidos
    referido = ejecutar_sql_unico(
        "select usuario_id from referidos where codigo = ?", (codigo,)
    )
    if not referido:
        raise HTTPException(status_code=404, detail="codigo de referido no encontrado")

    referidor_id = referido["usuario_id"]
    if referidor_id == uid:
        raise HTTPException(status_code=400, detail="no puedes autoreferirte")

    # actualizar el campo referido_por en usuarios
    ejecutar_sql(
        "update usuarios set referido_por = ? where id = ?",
        (codigo, uid),
    )

    logger.info(f"referido registrado: usuario={uid} referidor={referidor_id} codigo={codigo}")
    return {
        "exito": True,
        "referidor_id": referidor_id,
        "mensaje": "referido registrado exitosamente",
    }


# ---------------------------------------------------------------------------
# get /api/referidos/mis_referidos
# ---------------------------------------------------------------------------
@router.get("/mis_referidos")
async def mis_referidos(sesion: dict = Depends(verificar_token_opcional)):
    """lista los usuarios que se han registrado con el codigo del usuario."""
    uid = _usuario_requerido(sesion)

    # obtener codigo del usuario
    codigo_info = ejecutar_sql_unico(
        "select codigo from referidos where usuario_id = ?", (uid,)
    )
    if not codigo_info:
        return {"exito": True, "codigo": None, "referidos": []}

    codigo = codigo_info["codigo"]

    # buscar usuarios que usaron este codigo
    referidos = ejecutar_sql(
        "select id, email, username, fecha_registro from usuarios "
        "where referido_por = ? order by fecha_registro desc",
        (codigo,),
    )

    return {
        "exito": True,
        "codigo": codigo,
        "cantidad": len(referidos),
        "referidos": referidos,
    }


# ---------------------------------------------------------------------------
# get /api/referidos/recompensas
# ---------------------------------------------------------------------------
@router.get("/recompensas")
async def recompensas_referidos(sesion: dict = Depends(verificar_token_opcional)):
    """lista las recompensas acumuladas por referidos."""
    uid = _usuario_requerido(sesion)

    recompensas = ejecutar_sql(
        "select id, origen_id as granjero_id, monto, concepto, fecha "
        "from transacciones where destino_id = ? and tipo = 'referido' "
        "order by fecha desc",
        (uid,),
    )

    total = sum(float(r.get("monto", 0)) for r in recompensas)

    return {
        "exito": True,
        "total_tokens": round(total, 8),
        "cantidad": len(recompensas),
        "recompensas": recompensas,
    }