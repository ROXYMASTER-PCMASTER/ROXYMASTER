# pedidos_vigilante.py - modulo vigilante de pedidos en progreso
# monitorea pedidos activos y reemplaza perfiles caidos
# parte del modulo pedidos_vigilante

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta

from db import ejecutar_sql, ejecutar_sql_unico
from ws_manager import enviar_comando_al_pcbot

logger = logging.getLogger("roxymaster.pedidos_vigilante")

# nombre de la tabla de asignaciones (se crea en db_pedidos_vigilante.py)
TABLA_ASIGNACIONES = "pedido_asignaciones"

# intervalo de monitoreo en segundos
INTERVALO_SEG = 30

# tiempo maximo sin heartbeat antes de considerar pcbot desconectado
TIMEOUT_HEARTBEAT_SEG = 60


async def monitorear_pedidos():
    """bucle principal del vigilante: cada INTERVALO_SEG revisa pedidos activos."""
    logger.info("vigilante de pedidos iniciado, intervalo=%ss", INTERVALO_SEG)
    while True:
        try:
            await _revisar_pedidos()
        except asyncio.CancelledError:
            logger.info("vigilante de pedidos detenido")
            raise
        except Exception as e:
            logger.error("error en ciclo vigilante: %s", e, exc_info=True)
        await asyncio.sleep(INTERVALO_SEG)


async def _revisar_pedidos():
    """obtiene pedidos en_progreso y los procesa uno por uno."""
    try:
        pedidos = ejecutar_sql(
            "select id, usuario_id, url, cantidad_perfiles, duracion_horas, "
            "nivel_comentarios, fecha_creacion, estado "
            "from pedidos where estado = 'en_progreso'"
        )
    except Exception as e:
        logger.error("error consultando pedidos en_progreso: %s", e)
        return

    if not pedidos:
        logger.info("vigilante: no hay pedidos en_progreso")
        return

    logger.info("vigilante: %d pedido(s) en_progreso", len(pedidos))
    for pedido in pedidos:
        try:
            await _procesar_pedido(pedido)
        except Exception as e:
            logger.error("error procesando pedido %s: %s", pedido["id"], e)


def _obtener_pcbot_del_pedido(pedido: dict) -> str:
    """obtiene el pcbot_id asociado al usuario del pedido."""
    usuario_id = pedido.get("usuario_id")
    if not usuario_id:
        return None
    try:
        row = ejecutar_sql_unico(
            "select pcbot_id from usuarios where id = ?", (usuario_id,)
        )
        return row["pcbot_id"] if row and row.get("pcbot_id") else None
    except Exception as e:
        logger.error("error obteniendo pcbot para usuario %s: %s", usuario_id, e)
        return None


def _obtener_perfiles_heartbeat(pcbot_id: str) -> set:
    """obtiene el set de profile_id activos desde el ultimo heartbeat del pcbot.
    retorna None si el pcbot esta desconectado.
    """
    try:
        from ws_manager import _conexiones_por_pcbot
    except ImportError:
        logger.error("no se puede importar _conexiones_por_pcbot desde ws_manager")
        return set()

    datos_pcbot = _conexiones_por_pcbot.get(pcbot_id)
    if not datos_pcbot:
        logger.warning("pcbot %s: no hay datos de conexion", pcbot_id)
        return set()

    ultimo_hb = datos_pcbot.get("ultimo_heartbeat")
    if not ultimo_hb:
        return set()

    ahora = datetime.now(timezone.utc)
    if isinstance(ultimo_hb, str):
        try:
            ts_hb = datetime.fromisoformat(ultimo_hb)
        except Exception:
            ts_hb = ahora - timedelta(hours=1)
    else:
        ts_hb = ahora - timedelta(hours=1)

    if ts_hb.tzinfo is None:
        ts_hb = ts_hb.replace(tzinfo=timezone.utc)

    # si pasaron mas de TIMEOUT_HEARTBEAT_SEG seg sin heartbeat, pcbot desconectado
    if (ahora - ts_hb).total_seconds() > TIMEOUT_HEARTBEAT_SEG:
        logger.warning("pcbot %s: heartbeat vencido (>%ds), considerando desconectado",
                       pcbot_id, TIMEOUT_HEARTBEAT_SEG)
        return None

    # obtener perfiles del heartbeat almacenado
    try:
        perfiles_lista = datos_pcbot.get("perfiles", [])
        if isinstance(perfiles_lista, str):
            perfiles_lista = json.loads(perfiles_lista)
    except Exception:
        return set()

    return {p.get("profile_id", p.get("dirId", ""))
            for p in perfiles_lista if p.get("activo")}


