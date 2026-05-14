# procesador_cola.py - procesador fifo de cola de pedidos
# roxymaster v8.3 - utf-8 sin bom, nombres en minusculas
# modulo independiente que procesa pedidos pendientes y programados
# y los asigna perfil por perfil a los pcbots del usuario
# parte principal del modulo; funciones auxiliares en procesador_cola_ext.py

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import heartbeat_cache
from ws_manager import (
    obtener_pcbots_de_usuario,
    obtener_pcbot_de_usuario,
    enviar_comando_al_pcbot,
)
from db import ejecutar_sql, ejecutar_insercion, ejecutar_sql_unico

# importar funciones auxiliares desde el modulo extendido
from procesador_cola_ext import (
    _ahora_str,
    _ahora_dt,
    _enviar_comando_seguro,
    _liberar_reservas_caducadas,
    _obtener_pcbots_usuario,
)

logger = logging.getLogger("procesador_cola")

# ---------------------------------------------------------------------------
# parametros configurables del ritmo de entrega
# (posteriormente se leeran de bd o dashboard)
# ---------------------------------------------------------------------------
PERFILES_POR_LOTE_NORMAL = 10   # cuantos perfiles asignar por ciclo para pedidos normales
PERFILES_POR_LOTE_VIP = 20      # idem para pedidos vip
INTERVALO_ENTRE_LOTES = 10      # segundos entre ciclos de asignacion (coincide con el ciclo del procesador)
TIMEOUT_RESERVA = 15            # segundos que un perfil puede estar en 'reservado' sin confirmar


# ---------------------------------------------------------------------------
# bucle principal
# ---------------------------------------------------------------------------
async def procesar_cola_pedidos():
    """bucle principal del procesador de cola fifo.
    se ejecuta cada INTERVALO_ENTRE_LOTES segundos y procesa:
    - pedidos en estado 'programado' cuya hora_inicio ya llego -> pendiente
    - pedidos en estado 'pendiente' -> asigna perfiles y pasa a en_progreso
    """
    logger.info(
        "procesador de cola pedidos iniciado (intervalo %ss)",
        INTERVALO_ENTRE_LOTES,
    )
    while True:
        try:
            await _ciclo_procesador()
        except Exception as e:
            logger.error("error en ciclo procesador cola: %s", str(e)[:200])
        await asyncio.sleep(INTERVALO_ENTRE_LOTES)


async def _ciclo_procesador():
    """ejecuta una ronda de procesamiento de la cola fifo."""

    ahora = _ahora_dt()

    # paso 1: liberar reservas caducadas antes de procesar nuevos pedidos
    await _liberar_reservas_caducadas()

    # obtener pedidos pendientes, programados o en_progreso con asignaciones incompletas
    # (incluye pedidos que quedaron colgados tras reconexion o que necesitan mas perfiles)
    # fifo estricto: order by fecha_creacion asc
    pedidos = ejecutar_sql(
        "select id, usuario_id, url, cantidad_perfiles, duracion_horas, "
        "nivel_comentarios, tipo_pedido, comando_id, fecha_creacion, estado, "
        "hora_inicio_programada, hora_fin_programada "
        "from pedidos "
        "where estado in ('pendiente', 'programado') "
        "   or (estado = 'en_progreso' "
        "       and not exists ( "
        "           select 1 from pedido_asignaciones pa "
        "           where pa.pedido_id = pedidos.id "
        "           and pa.estado in ('activo', 'reservado') "
        "       ) "
        "   ) "
        "order by fecha_creacion asc"
    )
    if not pedidos:
        return

    logger.info("[COLA] procesando %s pedidos pendientes/programados/en_progreso", len(pedidos))

    for pedido in pedidos:
        pedido_id = pedido["id"]
        estado_actual = pedido["estado"]

        # log especifico para pedidos en_progreso sin asignaciones activas
        if estado_actual == "en_progreso":
            logger.info(
                "pedido %s en_progreso sin asignaciones activas, reintentando",
                pedido_id,
            )

        try:

            # si es programado, verificar si ya llego su hora de inicio
            if estado_actual == "programado":
                hora_inicio_prog = pedido.get("hora_inicio_programada") or ""
                if hora_inicio_prog:
                    try:
                        # intentar parsear en formato iso o "%Y-%m-%d %H:%M:%S"
                        if "+" in hora_inicio_prog or "Z" in hora_inicio_prog:
                            limpia = hora_inicio_prog.replace("Z", "+00:00")
                            inicio_dt = datetime.fromisoformat(limpia)
                        else:
                            inicio_dt = datetime.strptime(
                                hora_inicio_prog, "%Y-%m-%d %H:%M:%S"
                            )
                            inicio_dt = inicio_dt.replace(tzinfo=timezone.utc)
                    except Exception:
                        # si no se puede parsear, asumir que ya paso
                        inicio_dt = ahora - timedelta(seconds=1)

                    if inicio_dt > ahora:
                        # aun no es hora, saltar este pedido
                        logger.info(
                            "[COLA] pedido %s programado para %s, aun no es hora",
                            pedido_id, hora_inicio_prog,
                        )
                        continue

                # pasar a pendiente
                logger.info(
                    "[COLA] pedido %s programado, hora llegada, pasando a pendiente",
                    pedido_id,
                )
                ejecutar_sql(
                    "update pedidos set estado = 'pendiente' where id = ?",
                    (pedido_id,),
                )
                estado_actual = "pendiente"

            if estado_actual not in ("pendiente", "en_progreso"):
                continue

            await _procesar_pedido_pendiente(pedido)

        except Exception as e:
            logger.error(
                "[COLA] error procesando pedido %s: %s",
                pedido_id, str(e)[:400],
            )


