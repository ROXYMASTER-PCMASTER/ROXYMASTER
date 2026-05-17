# api_pedidos_acciones.py - acciones sobre pedidos existentes: eliminar y detener.
# roxymaster v8.3 - utf-8 sin bom, nombres en minusculas, <= 400 lineas

import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from db import ejecutar_sql, ejecutar_sql_unico, ejecutar_insercion
from auth import verificar_token_opcional
from ws_manager import obtener_pcbot_de_usuario
from orchestrator import crear_comando

logger = logging.getLogger("roxymaster.api_pedidos_acciones")

router = APIRouter(prefix="/api/pedidos", tags=["pedidos_acciones"])


def _usuario_requerido(sesion: dict) -> int:
    """valida que la sesion tenga usuario_id y lo devuelve."""
    if not sesion:
        raise HTTPException(status_code=401, detail="autenticacion requerida")
    uid = sesion.get("usuario_id")
    if not uid:
        raise HTTPException(status_code=401, detail="token invalido")
    return uid


# ---------------------------------------------------------------------------
# delete /api/pedidos/{pedido_id} - eliminar pedido pendiente
# ---------------------------------------------------------------------------
@router.delete("/{pedido_id}")
async def eliminar_pedido(pedido_id: int, sesion: dict = Depends(verificar_token_opcional)):
    """elimina un pedido solo si esta en estado pendiente y pertenece al usuario."""
    uid = _usuario_requerido(sesion)

    pedido = ejecutar_sql_unico(
        "select id, estado, costo_tokens from pedidos where id = ? and usuario_id = ?",
        (pedido_id, uid),
    )
    if not pedido:
        raise HTTPException(status_code=404, detail="pedido no encontrado")

    estado = pedido.get("estado", "").lower()
    if estado != "pendiente":
        raise HTTPException(
            status_code=400,
            detail=f"no se puede eliminar un pedido en estado '{estado}'. solo pendientes.",
        )

    costo = float(pedido.get("costo_tokens", 0))
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # reembolsar tokens
    if costo > 0:
        ejecutar_sql(
            "update wallets set balance = balance + ? where usuario_id = ?",
            (costo, uid),
        )
        ejecutar_insercion(
            "insert into transacciones (origen_id, destino_id, tipo, monto, concepto, fecha) "
            "values (?, null, 'reembolso', ?, ?, ?)",
            (uid, costo, f"reembolso por eliminacion de pedido #{pedido_id}", ahora),
        )
        logger.info(f"[PEDIDO] reembolso de {costo} tokens a usuario {uid} por pedido #{pedido_id}")

    # eliminar pedido
    ejecutar_sql("delete from pedidos where id = ? and usuario_id = ?", (pedido_id, uid))

    logger.info(f"[PEDIDO] pedido #{pedido_id} eliminado por usuario {uid}")
    return {
        "exito": True,
        "mensaje": f"pedido #{pedido_id} eliminado. se reembolsaron {costo} tokens." if costo > 0 else f"pedido #{pedido_id} eliminado.",
    }


# ---------------------------------------------------------------------------
# post /api/pedidos/{pedido_id}/detener - detener pedido en progreso
# ---------------------------------------------------------------------------
@router.post("/{pedido_id}/detener")
async def detener_pedido(pedido_id: int, sesion: dict = Depends(verificar_token_opcional)):
    """detiene un pedido en estado trabajando o en progreso."""
    uid = _usuario_requerido(sesion)

    pedido = ejecutar_sql_unico(
        "select id, estado, comando_id from pedidos where id = ? and usuario_id = ?",
        (pedido_id, uid),
    )
    if not pedido:
        raise HTTPException(status_code=404, detail="pedido no encontrado")

    estado = pedido.get("estado", "").lower()
    estados_detenibles = ["trabajando", "en progreso", "enviado"]
    if estado not in estados_detenibles:
        raise HTTPException(
            status_code=400,
            detail=f"no se puede detener un pedido en estado '{estado}'.",
        )

    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    comando_id = pedido.get("comando_id")

    # enviar comando de detener al pcbot
    if comando_id:
        try:
            resultado_orch = await crear_comando(
                tipo="detener",
                parametros={"pedido_id": pedido_id, "comando_id": comando_id},
                comando_id=f"detener_{comando_id}",
            )
            if resultado_orch.get("exito"):
                logger.info(f"[PEDIDO] comando detener enviado para pedido #{pedido_id}")
            else:
                logger.warning(f"[PEDIDO] no se pudo enviar comando detener para pedido #{pedido_id}: {resultado_orch.get('error')}")
        except Exception as e:
            logger.error(f"[PEDIDO] error al enviar comando detener para pedido #{pedido_id}: {e}")

    # actualizar estado a detenido
    ejecutar_sql(
        "update pedidos set estado = 'detenido', fecha_actualizacion = ? where id = ?",
        (ahora, pedido_id),
    )

    # registrar transaccion de reembolso parcial
    reembolso_total = 0
    pedido_completo = ejecutar_sql_unico(
        "select costo_tokens from pedidos where id = ?",
        (pedido_id,),
    )
    if pedido_completo:
        costo_total = float(pedido_completo.get("costo_tokens", 0))
        reembolso_total = round(costo_total * 0.5, 4)  # 50% de reembolso
        if reembolso_total > 0:
            ejecutar_sql(
                "update wallets set balance = balance + ? where usuario_id = ?",
                (reembolso_total, uid),
            )
            ejecutar_insercion(
                "insert into transacciones (origen_id, destino_id, tipo, monto, concepto, fecha) "
                "values (?, null, 'reembolso_parcial', ?, ?, ?)",
                (uid, reembolso_total, f"reembolso parcial 50% por detener pedido #{pedido_id}", ahora),
            )
            logger.info(f"[PEDIDO] reembolso parcial de {reembolso_total} tokens a usuario {uid} por pedido #{pedido_id}")
    logger.info(f"[PEDIDO] pedido #{pedido_id} detenido por usuario {uid}")
    return {
        "exito": True,
        "mensaje": f"pedido #{pedido_id} detenido.",
        "reembolso": reembolso_total,
    }
