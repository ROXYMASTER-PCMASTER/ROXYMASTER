# api_kbt.py - router fastapi para endpoints kbt. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from api_auth import verificar_token_dependencia
from tokenomics import (
    obtener_balance as consultar_balance,
    estadisticas_kbt as obtener_estadisticas_kbt,
    generar_proyecciones,
)
from db import ejecutar_sql_unico, ejecutar_sql, ejecutar_insercion
from variables_globales import obtener_variables

router = APIRouter(prefix="/api/kbt", tags=["kbt"])


class ComprarKbtRequest(BaseModel):
    cantidad_kbt: float
    moneda: str = "pen"  # pen o usd


@router.get("/balance")
async def api_balance(sesion: dict = Depends(verificar_token_dependencia)):
    """consulta el balance kbt del usuario autenticado."""
    usuario_id = sesion["usuario_id"]
    balance = consultar_balance(usuario_id)
    if balance is None:
        raise HTTPException(status_code=404, detail="wallet no encontrada")

    # obtener totales adicionales
    wallet = ejecutar_sql_unico(
        "select minado_total, comprado_total, retirado_total from wallets where usuario_id = ?",
        (usuario_id,),
    )
    return {
        "exito": True,
        "balance": balance,
        "minado_total": wallet["minado_total"] if wallet else 0,
        "comprado_total": wallet["comprado_total"] if wallet else 0,
        "retirado_total": wallet["retirado_total"] if wallet else 0,
    }


@router.post("/comprar")
async def api_comprar_kbt(
    req: ComprarKbtRequest,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """compra tokens kbt. debita del admin (id=1) y acredita al comprador."""
    usuario_id = sesion["usuario_id"]

    if req.cantidad_kbt <= 0:
        raise HTTPException(status_code=400, detail="la cantidad debe ser positiva")

    # precio real desde variables_globales
    vars_sistema = obtener_variables()
    p_token = float(vars_sistema.get("p_token", 1.0))

    if req.moneda == "usd":
        fx = float(vars_sistema.get("fx", 3.70))
        precio_unitario_pen = p_token
        costo_fiat = round(req.cantidad_kbt * (precio_unitario_pen / fx), 2)
    else:
        costo_fiat = round(req.cantidad_kbt * p_token, 2)

    comision_pct = 0.05  # 5% de comision
    comision = round(costo_fiat * comision_pct, 2)
    total_fiat = round(costo_fiat + comision, 2)

    # verificar saldo del admin (id=1)
    admin_wallet = ejecutar_sql_unico(
        "select id, balance from wallets where usuario_id = ?",
        (1,),
    )
    if not admin_wallet or admin_wallet["balance"] < req.cantidad_kbt:
        raise HTTPException(
            status_code=400,
            detail="el sistema no tiene suficientes tokens disponibles. contacta al administrador.",
        )

    # verificar wallet del comprador
    comprador_wallet = ejecutar_sql_unico(
        "select id, balance from wallets where usuario_id = ?",
        (usuario_id,),
    )

    from datetime import datetime
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # debitar del admin
    ejecutar_sql(
        "update wallets set balance = coalesce(balance, 0) - ? where usuario_id = ?",
        (req.cantidad_kbt, 1),
    )

    # acreditar al comprador
    if not comprador_wallet:
        ejecutar_insercion(
            "insert into wallets (usuario_id, balance, comprado_total) values (?, ?, ?)",
            (usuario_id, req.cantidad_kbt, req.cantidad_kbt),
        )
        balance_nuevo = req.cantidad_kbt
    else:
        ejecutar_sql(
            "update wallets set balance = coalesce(balance, 0) + ?, "
            "comprado_total = coalesce(comprado_total, 0) + ? where usuario_id = ?",
            (req.cantidad_kbt, req.cantidad_kbt, usuario_id),
        )
        balance_nuevo = float(comprador_wallet["balance"]) + req.cantidad_kbt

    # registrar transaccion para el comprador
    ejecutar_insercion(
        "insert into transacciones (origen_id, destino_id, tipo, monto, concepto, fecha) "
        "values (?, ?, 'compra_sistema', ?, ?, ?)",
        (1, usuario_id, req.cantidad_kbt,
         f"compra de {req.cantidad_kbt} kbt a s/ {costo_fiat}", ahora),
    )

    # registrar transaccion de auditoria para el admin
    ejecutar_insercion(
        "insert into transacciones (origen_id, destino_id, tipo, monto, concepto, fecha) "
        "values (?, ?, 'compra_sistema', ?, ?, ?)",
        (usuario_id, 1, req.cantidad_kbt,
         f"venta de {req.cantidad_kbt} kbt a usuario {usuario_id}", ahora),
    )

    return {
        "exito": True,
        "balance_nuevo": balance_nuevo,
        "cantidad_kbt": req.cantidad_kbt,
        "costo_fiat": costo_fiat,
        "comision": comision,
        "total_fiat": total_fiat,
        "moneda": req.moneda,
        "precio_unitario_pen": p_token,
    }


@router.get("/estadisticas")
async def api_estadisticas(sesion: dict = Depends(verificar_token_dependencia)):
    """obtiene estadisticas globales del token kbt."""
    stats = obtener_estadisticas_kbt()
    return {"exito": True, "estadisticas": stats}


@router.get("/proyecciones")
async def api_proyecciones(
    meses: int = 3,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """genera proyecciones a 3, 9 o 18 meses."""
    if meses not in (3, 9, 18):
        raise HTTPException(status_code=400, detail="meses debe ser 3, 9 o 18")
    proyecciones = generar_proyecciones(meses)
    return {"exito": True, "meses": meses, "proyecciones": proyecciones}