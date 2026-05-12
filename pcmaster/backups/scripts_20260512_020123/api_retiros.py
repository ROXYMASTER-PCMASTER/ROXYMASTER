# api_retiros.py - router de retiros de tokens a soles.
# roxymaster v8.3 - utf-8 sin bom, nombres en minusculas, <= 400 lineas

import json
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request

from db import ejecutar_sql, ejecutar_sql_unico, ejecutar_insercion
from tokenomics_core import (
    calcular_retiro,
    comision_retiro,
    _cargar_params,
    _ahora_str,
)
from auth import verificar_token_opcional

logger = logging.getLogger("roxymaster.api_retiros")

router = APIRouter(prefix="/api/retiros", tags=["retiros"])


def _usuario_requerido(sesion: dict) -> int:
    if not sesion:
        raise HTTPException(status_code=401, detail="autenticacion requerida")
    uid = sesion.get("usuario_id")
    if not uid:
        raise HTTPException(status_code=401, detail="token invalido")
    return uid


# ---------------------------------------------------------------------------
# post /api/retiros/solicitar
# ---------------------------------------------------------------------------
@router.post("/solicitar")
async def solicitar_retiro(request: Request, sesion: dict = Depends(verificar_token_opcional)):
    """solicita un retiro bloqueando tokens."""
    uid = _usuario_requerido(sesion)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="cuerpo invalido")

    tokens = float(body.get("tokens", 0))
    plazo_dias = int(body.get("plazo_dias", 0))

    if tokens <= 0:
        raise HTTPException(status_code=400, detail="cantidad de tokens debe ser > 0")
    if plazo_dias < 0:
        raise HTTPException(status_code=400, detail="plazo_dias no puede ser negativo")

    # verificar saldo
    wallet = ejecutar_sql_unico("select balance from wallets where usuario_id = ?", (uid,))
    if not wallet or float(wallet["balance"]) < tokens:
        raise HTTPException(status_code=400, detail="saldo insuficiente")

    # calcular valores del retiro (info)
    calculo = calcular_retiro(tokens, plazo_dias)

    # descontar tokens del balance
    ejecutar_sql("update wallets set balance = balance - ? where usuario_id = ?", (tokens, uid))

    # registrar en retiros_pendientes
    ahora = _ahora_str()
    ejecutar_insercion(
        """insert into retiros_pendientes
           (usuario_id, tokens_bloqueados, fecha_solicitud, plazo_dias, estado)
           values (?, ?, ?, ?, 'pendiente')""",
        (uid, tokens, ahora, plazo_dias),
    )

    # registrar transaccion
    ejecutar_insercion(
        "insert into transacciones (origen_id, destino_id, tipo, monto, concepto, fecha) "
        "values (?, null, 'retiro_bloqueado', ?, ?, ?)",
        (uid, tokens,
         f"solicitud retiro: {tokens} tokens a {plazo_dias} dias. neto estimado: {calculo['monto_neto']} soles",
         ahora),
    )

    logger.info(f"retiro solicitado: usuario={uid} tokens={tokens} plazo={plazo_dias}d")
    return {
        "exito": True,
        "tokens_bloqueados": tokens,
        "plazo_dias": plazo_dias,
        "estimacion": calculo,
        "mensaje": "retiro solicitado. los tokens estan bloqueados hasta la ejecucion.",
    }


# ---------------------------------------------------------------------------
# post /api/retiros/ejecutar
# ---------------------------------------------------------------------------
@router.post("/ejecutar")
async def ejecutar_retiro(request: Request, sesion: dict = Depends(verificar_token_opcional)):
    """ejecuta un retiro pendiente, aplica comision, impuesto, bonificacion."""
    uid = _usuario_requerido(sesion)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="cuerpo invalido")

    retiro_id = int(body.get("id_retiro", 0))
    if retiro_id <= 0:
        raise HTTPException(status_code=400, detail="id_retiro invalido")

    # buscar retiro pendiente
    retiro = ejecutar_sql_unico(
        "select * from retiros_pendientes where id = ? and usuario_id = ?",
        (retiro_id, uid),
    )
    if not retiro:
        raise HTTPException(status_code=404, detail="retiro no encontrado")
    if retiro["estado"] != "pendiente":
        raise HTTPException(status_code=400, detail="el retiro ya fue ejecutado o cancelado")

    # calcular dias transcurridos
    try:
        fecha_sol = datetime.strptime(str(retiro["fecha_solicitud"]), "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        fecha_sol = datetime.strptime(str(retiro["fecha_solicitud"]), "%Y-%m-%d")
    dias_transcurridos = (datetime.now() - fecha_sol).days

    # usar el mayor entre dias_transcurridos y plazo_dias para la comision
    dias_efectivos = max(dias_transcurridos, retiro["plazo_dias"])

    tokens = float(retiro["tokens_bloqueados"])
    calculo = calcular_retiro(tokens, dias_efectivos)

    # actualizar retiro como ejecutado
    ahora = _ahora_str()
    ejecutar_sql(
        """update retiros_pendientes
           set estado = 'ejecutado',
               fecha_ejecucion = ?,
               comision_aplicada = ?,
               impuesto_aplicado = ?,
               monto_neto = ?
           where id = ?""",
        (ahora, calculo["comision"], calculo["impuesto"], calculo["monto_neto"], retiro_id),
    )

    # actualizar wallet (retirado_total)
    ejecutar_sql(
        "update wallets set retirado_total = retirado_total + ? where usuario_id = ?",
        (tokens, uid),
    )

    # registrar transaccion
    ejecutar_insercion(
        "insert into transacciones (origen_id, destino_id, tipo, monto, concepto, fecha) "
        "values (?, null, 'retiro_ejecutado', ?, ?, ?)",
        (uid, tokens,
         f"retiro #{retiro_id} ejecutado: {tokens} tokens -> {calculo['monto_neto']} soles netos",
         ahora),
    )

    logger.info(f"retiro ejecutado #{retiro_id} usuario={uid} neto={calculo['monto_neto']} soles")
    return {
        "exito": True,
        "retiro_id": retiro_id,
        "tokens_retirados": tokens,
        "dias_transcurridos": dias_transcurridos,
        "detalle": calculo,
        "mensaje": f"retiro ejecutado. monto neto: {calculo['monto_neto']} soles",
    }


# ---------------------------------------------------------------------------
# get /api/retiros/mis_retiros
# ---------------------------------------------------------------------------
@router.get("/mis_retiros")
async def mis_retiros(sesion: dict = Depends(verificar_token_opcional)):
    """lista los retiros del usuario."""
    uid = _usuario_requerido(sesion)
    retiros = ejecutar_sql(
        "select * from retiros_pendientes where usuario_id = ? order by fecha_solicitud desc",
        (uid,),
    )
    return {"exito": True, "retiros": retiros}


# ---------------------------------------------------------------------------
# get /api/retiros/calcular
# ---------------------------------------------------------------------------
@router.get("/calcular")
async def calcular_retiro_endpoint(tokens: float = 0, plazo_dias: int = 0,
                                   sesion: dict = Depends(verificar_token_opcional)):
    """calcula el monto neto de un retiro sin solicitar."""
    if not sesion:
        raise HTTPException(status_code=401, detail="autenticacion requerida")
    if tokens <= 0:
        raise HTTPException(status_code=400, detail="tokens debe ser > 0")
    calculo = calcular_retiro(tokens, plazo_dias)
    return {"exito": True, "detalle": calculo}