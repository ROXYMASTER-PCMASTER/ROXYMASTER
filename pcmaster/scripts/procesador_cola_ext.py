# procesador_cola_ext.py - parte extendida del modulo procesador_cola
# roxymaster v8.3 - utf-8 sin bom, nombres en minusculas
# contiene funciones auxiliares de comunicacion, gestion de pcbots,
# y logica de observador/comentarios extraida del modulo principal
# importa explicitamente de procesador_cola cuando es necesario

import asyncio
import json
import logging
import random
from datetime import datetime, timezone, timedelta
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


async def _enviar_comando_seguro(usuario_id: int, comando: dict, pcbot_id: str = None) -> dict:
    """wrapper seguro para enviar_comando_al_pcbot.
    maneja excepciones y devuelve siempre dict con exito/error.
    si se proporciona pcbot_id, envia directamente a ese pcbot (v2)."""
    try:
        resultado = await enviar_comando_al_pcbot(usuario_id, comando, pcbot_id)
        if isinstance(resultado, dict):
            return resultado
        exito = bool(resultado)
        return {"exito": exito, "error": "" if exito else "resultado inesperado"}
    except Exception as e:
        logger.error("[COLA] error enviando comando: %s", str(e)[:200])
        return {"exito": False, "error": str(e)[:200]}


async def _liberar_reservas_caducadas():
    """libera reservas cuyo timeout haya expirado.
    ejecutado al inicio de cada ciclo del procesador.
    las asignaciones en 'reservado' con timeout < ahora se marcan como 'fallido'."""
    try:
        ahora = _ahora_str()
        liberadas = ejecutar_sql(
            "update pedido_asignaciones set estado = 'fallido' "
            "where estado = 'reservado' and timeout < ?",
            (ahora,),
        )
        if liberadas is not None:
            logger.info(
                "[COLA] liberadas %s reservas caducadas",
                len(liberadas) if isinstance(liberadas, (list, tuple)) else "?",
            )
    except Exception as e:
        logger.error("[COLA] error liberando reservas caducadas: %s", str(e)[:200])


# ---------------------------------------------------------------------------
# obtener pcbots del usuario (con fallbacks)
# ---------------------------------------------------------------------------
def _obtener_pcbots_usuario(usuario_id: int) -> list:
    """obtiene lista de pcbot_ids (strings) conectados para un usuario.
    fallback: si obtener_pcbots_de_usuario devuelve lista vacia,
    intenta con obtener_pcbot_de_usuario."""
    try:
        pcbots_dicts = obtener_pcbots_de_usuario(int(usuario_id))
        if pcbots_dicts and isinstance(pcbots_dicts, list):
            ids = []
            for entry in pcbots_dicts:
                if isinstance(entry, dict):
                    pid = entry.get("pcbot_id")
                    if pid:
                        ids.append(pid)
                elif isinstance(entry, str):
                    ids.append(entry)
            if ids:
                return ids
    except Exception as e:
        logger.debug("[COLA] obtener_pcbots_de_usuario fallo: %s", str(e)[:100])

    try:
        pcbot_unico = obtener_pcbot_de_usuario(int(usuario_id))
        if pcbot_unico:
            return [pcbot_unico]
    except Exception as e:
        logger.debug("[COLA] obtener_pcbot_de_usuario fallo: %s", str(e)[:100])

    try:
        usuarios = ejecutar_sql(
            "select pcbot_id from usuarios where id = ? and pcbot_id is not null",
            (usuario_id,),
        )
        if usuarios:
            ids = [u["pcbot_id"] for u in usuarios if u.get("pcbot_id")]
            if ids:
                return ids
    except Exception as e:
        logger.debug("[COLA] consulta usuarios bd fallo: %s", str(e)[:100])

    try:
        comps = ejecutar_sql(
            "select distinct pcbot_id from computadoras where usuario_id = ? and pcbot_id is not null",
            (usuario_id,),
        )
        if comps:
            ids = [c["pcbot_id"] for c in comps if c.get("pcbot_id")]
            if ids:
                return ids
    except Exception as e:
        logger.debug("[COLA] consulta computadoras bd fallo: %s", str(e)[:100])

    try:
        perfiles = ejecutar_sql(
            "select distinct pcbot_id from perfiles_roxy where usuario_id = ? and pcbot_id is not null",
            (usuario_id,),
        )
        if perfiles:
            ids = [p["pcbot_id"] for p in perfiles if p.get("pcbot_id")]
            if ids:
                return ids
    except Exception as e:
        logger.debug("[COLA] consulta perfiles_roxy bd fallo: %s", str(e)[:100])

    return []


