# procesador_cola.py - procesador fifo de cola de pedidos (v2 centralizado)
# roxymaster v8.3 - utf-8 sin bom, nombres en minusculas
# modulo independiente que procesa pedidos agendados y los asigna
# segun el nuevo modelo de planificacion centralizada en bd.
# parte principal del modulo; funciones auxiliares en procesador_cola_ext.py
# modulo dividido: principal aqui, auxiliares y logica extendida en _ext

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
    _contar_asignaciones_activas,
    _contar_observadores_por_pcbot,
    _obtener_contexto_streamer,
    _obtener_pedidos_planificables,
    _obtener_perfiles_libres,
    _limpiar_asignaciones_huerfanas,
    _tiene_observador_activo,
    _buscar_perfil_relevo_observador,
    _enviar_cambio_rol_observador,
    _iniciar_distribucion_comentarios,
)

logger = logging.getLogger("procesador_cola")

# ---------------------------------------------------------------------------
# parametros del nuevo modelo centralizado
# ---------------------------------------------------------------------------
TIEMPO_ESPERA_CONFIRMACION = 35   # segundos maximo para que pcbot confirme
INTERVALO_CICLO = 35               # segundos entre ciclos (30s heartbeat + 5s margen)
MARGEN_PRIORIDAD = 5               # segundos de prioridad post-heartbeat para reasignar bajas

# flag de reentrada para evitar ciclos de match simultaneos
_match_en_progreso = False

