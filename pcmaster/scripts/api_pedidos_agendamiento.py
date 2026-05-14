# api_pedidos_agendamiento.py - endpoint para crear pedidos con agendamiento por hora
# roxymaster v8.3 - utf-8 sin bom, nombres en minusculas
# modulo separado porque api_pedidos.py ya supera 400 lineas
# v2: eliminado envio directo al pcbot, delegado a procesador_cola.py (cola fifo)

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

from db import ejecutar_sql, ejecutar_sql_unico, ejecutar_insercion
from tokenomics_core import calcular_costo_streamer
from auth import verificar_token_opcional

logger = logging.getLogger("roxymaster.api_pedidos_agendamiento")

router = APIRouter(prefix="/api/pedidos", tags=["pedidos_agendamiento"])


def _usuario_requerido(sesion: dict) -> int:
    """valida que la sesion tenga usuario_id y lo devuelve."""
    if not sesion:
        raise HTTPException(status_code=401, detail="autenticacion requerida")
    uid = sesion.get("usuario_id")
    if not uid:
        raise HTTPException(status_code=401, detail="token invalido")
    return uid


# ---------------------------------------------------------------------------
# post /api/pedidos/crear_con_agenda
# ---------------------------------------------------------------------------
@router.post("/crear_con_agenda")
async def crear_pedido_con_agenda(request: Request, sesion: dict = Depends(verificar_token_opcional)):
    """crea un pedido con soporte opcional de agendamiento (hora_inicio, hora_fin).

    campos obligatorios: url, seguidores, perfiles, minutos (o horas).
    campos opcionales: hora_inicio, hora_fin (formato iso 8601 utc).

    nota: el envio al pcbot lo maneja procesador_cola.py (cola fifo) de forma async.
    este endpoint solo valida, descuenta tokens, y guarda en bd.
    """
    uid = _usuario_requerido(sesion)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="cuerpo invalido")

    # --- campos basicos del pedido ---
    url = body.get("url", "").strip()
    seguidores = int(body.get("seguidores", 0))
    perfiles = int(body.get("perfiles", 0))
    minutos = float(body.get("minutos", 0) or body.get("horas", 0) or 0)
    if body.get("horas") and not body.get("minutos"):
        horas = float(body.get("horas", 0))
    else:
        horas = minutos / 60.0
    nivel_comentarios = body.get("nivel_comentarios", "basico")
    tipo_pedido = body.get("tipo_pedido") or body.get("tipo", "vistas")

    # --- validaciones basicas ---
    if not url:
        raise HTTPException(status_code=400, detail="url requerida")
    if seguidores <= 0 or perfiles <= 0 or horas <= 0:
        raise HTTPException(status_code=400, detail="seguidores, perfiles y horas deben ser > 0")

    # --- campos de agendamiento opcionales ---
    hora_inicio_str = body.get("hora_inicio", "").strip()
    hora_fin_str = body.get("hora_fin", "").strip()

    hora_inicio_dt = None
    hora_fin_dt = None
    es_programado = False

    if hora_inicio_str and hora_fin_str:
        # validar ambos
        try:
            hora_inicio_dt = datetime.fromisoformat(hora_inicio_str.replace("Z", "+00:00"))
            hora_fin_dt = datetime.fromisoformat(hora_fin_str.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="formato iso 8601 invalido en hora_inicio o hora_fin")

        ahora_utc = datetime.now(timezone.utc)

        # validar hora_inicio futura
        if hora_inicio_dt <= ahora_utc:
            raise HTTPException(status_code=400, detail="hora_inicio debe ser una fecha futura")

        # validar que hora_fin > hora_inicio
        if hora_fin_dt <= hora_inicio_dt:
            raise HTTPException(status_code=400, detail="hora_fin debe ser posterior a hora_inicio")

        es_programado = True

    elif hora_inicio_str and not hora_fin_str:
        # solo hora_inicio sin hora_fin -> usar duracion normal
        try:
            hora_inicio_dt = datetime.fromisoformat(hora_inicio_str.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="formato iso 8601 invalido en hora_inicio")

        ahora_utc = datetime.now(timezone.utc)
        if hora_inicio_dt <= ahora_utc:
            raise HTTPException(status_code=400, detail="hora_inicio debe ser una fecha futura")

        es_programado = True

    elif not hora_inicio_str and hora_fin_str:
        # hora_fin sin hora_inicio -> error
        raise HTTPException(status_code=400, detail="hora_fin requiere hora_inicio")

    # calcular duracion en segundos si ambos campos presentes
    duracion_seg = None
    if hora_inicio_dt and hora_fin_dt:
        duracion_seg = int((hora_fin_dt - hora_inicio_dt).total_seconds())
        # la duracion en horas se sobreescribe con la diferencia real
        horas = duracion_seg / 3600.0

    # --- calcular costo ---
    costo = calcular_costo_streamer(seguidores, perfiles, horas)
    costo_tokens = costo["tokens"]

    multiplicador_vip = 2.0 if tipo_pedido == "vip" else 1.0
    costo_tokens *= multiplicador_vip

    # --- verificar saldo ---
    wallet = ejecutar_sql_unico("select balance from wallets where usuario_id = ?", (uid,))
    if not wallet or float(wallet["balance"]) < costo_tokens:
        raise HTTPException(status_code=400, detail="saldo insuficiente")

    # --- descontar tokens ---
    ejecutar_sql(
        "update wallets set balance = balance - ? where usuario_id = ?",
        (costo_tokens, uid),
    )

    # --- generar comando_id ---
    comando_id = f"pedido_{uuid.uuid4().hex[:12]}"

    # --- determinar estado inicial ---
    # ambos casos (programado y pendiente) los maneja procesador_cola.py
    estado_inicial = "programado" if es_programado else "pendiente"

    # --- guardar en bd con campos de agendamiento ---
    ahora = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    hora_inicio_iso = hora_inicio_dt.strftime("%Y-%m-%dT%H:%M:%S+00:00") if hora_inicio_dt else None
    hora_fin_iso = hora_fin_dt.strftime("%Y-%m-%dT%H:%M:%S+00:00") if hora_fin_dt else None

    logger.info(
        "[PEDIDO-AGENDA] insertando pedido uid=%s url=%s estado=%s hora_inicio=%s hora_fin=%s",
        uid, url, estado_inicial, hora_inicio_iso, hora_fin_iso,
    )

    pedido_id = ejecutar_insercion(
        """insert into pedidos (usuario_id, url, seguidores_streamer, cantidad_perfiles,
           duracion_horas, nivel_comentarios, tipo_pedido, costo_tokens, estado,
           comando_id, fecha_creacion, hora_inicio_programada, hora_fin_programada)
           values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (uid, url, seguidores, perfiles, horas, nivel_comentarios, tipo_pedido,
         costo_tokens, estado_inicial, comando_id, ahora,
         hora_inicio_iso, hora_fin_iso),
    )

    if not pedido_id:
        logger.error("[PEDIDO-AGENDA] fallo insercion, revirtiendo descuento uid=%s", uid)
        ejecutar_sql("update wallets set balance = balance + ? where usuario_id = ?",
                     (costo_tokens, uid))
        raise HTTPException(status_code=500, detail="error al crear pedido")

    # --- registrar transaccion ---
    ejecutar_insercion(
        "insert into transacciones (origen_id, destino_id, tipo, monto, concepto, fecha) "
        "values (?, null, 'pedido', ?, ?, ?)",
        (uid, costo_tokens,
         f"pedido #{pedido_id}: {perfiles} perfiles x {horas:.1f}h para {seguidores} seguidores",
         ahora),
    )

    # --- respuesta generica para ambos casos ---
    # el envio al pcbot lo realiza procesador_cola.py (cola fifo)
    if es_programado:
        return {
            "exito": True,
            "pedido_id": pedido_id,
            "costo_tokens": costo_tokens,
            "comando_id": comando_id,
            "comando_enviado": False,
            "programado": True,
            "estado": "programado",
            "hora_inicio": hora_inicio_iso,
            "hora_fin": hora_fin_iso,
            "mensaje": (
                f"pedido programado para ejecutarse desde {hora_inicio_iso} hasta {hora_fin_iso}. "
                "sera procesado por la cola fifo."
            ),
        }

    # pedido inmediato (pendiente)
    return {
        "exito": True,
        "pedido_id": pedido_id,
        "costo_tokens": costo_tokens,
        "comando_id": comando_id,
        "comando_enviado": False,
        "programado": False,
        "estado": "pendiente",
        "mensaje": (
            "pedido creado en cola pendiente. sera procesado por la cola fifo "
            "y asignado a perfiles disponibles en los proximos segundos."
        ),
    }