# ---------------------------------------------------------------------------
# helpers de consulta a base de datos (extraidos del modulo principal)
# ---------------------------------------------------------------------------
def _contar_asignaciones_activas(pedido_id: int) -> int:
    """cuenta asignaciones activas no vencidas para un pedido."""
    result = ejecutar_sql_unico(
        "select count(*) as total from pedido_asignaciones "
        "where pedido_id = ? and estado in ('planificado', 'ejecutando')",
        (pedido_id,),
    )
    return result["total"] if result else 0


def _contar_observadores_por_pcbot(pcbot_id: str) -> int:
    """cuenta cuantas asignaciones en estado ejecutando/planificado
    tiene un pcbot con rol='observador'."""
    result = ejecutar_sql_unico(
        "select count(*) as total from pedido_asignaciones "
        "where pcbot_id = ? and estado in ('planificado', 'ejecutando') "
        "and rol = 'observador'",
        (pcbot_id,),
    )
    return result["total"] if result else 0


def _obtener_contexto_streamer(url: str):
    """obtiene el contexto de un streamer por url desde contextos_streamer.
    devuelve dict con ultimo_analisis o none si no existe."""
    if not url:
        return None
    cinco_min_atras = (_ahora_dt() - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    return ejecutar_sql_unico(
        "select id, url, ultimo_analisis, activo from contextos_streamer "
        "where url = ? and activo = 1",
        (url,),
    )


def _obtener_pedidos_planificables() -> (list, list):
    """devuelve (urgentes, normales) ordenados por fecha_creacion asc.
    urgentes: pedidos en_progreso con deficit y prioridad activa (< 5s).
    normales: pedidos agendados y programados listos.
    """
    # lazy import para evitar import circular
    from procesador_cola import _prioridad_recuperacion, MARGEN_PRIORIDAD

    ahora = _ahora_dt()

    # --- grupo urgente: pedidos en_progreso con deficit y prioridad activa ---
    urgente_ids = [
        pid for pid, ts in _prioridad_recuperacion.items()
        if (ahora - ts).total_seconds() < MARGEN_PRIORIDAD
    ]
    urgentes = []
    if urgente_ids:
        urgentes = ejecutar_sql(
            """select id, usuario_id, url, cantidad_perfiles, duracion_horas,
                      nivel_comentarios, tipo_pedido, comando_id, fecha_creacion,
                      estado, hora_inicio_programada, hora_fin_programada
               from pedidos
               where id in ({}) and estado = 'en_progreso'
               order by fecha_creacion asc""".format(
                ','.join('?' for _ in urgente_ids)
            ),
            urgente_ids,
        )

    # --- grupo normal: pedidos agendados y programados listos ---
    normales = ejecutar_sql(
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

    # urgentes primero, normales despues
    return urgentes, normales


def _obtener_perfiles_libres(pcbots: list, maximo: int) -> list:
    """obtiene perfiles libres de los pcbots especificados.
    un perfil se considera libre si:
    - activo = 1 (conectado al pcbot)
    - no tiene asignaciones activas en pedido_asignaciones
    - o liberacion_estimada <= ahora (perfil que termino y debe liberarse)
    returns:
        list[dict]: perfiles disponibles con keys: perfil_id, pcbot_id, hash
    """
    ahora_str = _ahora_str()
    cinco_seg = (_ahora_dt() + timedelta(seconds=5)).strftime("%Y-%m-%d %H:%M:%S")
    libres = []
    candidatos = []

    seen = set()
    for pcbot_id in pcbots:
        resultados = ejecutar_sql(
            """
            select pr.hash as perfil_id, pr.pcbot_id, pr.liberacion_estimada
            from perfiles_roxy pr
            where pr.pcbot_id = ?
              and pr.activo = 1
              and not exists (
                  select 1 from pedido_asignaciones pa
                  where pa.perfil_id = pr.hash
                    and pa.estado in ('planificado', 'ejecutando', 'activo')
              )
            union
            select pr.hash as perfil_id, pr.pcbot_id, pr.liberacion_estimada
            from perfiles_roxy pr
            where pr.pcbot_id = ?
              and pr.activo = 1
              and pr.liberacion_estimada is not null
              and pr.liberacion_estimada <= ?
            order by liberacion_estimada asc nulls last""",
            (pcbot_id, pcbot_id, cinco_seg),
        )
        for r in (resultados or []):
            pid = r["perfil_id"]
            if pid in seen:
                continue
            seen.add(pid)
            candidatos.append({
                "perfil_id": pid,
                "pcbot_id": pcbot_id,
                "hash": pid,
            })

    # doble verificacion: solo perfiles sin asignaciones activas en bd
    for c in candidatos:
        pid = c["perfil_id"]
        ocupado = ejecutar_sql_unico(
            "select count(*) as cnt from pedido_asignaciones "
            "where perfil_id = ? and estado in ('planificado', 'ejecutando', 'activo')",
            (pid,),
        )
        if ocupado and ocupado.get("cnt", 0) == 0:
            libres.append(c)

    logger.info("[MATCH] %s perfiles libres para asignar (de %s candidatos)",
                len(libres), len(candidatos))

    return libres[:maximo]


# ---------------------------------------------------------------------------
# tarea 1: designacion de observador
# ---------------------------------------------------------------------------
def _tiene_observador_activo(pcbot_id: str) -> bool:
    """verifica si un pcbot ya tiene una asignacion con rol='observador' activa.
    devuelve true si la consulta devuelve algun resultado."""
    result = ejecutar_sql_unico(
        "select 1 as existe from pedido_asignaciones "
        "where pcbot_id = ? and rol = 'observador' and estado = 'ejecutando'",
        (pcbot_id,),
    )
    return result is not None and result.get("existe") == 1


# ---------------------------------------------------------------------------
# tarea 2: rotacion de observador
# ---------------------------------------------------------------------------
def _buscar_perfil_relevo_observador(pcbot_id: str, asig_excluir_id: int) -> str:
    """busca otro perfil en el mismo pcbot con asignacion activa
    para transferirle el rol de observador.
    devuelve el perfil_id del candidato o none si no hay."""
    result = ejecutar_sql_unico(
        "select id, perfil_id from pedido_asignaciones "
        "where pcbot_id = ? and estado = 'ejecutando' and id != ? limit 1",
        (pcbot_id, asig_excluir_id),
    )
    if result:
        return result.get("perfil_id")
    return None


async def _enviar_cambio_rol_observador(usuario_id: int, pcbot_id: str,
                                         perfil_entrante: str):
    """envia comando 'cambiar_rol' al pcbot para transferir el rol observador."""
    comando = {
        "tipo": "cambiar_rol",
        "comando_id": str(uuid4()),
        "parametros": {
            "perfil_id": perfil_entrante,
            "rol": "observador",
        },
    }
    resultado = await _enviar_comando_seguro(usuario_id, comando, pcbot_id)
    return resultado.get("exito", False)


# ---------------------------------------------------------------------------
# tarea 4: distribucion de comentarios
# ---------------------------------------------------------------------------
async def _iniciar_distribucion_comentarios(pedido_id: int, usuario_id: int,
                                            pcbot_id: str, perfil_id: str,
                                            url: str):
    """programa una tarea asincrona que distribuye comentarios
    desde el pool de frases de la url al pcbot.
    se reprograma automaticamente tras cada envio."""
    try:
        # consultar pool de frases
        streamer = ejecutar_sql_unico(
            "select frases_pool, frases_usadas from contextos_streamer "
            "where url = ? and activo = 1",
            (url,),
        )
        if not streamer:
            logger.debug("[COMENTARIOS] sin contexto streamer para %s, reintentando en 60s", url)
            await asyncio.sleep(60)
            asyncio.create_task(
                _iniciar_distribucion_comentarios(
                    pedido_id, usuario_id, pcbot_id, perfil_id, url
                )
            )
            return

        frases_pool_raw = streamer.get("frases_pool", "[]")
        frases_usadas = streamer.get("frases_usadas", 0)

        try:
            frases_pool = json.loads(frases_pool_raw) if isinstance(frases_pool_raw, str) else frases_pool_raw
        except (json.JSONDecodeError, TypeError):
            frases_pool = []

        if not frases_pool or len(frases_pool) <= frases_usadas:
            logger.debug("[COMENTARIOS] pool vacio o agotado para %s, reintentando en 60s", url)
            await asyncio.sleep(60)
            asyncio.create_task(
                _iniciar_distribucion_comentarios(
                    pedido_id, usuario_id, pcbot_id, perfil_id, url
                )
            )
            return

        # seleccionar frase al azar entre las no usadas
        frases_disponibles = frases_pool[frases_usadas:]
        frase = random.choice(frases_disponibles)

        # marcar como usada
        ejecutar_sql(
            "update contextos_streamer set frases_usadas = frases_usadas + 1 "
            "where url = ?",
            (url,),
        )

        # enviar comentario
        comando = {
            "tipo": "comentar",
            "comando_id": str(uuid4()),
            "parametros": {
                "perfil_id": perfil_id,
                "texto": frase,
            },
        }
        await _enviar_comando_seguro(usuario_id, comando, pcbot_id)
        logger.info("[COMENTARIOS] comentario enviado a perfil %s en pcbot %s",
                    perfil_id, pcbot_id)

        # reprogramar en intervalo aleatorio 120-2700 segundos (2-45 min)
        intervalo = random.randint(120, 2700)
        logger.debug("[COMENTARIOS] proximo comentario en %d segundos para %s",
                     intervalo, url)
        await asyncio.sleep(intervalo)

        # reprogramar
        asyncio.create_task(
            _iniciar_distribucion_comentarios(
                pedido_id, usuario_id, pcbot_id, perfil_id, url
            )
        )

    except Exception as e:
        logger.error("[COMENTARIOS] error en distribucion: %s", str(e)[:200])
        await asyncio.sleep(60)
        asyncio.create_task(
            _iniciar_distribucion_comentarios(
                pedido_id, usuario_id, pcbot_id, perfil_id, url
            )
        )


# ---------------------------------------------------------------------------
# limpieza de asignaciones huerfanas (extraido del modulo principal)
# ---------------------------------------------------------------------------
async def _limpiar_asignaciones_huerfanas():
    """limpia asignaciones huerfanas que bloquean perfiles.
    reglas:
    1. si un perfil tiene mas de una asignacion activa, marca todas
       menos la mas reciente como 'fallido'.
    2. si una asignacion activa pertenece a un pedido ya completado/cancelado,
       marca esa asignacion como 'fallido'.
    """
    ahora_str = _ahora_str()
    total_limpiadas = 0

    # regla 1: perfiles con multiples asignaciones activas
    perfiles_duplicados = ejecutar_sql(
        """select perfil_id, pcbot_id, count(*) as total
           from pedido_asignaciones
           where estado in ('planificado', 'ejecutando')
           group by perfil_id, pcbot_id
           having count(*) > 1"""
    )

    for fila in (perfiles_duplicados or []):
        perfil_id = fila["perfil_id"]
        pcbot_id = fila["pcbot_id"]
        asignaciones = ejecutar_sql(
            """select id, inicio
               from pedido_asignaciones
               where perfil_id = ?
                 and pcbot_id = ?
                 and estado in ('planificado', 'ejecutando')
               order by inicio desc""",
            (perfil_id, pcbot_id),
        )
        if not asignaciones or len(asignaciones) <= 1:
            continue
        for asig in asignaciones[1:]:
            try:
                ejecutar_sql(
                    "update pedido_asignaciones set estado = 'fallido', fin = ? "
                    "where id = ? and estado in ('planificado', 'ejecutando')",
                    (ahora_str, asig["id"]),
                )
                total_limpiadas += 1
                logger.warning(
                    "[MATCH] huerfana: perfil %s tenia %d asignaciones activas, "
                    "se marco #%s como fallido",
                    perfil_id, len(asignaciones), asig["id"],
                )
            except Exception as e:
                logger.error("[MATCH] error limpiando duplicado perfil %s asig %s: %s",
                             perfil_id, asig["id"], str(e)[:200])

    # regla 2: asignaciones activas para pedidos ya completados o cancelados
    asignaciones_huerfanas = ejecutar_sql(
        """select pa.id, pa.perfil_id, pa.pcbot_id, pa.pedido_id
           from pedido_asignaciones pa
           join pedidos p on p.id = pa.pedido_id
           where pa.estado in ('planificado', 'ejecutando')
             and p.estado in ('completado', 'cancelado')"""
    )

    for asig in (asignaciones_huerfanas or []):
        try:
            ejecutar_sql(
                "update pedido_asignaciones set estado = 'fallido', fin = ? "
                "where id = ? and estado in ('planificado', 'ejecutando')",
                (ahora_str, asig["id"]),
            )
            total_limpiadas += 1
            logger.warning(
                "[MATCH] huerfana: asignacion %s (perfil %s) para pedido %s "
                "ya en estado completado/cancelado -> fallido",
                asig["id"], asig.get("perfil_id"), asig.get("pedido_id"),
            )
        except Exception as e:
            logger.error("[MATCH] error limpiando huerfana asig %s: %s",
                         asig["id"], str(e)[:200])

    if total_limpiadas > 0:
        logger.info("[MATCH] limpieza completada: %s asignaciones huerfanas marcadas como fallido",
                    total_limpiadas)

    # verificar pedidos completados (todas sus asignaciones finalizadas)
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

    # eliminar asignaciones planificadas huerfanas (>35s sin respuesta)
    timeout_dt = _ahora_dt() - timedelta(seconds=35)
    timeout_str = timeout_dt.strftime("%Y-%m-%d %H:%M:%S")
    colgadas = ejecutar_sql(
        """select id from pedido_asignaciones
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
            logger.warning("[MATCH] asignacion planificada %s marcada fallida por timeout (>35s)",
                          asig["id"])
        except Exception as e:
            logger.error("[MATCH] error marcando timeout asignacion %s: %s",
                         asig["id"], str(e)[:200])