# diccionario de prioridad de recuperacion: {pedido_id: timestamp_deteccion}
_prioridad_recuperacion: dict = {}

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
    no tiene su propio bucle sleep.
    protegido contra reentrada via flag _match_en_progreso."""
    global _match_en_progreso
    logger.info("[DIAG-MATCH] ejecutar_ciclo_match iniciado, _prioridad_recuperacion=%s", _prioridad_recuperacion)
    if _match_en_progreso:
        logger.warning("[MATCH] ciclo de match ya en ejecucion, se omite esta llamada (reentrada)")
        return
    _match_en_progreso = True
    try:
        await _ciclo_match()
    except Exception as e:
        logger.error("[MATCH] error en ciclo match: %s", str(e)[:400])
    finally:
        _match_en_progreso = False


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

    # paso 0: limpiar asignaciones huerfanas (perfiles con multiples asignaciones activas
    # o asignaciones activas para pedidos ya completados/cancelados)
    await _limpiar_asignaciones_huerfanas()

    # paso 0.1: liberar asignaciones que ya cumplieron su duracion
    await _liberar_asignaciones_vencidas()

    # paso 0.2: limpiar prioridades de recuperacion caducadas
    ahora_local = _ahora_dt()
    for pid, ts in list(_prioridad_recuperacion.items()):
        if (ahora_local - ts).total_seconds() >= MARGEN_PRIORIDAD:
            del _prioridad_recuperacion[pid]
    # paso 1: obtener pedidos urgentes (con prioridad post-heartbeat) + normales
    urgentes, normales = _obtener_pedidos_planificables()
    pedidos = urgentes + normales
    if not pedidos:
        logger.debug("[MATCH] no hay pedidos planificables")
        return

    logger.info("[MATCH] procesando %s pedidos (%s urgentes, %s normales)",
                len(pedidos), len(urgentes), len(normales))

    # agrupar pedidos por usuario para obtener perfiles libres una sola vez por grupo
    pedidos_por_usuario = {}
    for p in pedidos:
        uid = p.get("usuario_id")
        if uid is None:
            continue
        pedidos_por_usuario.setdefault(uid, []).append(p)

    for uid, pedidos_user in pedidos_por_usuario.items():
        # obtener pcbots y perfiles libres una sola vez para este usuario
        pcbots = _obtener_pcbots_usuario(uid)
        if not pcbots:
            logger.info("[MATCH] usuario %s sin pcbots, saltando %d pedidos",
                        uid, len(pedidos_user))
            continue

        perfiles_pool = _obtener_perfiles_libres(pcbots, 9999)
        if not perfiles_pool:
            logger.info("[MATCH] usuario %s sin perfiles libres, saltando %d pedidos",
                        uid, len(pedidos_user))
            continue

        logger.info("[MATCH] usuario %s: %d perfiles en pool, %d pedidos pendientes",
                    uid, len(perfiles_pool), len(pedidos_user))

        for pedido in pedidos_user:
            try:
                await _planificar_pedido(pedido, ahora_str, ahora, perfiles_pool)
            except Exception as e:
                logger.error("[MATCH] error planificando pedido %s: %s",
                             pedido.get("id"), str(e)[:400])
            # si el pool se agoto, ya no tiene sentido seguir con mas pedidos de este usuario
            if not perfiles_pool:
                logger.info("[MATCH] pool de perfiles agotado para usuario %s", uid)
                break


async def _planificar_pedido(pedido: dict, ahora_str: str, ahora_dt: datetime,
                              perfiles_pool: list):
    """planifica un pedido usando UNICAMENTE el pool compartido por usuario.
    perfiles_pool es obligatorio. no existe modo legacy.
    si esta vacio, retorna sin hacer nada (el pedido queda para el siguiente ciclo).
    los perfiles se eliminan del pool ANTES de insertar la asignacion,
    y si la insercion falla no se reinsertan (se pierden para este ciclo)."""
    pedido_id = pedido["id"]
    usuario_id = pedido.get("usuario_id")
    try:
        cantidad_total = int(pedido.get("cantidad_perfiles", 1))
    except (ValueError, TypeError):
        cantidad_total = 1
    url = pedido.get("url", "")
    try:
        nivel_comentarios = int(pedido.get("nivel_comentarios", 0))
    except (ValueError, TypeError):
        nivel_comentarios = 0
    try:
        duracion_horas = float(pedido.get("duracion_horas", 0))
    except (ValueError, TypeError):
        duracion_horas = 0.0

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

    # modo pool OBLIGATORIO: consumir perfiles del pool compartido
    if not perfiles_pool:
        logger.info("[MATCH] pool compartido vacio para pedido %s, se omite (siguiente ciclo)", pedido_id)
        return

    disponibles = []
    while len(disponibles) < pendientes and perfiles_pool:
        disponibles.append(perfiles_pool.pop(0))
    if not disponibles:
        logger.info("[MATCH] pedido %s: pool compartido agotado", pedido_id)
        return
    perfiles_a_usar = disponibles
    logger.info("[MATCH] pedido %s: %d pendientes, %d perfiles del pool",
                pedido_id, pendientes, len(perfiles_a_usar))

    # asignar perfiles uno a uno
    for perfil in perfiles_a_usar:
        exito = await _asignar_perfil_planificado(
            pedido_id, usuario_id, url, duracion_horas,
            nivel_comentarios, perfil,
        )
        if exito:
            _prioridad_recuperacion.pop(pedido_id, None)
            asignadas += 1
            # tarea 4: distribucion de comentarios
            # programar tarea asincrona que distribuya comentarios
            # desde el pool de frases de la url del pedido
            asyncio.create_task(
                _iniciar_distribucion_comentarios(
                    pedido_id, usuario_id,
                    perfil["pcbot_id"], perfil["perfil_id"],
                    url,
                )
            )
        else:
            logger.warning("[MATCH] fallo asignacion perfil %s a pedido %s",
                           perfil.get("perfil_id"), pedido_id)

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


async def _asignar_perfil_planificado(
    pedido_id: int,
    usuario_id: int,
    url: str,
    duracion_horas: float,
    nivel_comentarios: int,
    perfil: dict,
) -> bool:
    """asigna un perfil especifico a un pedido usando el nuevo flujo planificado.

    paso 0: verificacion atomica de unicidad (evita doble asignacion del mismo perfil).
    paso 1: insertar 'planificado' en pedido_asignaciones.
    paso 2: enviar comando 'asignar' al pcbot.
    paso 3: si exito -> 'ejecutando'; si fallo -> 'fallido'.

    designacion de observador (tarea 1):
    despues de construir el comando 'asignar', verifica si el pcbot destino
    ya tiene un observador activo. si no tiene, añade "rol":"observador"
    a los parametros y registra el log correspondiente."""
    pcbot_id = perfil["pcbot_id"]
    perfil_id = perfil["perfil_id"]
    comando_id = str(uuid4())
    ahora_str = _ahora_str()
    rol = None  # por defecto, rol normal

    if not duracion_horas or duracion_horas <= 0:
        duracion_seg = 60
    else:
        duracion_seg = int(duracion_horas * 3600)

    # calcular liberacion_estimada
    liberacion_dt = _ahora_dt() + timedelta(seconds=duracion_seg)
    liberacion_str = liberacion_dt.strftime("%Y-%m-%d %H:%M:%S")

    # tarea 1: designacion de observador
    # solo si el pedido contrato comentarista ia (nivel_comentarios > 0)
    # y el pcbot no tiene ya un observador activo
    if nivel_comentarios > 0 and not _tiene_observador_activo(pcbot_id):
        rol = "observador"
        logger.info(
            "[MATCH] perfil %s designado observador en pcbot %s (pedido %s)",
            perfil_id, pcbot_id, pedido_id,
        )

    # paso 0: verificacion atomica de unicidad
    logger.info("[MATCH] verificando duplicidad: perfil=%s para pedido=%s", perfil_id, pedido_id)
    try:
        duplicado = ejecutar_sql_unico(
            """select count(*) as cnt from pedido_asignaciones
               where perfil_id = ? and estado in ('planificado', 'ejecutando')""",
            (perfil_id,),
        )
        if duplicado and duplicado["cnt"] > 0:
            logger.warning(
                "[MATCH] intento de asignacion duplicada para perfil %s en pedido %s, se omite",
                perfil_id, pedido_id,
            )
            return False
    except Exception as e:
        logger.error("[MATCH] error en verificacion de duplicidad perfil %s: %s",
                     perfil_id, str(e)[:200])
        return False

    # paso 1: insertar planificado
    try:
        ejecutar_insercion(
            """insert into pedido_asignaciones
               (pedido_id, perfil_id, pcbot_id, url, duracion_seg, inicio, estado,
                comando_id, liberacion_estimada, rol)
               values (?, ?, ?, ?, ?, ?, 'planificado', ?, ?, ?)""",
            (pedido_id, perfil_id, pcbot_id, url, duracion_seg,
             ahora_str, comando_id, liberacion_str, rol),
        )
    except Exception as e:
        logger.error("[MATCH] error insertando asignacion planificada perfil %s: %s",
                     perfil_id, str(e)[:200])
        return False

    logger.info("[MATCH] perfil %s planificado para pedido %s (pcbot=%s, libre_aprox=%s, rol=%s)",
                perfil_id, pedido_id, pcbot_id, liberacion_str, rol or "normal")

    # paso 2: construir y enviar comando
    parametros = {
        "cantidad": 1,
        "url": url,
        "duracion": duracion_seg,
        "nivel_comentarios": nivel_comentarios,
        "perfil_id": perfil_id,
    }
    if rol == "observador":
        parametros["rol"] = "observador"
        parametros["observador_extra"] = 1

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
        logger.info("[MATCH] perfil %s -> ejecutando en pcbot %s para pedido %s (rol=%s)",
                    perfil_id, pcbot_id, pedido_id, rol or "normal")
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

    tarea 2: rotacion de observador
    cuando una asignacion con rol='observador' se completa,
    busca otro perfil activo en el mismo pcbot para transferirle el rol."""
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
            perfil_id = asig.get("perfil_id")
            pcbot_id = asig.get("pcbot_id")
            if perfil_id and pcbot_id:
                ejecutar_sql(
                    "update perfiles_roxy set liberacion_estimada = null "
                    "where hash = ? and pcbot_id = ?",
                    (perfil_id, pcbot_id),
                )
            logger.info("[MATCH] asignacion %s completada (vencio duracion), perfil %s liberado",
                        asig["id"], perfil_id)

            # tarea 2: rotacion de observador
            # si esta asignacion tenia rol='observador', transferir a otro perfil
            if asig.get("perfil_id") and asig.get("pcbot_id"):
                _rotar_observador_al_completar(asig)

        except Exception as e:
            logger.error("[MATCH] error liberando asignacion %s: %s",
                         asig["id"], str(e)[:200])


