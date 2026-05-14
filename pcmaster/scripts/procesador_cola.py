# procesador_cola.py - procesador fifo de cola de pedidos (v2 centralizado)
# roxymaster v8.3 - utf-8 sin bom, nombres en minusculas
# modulo independiente que procesa pedidos agendados y los asigna
# segun el nuevo modelo de planificacion centralizada en bd.
# parte principal del modulo; funciones auxiliares en procesador_cola_ext.py

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from uuid import uuid4

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
    _obtener_pcbots_usuario,
)

logger = logging.getLogger("procesador_cola")

# ---------------------------------------------------------------------------
# parametros del nuevo modelo centralizado
# ---------------------------------------------------------------------------
TIEMPO_ESPERA_CONFIRMACION = 35   # segundos maximo para que pcbot confirme
INTERVALO_CICLO = 35               # segundos entre ciclos (30s heartbeat + 5s margen)

# estados de pedido_asignaciones en el nuevo modelo:
# planificado: pcmaster decidio que este perfil va a este pedido, aun no se envio
# ejecutando: se envio comando al pcbot y se confirmo (o se asume)
# completado: el perfil termino su tiempo y se libero
# fallido: no se pudo ejecutar


# ---------------------------------------------------------------------------
# punto de entrada: ejecutar un ciclo de match a demanda
# ---------------------------------------------------------------------------
async def ejecutar_ciclo_match():
    """ejecuta un ciclo de match inmediatamente.
    llamada desde orchestrator tras recibir un heartbeat del pcbot.
    no tiene su propio bucle sleep."""
    try:
        await _ciclo_match()
    except Exception as e:
        logger.error("[MATCH] error en ciclo match: %s", str(e)[:400])


# ---------------------------------------------------------------------------
# ciclo principal de match (se ejecuta bajo demanda, no en bucle)
# ---------------------------------------------------------------------------
async def _ciclo_match():
    """ejecuta una ronda de match entre pedidos agendados y perfiles libres.

    logica:
    1. liberar asignaciones que vencieron (completadas por tiempo)
    2. obtener pedidos agendados ordenados fifo
    3. obtener perfiles libres (activo=1 sin asignaciones activas)
    4. para cada pedido, asignar perfiles uno a uno:
       - insertar 'planificado' en pedido_asignaciones
       - enviar comando al pcbot
       - si exito -> 'ejecutando'; si fallo -> 'fallido'
    5. marcar pedidos completados como 'en_progreso'
    """
    ahora = _ahora_dt()
    ahora_str = _ahora_str()

    # paso 0: liberar asignaciones que ya cumplieron su duracion
    await _liberar_asignaciones_vencidas()

    # paso 1: obtener pedidos agendados (y programados que ya llegaron)
    pedidos = _obtener_pedidos_planificables()
    if not pedidos:
        logger.debug("[MATCH] no hay pedidos planificables")
        return

    logger.info("[MATCH] procesando %s pedidos planificables", len(pedidos))

    for pedido in pedidos:
        try:
            await _planificar_pedido(pedido, ahora_str, ahora)
        except Exception as e:
            logger.error("[MATCH] error planificando pedido %s: %s",
                         pedido.get("id"), str(e)[:400])


def _obtener_pedidos_planificables() -> list:
    """obtiene pedidos agendados y programados listos para planificar.

    returns:
        list[dict]: pedidos ordenados por fecha_creacion asc (fifo)
    """
    ahora = _ahora_dt()
    return ejecutar_sql(
        """select id, usuario_id, url, cantidad_perfiles, duracion_horas,
                  nivel_comentarios, tipo_pedido, comando_id, fecha_creacion,
                  estado, hora_inicio_programada, hora_fin_programada
           from pedidos
           where estado = 'agendado'
              or (estado = 'programado'
                  and hora_inicio_programada is not null
                  and hora_inicio_programada <= ?)
           order by fecha_creacion asc""",
        (_ahora_str(),),
    )


