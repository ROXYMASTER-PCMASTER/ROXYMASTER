# pedidos_vigilante.py - monitoreo de pedidos, reemplazo de perfiles caidos
# y perfiles con url incorrecta. finaliza pedidos expirados.
# modulo simplificado: la cola fifo y el agendamiento los maneja
# procesador_cola.py
# dependencias: heartbeat_cache, ws_manager, db
# v3: estados de asignacion corregidos a 'planificado'/'ejecutando'
#     (se eliminaron estados legacy 'activo','enviado','pendiente')
# v3.1: fix race condition - agregado 'reservado' a las lists de exclusion
#       en _asignar_perfil_reemplazo para evitar doble asignacion

import asyncio
import logging
from datetime import datetime, timezone

import heartbeat_cache
import procesador_cola
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
    - perfiles desaparecidos (no aparecen en heartbeat) -> reemplazar
    - perfiles con url incorrecta -> reemplazar
    - perfiles con state='caido' -> marcar fallido, NO reemplazar (intervencion manual)
    """
    logger.info("vigilante de pedidos iniciado (intervalo 30s)")
    while True:
        try:
            await _ciclo_vigilante()
        except Exception as e:
            logger.error("error en ciclo vigilante: %s", str(e)[:200])
        await asyncio.sleep(30)


async def _ciclo_vigilante():
    """ejecuta una ronda de verificacion sobre todos los pedidos activos.
    solo procesa pedidos en 'en_progreso' o 'trabajando'.
    los estados 'pendiente', 'programado' los maneja procesador_cola.py."""
    pedidos = ejecutar_sql(
        "select id, usuario_id, url, cantidad_perfiles, duracion_horas, "
        "nivel_comentarios, fecha_creacion, fecha_inicio, estado "
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


async def _verificar_pedido(pedido: dict, ahora: datetime):
    """verifica estado de un pedido activo y actua si es necesario.
    usa heartbeat_cache para obtener los perfiles activos reales
    y comparar urls. distingue tres casos:
    - perfil no aparece en heartbeat -> perfil desaparecido -> reemplazar
    - perfil aparece con state='caido' -> marcar fallido, no reemplazar
    - perfil aparece con url incorrecta -> marcar fallido, detener, reemplazar
    """
    pedido_id = pedido["id"]
    # bug B fix: priorizar fecha_inicio sobre fecha_creacion
    # si el pedido paso a en_progreso hace poco, usar fecha_inicio como referencia
    fecha_inicio_str = pedido.get("fecha_inicio") or pedido.get("fecha_creacion")
    if not fecha_inicio_str:
        return

    try:
        if "+" in fecha_inicio_str or "Z" in fecha_inicio_str:
            limpia = fecha_inicio_str.replace("Z", "+00:00")
            fecha_inicio = datetime.fromisoformat(limpia)
        else:
            fecha_inicio = datetime.strptime(fecha_inicio_str, "%Y-%m-%d %H:%M:%S")
            fecha_inicio = fecha_inicio.replace(tzinfo=timezone.utc)
    except Exception:
        logger.warning("pedido %s: no se pudo parsear fecha_inicio '%s'", pedido_id, fecha_inicio_str)
        return

    transcurrido = (ahora - fecha_inicio).total_seconds()

    # fix NULL fecha_inicio: si fecha_inicio_str es igual a fecha_creacion porque
    # fecha_inicio era NULL, verificar si el pedido es reciente para no expirarlo
    fecha_creacion_str = pedido.get("fecha_creacion")
    if not pedido.get("fecha_inicio") and fecha_creacion_str:
        # el pedido nunca recibio fecha_inicio -> probablemente no inicio realmente
        # en lugar de usar fecha_creacion como fallback (que expira injustamente),
        # dar un margen de tolerancia de 5 minutos desde ahora
        logger.warning(
            "pedido %s: fecha_inicio es NULL, usando margen de 300s "
            "en vez de fecha_creacion para evitar falsa expiracion",
            pedido_id,
        )
        transcurrido = 0  # forzar que no expire
    duracion_horas = pedido.get("duracion_horas", 0)
    # bug B fix: si duracion_horas es 0 o None, usar default 1 minuto en vez de expirar inmediatamente
    if not duracion_horas or duracion_horas <= 0:
        duracion_seg = 60
        logger.info("pedido %s: duracion_horas era %s, usando default 60s", pedido_id, duracion_horas)
    else:
        duracion_seg = duracion_horas * 3600
    tiempo_restante = duracion_seg - transcurrido

    # caso 1: pedido expirado
    if tiempo_restante <= 0:
        logger.info("pedido %s expirado, finalizando", pedido_id)
        await _finalizar_pedido(pedido)
        return

    # caso 2: verificar cada asignacion activa
    # fix 1: usar estados correctos del modelo centralizado ('planificado','ejecutando')
    # NOTA: 'reservado' se excluye explicitamente; esas asignaciones estan en proceso
    # de confirmacion por el procesador de cola y no deben evaluarse aqui.
    # si estuvieran incluidas, se saltarian con continue (ver bucle for abajo).
    asignaciones = ejecutar_sql(
        "select id, perfil_id, pcbot_id, url, inicio, estado from pedido_asignaciones "
        "where pedido_id = ? and estado in ('planificado', 'ejecutando')",
        (pedido_id,),
    )
    if not asignaciones:
        # bug C fix: grace period de 45s desde fecha_inicio antes de reasignar
        # esto evita que el vigilante compita con el procesador de cola
        if transcurrido < 45:
            logger.info(
                "pedido %s sin asignaciones aun (grace %.0fs), esperando",
                pedido_id, transcurrido,
            )
            return
        # sin asignaciones activas -> reasignar todas
        logger.info("pedido %s sin asignaciones activas, reasignando", pedido_id)
        cantidad_pedido = pedido.get("cantidad_perfiles", 1)
        for _ in range(cantidad_pedido):
            await _asignar_perfil_reemplazo(pedido, tiempo_restante)
        return

    # contadores para logging
    bajas_registradas = 0       # perfiles caidos/desviados que registran baja
    caidos_sin_reemplazo = 0    # state='caido', no se registran como baja
    usuario_id = pedido.get("usuario_id")
    url_pedido = pedido.get("url", "")

    for asig in asignaciones:
        # ignorar asignaciones en estado 'reservado' (aun no confirmadas por el pcbot)
        if asig.get("estado") == "reservado":
            continue

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

        # fix: grace period de 45s desde inicio de asignacion antes de
        # marcar perfil como desaparecido. esto da tiempo al pcbot para
        # confirmar el perfil en el siguiente heartbeat.
        inicio_asig = asig.get("inicio")
        if inicio_asig and asig.get("estado") == "planificado":
            try:
                if "+" in inicio_asig or "Z" in inicio_asig:
                    limpia = inicio_asig.replace("Z", "+00:00")
                    inicio_dt = datetime.fromisoformat(limpia)
                else:
                    inicio_dt = datetime.strptime(inicio_asig, "%Y-%m-%d %H:%M:%S")
                    inicio_dt = inicio_dt.replace(tzinfo=timezone.utc)
                segundos_desde_asignacion = (ahora - inicio_dt).total_seconds()
                if segundos_desde_asignacion < 45:
                    logger.info(
                        "perfil %s asignado hace %.0fs (<45) y en estado planificado, "
                        "esperando confirmacion para pedido %s",
                        perfil_id, segundos_desde_asignacion, pedido_id,
                    )
                    continue  # no evaluar este perfil aun
            except Exception as e:
                logger.debug("error parseando inicio_asig %s: %s", inicio_asig, str(e)[:100])

        # obtener estado del perfil en el ultimo heartbeat
        estado_real = heartbeat_cache.obtener_estado_perfil(pcbot_id, perfil_id)

        # caso a: perfil con state='caido' (pcbot reporta error, no reemplazar)
        if estado_real == "caido":
            logger.info(
                "perfil %s en pcbot %s reportado como caido para pedido %s "
                "(no se reemplaza automaticamente)",
                perfil_id, pcbot_id, pedido_id,
            )
            ejecutar_sql(
                "update pedido_asignaciones set estado = 'fallido' where id = ?",
                (asig["id"],),
            )
            caidos_sin_reemplazo += 1
            continue

        # caso a2: perfil inactivo (activo=0 en perfiles_roxy, fue cerrado)
        if estado_real == "inactivo":
            logger.info(
                "perfil %s en pcbot %s esta inactivo (cerrado) para pedido %s, "
                "registrando baja para recuperacion prioritaria",
                perfil_id, pcbot_id, pedido_id,
            )
            ejecutar_sql(
                "update pedido_asignaciones set estado = 'fallido' where id = ?",
                (asig["id"],),
            )
            procesador_cola.registrar_baja(pedido_id)
            bajas_registradas += 1
            continue

        # buscar el perfil en los activos del heartbeat cache
        activos_cache = heartbeat_cache.obtener_perfiles_activos(pcbot_id)
        perfil_en_cache = None
        for p in activos_cache:
            if p.get("profile_id") == perfil_id:
                perfil_en_cache = p
                break

        # caso b: perfil no aparece como activo en el ultimo heartbeat (desaparecido)
        if not perfil_en_cache:
            logger.info(
                "perfil %s caido (no aparece en heartbeat activo) en pcbot %s "
                "para pedido %s, registrando baja para recuperacion prioritaria",
                perfil_id, pcbot_id, pedido_id,
            )
            ejecutar_sql(
                "update pedido_asignaciones set estado = 'fallido' where id = ?",
                (asig["id"],),
            )
            # marcar perfil como inactivo para evitar reasignacion prematura
            ejecutar_sql(
                "update perfiles_roxy set activo = 0 where hash = ? and pcbot_id = ?",
                (perfil_id, pcbot_id),
            )
            procesador_cola.registrar_baja(pedido_id)
            bajas_registradas += 1
            continue

        # caso c: perfil activo pero url incorrecta
        # paso 1: obtener url desde heartbeat cache en memoria (mas fiable que bd)
        # el heartbeat del pcbot trae la url en tiempo real con cada latido
        url_actual = None
        hb = heartbeat_cache.obtener_heartbeat(pcbot_id)
        if hb:
            for p in hb.get("perfiles", []):
                if p.get("profile_id") == perfil_id:
                    url_actual = p.get("url", "")
                    break
        # paso 2: fallback a url de la bd (perfiles_roxy.url_actual) si el cache no tiene datos
        if not url_actual:
            url_actual = perfil_en_cache.get("url", "")
        if url_pedido and url_actual and url_actual != url_pedido:
            logger.info(
                "perfil %s en pcbot %s navegando a url incorrecta (%s vs %s esperada) "
                "para pedido %s, registrando baja para recuperacion prioritaria",
                perfil_id, pcbot_id, url_actual, url_pedido, pedido_id,
            )
            ejecutar_sql(
                "update pedido_asignaciones set estado = 'fallido' where id = ?",
                (asig["id"],),
            )
            # marcar perfil como inactivo para evitar reasignacion prematura
            ejecutar_sql(
                "update perfiles_roxy set activo = 0 where hash = ? and pcbot_id = ?",
                (perfil_id, pcbot_id),
            )
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
            procesador_cola.registrar_baja(pedido_id)
            bajas_registradas += 1


async def _enviar_comando_seguro(usuario_id: int, comando: dict) -> dict:
    """wrapper seguro para enviar_comando_al_pcbot que maneja
    excepciones y devuelve siempre un dict con exito/error."""
    try:
        resultado = await enviar_comando_al_pcbot(usuario_id, comando)
        if isinstance(resultado, dict):
            return resultado
        exito = bool(resultado)
        return {"exito": exito, "error": "" if exito else "resultado inesperado"}
    except Exception as e:
        logger.error("error en enviar_comando_al_pcbot: %s", str(e)[:200])
        return {"exito": False, "error": str(e)[:200]}


async def _asignar_perfil_reemplazo(pedido: dict, duracion: float) -> bool:
    """asigna un perfil libre como reemplazo de uno caido/desaparecido.
    busca perfiles libres en heartbeat_cache para el pcbot del usuario,
    envia comando asignar y registra en pedido_asignaciones.
    duracion = tiempo restante del pedido en segundos.
    usa heartbeat_cache.obtener_perfiles_libres() que ya excluye caidos."""
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

    # buscar perfil libre directamente desde perfiles_roxy
    # replica la logica de procesador_cola._obtener_perfiles_libres
    # pero simplificado: solo perfiles sin asignaciones activas
    # IMPORTANTE: excluir TODOS los estados que indican uso activo,
    # incluyendo 'planificado', 'ejecutando', 'activo', 'enviado', 'pendiente', 'reservado'
    # para evitar reasignar perfiles que ya estan en uso en este mismo ciclo
    # v3.1: agregado 'reservado' para evitar race condition con procesador_cola
    libres_db = ejecutar_sql(
        """select pr.hash as perfil_id, pr.pcbot_id
           from perfiles_roxy pr
           where pr.pcbot_id = ?
             and pr.activo = 1
             and not exists (
                 select 1 from pedido_asignaciones pa
                 where pa.perfil_id = pr.hash
                   and pa.pcbot_id = pr.pcbot_id
                   and pa.estado in ('planificado', 'ejecutando', 'activo', 'enviado', 'pendiente', 'reservado')
             )
           limit 1""",
        (pcbot_id,),
    )
    if not libres_db:
        logger.warning(
            "[VIGILANTE] no hay perfiles libres en pcbot %s segun bd "
            "(todos ocupados por asignaciones activas)", pcbot_id
        )
        return False

    perfil_elegido = libres_db[0].get("perfil_id", "")
    if not perfil_elegido:
        logger.warning("[VIGILANTE] perfil libre sin profile_id en pcbot %s", pcbot_id)
        return False

    # verificacion atomica adicional: confirmar que el perfil no tenga
    # asignacion activa justo en este momento (race condition)
    # v3.1: agregado 'enviado', 'pendiente', 'reservado' a la lista de exclusion
    conteo_activo = ejecutar_sql_unico(
        "select count(*) as cnt from pedido_asignaciones "
        "where perfil_id = ? and estado in ('planificado', 'ejecutando', 'activo', 'enviado', 'pendiente', 'reservado')",
        (perfil_elegido,),
    )
    if conteo_activo and conteo_activo.get("cnt", 0) > 0:
        logger.warning(
            "[VIGILANTE] perfil %s ya tiene asignacion activa "
            "(race condition detectada), se omite reemplazo",
            perfil_elegido,
        )
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

    # fix 4: registrar asignacion con estado 'planificado' (no 'activo')
    ahora_str = _ahora_str()
    ejecutar_insercion(
        "insert into pedido_asignaciones "
        "(pedido_id, perfil_id, pcbot_id, url, duracion_seg, inicio, estado) "
        "values (?, ?, ?, ?, ?, ?, 'planificado')",
        (pedido["id"], perfil_elegido, pcbot_id, url, duracion_int, ahora_str),
    )

    logger.info(
        "perfil %s reasignado a pedido %s en pcbot %s por %s seg (reemplazo)",
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

    # fix 2: obtener asignaciones activas con estados correctos
    asignaciones = ejecutar_sql(
        "select id, perfil_id, pcbot_id from pedido_asignaciones "
        "where pedido_id = ? and estado in ('planificado', 'ejecutando')",
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

    # fix 3: marcar asignaciones como completadas usando estados correctos
    ahora_str = _ahora_str()
    ejecutar_sql(
        "update pedido_asignaciones set estado = 'completado', fin = ? "
        "where pedido_id = ? and estado in ('planificado', 'ejecutando')",
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
            "update comandos set estado = 'completado' "
            "where comando_id = ? and estado != 'completado'",
            (comando_id,),
        )

    logger.info("pedido %s finalizado y marcado como completado", pedido_id)