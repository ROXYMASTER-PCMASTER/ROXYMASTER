# api_marketplace.py - router fastapi para marketplace p2p. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from api_auth import verificar_token_dependencia
from marketplace import (
    crear_orden,
    tomar_orden,
    liberar_orden,
    cancelar_orden,
    listar_ordenes,
    obtener_orden,
    resolver_disputa,
)
from variables_globales import comision_marketplace

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])


class CrearOrdenRequest(BaseModel):
    cantidad_kbt: float
    precio_pen: float
    tipo: str = "venta"
    comentario: Optional[str] = None


class IntercambiarRequest(BaseModel):
    orden_id: int


def _mapear_orden(orden: dict) -> dict:
    """mapea una orden raw a formato frontend estandar."""
    return {
        "id": orden["id"],
        "cantidad_kbt": orden["cantidad_kbt"],
        "precio_unitario": orden["precio_pen"],
        "total_pen": round(orden["cantidad_kbt"] * orden["precio_pen"], 2),
        "tipo": orden["tipo"],
        "estado": orden["estado"],
        "comentario": orden.get("comentario", "") or "",
        "usuario_email": orden.get("vendedor_email", ""),
        "fecha_creacion": orden.get("fecha_creacion", ""),
        "fecha_completada": orden.get("fecha_completada", ""),
    }


@router.get("/ordenes")
async def api_listar_ordenes(
    estado: Optional[str] = None,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """lista ordenes p2p con filtro opcional por estado."""
    ordenes = listar_ordenes(estado=estado)
    ordenes_mapeadas = [_mapear_orden(o) for o in ordenes]
    return {"exito": True, "ordenes": ordenes_mapeadas}


@router.get("/ordenes/{orden_id}")
async def api_obtener_orden(
    orden_id: int,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """obtiene detalle de una orden especifica."""
    orden = obtener_orden(orden_id)
    if not orden:
        raise HTTPException(status_code=404, detail="orden no encontrada")
    return {"exito": True, "orden": _mapear_orden(orden)}


@router.post("/crear")
async def api_crear_orden(
    req: CrearOrdenRequest,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """crea una nueva orden de venta o compra."""
    resultado = crear_orden(
        vendedor_id=sesion["usuario_id"],
        cantidad_kbt=req.cantidad_kbt,
        precio_pen=req.precio_pen,
        tipo=req.tipo,
        comentario=req.comentario,
    )
    if not resultado.get("exito"):
        raise HTTPException(status_code=400, detail=resultado.get("error"))
    return resultado


@router.post("/tomar/{orden_id}")
async def api_tomar_orden(
    orden_id: int,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """acepta una orden abierta y la pone en escrow."""
    resultado = tomar_orden(sesion["usuario_id"], orden_id)
    if not resultado.get("exito"):
        raise HTTPException(status_code=400, detail=resultado.get("error"))
    return resultado


@router.post("/intercambiar")
async def api_intercambiar(
    req: IntercambiarRequest,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """toma una orden (intercambio) y devuelve total con comision."""
    resultado = tomar_orden(sesion["usuario_id"], req.orden_id)
    if not resultado.get("exito"):
        raise HTTPException(status_code=400, detail=resultado.get("error"))

    orden = obtener_orden(req.orden_id)
    total = round(orden["cantidad_kbt"] * orden["precio_pen"], 2) if orden else 0
    comision_pct = comision_marketplace * 100

    return {
        "exito": True,
        "orden_id": req.orden_id,
        "total": total,
        "comision_15pct": round(total * comision_marketplace, 2),
        "mensaje": "intercambio iniciado, tokens en escrow",
    }


@router.post("/liberar/{orden_id}")
async def api_liberar_orden(
    orden_id: int,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """libera los kbt al vendedor confirmando la recepcion."""
    resultado = liberar_orden(sesion["usuario_id"], orden_id)
    if not resultado.get("exito"):
        raise HTTPException(status_code=400, detail=resultado.get("error"))
    return resultado


@router.post("/cancelar/{orden_id}")
async def api_cancelar_orden(
    orden_id: int,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """cancela una orden abierta propia."""
    resultado = cancelar_orden(sesion["usuario_id"], orden_id)
    if not resultado.get("exito"):
        raise HTTPException(status_code=400, detail=resultado.get("error"))
    return resultado


@router.post("/disputa/{orden_id}")
async def api_resolver_disputa(
    orden_id: int,
    a_favor_de: str = "vendedor",
    sesion: dict = Depends(verificar_token_dependencia),
):
    """resuelve una disputa (solo admin)."""
    if sesion.get("rol") != "admin":
        raise HTTPException(status_code=403, detail="solo administradores")
    resultado = resolver_disputa(orden_id, a_favor_de, sesion["usuario_id"])
    if not resultado.get("exito"):
        raise HTTPException(status_code=400, detail=resultado.get("error"))
    return resultado