async def _planificar_pedido(pedido: dict, ahora_str: str, ahora_dt: datetime):
    """planifica un pedido: busca perfiles libres, crea asignaciones
    y envia comandos al pcbot."""
    pedido_id = pedido["id"]
    usuario_id = pedido.get("usuario_id")
    cantidad_total = pedido.get("cantidad_perfiles", 1)
    url = pedido.get("url", "")
    nivel_comentarios = pedido.get("nivel_comentarios", 0)
    duracion_horas = pedido.get("duracion_horas", 0)

    if not usuario_id:
        logger.warning("[MATCH] pedido %s sin usuario_id", pedido_id)
        ejecutar_sql(
            "update pedidos set estado = 'fallido' where id = ?",
            (pedido_id,),
        )
        return

    # pasar de programado -> agendado si aplica
    if pedido["estado"] == "programado":
        ejecutar_sql(
            "update pedidos set estado = 'agendado' where id = ?",
            (pedido_id,),
        )

    # contar asignaciones en marcha para este pedido
    asignadas = _contar_asignaciones_activas(pedido_id)
    pendientes = cantidad_total - asignadas

    if pendientes <= 0:
        logger.info("[MATCH] pedido %s ya tiene %d/%d asignaciones, pasando a en_progreso",
                    pedido_id, asignadas, cantidad_total)
        ejecutar_sql(
            "update pedidos set estado = 'en_progreso', fecha_inicio = ? where id = ?",
            (ahora_str, pedido_id),
        )
        return

    # obtener pcbots del usuario
    pcbots = _obtener_pcbots_usuario(usuario_id)
    if not pcbots:
        logger.info("[MATCH] usuario %s sin pcbots conectados, pedido %s queda agendado",
                    usuario_id, pedido_id)
        return

    # obtener perfiles libres (conectados al pcbot sin asignaciones activas)
    perfiles_libres = _obtener_perfiles_libres(pcbots, pendientes)
    if not perfiles_libres:
        logger.info("[MATCH] no hay perfiles libres para pedido %s", pedido_id)
        return

    logger.info("[MATCH] pedido %s: %d pendientes, %d perfiles libres disponibles",
                pedido_id, pendientes, len(perfiles_libres))

    # asignar perfiles uno a uno
    for perfil in perfiles_libres[:pendientes]:
        exito = await _asignar_perfil_planificado(
            pedido_id, usuario_id, url, duracion_horas,
            nivel_comentarios, perfil,
        )
        if exito:
            asignadas += 1

    # verificar si el pedido ya se completo
    if asignadas >= cantidad_total:
        ejecutar_sql(
            "update pedidos set estado = 'en_progreso', fecha_inicio = ? where id = ?",
            (ahora_str, pedido_id),
        )
        logger.info("[MATCH] pedido %s: planificacion completa (%d/%d), estado -> en_progreso",
                    pedido_id, asignadas, cantidad_total)
    else:
        logger.info("[MATCH] pedido %s: planificados %d/%d, continuara en siguiente ciclo",
                    pedido_id, asignadas, cantidad_total)


def _contar_asignaciones_activas(pedido_id: int) -> int:
    """cuenta asignaciones activas no vencidas para un pedido."""
    result = ejecutar_sql_unico(
        "select count(*) as total from pedido_asignaciones "
        "where pedido_id = ? and estado in ('planificado', 'ejecutando')",
        (pedido_id,),
    )
    return result["total"] if result else 0


