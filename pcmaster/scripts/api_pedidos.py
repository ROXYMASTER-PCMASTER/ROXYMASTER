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
)
from auth import verificar_token_opcional
from ws_manager import obtener_pcbot_de_usuario
from orchestrator import crear_comando

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
    """crea un pedido de servicio, descuenta tokens y envia comando al pcbot."""
    uid = _usuario_requerido(sesion)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="cuerpo invalido")

    url = body.get("url", "").strip()
    seguidores = int(body.get("seguidores", 0))
    perfiles = int(body.get("perfiles", 0))
    horas = float(body.get("horas", 0))
    nivel_comentarios = body.get("nivel_comentarios", "basico")
    tipo_pedido = body.get("tipo_pedido", "vistas")

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

    logger.info(f"[PEDIDO-DIAG] uid={uid} url={url} perfiles={perfiles} horas={horas} costo={costo_tokens}")

    # guardar pedido en bd
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pedido_id = ejecutar_insercion(
        """insert into pedidos (usuario_id, url, seguidores_streamer, cantidad_perfiles,
           duracion_horas, nivel_comentarios, tipo_pedido, costo_tokens, estado,
           comando_id, fecha_creacion)
           values (?, ?, ?, ?, ?, ?, ?, ?, 'pendiente', ?, ?)""",
        (uid, url, seguidores, perfiles, horas, nivel_comentarios, tipo_pedido,
         costo_tokens, comando_id, ahora),
    )

    if not pedido_id:
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

    # enviar comando al pcbot
    duracion_minutos = int(horas * 60)

    parametros_pedido = {
        "url": url,
        "cantidad": perfiles,
        "duracion": duracion_minutos,
        "nivel_comentarios": nivel_comentarios,
    }

    pcbot_id = obtener_pcbot_de_usuario(uid)
    logger.info(f"[PEDIDO-DIAG] uid={uid} pcbot_id='{pcbot_id}' comando_id={comando_id}")

    # log del payload exacto que se enviara al pcbot (para depuracion)
    payload_exacto = {
        "tipo": "asignar",
        "comando_id": comando_id,
        "parametros": parametros_pedido,
    }
    logger.info(f"[PEDIDO-DIAG] PAYLOAD_EXACTO a enviar a pcbot_id='{pcbot_id}': {json.dumps(payload_exacto, ensure_ascii=False)}")
    logger.info(f"[PEDIDO-DIAG] pcbot_id='{pcbot_id}' presente en orchestrator._conexiones_ws? CHEQUEAR LOGS")

    resultado_orch = await crear_comando(
        tipo="asignar",
        parametros=parametros_pedido,
        pcbot_id=pcbot_id,
        comando_id=comando_id,
    )
    logger.info(f"[PEDIDO-DIAG] resultado_orch={resultado_orch}")

    if not resultado_orch.get("exito"):
        logger.warning(
            f"[PEDIDO-DIAG] pedido {pedido_id}: FALLO orchestrator. "
            f"pcbot_id='{pcbot_id}' error={resultado_orch.get('error')}"
        )
        return {
            "exito": True,
            "pedido_id": pedido_id,
            "costo_tokens": costo_tokens,
            "comando_id": comando_id,
            "comando_enviado": False,
            "mensaje": "pedido creado pero no se pudo encolar el comando. se reintentara.",
        }

    # actualizar estado a enviado
    ejecutar_sql("update pedidos set estado = 'enviado' where id = ?", (pedido_id,))

    logger.info(f"[PEDIDO-DIAG] pedido creado #{pedido_id} usuario={uid} costo={costo_tokens} pcbot_id='{pcbot_id}'")
    return {
        "exito": True,
        "pedido_id": pedido_id,
        "costo_tokens": costo_tokens,
        "comando_id": comando_id,
        "comando_enviado": True,
        "mensaje": "pedido creado y comando enviado al pcbot",
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
                  fecha_creacion
           from pedidos
           where usuario_id = ?
           order by fecha_creacion desc""",
        (uid,),
    )

    return {
        "exito": True,
        "pedidos": pedidos,
    }