# api_public_finanzas.py - endpoints de finanzas, retiros, kbt para dashboard publico
# roxymaster v8.3 - todo en minusculas, utf-8 sin bom, <= 400 lineas

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from api_auth import verificar_token_dependencia
from db import ejecutar_sql_unico, ejecutar_sql, ejecutar_insercion
from tokenomics import obtener_balance, obtener_tasa_kbt_pen, obtener_estadisticas_minado
from variables_globales import obtener_variables

router = APIRouter(prefix="/api", tags=["public_finanzas"])


# ---------------------------------------------------------------------------
# modelos
# ---------------------------------------------------------------------------
class SolicitarRetiroRequest(BaseModel):
    cantidad_kbt: float
    wallet_destino: str


# ---------------------------------------------------------------------------
# transacciones
# ---------------------------------------------------------------------------
@router.get("/transacciones")
async def api_listar_transacciones(
    tipo: Optional[str] = None,
    fecha_desde: Optional[str] = None,
    fecha_hasta: Optional[str] = None,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """historial de transacciones del usuario con filtros."""
    usuario_id = sesion["usuario_id"]

    sql = (
        "select id, tipo, monto, concepto, fecha from transacciones "
        "where (origen_id = ? or destino_id = ?)"
    )
    params = [usuario_id, usuario_id]

    if tipo:
        sql += " and tipo = ?"
        params.append(tipo)
    if fecha_desde:
        sql += " and fecha >= ?"
        params.append(fecha_desde)
    if fecha_hasta:
        sql += " and fecha <= ?"
        params.append(fecha_hasta)

    sql += " order by fecha desc limit 200"
    rows = ejecutar_sql(sql, tuple(params))
    return {"exito": True, "transacciones": [dict(r) for r in rows]}


# ---------------------------------------------------------------------------
# retiros
# ---------------------------------------------------------------------------
@router.post("/retiros/solicitar")
async def api_solicitar_retiro(
    req: SolicitarRetiroRequest,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """solicita retiro de kbt a pen."""
    usuario_id = sesion["usuario_id"]

    if req.cantidad_kbt <= 0:
        return {"exito": False, "mensaje": "cantidad debe ser mayor a 0"}

    if not req.wallet_destino or not req.wallet_destino.strip():
        return {"exito": False, "mensaje": "wallet destino es requerida"}

    # verificar balance
    balance = obtener_balance(usuario_id)
    if balance < req.cantidad_kbt:
        return {"exito": False, "mensaje": "balance insuficiente"}

    # obtener tasa de conversion
    tasa = obtener_tasa_kbt_pen()
    comision_pct = float(obtener_variables().get("comision_retiro", 0.05))
    comision = round(req.cantidad_kbt * comision_pct, 6)
    cantidad_pen = round((req.cantidad_kbt - comision) * tasa, 2)

    # crear solicitud
    id_solicitud = ejecutar_insercion(
        "insert into retiros (usuario_id, cantidad_kbt, cantidad_pen, comision, estado) "
        "values (?, ?, ?, ?, 'pendiente')",
        (usuario_id, req.cantidad_kbt, cantidad_pen, comision),
    )

    return {
        "exito": True,
        "id_solicitud": id_solicitud,
        "cantidad_kbt": req.cantidad_kbt,
        "cantidad_pen": cantidad_pen,
        "comision": comision,
        "mensaje": "solicitud de retiro creada",
    }


@router.get("/retiros")
async def api_listar_retiros(sesion: dict = Depends(verificar_token_dependencia)):
    """historial de solicitudes de retiro del usuario."""
    usuario_id = sesion["usuario_id"]
    rows = ejecutar_sql(
        "select id, cantidad_kbt, cantidad_pen, comision, estado, "
        "fecha_solicitud, fecha_procesado "
        "from retiros where usuario_id = ? order by id desc limit 100",
        (usuario_id,),
    )
    return {"exito": True, "retiros": [dict(r) for r in rows]}


@router.get("/retiros/{retiro_id}")
async def api_estado_retiro(
    retiro_id: int,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """consulta estado de una solicitud especifica."""
    usuario_id = sesion["usuario_id"]
    row = ejecutar_sql_unico(
        "select id, cantidad_kbt, cantidad_pen, comision, estado, "
        "fecha_solicitud, fecha_procesado "
        "from retiros where id = ? and usuario_id = ?",
        (retiro_id, usuario_id),
    )
    if not row:
        return {"exito": False, "mensaje": "retiro no encontrado"}
    return {"exito": True, "retiro": dict(row)}


# ---------------------------------------------------------------------------
# kbt
# ---------------------------------------------------------------------------
@router.get("/kbt/balance")
async def api_kbt_balance(sesion: dict = Depends(verificar_token_dependencia)):
    """balance actual de kbt del usuario."""
    usuario_id = sesion["usuario_id"]
    balance = obtener_balance(usuario_id)
    return {"exito": True, "balance": balance}


@router.get("/kbt/tasa")
async def api_kbt_tasa(sesion: dict = Depends(verificar_token_dependencia)):
    """tasa de conversion kbt a pen actual."""
    tasa = obtener_tasa_kbt_pen()
    return {"exito": True, "tasa_kbt_pen": tasa}


@router.get("/kbt/minado")
async def api_kbt_minado(sesion: dict = Depends(verificar_token_dependencia)):
    """estadisticas de minado personal."""
    usuario_id = sesion["usuario_id"]
    stats = obtener_estadisticas_minado(usuario_id)
    return {"exito": True, "minado": stats}


@router.get("/kbt/recoleccion")
async def api_kbt_recoleccion(sesion: dict = Depends(verificar_token_dependencia)):
    """estadisticas de recoleccion (comisiones)."""
    usuario_id = sesion["usuario_id"]

    wallet = ejecutar_sql_unico(
        "select recolectado_total from wallets where usuario_id = ?",
        (usuario_id,),
    )
    recolectado = float(wallet["recolectado_total"]) if wallet and wallet["recolectado_total"] else 0.0

    transacciones = ejecutar_sql(
        "select id, monto, concepto, fecha from transacciones "
        "where (origen_id = ? or destino_id = ?) and tipo = 'recoleccion' "
        "order by fecha desc limit 50",
        (usuario_id, usuario_id),
    )

    return {
        "exito": True,
        "recolectado_total": recolectado,
        "historial": [dict(t) for t in transacciones],
    }


@router.post("/kbt/reclamar")
async def api_kbt_reclamar(sesion: dict = Depends(verificar_token_dependencia)):
    """reclama tokens pendientes (staking, comisiones no distribuidas)."""
    usuario_id = sesion["usuario_id"]

    # buscar tokens pendientes en transacciones no reclamadas
    pendientes = ejecutar_sql(
        "select id, monto, concepto from transacciones "
        "where destino_id = ? and tipo = 'pendiente_reclamar'",
        (usuario_id,),
    )

    total_reclamado = 0.0
    ids_reclamados = []

    for t in pendientes:
        total_reclamado += float(t["monto"])
        ids_reclamados.append(t["id"])

    if not ids_reclamados:
        return {"exito": True, "total_reclamado": 0, "mensaje": "no hay tokens pendientes"}

    # actualizar wallet
    wallet = ejecutar_sql_unico(
        "select id, balance from wallets where usuario_id = ?",
        (usuario_id,),
    )
    if wallet:
        nuevo_balance = float(wallet["balance"]) + total_reclamado
        ejecutar_sql(
            "update wallets set balance = ?, actualizado = datetime('now','localtime') "
            "where usuario_id = ?",
            (nuevo_balance, usuario_id),
        )

    # marcar como reclamadas
    for tid in ids_reclamados:
        ejecutar_sql(
            "update transacciones set tipo = 'reclamado' where id = ?",
            (tid,),
        )

    return {
        "exito": True,
        "total_reclamado": total_reclamado,
        "mensaje": f"{total_reclamado} kbt reclamados",
    }


# ---------------------------------------------------------------------------
# genesis
# ---------------------------------------------------------------------------
@router.get("/genesis")
async def api_genesis(sesion: dict = Depends(verificar_token_dependencia)):
    """informacion de la genesis: etapa actual, tokens liberados, restantes."""
    etapas = ejecutar_sql(
        "select etapa, porcentaje, tokens, liberado, fecha_liberacion "
        "from genesis order by etapa"
    )

    etapa_actual = None
    total_liberado = 0.0
    total_tokens = 0.0
    proxima_liberacion = None

    for e in etapas:
        total_tokens += float(e["tokens"])
        if e["liberado"]:
            total_liberado += float(e["tokens"])
        if not e["liberado"] and etapa_actual is None:
            etapa_actual = e["etapa"]
            proxima_liberacion = e["fecha_liberacion"]

    porcentaje_liberado = round((total_liberado / total_tokens * 100), 2) if total_tokens > 0 else 0

    return {
        "exito": True,
        "etapa_actual": etapa_actual,
        "porcentaje_liberado": porcentaje_liberado,
        "tokens_liberados": total_liberado,
        "tokens_restantes": round(total_tokens - total_liberado, 2),
        "total_tokens": total_tokens,
        "proxima_liberacion": proxima_liberacion,
        "etapas": [dict(e) for e in etapas],
    }


# ---------------------------------------------------------------------------
# happy hour
# ---------------------------------------------------------------------------
@router.get("/happy_hour/actual")
async def api_happy_hour_actual(sesion: dict = Depends(verificar_token_dependencia)):
    """multiplicador activo y tiempo restante del happy hour actual."""
    now = ejecutar_sql_unico("select datetime('now','localtime') as ahora")
    ahora = now["ahora"] if now else ""

    hh = ejecutar_sql_unico(
        "select id, multiplicador, fecha_inicio, fecha_fin, activo "
        "from happy_hour where activo = 1 and fecha_inicio <= ? and fecha_fin >= ? "
        "order by id desc limit 1",
        (ahora, ahora),
    )

    if not hh:
        return {"exito": True, "activo": False, "mensaje": "no hay happy hour activo"}

    return {
        "exito": True,
        "activo": True,
        "multiplicador": hh["multiplicador"],
        "fecha_inicio": hh["fecha_inicio"],
        "fecha_fin": hh["fecha_fin"],
    }


@router.get("/happy_hour/historial")
async def api_happy_hour_historial(sesion: dict = Depends(verificar_token_dependencia)):
    """lista de happy hours pasadas."""
    rows = ejecutar_sql(
        "select id, multiplicador, fecha_inicio, fecha_fin, activo "
        "from happy_hour order by fecha_inicio desc limit 100"
    )
    return {"exito": True, "historial": [dict(r) for r in rows]}