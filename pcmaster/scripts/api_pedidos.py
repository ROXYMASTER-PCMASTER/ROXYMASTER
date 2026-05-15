# api_pedidos.py - router de pedidos de servicios para streamers.
# roxymaster v8.3 - utf-8 sin bom, nombres en minusculas, <= 400 lineas

import json
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from db import ejecutar_sql, ejecutar_sql_unico, ejecutar_insercion
from tokenomics_core import (
    calcular_costo_streamer,
    _cargar_params,
    RECARGO_COMENTARISTA_IA,
    RECARGO_PROGRAMACION,
)
from auth import verificar_token_opcional
# (asignacion inmediata eliminada - ahora el procesador_cola maneja la planificacion)

logger = logging.getLogger("roxymaster.api_pedidos")

router = APIRouter(prefix="/api/pedidos", tags=["pedidos"])


def _usuario_requerido(sesion: dict) -> int:
    """valida que la sesion tenga usuario_id y lo devuelve."""
    if not sesion:
        raise HTTPException(status_code=401, detail="autenticacion requerida")
    uid = sesion.get("usuario_id")
    if not uid:
        raise HTTPException(status_code=401, detail="token invalido")
    return uid


# ---------------------------------------------------------------------------
# post /api/pedidos/calcular_costo
# ---------------------------------------------------------------------------
@router.post("/calcular_costo")
async def calcular_costo_endpoint(request: Request, sesion: dict = Depends(verificar_token_opcional)):
    """calcula el costo de un pedido en tokens."""
    uid = _usuario_requerido(sesion)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="cuerpo invalido")

    seguidores = int(body.get("seguidores", 0))
    perfiles = int(body.get("perfiles", 0))
    horas = float(body.get("horas", 0))
    nivel_comentarios = body.get("nivel_comentarios", "basico")
    tipo_pedido = body.get("tipo_pedido", "vistas")

    if seguidores <= 0 or perfiles <= 0 or horas <= 0:
        raise HTTPException(status_code=400, detail="seguidores, perfiles y horas deben ser > 0")

    costo = calcular_costo_streamer(seguidores, perfiles, horas)
    costo_tokens = costo["tokens"]

    # aplicar multiplicador vip (x2.0)
    multiplicador_vip = 2.0 if tipo_pedido == "vip" else 1.0
    costo_tokens *= multiplicador_vip

    return {
        "exito": True,
        "costo_usd": costo["usd"] * multiplicador_vip,
        "costo_soles": costo["soles"] * multiplicador_vip,
        "costo_tokens": costo_tokens,
        "seguidores": seguidores,
        "perfiles": perfiles,
        "horas": horas,
        "nivel_comentarios": nivel_comentarios,
        "tipo_pedido": tipo_pedido,
    }