def _obtener_perfiles_libres(pcbots: list, maximo: int) -> list:
    """obtiene perfiles libres de los pcbots especificados.

    EN EL NUEVO MODELO CENTRALIZADO:
    un perfil se considera libre si:
    - activo = 1 (conectado al pcbot)
    - no tiene asignaciones activas en pedido_asignaciones (planificado o ejecutando)
    - o liberacion_estimada <= ahora (perfil que termino y debe liberarse)

    NOTA: en el modelo anterior se usaba activo=0 para perfiles libres.
    ahora activo=1 significa "conectado", activo=0 significa "desconectado/caido".
    la ocupacion se determina por pedido_asignaciones, no por activo.

    returns:
        list[dict]: perfiles disponibles con keys: perfil_id, pcbot_id, hash
    """
    ahora_str = _ahora_str()
    libres = []

    for pcbot_id in pcbots:
        # perfiles conectados (activo=1) sin asignaciones activas
        resultados = ejecutar_sql(
            """select pr.hash as perfil_id, pr.pcbot_id, pr.liberacion_estimada
               from perfiles_roxy pr
               where pr.pcbot_id = ?
                 and pr.activo = 1
                 and not exists (
                     select 1 from pedido_asignaciones pa
                     where pa.perfil_id = pr.hash
                       and pa.estado in ('planificado', 'ejecutando')
                 )
               order by pr.liberacion_estimada asc nulls last""",
            (pcbot_id,),
        )
        for r in (resultados or []):
            libres.append({
                "perfil_id": r["perfil_id"],
                "pcbot_id": pcbot_id,
                "hash": r["perfil_id"],
            })

    # incluir perfiles que estan por liberarse (liberacion_estimada <= ahora + 5s)
    cinco_seg = (_ahora_dt() + timedelta(seconds=5)).strftime("%Y-%m-%d %H:%M:%S")
    for pcbot_id in pcbots:
        resultados = ejecutar_sql(
            """select pr.hash as perfil_id, pr.pcbot_id, pr.liberacion_estimada
               from perfiles_roxy pr
               where pr.pcbot_id = ?
                 and pr.activo = 1
                 and pr.liberacion_estimada is not null
                 and pr.liberacion_estimada <= ?
                 and not exists (
                     select 1 from pedido_asignaciones pa
                     where pa.perfil_id = pr.hash
                       and pa.estado in ('planificado', 'ejecutando')
                 )
               order by pr.liberacion_estimada asc""",
            (pcbot_id, cinco_seg),
        )
        for r in (resultados or []):
            libres.append({
                "perfil_id": r["perfil_id"],
                "pcbot_id": pcbot_id,
                "hash": r["perfil_id"],
            })

    return libres[:maximo]


async def _asignar_perfil_planificado(
    pedido_id: int,
    usuario_id: int,
    url: str,
    duracion_horas: float,
    nivel_comentarios: int,
    perfil: dict,
) -> bool:
    """asigna un perfil especifico a un pedido usando el nuevo flujo planificado.

    paso 1: insertar 'planificado' en pedido_asignaciones.
    paso 2: enviar comando 'asignar' al pcbot.
    paso 3: si exito -> 'ejecutando'; si fallo -> 'fallido'."""
    pcbot_id = perfil["pcbot_id"]
    perfil_id = perfil["perfil_id"]
    comando_id = str(uuid4())
    ahora_str = _ahora_str()

    if not duracion_horas or duracion_horas <= 0:
        duracion_seg = 60
    else:
        duracion_seg = int(duracion_horas * 3600)

    # calcular liberacion_estimada
    liberacion_dt = _ahora_dt() + timedelta(seconds=duracion_seg)
    liberacion_str = liberacion_dt.strftime("%Y-%m-%d %H:%M:%S")

    # paso 1: insertar planificado
    try:
        ejecutar_insercion(
            """insert into pedido_asignaciones
               (pedido_id, perfil_id, pcbot_id, url, duracion_seg, inicio, estado,
                comando_id, liberacion_estimada)
               values (?, ?, ?, ?, ?, ?, 'planificado', ?, ?)""",
            (pedido_id, perfil_id, pcbot_id, url, duracion_seg,
             ahora_str, comando_id, liberacion_str),
        )
    except Exception as e:
        logger.error("[MATCH] error insertando asignacion planificada perfil %s: %s",
                     perfil_id, str(e)[:200])
        return False

    logger.info("[MATCH] perfil %s planificado para pedido %s (pcbot=%s, libre_aprox=%s)",
                perfil_id, pedido_id, pcbot_id, liberacion_str)

    # paso 2: construir y enviar comando
    parametros = {
        "cantidad": 1,
        "url": url,
        "duracion": duracion_seg,
        "nivel_comentarios": nivel_comentarios,
        "perfil_id": perfil_id,
    }

    comando = {
        "tipo": "asignar",
        "comando_id": comando_id,
        "parametros": parametros,
    }

    logger.info("[MATCH] enviando comando asignar perfil %s a pcbot %s para pedido %s",
                perfil_id, pcbot_id, pedido_id)

    resultado = await _enviar_comando_seguro(usuario_id, comando, pcbot_id)

    # paso 3: procesar respuesta
    if resultado.get("exito"):
        ejecutar_sql(
            "update pedido_asignaciones set estado = 'ejecutando' "
            "where comando_id = ? and estado = 'planificado'",
            (comando_id,),
        )
        # actualizar liberacion_estimada en perfiles_roxy
        ejecutar_sql(
            "update perfiles_roxy set activo = 1, liberacion_estimada = ? "
            "where hash = ? and pcbot_id = ?",
            (liberacion_str, perfil_id, pcbot_id),
        )
        logger.info("[MATCH] perfil %s -> ejecutando en pcbot %s para pedido %s",
                    perfil_id, pcbot_id, pedido_id)
        return True
    else:
        error_msg = resultado.get("error", "error desconocido")
        logger.warning("[MATCH] fallo comando perfil %s en pcbot %s: %s",
                       perfil_id, pcbot_id, error_msg)
        ejecutar_sql(
            "update pedido_asignaciones set estado = 'fallido' "
            "where comando_id = ? and estado = 'planificado'",
            (comando_id,),
        )
        return False