async def _procesar_pedido(pedido: dict):
    """procesa un pedido: calcula tiempo, verifica perfiles activos,
    reemplaza caidos, ajusta sobrantes.
    """
    pedido_id = pedido["id"]
    url = pedido["url"]
    cantidad_solicitada = pedido["cantidad_perfiles"]
    nivel_comentarios = pedido.get("nivel_comentarios", 1)
    duracion_horas = pedido.get("duracion_horas", 0)

    fecha_creacion_str = pedido.get("fecha_creacion")
    if not fecha_creacion_str:
        logger.warning("pedido %s sin fecha_creacion, saltando", pedido_id)
        return

    try:
        fecha_creacion = datetime.fromisoformat(fecha_creacion_str)
        if fecha_creacion.tzinfo is None:
            fecha_creacion = fecha_creacion.replace(tzinfo=timezone.utc)
    except Exception:
        logger.warning("fecha_creacion invalida en pedido %s: %s", pedido_id, fecha_creacion_str)
        return

    duracion_total_seg = duracion_horas * 3600
    ahora = datetime.now(timezone.utc)
    tiempo_transcurrido = (ahora - fecha_creacion).total_seconds()
    tiempo_restante = duracion_total_seg - tiempo_transcurrido

    if tiempo_restante <= 0:
        logger.info("pedido %s: tiempo cumplido, finalizando", pedido_id)
        await _finalizar_pedido(pedido_id)
        return

    # obtener asignaciones activas de este pedido
    try:
        asignaciones = ejecutar_sql(
            f"select id, pcbot_id, perfil_id, estado, comando_id "
            f"from {TABLA_ASIGNACIONES} "
            f"where pedido_id = ? and estado = 'activo'",
            (pedido_id,)
        )
    except Exception as e:
        logger.error("error consultando asignaciones para pedido %s: %s", pedido_id, e)
        return

    # obtener el pcbot del usuario del pedido
    pcbot_id = _obtener_pcbot_del_pedido(pedido)
    if not pcbot_id:
        logger.warning("pedido %s: no se pudo determinar pcbot, saltando", pedido_id)
        return

    # contar perfiles realmente activos segun heartbeat
    activos = _contar_perfiles_activos_en_pcbot(pcbot_id, asignaciones)
    logger.info("pedido %s: activos=%d solicitados=%d tiempo_restante=%ds",
                pedido_id, activos, cantidad_solicitada, int(tiempo_restante))

    if activos < cantidad_solicitada:
        faltantes = cantidad_solicitada - activos
        logger.info("pedido %s: faltan %d perfiles, abriendo reemplazos", pedido_id, faltantes)
        for _ in range(faltantes):
            await _abrir_perfil_reemplazo(pedido_id, pcbot_id, url,
                                          tiempo_restante, nivel_comentarios)
    elif activos > cantidad_solicitada:
        sobrantes = activos - cantidad_solicitada
        logger.info("pedido %s: sobran %d perfiles, cerrando extras", pedido_id, sobrantes)
        await _cerrar_perfiles_sobrantes(pedido_id, asignaciones, sobrantes)

    # marcar como fallidas las asignaciones cuyo perfil ya no esta activo
    _actualizar_asignaciones_caidas(pcbot_id, asignaciones)


def _contar_perfiles_activos_en_pcbot(pcbot_id: str, asignaciones: list) -> int:
    """cuenta cuantos perfiles de las asignaciones estan realmente activos
    segun el ultimo heartbeat del pcbot.
    """
    perfiles_heartbeat = _obtener_perfiles_heartbeat(pcbot_id)
    if perfiles_heartbeat is None:
        # pcbot desconectado o sin heartbeat
        return 0

    activos = 0
    for asig in asignaciones:
        perfil_id = asig.get("perfil_id")
        if perfil_id and perfil_id in perfiles_heartbeat:
            activos += 1
    return activos