# ---------------------------------------------------------------------------
# post /api/pedidos/crear
# ---------------------------------------------------------------------------
@router.post("/crear")
async def crear_pedido(request: Request, sesion: dict = Depends(verificar_token_opcional)):
    """crea un pedido de servicio, descuenta tokens y lo deja agendado para el procesador_cola."""
    uid = _usuario_requerido(sesion)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="cuerpo invalido")

    url = body.get("url", "").strip()
    seguidores = int(body.get("seguidores", 0))
    perfiles = int(body.get("perfiles", 0))
    # aceptar 'minutos' (frontend) o 'horas' (api directa)
    minutos = float(body.get("minutos", 0) or body.get("horas", 0) or 0)
    if body.get("horas") and not body.get("minutos"):
        horas = float(body.get("horas", 0))
    else:
        horas = minutos / 60.0  # convertir minutos a horas
    nivel_comentarios = body.get("nivel_comentarios", "basico")
    # aceptar 'tipo' (frontend) o 'tipo_pedido' (api directa)
    tipo_pedido = body.get("tipo_pedido") or body.get("tipo", "vistas")

    # nuevos campos: comentarista ia y hora de inicio (programacion)
    comentarios_ia = body.get("comentarios_ia", False)
    hora_inicio = body.get("hora_inicio", None)

    if not url:
        raise HTTPException(status_code=400, detail="url requerida")
    if seguidores <= 0 or perfiles <= 0 or horas <= 0:
        raise HTTPException(status_code=400, detail="seguidores, perfiles y horas deben ser > 0")

    # calcular costo
    costo = calcular_costo_streamer(seguidores, perfiles, horas)
    costo_tokens = costo["tokens"]

    # aplicar multiplicador vip (x2.0)
    multiplicador_vip = 2.0 if tipo_pedido == "vip" else 1.0
    costo_tokens *= multiplicador_vip

    # aplicar recargos configurables
    if hora_inicio:
        costo_tokens *= RECARGO_PROGRAMACION
    if comentarios_ia:
        costo_tokens *= RECARGO_COMENTARISTA_IA

    # verificar saldo
    wallet = ejecutar_sql_unico("select balance from wallets where usuario_id = ?", (uid,))
    if not wallet or float(wallet["balance"]) < costo_tokens:
        raise HTTPException(status_code=400, detail="saldo insuficiente")

    # descuento de tokens
    ejecutar_sql(
        "update wallets set balance = balance - ? where usuario_id = ?",
        (costo_tokens, uid),
    )

    # generar comando_id
    comando_id = f"pedido_{uuid.uuid4().hex[:12]}"

    logger.info(f"[PEDIDO-DIAG] uid={uid} url={url} perfiles={perfiles} horas={horas} costo={costo_tokens} comentarios_ia={comentarios_ia} hora_inicio={hora_inicio}")

    # LOG-ANTES: antes de insertar pedido en bd
    logger.info(f"[PEDIDO-LOG] paso 1/6: insertando pedido en bd uid={uid} url={url}")
    ahora = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # preparar hora_inicio_programada si aplica
    hora_inicio_programada = hora_inicio if hora_inicio else None

    pedido_id = ejecutar_insercion(
        """insert into pedidos (usuario_id, url, seguidores_streamer, cantidad_perfiles,
           duracion_horas, nivel_comentarios, tipo_pedido, costo_tokens, estado,
           comando_id, fecha_creacion, comentarios_ia, hora_inicio_programada)
           values (?, ?, ?, ?, ?, ?, ?, ?, 'agendado', ?, ?, ?, ?)""",
        (uid, url, seguidores, perfiles, horas, nivel_comentarios, tipo_pedido,
         costo_tokens, comando_id, ahora, comentarios_ia, hora_inicio_programada),
    )

    # LOG-DESPUES: resultado de insercion
    logger.info(f"[PEDIDO-LOG] paso 2/6: pedido insertado id={pedido_id}")
    if not pedido_id:
        logger.error(f"[PEDIDO-LOG] paso 2/6 FALLO: no se obtuvo pedido_id. revirtiendo descuento")
        # revertir descuento
        ejecutar_sql("update wallets set balance = balance + ? where usuario_id = ?",
                     (costo_tokens, uid))
        raise HTTPException(status_code=500, detail="error al crear pedido")

    # registrar transaccion
    ejecutar_insercion(
        "insert into transacciones (origen_id, destino_id, tipo, monto, concepto, fecha) "
        "values (?, null, 'pedido', ?, ?, ?)",
        (uid, costo_tokens,
         f"pedido #{pedido_id}: {perfiles} perfiles x {horas}h para {seguidores} seguidores",
         ahora),
    )

    logger.info(f"[PEDIDO-DIAG] pedido creado #{pedido_id} usuario={uid} costo={costo_tokens} — queda agendado para planificacion centralizada")
    return {
        "exito": True,
        "pedido_id": pedido_id,
        "costo_tokens": costo_tokens,
        "comando_id": comando_id,
        "mensaje": "pedido creado y en cola para ser procesado",
    }