async def _procesar_pedido_pendiente(pedido: dict):
    """asigna perfiles gradualmente a un pedido pendiente.
    implementa entrega por lotes configurables para evitar saturar el pcbot."""
    pedido_id = pedido["id"]
    usuario_id = pedido.get("usuario_id")

    if not usuario_id:
        logger.warning("[COLA] pedido %s sin usuario_id", pedido_id)
        ejecutar_sql(
            "update pedidos set estado = 'fallido' where id = ?",
            (pedido_id,),
        )
        return

    # obtener pcbots del usuario
    pcbots = _obtener_pcbots_usuario(usuario_id)
    if not pcbots:
        logger.warning("[COLA] usuario %s sin pcbots conectados", usuario_id)
        return

    cantidad_total = pedido.get("cantidad_perfiles", 1)
    tipo_pedido = pedido.get("tipo_pedido", "normal")

    # contar asignaciones actuales (activas + reservadas) para este pedido
    asignadas = ejecutar_sql_unico(
        "select count(*) as total from pedido_asignaciones "
        "where pedido_id = ? and estado in ('activo', 'reservado')",
        (pedido_id,),
    )
    asignados_actuales = asignadas["total"] if asignadas else 0
    cantidad_pendiente = cantidad_total - asignados_actuales

    if cantidad_pendiente <= 0:
        # todas las asignaciones ya estan completas -> pasar a en_progreso
        ahora_str = _ahora_str()
        ejecutar_sql(
            "update pedidos set estado = 'en_progreso', fecha_inicio = ? where id = ?",
            (ahora_str, pedido_id),
        )
        logger.info(
            "[COLA] pedido %s: ya asignados %d/%d, estado -> en_progreso",
            pedido_id, asignados_actuales, cantidad_total,
        )
        return

    # calcular lote maximo para este ciclo
    lote_maximo = PERFILES_POR_LOTE_VIP if tipo_pedido == "vip" else PERFILES_POR_LOTE_NORMAL
    logger.info(
        "[COLA] pedido %s: %d/%d asignados, %d pendientes, lote maximo=%d, tipo=%s",
        pedido_id, asignados_actuales, cantidad_total,
        cantidad_pendiente, lote_maximo, tipo_pedido,
    )

    perfiles_a_asignar = min(cantidad_pendiente, lote_maximo)

    for pcbot_id in pcbots:
        if perfiles_a_asignar <= 0:
            break

        # obtener perfiles libres desde heartbeat_cache (excluye los ya asignados y caidos)
        libres = heartbeat_cache.obtener_perfiles_libres(pcbot_id)
        if not libres:
            continue

        # filtrar perfiles que ya estan asignados a este pedido
        asignados_ids = ejecutar_sql(
            "select perfil_id from pedido_asignaciones "
            "where pedido_id = ? and perfil_id is not null",
            (pedido_id,),
        )
        asignados_set = {
            a["perfil_id"] for a in (asignados_ids or []) if a.get("perfil_id")
        }

        elegibles = [p for p in libres if p.get("profile_id") not in asignados_set]

        if not elegibles:
            continue

        cuantos = min(perfiles_a_asignar, len(elegibles))
        logger.info(
            "[COLA] pcbot %s: %d perfiles elegibles, asignando %d de %d",
            pcbot_id, len(elegibles), cuantos, perfiles_a_asignar,
        )

        por_asignar_elegidos = elegibles[:cuantos]

        for perfil in por_asignar_elegidos:
            perfil_id = perfil.get("profile_id", "")
            if not perfil_id:
                continue
            exito = await _asignar_perfil(pedido, pcbot_id, perfil_id)
            if exito:
                perfiles_a_asignar -= 1
                asignados_actuales += 1

    if asignados_actuales >= cantidad_total:
        ahora_str = _ahora_str()
        ejecutar_sql(
            "update pedidos set estado = 'en_progreso', fecha_inicio = ? where id = ?",
            (ahora_str, pedido_id),
        )
        logger.info(
            "[COLA] pedido %s: asignacion completa (%d/%d), estado -> en_progreso",
            pedido_id, asignados_actuales, cantidad_total,
        )
    else:
        logger.info(
            "[COLA] pedido %s: asignados %d/%d, continuara en siguiente ciclo",
            pedido_id, asignados_actuales, cantidad_total,
        )