async def _abrir_perfil_reemplazo(pedido_id: int, pcbot_id: str, url: str,
                                  duracion_seg: int, nivel_comentarios: int):
    """envia comando asignar para abrir un perfil de reemplazo y registra asignacion."""
    comando_id = str(uuid.uuid4())

    # asegurar duracion minima 60 seg
    if duracion_seg < 60:
        duracion_seg = 60

    comando = {
        "tipo": "asignar",
        "parametros": {
            "cantidad": 1,
            "url": url,
            "duracion": duracion_seg,
            "nivel_comentarios": nivel_comentarios
        },
        "comando_id": comando_id
    }

    # obtener usuario_id del pcbot para el comando
    usuario_id = _obtener_usuario_por_pcbot(pcbot_id)
    if not usuario_id:
        logger.error("no se pudo determinar usuario_id para pcbot %s", pcbot_id)
        return

    try:
        resultado = await enviar_comando_al_pcbot(usuario_id, comando)
        logger.info("reemplazo enviado: pedido=%s comando=%s resultado=%s",
                    pedido_id, comando_id, resultado)
    except Exception as e:
        logger.error("error enviando reemplazo para pedido %s: %s", pedido_id, e)
        return

    # registrar asignacion en bd
    ahora_str = datetime.now(timezone.utc).isoformat()
    try:
        ejecutar_sql(
            f"insert into {TABLA_ASIGNACIONES} "
            f"(pedido_id, pcbot_id, perfil_id, url, duracion_seg, inicio, estado, comando_id) "
            f"values (?, ?, '', ?, ?, ?, 'activo', ?)",
            (pedido_id, pcbot_id, url, duracion_seg, ahora_str, comando_id)
        )
    except Exception as e:
        logger.error("error registrando asignacion en bd: %s", e)


async def _cerrar_perfiles_sobrantes(pedido_id: int, asignaciones: list, cantidad: int):
    """cierra perfiles sobrantes."""
    if not asignaciones or cantidad <= 0:
        return

    cerrados = 0
    for asig in asignaciones:
        if cerrados >= cantidad:
            break
        comando_id = asig.get("comando_id")
        if not comando_id:
            continue

        try:
            await enviar_comando_al_pcbot(
                usuario_id=None,
                comando={
                    "tipo": "detener",
                    "parametros": {"comando_id": comando_id},
                    "comando_id": str(uuid.uuid4())
                }
            )
        except Exception as e:
            logger.error("error cerrando perfil sobrante: %s", e)
            continue

        # marcar asignacion como completada
        try:
            ejecutar_sql(
                f"update {TABLA_ASIGNACIONES} set estado='completado', "
                f"fin=datetime('now') where id=?",
                (asig["id"],)
            )
        except Exception:
            pass
        cerrados += 1


def _actualizar_asignaciones_caidas(pcbot_id: str, asignaciones: list):
    """marca como fallidas las asignaciones cuyo perfil ya no aparece en heartbeat."""
    perfiles_heartbeat = _obtener_perfiles_heartbeat(pcbot_id)
    if perfiles_heartbeat is None:
        perfiles_heartbeat = set()

    for asig in asignaciones:
        perfil_id = asig.get("perfil_id", "")
        if perfil_id and perfil_id not in perfiles_heartbeat:
            try:
                ejecutar_sql(
                    f"update {TABLA_ASIGNACIONES} set estado='fallido' where id=?",
                    (asig["id"],)
                )
            except Exception as e:
                logger.error("error actualizando asignacion caida: %s", e)


async def _finalizar_pedido(pedido_id: int):
    """finaliza un pedido: detiene perfiles activos, marca asignaciones y actualiza estado."""
    try:
        asignaciones = ejecutar_sql(
            f"select id, pcbot_id, comando_id from {TABLA_ASIGNACIONES} "
            f"where pedido_id = ? and estado = 'activo'",
            (pedido_id,)
        )
    except Exception as e:
        logger.error("error consultando asignaciones para finalizar pedido %s: %s", pedido_id, e)
        return

    for asig in asignaciones:
        comando_id = asig.get("comando_id")
        if comando_id:
            try:
                await enviar_comando_al_pcbot(
                    usuario_id=None,
                    comando={
                        "tipo": "detener",
                        "parametros": {"comando_id": comando_id},
                        "comando_id": str(uuid.uuid4())
                    }
                )
            except Exception:
                pass

        try:
            ejecutar_sql(
                f"update {TABLA_ASIGNACIONES} set estado='completado', "
                f"fin=datetime('now') where id=?",
                (asig["id"],)
            )
        except Exception:
            pass

    try:
        ejecutar_sql(
            "update pedidos set estado='completado' where id=?",
            (pedido_id,)
        )
        logger.info("pedido %s finalizado y marcado como completado", pedido_id)
    except Exception as e:
        logger.error("error actualizando estado del pedido %s: %s", pedido_id, e)


def _obtener_usuario_por_pcbot(pcbot_id: str) -> int:
    """obtiene el usuario_id asociado a un pcbot."""
    try:
        row = ejecutar_sql_unico(
            "select id from usuarios where pcbot_id = ?", (pcbot_id,)
        )
        return row["id"] if row else None
    except Exception as e:
        logger.error("error obteniendo usuario por pcbot %s: %s", pcbot_id, e)
        return None