# ---------------------------------------------------------------------------
# get /api/pedidos/mis_pedidos
# ---------------------------------------------------------------------------
@router.get("/mis_pedidos")
async def mis_pedidos(sesion: dict = Depends(verificar_token_opcional)):
    """lista los pedidos del usuario autenticado."""
    uid = _usuario_requerido(sesion)

    pedidos = ejecutar_sql(
        """select id, url, seguidores_streamer, cantidad_perfiles, duracion_horas,
                  nivel_comentarios, tipo_pedido, costo_tokens, estado, comando_id,
                  fecha_creacion, hora_inicio_programada, hora_fin_programada
           from pedidos
           where usuario_id = ?
           order by fecha_creacion desc""",
        (uid,),
    )

    # mapear nombres de campos para compatibilidad con frontend
    pedidos_mapeados = []
    for p in pedidos:
        duracion_horas = p["duracion_horas"] or 0
        pedidos_mapeados.append({
            "id": p["id"],
            "url": p["url"],
            "seguidores": p["seguidores_streamer"],
            "perfiles": p["cantidad_perfiles"],
            "duracion": int(duracion_horas * 60),
            "duracion_horas": duracion_horas,
            "minutos": int(duracion_horas * 60),
            "nivel_comentarios": p["nivel_comentarios"],
            "tipo": p["tipo_pedido"],
            "costo": p["costo_tokens"],
            "costo_total": p["costo_tokens"],
            "estado": p["estado"],
            "comando_id": p["comando_id"],
            "fecha_creacion": p["fecha_creacion"],
            "created_at": p["fecha_creacion"],
            "hora_inicio_programada": p["hora_inicio_programada"],
            "hora_fin_programada": p["hora_fin_programada"],
        })

    return {
        "exito": True,
        "pedidos": pedidos_mapeados,
    }


