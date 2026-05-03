# api_pedidos.py - flujo de pedidos con estados. roxymaster v8.3
# utf-8 sin bom, nombres en minusculas, <= 400 lineas

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth import verificar_token
from db import ejecutar_sql, ejecutar_sql_unico

logger = logging.getLogger("roxymaster.api_pedidos")
router = APIRouter(prefix="/api/pedidos", tags=["pedidos"])


class PedidoCrear(BaseModel):
    tipo: str  # "comando", "kbt", "servicio"
    descripcion: str
    metadata: Optional[dict] = None


class PedidoActualizar(BaseModel):
    estado: str  # "pendiente", "en_progreso", "completado", "cancelado"
    notas: Optional[str] = None


@router.post("/crear")
async def crear_pedido(pedido: PedidoCrear, token: str = Depends(verificar_token)):
    """crea un nuevo pedido."""
    usuario = obtener_usuario_por_token(token)
    if not usuario:
        raise HTTPException(status_code=401, detail="token invalido")
    ahora = datetime.now().isoformat()
    meta_str = json.dumps(pedido.metadata) if pedido.metadata else "{}"
    try:
        pid = ejecutar_sql(
            """insert into pedidos (usuario_id, tipo, descripcion, metadata, estado, creado_en, actualizado_en)
               values (?, ?, ?, ?, 'pendiente', ?, ?) returning id""",
            (usuario["id"], pedido.tipo, pedido.descripcion, meta_str, ahora, ahora),
        )
        if isinstance(pid, (list, tuple)):
            pid = pid[0]
        elif hasattr(pid, "fetchone"):
            row = pid.fetchone()
            pid = row[0] if row else None
        elif isinstance(pid, int):
            pass
        else:
            pid = pid.get("id") if isinstance(pid, dict) else getattr(pid, "id", None)
        logger.info(f"pedido creado: id={pid}, tipo={pedido.tipo}")
        return {"exito": True, "pedido_id": pid, "mensaje": "pedido creado correctamente"}
    except Exception as e:
        logger.error(f"error al crear pedido: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/listar")
async def listar_pedidos(
    estado: Optional[str] = Query(None),
    token: str = Depends(verificar_token),
):
    """lista pedidos, opcionalmente filtrados por estado."""
    usuario = obtener_usuario_por_token(token)
    if not usuario:
        raise HTTPException(status_code=401, detail="token invalido")
    try:
        if estado:
            rows = ejecutar_sql(
                "select id, tipo, descripcion, estado, creado_en from pedidos where usuario_id = ? and estado = ? order by creado_en desc",
                (usuario["id"], estado),
            )
        else:
            rows = ejecutar_sql(
                "select id, tipo, descripcion, estado, creado_en from pedidos where usuario_id = ? order by creado_en desc",
                (usuario["id"],),
            )
        pedidos = []
        for r in rows:
            pedidos.append({"id": r[0], "tipo": r[1], "descripcion": r[2], "estado": r[3], "creado_en": r[4]})
        return {"exito": True, "pedidos": pedidos}
    except Exception as e:
        logger.error(f"error al listar pedidos: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{pedido_id}")
async def actualizar_pedido(pedido_id: int, datos: PedidoActualizar, token: str = Depends(verificar_token)):
    """actualiza el estado de un pedido."""
    usuario = obtener_usuario_por_token(token)
    if not usuario:
        raise HTTPException(status_code=401, detail="token invalido")
    estados_validos = ["pendiente", "en_progreso", "completado", "cancelado"]
    if datos.estado not in estados_validos:
        raise HTTPException(status_code=400, detail=f"estado invalido. usar: {', '.join(estados_validos)}")
    ahora = datetime.now().isoformat()
    try:
        ejecutar_sql(
            "update pedidos set estado = ?, notas = ?, actualizado_en = ? where id = ? and usuario_id = ?",
            (datos.estado, datos.notas, ahora, pedido_id, usuario["id"]),
        )
        logger.info(f"pedido {pedido_id} actualizado a {datos.estado}")
        return {"exito": True, "mensaje": f"pedido {pedido_id} actualizado a '{datos.estado}'"}
    except Exception as e:
        logger.error(f"error al actualizar pedido {pedido_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{pedido_id}")
async def obtener_pedido(pedido_id: int, token: str = Depends(verificar_token)):
    """obtiene detalles de un pedido especifico."""
    usuario = obtener_usuario_por_token(token)
    if not usuario:
        raise HTTPException(status_code=401, detail="token invalido")
    try:
        row = ejecutar_sql_unico(
            "select id, tipo, descripcion, metadata, estado, notas, creado_en, actualizado_en from pedidos where id = ? and usuario_id = ?",
            (pedido_id, usuario["id"]),
        )
        if not row:
            raise HTTPException(status_code=404, detail="pedido no encontrado")
        return {
            "exito": True,
            "pedido": {
                "id": row[0],
                "tipo": row[1],
                "descripcion": row[2],
                "metadata": json.loads(row[3]) if row[3] else {},
                "estado": row[4],
                "notas": row[5],
                "creado_en": row[6],
                "actualizado_en": row[7],
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"error al obtener pedido {pedido_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def obtener_usuario_por_token(token: str) -> Optional[dict]:
    """obtiene datos del usuario desde un token de sesion."""
    try:
        from auth import verificar_token
        resultado = verificar_token(token)
        if resultado.get("exito") and resultado.get("usuario"):
            return resultado["usuario"]
        return None
    except Exception:
        return None