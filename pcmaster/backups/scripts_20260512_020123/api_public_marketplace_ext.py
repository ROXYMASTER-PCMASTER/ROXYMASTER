# api_public_marketplace_ext.py - endpoints publicos de marketplace para dashboard
# roxymaster v8.3 - todo en minusculas, utf-8 sin bom, <= 400 lineas

from fastapi import APIRouter, Depends, HTTPException
from typing import Optional

from api_auth import verificar_token_dependencia
from db import ejecutar_sql_unico, ejecutar_sql, ejecutar_insercion
from marketplace import tomar_orden, listar_ordenes, obtener_orden
from variables_globales import comision_marketplace

router = APIRouter(prefix="/api/marketplace", tags=["public_marketplace_ext"])


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _mapear_orden_publica(orden: dict) -> dict:
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


# ---------------------------------------------------------------------------
# mis ordenes
# ---------------------------------------------------------------------------
@router.get("/mis_ordenes")
async def api_mis_ordenes(
    estado: Optional[str] = None,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """lista las ordenes propias del usuario (compra/venta) con estado."""
    usuario_id = sesion["usuario_id"]

    sql = (
        "select id, cantidad_kbt, precio_pen, tipo, estado, comentario, "
        "vendedor_id, comprador_id, fecha_creacion, fecha_completada "
        "from ordenes_p2p where vendedor_id = ? or comprador_id = ?"
    )
    params = [usuario_id, usuario_id]

    if estado:
        sql += " and estado = ?"
        params.append(estado)

    sql += " order by id desc limit 100"
    rows = ejecutar_sql(sql, tuple(params))

    ordenes = []
    for r in rows:
        orden = dict(r)
        # determinar si es compra o venta desde la perspectiva del usuario
        if orden["vendedor_id"] == usuario_id:
            rol_usuario = "vendedor"
        else:
            rol_usuario = "comprador"

        ordenes.append({
            "id": orden["id"],
            "cantidad_kbt": orden["cantidad_kbt"],
            "precio_unitario": orden["precio_pen"],
            "total_pen": round(orden["cantidad_kbt"] * orden["precio_pen"], 2),
            "tipo": orden["tipo"],
            "estado": orden["estado"],
            "comentario": orden.get("comentario", "") or "",
            "rol_usuario": rol_usuario,
            "fecha_creacion": orden.get("fecha_creacion", ""),
            "fecha_completada": orden.get("fecha_completada", ""),
        })

    return {"exito": True, "ordenes": ordenes}


# ---------------------------------------------------------------------------
# libro de ordenes (ordenes abiertas de otros usuarios)
# ---------------------------------------------------------------------------
@router.get("/libro")
async def api_libro_ordenes(
    tipo: Optional[str] = None,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """ver ordenes abiertas de otros usuarios para comprar/vender kbt."""
    usuario_id = sesion["usuario_id"]

    sql = (
        "select o.id, o.cantidad_kbt, o.precio_pen, o.tipo, o.estado, "
        "o.comentario, o.fecha_creacion, u.email as vendedor_email "
        "from ordenes_p2p o join usuarios u on u.id = o.vendedor_id "
        "where o.estado = 'abierta' and o.vendedor_id != ?"
    )
    params = [usuario_id]

    if tipo:
        sql += " and o.tipo = ?"
        params.append(tipo)

    sql += " order by o.precio_pen asc, o.fecha_creacion asc"
    rows = ejecutar_sql(sql, tuple(params))

    return {
        "exito": True,
        "ordenes": [_mapear_orden_publica(dict(r)) for r in rows],
    }


# ---------------------------------------------------------------------------
# ejecutar orden (comprar/vender al precio publicado)
# ---------------------------------------------------------------------------
@router.post("/ejecutar/{orden_id}")
async def api_ejecutar_orden(
    orden_id: int,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """ejecuta una orden (compra el kbt publicado)."""
    usuario_id = sesion["usuario_id"]

    # verificar que la orden exista y este abierta
    orden = obtener_orden(orden_id)
    if not orden:
        raise HTTPException(status_code=404, detail="orden no encontrada")

    if orden["estado"] != "abierta":
        raise HTTPException(status_code=400, detail="la orden no esta abierta")

    if orden["vendedor_id"] == usuario_id:
        raise HTTPException(status_code=400, detail="no puedes ejecutar tu propia orden")

    # ejecutar usando el sistema de marketplace existente
    resultado = tomar_orden(usuario_id, orden_id)
    if not resultado.get("exito"):
        raise HTTPException(status_code=400, detail=resultado.get("error", "error al ejecutar orden"))

    # calcular total con comision
    total_pen = round(orden["cantidad_kbt"] * orden["precio_pen"], 2)
    comision = round(total_pen * comision_marketplace, 2)

    return {
        "exito": True,
        "orden_id": orden_id,
        "cantidad_kbt": orden["cantidad_kbt"],
        "precio_unitario": orden["precio_pen"],
        "total_pen": total_pen,
        "comision": comision,
        "mensaje": "orden ejecutada exitosamente",
    }