# ---------------------------------------------------------------------------
# delete /api/pedidos/{pedido_id}
# ---------------------------------------------------------------------------
@router.delete("/{pedido_id}")
async def eliminar_pedido(pedido_id: int, sesion: dict = Depends(verificar_token_opcional)):
    """elimina un pedido pendiente y reembolsa los tokens."""
    uid = _usuario_requerido(sesion)

    pedido = ejecutar_sql_unico(
        "select id, usuario_id, costo_tokens, estado from pedidos where id = ?",
        (pedido_id,),
    )
    if not pedido:
        raise HTTPException(status_code=404, detail="pedido no encontrado")
    if pedido["usuario_id"] != uid:
        raise HTTPException(status_code=403, detail="no tienes permiso para eliminar este pedido")
    if pedido["estado"] not in ("pendiente", "agendado"):
        raise HTTPException(status_code=400, detail="solo se pueden eliminar pedidos pendientes o agendados")

    # reembolsar tokens
    costo = float(pedido["costo_tokens"])
    ejecutar_sql("update wallets set balance = balance + ? where usuario_id = ?", (costo, uid))
    ejecutar_sql("delete from pedidos where id = ?", (pedido_id,))
    ejecutar_insercion(
        "insert into transacciones (origen_id, destino_id, tipo, monto, concepto, fecha) "
        "values (?, null, 'reembolso', ?, ?, ?)",
        (uid, costo, f"reembolso eliminacion pedido #{pedido_id}", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )

    logger.info(f"[PEDIDO] pedido #{pedido_id} eliminado por usuario {uid}, reembolso {costo} tokens")
    return {"exito": True, "mensaje": f"pedido #{pedido_id} eliminado, reembolso de {costo} tokens"}


# ---------------------------------------------------------------------------
# post /api/pedidos/{pedido_id}/detener
# ---------------------------------------------------------------------------
@router.post("/{pedido_id}/detener")
async def detener_pedido(pedido_id: int, sesion: dict = Depends(verificar_token_opcional)):
    """detiene un pedido en curso y reembolsa el 50% de los tokens."""
    uid = _usuario_requerido(sesion)

    pedido = ejecutar_sql_unico(
        "select id, usuario_id, costo_tokens, estado from pedidos where id = ?",
        (pedido_id,),
    )
    if not pedido:
        raise HTTPException(status_code=404, detail="pedido no encontrado")
    if pedido["usuario_id"] != uid:
        raise HTTPException(status_code=403, detail="no tienes permiso para detener este pedido")
    if pedido["estado"] not in ("trabajando", "en_progreso", "enviado"):
        raise HTTPException(status_code=400, detail="solo se pueden detener pedidos en curso")

    costo = float(pedido["costo_tokens"])
    reembolso = round(costo * 0.5, 4)

    ejecutar_sql("update wallets set balance = balance + ? where usuario_id = ?", (reembolso, uid))
    ejecutar_sql("update pedidos set estado = 'detenido' where id = ?", (pedido_id,))
    ejecutar_insercion(
        "insert into transacciones (origen_id, destino_id, tipo, monto, concepto, fecha) "
        "values (?, null, 'reembolso_parcial', ?, ?, ?)",
        (uid, reembolso, f"reembolso parcial (50%) detener pedido #{pedido_id}",
         datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )

    logger.info(f"[PEDIDO] pedido #{pedido_id} detenido por usuario {uid}, reembolso {reembolso} tokens")
    return {"exito": True, "mensaje": f"pedido #{pedido_id} detenido", "reembolso": reembolso}


# ---------------------------------------------------------------------------
# post /api/pedidos/{pedido_id}/reabrir
# ---------------------------------------------------------------------------
@router.post("/{pedido_id}/reabrir")
async def reabrir_pedido(pedido_id: int, sesion: dict = Depends(verificar_token_opcional)):
    """reabre un pedido detenido o fallido y lo pone en pendiente para reprocesar."""
    uid = _usuario_requerido(sesion)

    pedido = ejecutar_sql_unico(
        "select id, usuario_id, estado from pedidos where id = ?",
        (pedido_id,),
    )
    if not pedido:
        raise HTTPException(status_code=404, detail="pedido no encontrado")
    if pedido["usuario_id"] != uid:
        raise HTTPException(status_code=403, detail="no tienes permiso para reabrir este pedido")
    if pedido["estado"] not in ("detenido", "fallido"):
        raise HTTPException(status_code=400, detail="solo se pueden reabrir pedidos detenidos o fallidos")

    ejecutar_sql("update pedidos set estado = 'agendado' where id = ?", (pedido_id,))
    logger.info(f"[PEDIDO] pedido #{pedido_id} reabierto por usuario {uid}")

    return {"exito": True, "mensaje": f"pedido #{pedido_id} reabierto, sera reprocesado"}


# ---------------------------------------------------------------------------
# post /api/pedidos/{pedido_id}/cancelar
# ---------------------------------------------------------------------------
@router.post("/{pedido_id}/cancelar")
async def cancelar_pedido(pedido_id: int, sesion: dict = Depends(verificar_token_opcional)):
    """cancela un pedido sin reembolso y lo marca como finalizado."""
    uid = _usuario_requerido(sesion)

    pedido = ejecutar_sql_unico(
        "select id, usuario_id, costo_tokens, estado from pedidos where id = ?",
        (pedido_id,),
    )
    if not pedido:
        raise HTTPException(status_code=404, detail="pedido no encontrado")
    if pedido["usuario_id"] != uid:
        raise HTTPException(status_code=403, detail="no tienes permiso para cancelar este pedido")
    if pedido["estado"] not in ("agendado", "pendiente", "enviado", "trabajando", "en-progreso", "en_progreso"):
        raise HTTPException(status_code=400, detail="solo se pueden cancelar pedidos en estado agendado, pendiente, enviado o en progreso")

    costo = float(pedido["costo_tokens"])
    ejecutar_sql("update pedidos set estado = 'finalizado' where id = ?", (pedido_id,))
    ejecutar_insercion(
        "insert into transacciones (origen_id, destino_id, tipo, monto, concepto, fecha) "
        "values (?, null, 'cancelacion', 0, ?, ?)",
        (uid, f"cancelacion sin reembolso pedido #{pedido_id}: {costo} tokens retenidos",
         datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )

    logger.info(f"[PEDIDO] pedido #{pedido_id} cancelado por usuario {uid}, sin reembolso ({costo} tokens retenidos)")
    return {"exito": True, "mensaje": f"pedido #{pedido_id} cancelado. no hay devolucion ni reembolso"}