async def _liberar_asignaciones_vencidas():
    """libera asignaciones cuya duracion ya vencio.

    busca asignaciones en estado 'ejecutando' cuya liberacion_estimada ya paso,
    las marca como 'completado' y libera el perfil asociado.
    """
    ahora_str = _ahora_str()
    vencidas = ejecutar_sql(
        """select id, perfil_id, pcbot_id, pedido_id
           from pedido_asignaciones
           where estado = 'ejecutando'
             and liberacion_estimada is not null
             and liberacion_estimada <= ?""",
        (ahora_str,),
    )

    if not vencidas:
        return

    for asig in vencidas:
        try:
            # marcar asignacion como completada
            ejecutar_sql(
                "update pedido_asignaciones set estado = 'completado', fin = ? "
                "where id = ? and estado = 'ejecutando'",
                (ahora_str, asig["id"]),
            )
            # liberar perfil: mantener activo=1 (sigue conectado) pero quitar liberacion_estimada
            if asig.get("perfil_id") and asig.get("pcbot_id"):
                ejecutar_sql(
                    "update perfiles_roxy set liberacion_estimada = null "
                    "where hash = ? and pcbot_id = ?",
                    (asig["perfil_id"], asig["pcbot_id"]),
                )
            logger.info("[MATCH] asignacion %s completada (vencio duracion), perfil %s liberado",
                        asig["id"], asig.get("perfil_id"))
        except Exception as e:
            logger.error("[MATCH] error liberando asignacion %s: %s",
                         asig["id"], str(e)[:200])

    # verificar si hay pedidos completados (todas sus asignaciones estan completadas/fallidas)
    pedidos_a_cerrar = ejecutar_sql(
        """select p.id from pedidos p
           where p.estado = 'en_progreso'
             and not exists (
                 select 1 from pedido_asignaciones pa
                 where pa.pedido_id = p.id
                   and pa.estado in ('planificado', 'ejecutando')
             )
             and exists (
                 select 1 from pedido_asignaciones pa
                 where pa.pedido_id = p.id
                   and pa.estado in ('completado', 'fallido')
             )"""
    )
    for pedido in (pedidos_a_cerrar or []):
        try:
            ejecutar_sql(
                "update pedidos set estado = 'completado', fecha_fin = ? where id = ?",
                (ahora_str, pedido["id"]),
            )
            logger.info("[MATCH] pedido %s completado (todas las asignaciones finalizadas)",
                        pedido["id"])
        except Exception as e:
            logger.error("[MATCH] error cerrando pedido %s: %s",
                         pedido["id"], str(e)[:200])

    # eliminar asignaciones huérfanas (planificado sin respuesta por >35s)
    timeout_dt = _ahora_dt() - timedelta(seconds=TIEMPO_ESPERA_CONFIRMACION)
    timeout_str = timeout_dt.strftime("%Y-%m-%d %H:%M:%S")
    colgadas = ejecutar_sql(
        """select id, perfil_id, pcbot_id, pedido_id from pedido_asignaciones
           where estado = 'planificado'
             and inicio is not null
             and inicio <= ?""",
        (timeout_str,),
    )
    for asig in (colgadas or []):
        try:
            ejecutar_sql(
                "update pedido_asignaciones set estado = 'fallido' where id = ?",
                (asig["id"],),
            )
            logger.warning("[MATCH] asignacion planificada %s marcada fallida por timeout (>%ss)",
                          asig["id"], TIEMPO_ESPERA_CONFIRMACION)
        except Exception as e:
            logger.error("[MATCH] error marcando timeout asignacion %s: %s",
                         asig["id"], str(e)[:200])