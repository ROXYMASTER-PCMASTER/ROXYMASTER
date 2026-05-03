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

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])


class CrearOrdenRequest(BaseModel):
    cantidad_kbt: float
    precio_pen: float
    tipo: str = "venta"
    comentario: Optional[str] = None


@router.get("/ordenes")
async def api_listar_ordenes(
    estado: Optional[str] = None,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """lista ordenes p2p con filtro opcional por estado."""
    ordenes = listar_ordenes(estado=estado)
    return {"exito": True, "ordenes": ordenes}


@router.get("/ordenes/{orden_id}")
async def api_obtener_orden(
    orden_id: int,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """obtiene detalle de una orden especifica."""
    orden = obtener_orden(orden_id)
    if not orden:
        raise HTTPException(status_code=404, detail="orden no encontrada")
    return {"exito": True, "orden": orden}


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