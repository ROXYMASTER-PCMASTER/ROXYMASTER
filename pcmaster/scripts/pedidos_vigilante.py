# pedidos_vigilante.py - monitoreo de pedidos, reemplazo de perfiles caidos,
# y transicion de estados pendiente->enviado->trabajando
# modulo para vigilante de pedidos, se ejecuta como tarea asincrona
# dependencias: heartbeat_cache, db, orchestrator

import asyncio
import json
import logging
from datetime import datetime, timezone

import heartbeat_cache
from ws_manager import enviar_comando_al_pcbot, obtener_pcbot_de_usuario
from db import ejecutar_sql, ejecutar_insercion, ejecutar_sql_unico

logger = logging.getLogger("vigilante_pedidos")


def _ahora_str() -> str:
    """devuelve timestamp utc en formato iso."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _ahora_dt() -> datetime:
    """devuelve datetime utc actual."""
    return datetime.now(timezone.utc)


async def monitorear_pedidos():
    """bucle principal del vigilante.
    se ejecuta cada 30 segundos y verifica:
    - pedidos expirados -> finalizar
    - perfiles caidos -> reemplazar
    - perfiles con url incorrecta -> reemplazar
    - pedidos pendientes/enviados -> procesar transicion
    """
    logger.info("vigilante de pedidos iniciado")
    while True:
        try:
            await _ciclo_vigilante()
        except Exception as e:
            logger.error("error en ciclo vigilante: %s", str(e)[:200])
        await asyncio.sleep(30)


async def _ciclo_vigilante():
    """ejecuta una ronda de verificacion sobre todos los pedidos activos."""

    # --- PASO 1: procesar pedidos pendientes y enviados ---
    await _procesar_pendientes_y_enviados()

    # --- PASO 2: verificar pedidos en progreso (trabajando, en_progreso) ---
    pedidos = ejecutar_sql(
        "select id, usuario_id, url, cantidad_perfiles, duracion_horas, "
        "nivel_comentarios, fecha_creacion, estado "
        "from pedidos where estado in ('trabajando', 'en_progreso')"
    )
    if not pedidos:
        return

    ahora = _ahora_dt()

    for pedido in pedidos:
        try:
            await _verificar_pedido(pedido, ahora)
        except Exception as e:
            logger.error(
                "error verificando pedido %s: %s",
                pedido.get("id"), str(e)[:200],
            )


# ---------------------------------------------------------------------------
# cambio 2 y 3: procesar pedidos en estados pendiente / enviado
# ---------------------------------------------------------------------------
async def _procesar_pendientes_y_enviados():
    """busca pedidos en 'pendiente' o 'enviado' y los transiciona.

    - 'pendiente': intenta enviar comando via orchestrator si no hay comando en db
    - 'enviado': verifica si el comando ya fue confirmado por el pcbot
                 (comandos.estado = 'enviado' o heartbeat_cache tiene perfiles activos)
    """
    pedidos_a_procesar = ejecutar_sql(
        "select id, usuario_id, url, cantidad_perfiles, duracion_horas, "
        "nivel_comentarios, tipo_pedido, comando_id, fecha_creacion, estado "
        "from pedidos where estado in ('pendiente', 'enviado') "
        "order by fecha_creacion asc"
    )
    if not pedidos_a_procesar:
        return

    logger.info("[VIGILANTE] procesando %s pedidos pendientes/enviados", len(pedidos_a_procesar))

    for pedido in pedidos_a_procesar:
        pedido_id = pedido["id"]
        uid = pedido["usuario_id"]
        comando_id = pedido["comando_id"]
        estado_actual = pedido["estado"]

        try:
            if estado_actual == "pendiente":
                await _procesar_pendiente(pedido)
            elif estado_actual == "enviado":
                await _procesar_enviado(pedido)
        except Exception as e:
            logger.error("[VIGILANTE] error procesando pedido %s estado=%s: %s",
                         pedido_id, estado_actual, str(e)[:200])


async def _procesar_pendiente(pedido: dict):
    """intenta enviar el comando de un pedido pendiente via orchestrator.
    si el comando ya existe en la tabla comandos, solo actualiza estado.
    si no existe, crea el comando."""
    pedido_id = pedido["id"]
    uid = pedido["usuario_id"]
    comando_id = pedido["comando_id"]

    # verificar si el comando ya existe
    cmd_existente = ejecutar_sql_unico(
        "select estado from comandos where comando_id = ?",
        (comando_id,),
    )

    if cmd_existente and cmd_existente["estado"] in ("enviado", "pendiente"):
        # comando ya existe, actualizar pedido a enviado
        ejecutar_sql("update pedidos set estado = 'enviado' where id = ?", (pedido_id,))
        logger.info("[VIGILANTE] pedido %s: comando %s ya existe con estado '%s', transicionando a enviado",
                    pedido_id, comando_id, cmd_existente["estado"])
        return

    if cmd_existente and cmd_existente["estado"] in ("completado", "fallido"):
        logger.info("[VIGILANTE] pedido %s: comando %s ya esta %s, marcando pedido como completado",
                    pedido_id, comando_id, cmd_existente["estado"])
        ejecutar_sql("update pedidos set estado = 'completado' where id = ?", (pedido_id,))
        return

    # no existe comando -> intentar crear via orchestrator
    parametros = {
        "url": pedido["url"],
        "cantidad": pedido["cantidad_perfiles"],
        "duracion": int(pedido["duracion_horas"] * 60),
        "nivel_comentarios": pedido.get("nivel_comentarios", "basico"),
    }

    # buscar pcbot_id del usuario
    usuario = ejecutar_sql_unico(
        "select pcbot_id from usuarios where id = ?",
        (uid,),
    )
    if not usuario or not usuario["pcbot_id"]:
        logger.warning("[VIGILANTE] pedido %s: usuario %s no tiene pcbot_id, no se puede enviar comando",
                       pedido_id, uid)
        return

    try:
        from orchestrator import crear_comando as orc_crear_comando
        orc_result = await orc_crear_comando(
            tipo="asignar",
            parametros=parametros,
            pcbot_id=usuario["pcbot_id"],
            comando_id=comando_id,
        )

        if orc_result.get("exito"):
            nuevo_estado = orc_result.get("estado", "pendiente")
            ejecutar_sql("update pedidos set estado = 'enviado' where id = ?", (pedido_id,))
            logger.info("[VIGILANTE] pedido %s: comando creado y %s via orchestrator",
                        pedido_id, nuevo_estado)
        else:
            logger.warning("[VIGILANTE] pedido %s: orchestrator fallo al crear comando: %s",
                           pedido_id, orc_result.get("error"))
    except Exception as e:
        logger.error("[VIGILANTE] pedido %s: excepcion en orchestrator: %s",
                     pedido_id, str(e)[:200])


async def _procesar_enviado(pedido: dict):
    """verifica si un pedido en estado 'enviado' ya fue confirmado por el pcbot.
    confirmacion = el comando esta en estado 'enviado' y el pcbot tiene perfiles activos
    (segun heartbeat_cache) que coinciden con la url del pedido."""
    pedido_id = pedido["id"]
    uid = pedido["usuario_id"]
    comando_id = pedido["comando_id"]
    url_pedido = pedido["url"]

    # buscar pcbot_id del usuario
    usuario = ejecutar_sql_unico(
        "select pcbot_id from usuarios where id = ?",
        (uid,),
    )
    if not usuario or not usuario["pcbot_id"]:
        logger.warning("[VIGILANTE] pedido %s enviado: usuario %s no tiene pcbot_id",
                       pedido_id, uid)
        return

    pcbot_id = usuario["pcbot_id"]

    # verificar si el comando fue marcado como enviado en la tabla comandos
    cmd = ejecutar_sql_unico(
        "select estado from comandos where comando_id = ?",
        (comando_id,),
    )
    if cmd and cmd["estado"] == "enviado":
        # comando fue enviado al pcbot -> verificar si el pcbot ya esta ejecutando
        perfiles_activos = heartbeat_cache.obtener_perfiles_activos(pcbot_id)
        if perfiles_activos:
            # ver si algun perfil activo tiene la url del pedido
            perfiles_coincidentes = [
                p for p in perfiles_activos
                if p.get("url") == url_pedido
            ]
            if perfiles_coincidentes:
                # el pcbot ya esta trabajando en este pedido -> transicionar
                ejecutar_sql("update pedidos set estado = 'trabajando' where id = ?", (pedido_id,))
                logger.info("[VIGILANTE] pedido %s: transicionando enviado -> trabajando "
                            "(%s perfiles activos coinciden con url)",
                            pedido_id, len(perfiles_coincidentes))
                return

        # si no hay perfiles activos coincidentes, esperar
        logger.debug("[VIGILANTE] pedido %s: comando enviado pero pcbot %s no muestra perfiles activos aun",
                     pedido_id, pcbot_id)
    elif cmd and cmd["estado"] == "pendiente":
        logger.debug("[VIGILANTE] pedido %s: comando %s aun pendiente en cola de orchestrator",
                     pedido_id, comando_id)
    else:
        # comando no encontrado -> reintentar
        logger.warning("[VIGILANTE] pedido %s: comando %s no encontrado en db, "
                       "reintentando envio",
                       pedido_id, comando_id)
        ejecutar_sql("update pedidos set estado = 'pendiente' where id = ?", (pedido_id,))


async def _verificar_pedido(pedido: dict, ahora: datetime):
    """verifica estado de un pedido y actua si es necesario.
    usa heartbeat_cache para obtener los perfiles activos reales
    y comparar urls."""
    pedido_id = pedido["id"]

    # calcular tiempo restante usando fecha_creacion + duracion_horas
    fecha_creacion_str = pedido.get("fecha_creacion")
    if not fecha_creacion_str:
        return

    fecha_inicio = datetime.strptime(fecha_creacion_str, "%Y-%m-%d %H:%M:%S")
    fecha_inicio = fecha_inicio.replace(tzinfo=timezone.utc)
    transcurrido = (ahora - fecha_inicio).total_seconds()
    duracion_horas = pedido.get("duracion_horas", 0)
    duracion_seg = duracion_horas * 3600
    tiempo_restante = duracion_seg - transcurrido

    # caso 1: pedido expirado
    if tiempo_restante <= 0:
        logger.info("pedido %s expirado, finalizando", pedido_id)
        await _finalizar_pedido(pedido)
        return

    # caso 2: verificar perfiles activos contra el heartbeat cache
    asignaciones = ejecutar_sql(
        "select id, perfil_id, pcbot_id, url from pedido_asignaciones "
        "where pedido_id = ? and estado = 'activo'",
        (pedido_id,),
    )
    if not asignaciones:
        # sin asignaciones activas -> reasignar todas
        logger.info("pedido %s sin asignaciones activas, reasignando", pedido_id)
        cantidad_pedido = pedido.get("cantidad_perfiles", 1)
        for _ in range(cantidad_pedido):
            await _asignar_perfil(pedido, tiempo_restante)
        return

    # contar perfiles caidos o con url incorrecta
    perfiles_fallidos = 0
    usuario_id = pedido.get("usuario_id")
    url_pedido = pedido.get("url", "")

    for asig in asignaciones:
        pcbot_id = asig.get("pcbot_id")
        perfil_id = asig.get("perfil_id")

        if not pcbot_id:
            # si no tiene pcbot_id, obtenerlo del usuario
            try:
                pcbot_id = obtener_pcbot_de_usuario(int(usuario_id))
            except Exception:
                logger.warning(
                    "no se pudo obtener pcbot para usuario %s en asig %s",
                    usuario_id, asig.get("id"),
                )
                continue

        # obtener perfiles activos desde el heartbeat cache (datos reales del pcbot)
        activos_cache = heartbeat_cache.obtener_perfiles_activos(pcbot_id)
        perfil_en_cache = None
        for p in activos_cache:
            if p.get("profile_id") == perfil_id:
                perfil_en_cache = p
                break

        if not perfil_en_cache:
            # perfil no aparece como activo en el ultimo heartbeat
            logger.info(
                "perfil %s caido en pcbot %s para pedido %s (no aparece en heartbeat)",
                perfil_id, pcbot_id, pedido_id,
            )
            # marcar asignacion como fallida
            ejecutar_sql(
                "update pedido_asignaciones set estado = 'fallido' where id = ?",
                (asig["id"],),
            )
            perfiles_fallidos += 1
            continue

        # verificar que la url del perfil coincida con la url del pedido
        url_actual = perfil_en_cache.get("url", "")
        if url_pedido and url_actual and url_actual != url_pedido:
            logger.info(
                "perfil %s en pcbot %s navegando a url incorrecta (%s vs %s esperada) para pedido %s",
                perfil_id, pcbot_id, url_actual, url_pedido, pedido_id,
            )
            # marcar asignacion como fallida por url incorrecta
            ejecutar_sql(
                "update pedido_asignaciones set estado = 'fallido' where id = ?",
                (asig["id"],),
            )
            perfiles_fallidos += 1
            # enviar comando detener para liberar ese perfil
            comando_detener = {
                "tipo": "detener",
                "parametros": {"perfil_id": perfil_id},
            }
            try:
                await _enviar_comando_seguro(int(usuario_id), comando_detener)
            except Exception as e:
                logger.error(
                    "error enviando detener perfil %s con url incorrecta: %s",
                    perfil_id, str(e)[:200],
                )

    # reemplazar perfiles caidos si hay
    if perfiles_fallidos > 0:
        logger.info(
            "reemplazando %s perfiles caidos en pedido %s",
            perfiles_fallidos, pedido_id,
        )
        for _ in range(perfiles_fallidos):
            await _asignar_perfil(pedido, tiempo_restante)


async def _enviar_comando_seguro(usuario_id: int, comando: dict) -> dict:
    """wrapper seguro para enviar_comando_al_pcbot que maneja
    excepciones y devuelve siempre un dict con exito/error."""
    try:
        resultado = await enviar_comando_al_pcbot(usuario_id, comando)
        if isinstance(resultado, dict):
            return resultado
        # si devolvio bool o None, convertir a dict
        exito = bool(resultado)
        return {"exito": exito, "error": "" if exito else "resultado inesperado"}
    except Exception as e:
        logger.error("error en enviar_comando_al_pcbot: %s", str(e)[:200])
        return {"exito": False, "error": str(e)[:200]}


async def _asignar_perfil(pedido: dict, duracion: float) -> bool:
    """asigna un perfil libre al pedido.
    busca perfiles libres en heartbeat_cache para el pcbot del usuario,
    envia comando asignar y registra en pedido_asignaciones."""
    usuario_id = pedido.get("usuario_id")
    if not usuario_id:
        logger.warning("pedido %s sin usuario_id", pedido.get("id"))
        return False

    try:
        pcbot_id = obtener_pcbot_de_usuario(int(usuario_id))
    except Exception as e:
        logger.warning(
            "no se pudo obtener pcbot para usuario %s: %s",
            usuario_id, str(e)[:100],
        )
        return False

    if not pcbot_id:
        logger.warning("usuario %s no tiene pcbot conectado", usuario_id)
        return False

    # buscar perfil libre desde heartbeat_cache
    # perfil libre = existe en el heartbeat del pcbot pero NO esta activo
    libres_cache = heartbeat_cache.obtener_perfiles_libres(pcbot_id)
    if not libres_cache:
        logger.warning("no hay perfiles libres en pcbot %s segun heartbeat", pcbot_id)
        return False

    perfil_elegido = libres_cache[0].get("profile_id", "")
    if not perfil_elegido:
        logger.warning("perfil libre sin profile_id en pcbot %s", pcbot_id)
        return False

    url = pedido.get("url", "")
    nivel_comentarios = pedido.get("nivel_comentarios", 0)
    duracion_int = max(1, int(duracion))

    comando = {
        "tipo": "asignar",
        "parametros": {
            "cantidad": 1,
            "url": url,
            "duracion": duracion_int,
            "nivel_comentarios": nivel_comentarios,
            "perfil_id": perfil_elegido,
        },
    }

    resultado = await _enviar_comando_seguro(int(usuario_id), comando)
    if not resultado.get("exito"):
        logger.warning(
            "no se pudo enviar comando a pcbot para usuario %s: %s",
            usuario_id, resultado.get("error", "error desconocido"),
        )
        return False

    # registrar asignacion
    ahora_str = _ahora_str()
    ejecutar_insercion(
        "insert into pedido_asignaciones "
        "(pedido_id, perfil_id, pcbot_id, url, duracion_seg, inicio, estado) "
        "values (?, ?, ?, ?, ?, ?, 'activo')",
        (
            pedido["id"],
            perfil_elegido,
            pcbot_id,
            url,
            duracion_int,
            ahora_str,
        ),
    )

    logger.info(
        "perfil %s asignado a pedido %s en pcbot %s por %s seg",
        perfil_elegido, pedido["id"], pcbot_id, duracion_int,
    )
    return True


async def _finalizar_pedido(pedido: dict):
    """finaliza un pedido expirado:
    - envia detener a perfiles activos
    - marca asignaciones como completadas
    - cambia estado del pedido a completado
    """
    pedido_id = pedido["id"]
    usuario_id = pedido.get("usuario_id")

    # obtener asignaciones activas
    asignaciones = ejecutar_sql(
        "select id, perfil_id, pcbot_id from pedido_asignaciones "
        "where pedido_id = ? and estado = 'activo'",
        (pedido_id,),
    )

    if usuario_id:
        for asig in asignaciones:
            perfil_id = asig.get("perfil_id")
            comando = {
                "tipo": "detener",
                "parametros": {"perfil_id": perfil_id},
            }
            try:
                await _enviar_comando_seguro(int(usuario_id), comando)
            except Exception as e:
                logger.error(
                    "error enviando detener perfil %s: %s",
                    perfil_id, str(e)[:200],
                )

    # marcar asignaciones como completadas
    ahora_str = _ahora_str()
    ejecutar_sql(
        "update pedido_asignaciones set estado = 'completado', fin = ? "
        "where pedido_id = ? and estado = 'activo'",
        (ahora_str, pedido_id),
    )

    # cambiar estado del pedido
    ejecutar_sql(
        "update pedidos set estado = 'completado' where id = ?",
        (pedido_id,),
    )

    # marcar comando como completado si existe
    comando_id = pedido.get("comando_id")
    if comando_id:
        ejecutar_sql(
            "update comandos set estado = 'completado' where comando_id = ? and estado != 'completado'",
            (comando_id,),
        )

    logger.info("pedido %s finalizado y marcado como completado", pedido_id)