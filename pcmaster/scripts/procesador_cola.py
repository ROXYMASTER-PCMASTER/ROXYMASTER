# procesador_cola.py - procesador fifo de cola de pedidos
# roxymaster v8.3 - utf-8 sin bom, nombres en minusculas
# modulo independiente que procesa pedidos pendientes y programados
# y los asigna perfil por perfil a los pcbots del usuario

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

import heartbeat_cache
from ws_manager import (
    obtener_pcbots_de_usuario,
    obtener_pcbot_de_usuario,
    enviar_comando_al_pcbot,
)
from db import ejecutar_sql, ejecutar_insercion, ejecutar_sql_unico

logger = logging.getLogger("procesador_cola")


def _ahora_str() -> str:
    """devuelve timestamp utc en formato iso."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _ahora_dt() -> datetime:
    """devuelve datetime utc actual."""
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# bucle principal
# ---------------------------------------------------------------------------
async def procesar_cola_pedidos():
    """bucle principal del procesador de cola fifo.
    se ejecuta cada 10 segundos y procesa:
    - pedidos en estado 'programado' cuya hora_inicio ya llego -> pendiente
    - pedidos en estado 'pendiente' -> asigna perfiles y pasa a en_progreso
    """
    logger.info("procesador de cola pedidos iniciado (intervalo 10s)")
    while True:
        try:
            await _ciclo_procesador()
        except Exception as e:
            logger.error("error en ciclo procesador cola: %s", str(e)[:200])
        await asyncio.sleep(10)


async def _ciclo_procesador():
    """ejecuta una ronda de procesamiento de la cola fifo."""

    ahora = _ahora_dt()

    # obtener pedidos pendientes o programados listos para procesar
    # fifo estricto: order by fecha_creacion asc
    # incluir hora_inicio_programada y hora_fin_programada para agendamiento
    pedidos = ejecutar_sql(
        "select id, usuario_id, url, cantidad_perfiles, duracion_horas, "
        "nivel_comentarios, tipo_pedido, comando_id, fecha_creacion, estado, "
        "hora_inicio_programada, hora_fin_programada "
        "from pedidos "
        "where estado in ('pendiente', 'programado') "
        "order by fecha_creacion asc"
    )
    if not pedidos:
        return

    logger.info("[COLA] procesando %s pedidos pendientes/programados", len(pedidos))

    for pedido in pedidos:
        pedido_id = pedido["id"]
        estado_actual = pedido["estado"]

        try:
            # si es programado, verificar si ya es hora
            if estado_actual == "programado":
                if not _es_hora_de_ejecutar(pedido, ahora):
                    continue
                # transicionar a pendiente para procesarlo
                logger.info(
                    "[COLA] pedido %s programado: hora_inicio llego, pasando a pendiente",
                    pedido_id,
                )
                ejecutar_sql(
                    "update pedidos set estado = 'pendiente' where id = ?",
                    (pedido_id,),
                )

            # ahora procesar el pedido como pendiente
            await _procesar_pedido_pendiente(pedido)

        except Exception as e:
            logger.error(
                "[COLA] error procesando pedido %s: %s",
                pedido_id, str(e)[:200],
            )


def _es_hora_de_ejecutar(pedido: dict, ahora: datetime) -> bool:
    """verifica si un pedido programado ya debe ejecutarse.
    retorna true si hora_inicio_programada es nula o ya paso."""
    hora_inicio_str = pedido.get("hora_inicio_programada")
    if not hora_inicio_str:
        # no tiene hora programada, ejecutar ya
        return True

    try:
        if "+" in hora_inicio_str or "Z" in hora_inicio_str:
            hora_limpia = hora_inicio_str.replace("Z", "+00:00")
            hora_inicio = datetime.fromisoformat(hora_limpia)
        else:
            hora_inicio = datetime.strptime(hora_inicio_str, "%Y-%m-%d %H:%M:%S")
            hora_inicio = hora_inicio.replace(tzinfo=timezone.utc)

        return ahora >= hora_inicio
    except Exception as e:
        logger.error(
            "[COLA] error parseando hora_inicio '%s' en pedido %s: %s",
            hora_inicio_str, pedido.get("id"), str(e)[:200],
        )
        # si hay error, pasar a pendiente para no bloquear
        return True


# ---------------------------------------------------------------------------
# procesar pedido pendiente: asignar perfiles individualmente
# ---------------------------------------------------------------------------
async def _procesar_pedido_pendiente(pedido: dict):
    """procesa un pedido en estado pendiente.
    busca perfiles libres en los pcbots del usuario y asigna
    uno por uno hasta completar la cantidad solicitada."""
    pedido_id = pedido["id"]
    usuario_id = pedido["usuario_id"]
    cantidad_deseada = pedido.get("cantidad_perfiles", 1)
    url_pedido = pedido.get("url", "")
    duracion_horas = pedido.get("duracion_horas", 0)
    duracion_seg = max(1, int(duracion_horas * 3600))
    nivel_comentarios = pedido.get("nivel_comentarios", "basico")
    hora_inicio = pedido.get("hora_inicio_programada")
    hora_fin = pedido.get("hora_fin_programada")

    # obtener pcbots del usuario (todos los conectados)
    pcbots = _obtener_pcbots_usuario(usuario_id)
    if not pcbots:
        logger.warning(
            "[COLA] pedido %s: usuario %s no tiene pcbots conectados",
            pedido_id, usuario_id,
        )
        return

    asignados = 0

    for pcbot_id in pcbots:
        if asignados >= cantidad_deseada:
            break

        # obtener perfiles libres (cruza perfiles_roxy con heartbeat)
        libres = _obtener_perfiles_libres(pcbot_id)
        if not libres:
            logger.debug(
                "[COLA] pcbot %s: no hay perfiles libres", pcbot_id,
            )
            continue

        # asignar tantos perfiles como sea posible de este pcbot
        for perfil_hash in libres:
            if asignados >= cantidad_deseada:
                break

            exito = await _asignar_perfil(
                pedido_id=pedido_id,
                usuario_id=usuario_id,
                pcbot_id=pcbot_id,
                perfil_id=perfil_hash,
                url=url_pedido,
                duracion_seg=duracion_seg,
                nivel_comentarios=nivel_comentarios,
                hora_inicio=hora_inicio,
                hora_fin=hora_fin,
            )
            if exito:
                asignados += 1
                logger.info(
                    "[COLA] pedido %s: perfil %s asignado en pcbot %s (%d/%d)",
                    pedido_id, perfil_hash, pcbot_id, asignados, cantidad_deseada,
                )

    # si se asigno al menos un perfil, marcar pedido como en_progreso
    if asignados > 0:
        ahora_str = _ahora_str()
        ejecutar_sql(
            "update pedidos set estado = 'en_progreso', fecha_inicio = ? where id = ?",
            (ahora_str, pedido_id),
        )
        logger.info(
            "[COLA] pedido %s: %d perfiles asignados, estado -> en_progreso",
            pedido_id, asignados,
        )
    else:
        logger.warning(
            "[COLA] pedido %s: no se pudo asignar ningun perfil, "
            "se reintentara en el proximo ciclo",
            pedido_id,
        )


def _obtener_pcbots_usuario(usuario_id: int) -> list:
    """obtiene lista de pcbot_ids conectados para un usuario.
    fallback: si obtener_pcbots_de_usuario devuelve lista vacia,
    intenta con obtener_pcbot_de_usuario."""
    try:
        pcbots = obtener_pcbots_de_usuario(int(usuario_id))
        if pcbots:
            return pcbots
    except Exception as e:
        logger.debug("[COLA] obtener_pcbots_de_usuario fallo: %s", str(e)[:100])

    # fallback: intentar con la version singular
    try:
        pcbot_unico = obtener_pcbot_de_usuario(int(usuario_id))
        if pcbot_unico:
            return [pcbot_unico]
    except Exception as e:
        logger.debug("[COLA] obtener_pcbot_de_usuario fallo: %s", str(e)[:100])

    # fallback: consultar bd directamente
    try:
        usuarios = ejecutar_sql(
            "select pcbot_id from usuarios where id = ? and pcbot_id is not null",
            (usuario_id,),
        )
        if usuarios:
            return [u["pcbot_id"] for u in usuarios if u.get("pcbot_id")]
    except Exception as e:
        logger.debug("[COLA] consulta bd fallo: %s", str(e)[:100])

    return []


# ---------------------------------------------------------------------------
# perfil libre: cruza perfiles_roxy con heartbeat_cache
# ---------------------------------------------------------------------------
def _obtener_perfiles_libres(pcbot_id: str) -> list:
    """devuelve lista de profile_id que estan libres para asignar.
    cruza el inventario de perfiles_roxy con el heartbeat cache:
    un perfil esta libre si:
    1. existe en perfiles_roxy (tiene hash valido)
    2. no aparece como activo en el ultimo heartbeat del pcbot
    """
    # obtener todos los perfiles del pcbot desde perfiles_roxy
    todos_perfiles = ejecutar_sql(
        "select hash from perfiles_roxy where pcbot_id = ? and activo = 1",
        (pcbot_id,),
    )
    if not todos_perfiles:
        logger.debug("[COLA] pcbot %s: no tiene perfiles en perfiles_roxy", pcbot_id)
        return []

    # obtener perfiles activos segun el ultimo heartbeat
    activos = heartbeat_cache.obtener_perfiles_activos(pcbot_id)
    ids_activos = {p["profile_id"] for p in activos}

    # un perfil esta libre si existe en perfiles_roxy pero NO esta activo
    libres = [
        p["hash"] for p in todos_perfiles
        if p["hash"] not in ids_activos
    ]

    logger.debug(
        "[COLA] pcbot %s: %d perfiles en roxy, %d activos, %d libres",
        pcbot_id, len(todos_perfiles), len(ids_activos), len(libres),
    )
    return libres


# ---------------------------------------------------------------------------
# asignar un perfil: enviar comando + registrar en bd
# ---------------------------------------------------------------------------
async def _asignar_perfil(
    pedido_id: int,
    usuario_id: int,
    pcbot_id: str,
    perfil_id: str,
    url: str,
    duracion_seg: int,
    nivel_comentarios: str,
    hora_inicio: str = None,
    hora_fin: str = None,
) -> bool:
    """asigna un perfil individual a un pedido.
    1. construye comando asignar (1 perfil, url, duracion)
    2. envia al pcbot via ws_manager
    3. si exito, registra en pedido_asignaciones
    retorna true si se asigno correctamente."""
    comando_id = f"pedido_{pedido_id}_{uuid4().hex[:8]}"

    parametros = {
        "cantidad": 1,
        "url": url,
        "duracion": duracion_seg,
        "nivel_comentarios": nivel_comentarios,
        "perfil_id": perfil_id,
    }

    # agregar campos de agendamiento si el pedido los tiene
    if hora_inicio:
        parametros["hora_inicio"] = hora_inicio
    if hora_fin:
        parametros["hora_fin"] = hora_fin

    comando = {
        "tipo": "asignar",
        "comando_id": comando_id,
        "parametros": parametros,
    }

    logger.info(
        "[COLA] enviando comando asignar perfil %s a pcbot %s para pedido %s",
        perfil_id, pcbot_id, pedido_id,
    )

    resultado = await _enviar_comando_seguro(int(usuario_id), comando)
    if not resultado.get("exito"):
        logger.warning(
            "[COLA] fallo envio comando perfil %s a pcbot %s: %s",
            perfil_id, pcbot_id, resultado.get("error", "error desconocido"),
        )
        return False

    # registrar asignacion en pedido_asignaciones
    ahora_str = _ahora_str()
    ejecutar_insercion(
        "insert into pedido_asignaciones "
        "(pedido_id, pcbot_id, perfil_id, url, duracion_seg, inicio, estado, comando_id) "
        "values (?, ?, ?, ?, ?, ?, 'activo', ?)",
        (pedido_id, pcbot_id, perfil_id, url, duracion_seg, ahora_str, comando_id),
    )

    logger.info(
        "[COLA] asignacion registrada: pedido %s - perfil %s - pcbot %s",
        pedido_id, perfil_id, pcbot_id,
    )
    return True


async def _enviar_comando_seguro(usuario_id: int, comando: dict) -> dict:
    """wrapper seguro para enviar_comando_al_pcbot.
    maneja excepciones y devuelve siempre dict con exito/error."""
    try:
        resultado = await enviar_comando_al_pcbot(usuario_id, comando)
        if isinstance(resultado, dict):
            return resultado
        exito = bool(resultado)
        return {"exito": exito, "error": "" if exito else "resultado inesperado"}
    except Exception as e:
        logger.error("[COLA] error enviando comando: %s", str(e)[:200])
        return {"exito": False, "error": str(e)[:200]}