async def _asignar_perfil(pedido: dict, pcbot_id: str, perfil_id: str) -> bool:
    """asigna un perfil especifico a un pedido usando el nuevo flujo reserva/confirmacion.
    paso 1: insertar 'reservado' con timeout en pedido_asignaciones.
    paso 2: enviar comando al pcbot.
    paso 3: si exito -> 'activo'; si fallo -> 'fallido'."""
    pedido_id = pedido["id"]
    usuario_id = pedido.get("usuario_id")
    url = pedido.get("url", "")
    nivel_comentarios = pedido.get("nivel_comentarios", 0)
    duracion_horas = pedido.get("duracion_horas", 0)

    if not duracion_horas or duracion_horas <= 0:
        duracion_seg = 60
    else:
        duracion_seg = duracion_horas * 3600

    ahora_str = _ahora_str()
    comando_id = str(uuid4())
    hora_inicio = pedido.get("hora_inicio_programada")
    hora_fin = pedido.get("hora_fin_programada")

    # paso 1: calcular timeout y registrar como 'reservado'
    timeout_dt = _ahora_dt() + timedelta(seconds=TIMEOUT_RESERVA)
    timeout_str = timeout_dt.strftime("%Y-%m-%d %H:%M:%S")

    try:
        ejecutar_insercion(
            "insert into pedido_asignaciones "
            "(pedido_id, perfil_id, pcbot_id, url, duracion_seg, inicio, estado, "
            "comando_id, timeout) "
            "values (?, ?, ?, ?, ?, ?, 'reservado', ?, ?)",
            (pedido_id, perfil_id, pcbot_id, url, duracion_seg, ahora_str,
             comando_id, timeout_str),
        )
    except Exception as e:
        logger.error(
            "[COLA] error insertando asignacion reservada para perfil %s: %s",
            perfil_id, str(e)[:200],
        )
        return False

    # contar asignaciones actuales para log
    asignadas = ejecutar_sql_unico(
        "select count(*) as total from pedido_asignaciones "
        "where pedido_id = ? and estado in ('activo', 'reservado')",
        (pedido_id,),
    )
    asignados_actuales = asignadas["total"] if asignadas else 0
    cantidad_total = pedido.get("cantidad_perfiles", 1)

    logger.info(
        "[COLA] perfil %s reservado para pedido %s (pcbot=%s, timeout=%s, %d/%d)",
        perfil_id, pedido_id, pcbot_id, timeout_str,
        asignados_actuales, cantidad_total,
    )

    # paso 2: construir y enviar comando
    parametros = {
        "cantidad": 1,
        "url": url,
        "duracion": duracion_seg,
        "nivel_comentarios": nivel_comentarios,
        "perfil_id": perfil_id,
    }

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

    resultado = await _enviar_comando_seguro(int(usuario_id), comando, pcbot_id)

    # paso 3: procesar respuesta del pcbot
    if resultado.get("exito"):
        # el pcbot recibio y acepto el comando
        try:
            ejecutar_sql(
                "update pedido_asignaciones set estado = 'activo', timeout = null "
                "where comando_id = ? and estado = 'reservado'",
                (comando_id,),
            )
        except Exception as e:
            logger.error(
                "[COLA] error confirmando asignacion %s: %s",
                comando_id, str(e)[:200],
            )
            return False

        logger.info(
            "[COLA] perfil %s confirmado por pcbot %s para pedido %s (%d/%d)",
            perfil_id, pcbot_id, pedido_id,
            asignados_actuales, cantidad_total,
        )

        # si con esta asignacion se completa la cantidad deseada, pasar a en_progreso
        if asignados_actuales >= cantidad_total:
            ejecutar_sql(
                "update pedidos set estado = 'en_progreso', fecha_inicio = ? where id = ?",
                (ahora_str, pedido_id),
            )
            logger.info(
                "[COLA] pedido %s: asignacion completa (%d/%d), estado -> en_progreso",
                pedido_id, asignados_actuales, cantidad_total,
            )

        return True
    else:
        # el pcbot rechazo el comando o hubo error de comunicacion
        error_msg = resultado.get("error", "error desconocido")
        logger.warning(
            "[COLA] fallo comando perfil %s en pcbot %s para pedido %s: %s",
            perfil_id, pcbot_id, pedido_id, error_msg,
        )
        try:
            ejecutar_sql(
                "update pedido_asignaciones set estado = 'fallido' "
                "where comando_id = ? and estado = 'reservado'",
                (comando_id,),
            )
            logger.info(
                "[COLA] asignacion %s del perfil %s marcada como fallida",
                comando_id, perfil_id,
            )
        except Exception as e:
            logger.error(
                "[COLA] error marcando asignacion como fallida: %s",
                str(e)[:200],
            )
        return False