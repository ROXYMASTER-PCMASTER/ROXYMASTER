# api_kbt.py - router fastapi para endpoints kbt. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional

from api_auth import verificar_token_dependencia
from tokenomics import (
    obtener_balance as consultar_balance,
    estadisticas_kbt as obtener_estadisticas_kbt,
    generar_proyecciones,
)

router = APIRouter(prefix="/api/kbt", tags=["kbt"])


@router.get("/balance")
async def api_balance(sesion: dict = Depends(verificar_token_dependencia)):
    """consulta el balance kbt del usuario autenticado."""
    usuario_id = sesion["usuario_id"]
    balance = consultar_balance(usuario_id)
    if balance is None:
        raise HTTPException(status_code=404, detail="wallet no encontrada")
    return {"exito": True, "balance": balance}


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