def _rotar_observador_al_completar(asig: dict):
    """tarea 2: cuando una asignacion con rol observador se completa,
    busca otro perfil activo en el mismo pcbot y le transfiere el rol."""
    pcbot_id = asig.get("pcbot_id")
    asig_id = asig["id"]
    perfil_saliente = asig.get("perfil_id")

    # verificar si la asignacion saliente tenia rol='observador'
    check_rol = ejecutar_sql_unico(
        "select rol from pedido_asignaciones where id = ?",
        (asig_id,),
    )
    if not check_rol or check_rol.get("rol") != "observador":
        return

    # buscar otro perfil activo en el mismo pcbot
    perfil_entrante = _buscar_perfil_relevo_observador(pcbot_id, asig_id)
    if not perfil_entrante:
        logger.info(
            "[MATCH] no hay perfil de relevo para observador en pcbot %s "
            "(asignacion %s completada)", pcbot_id, asig_id,
        )
        return

    # enviar comando cambiar_rol al pcbot (se necesita usuario_id)
    # obtenemos usuario_id de la asignacion o del pedido
    pedido_info = ejecutar_sql_unico(
        "select p.usuario_id from pedido_asignaciones pa "
        "join pedidos p on p.id = pa.pedido_id "
        "where pa.id = ?",
        (asig_id,),
    )
    usuario_id = pedido_info.get("usuario_id") if pedido_info else None
    if not usuario_id:
        logger.warning("[MATCH] no se pudo obtener usuario_id para rotar observador en asig %s",
                       asig_id)
        return

    # enviar el cambio de rol (tarea asincrona lanzada como fire-and-forget para no bloquear)
    asyncio.create_task(
        _ejecutar_rotacion_observador(
            usuario_id, pcbot_id, perfil_saliente, perfil_entrante, asig_id,
        )
    )


def registrar_baja(pedido_id: int):
    """llamado por el vigilante cuando detecta un perfil caido o desviado.
    registra el timestamp para dar prioridad en el proximo ciclo."""
    _prioridad_recuperacion[pedido_id] = datetime.now(timezone.utc)
    logger.info("[RECUPERACION] baja registrada para pedido %s con prioridad %ds",
                pedido_id, MARGEN_PRIORIDAD)


async def _ejecutar_rotacion_observador(usuario_id: int, pcbot_id: str,
                                         perfil_saliente: str,
                                         perfil_entrante: str, asig_id: int):
    """ejecuta el envio del comando cambiar_rol de forma asincrona."""
    exito = await _enviar_cambio_rol_observador(usuario_id, pcbot_id, perfil_entrante)
    if exito:
        logger.info(
            "[MATCH] rol observador transferido de %s a %s en pcbot %s",
            perfil_saliente, perfil_entrante, pcbot_id,
        )
    else:
        logger.warning(
            "[MATCH] fallo transferencia de rol observador de %s a %s en pcbot %s",
            perfil_saliente, perfil_entrante, pcbot_id,
        )
