# orchestrator_ext.py - parte extendida del modulo orchestrator
# funciones auxiliares de alto nivel (comandos, consultas, broadcast)
# roxymaster v8.3 - utf-8 sin bom, nombres en minusculas

import asyncio
import json
import time
import uuid
import logging
logger = logging.getLogger(__name__)
from datetime import datetime

import heartbeat_cache
from db import ejecutar_sql, ejecutar_sql_unico, ejecutar_insercion
from shs import firmar_payload, verificar_payload, secreto_bytes as secreto_sistema, generar_secreto_pcbot


# ---------------------------------------------------------------------------
# constantes / wrappers de compatibilidad para el protocolo envelope (payload+firma)
# ---------------------------------------------------------------------------
_secreto = secreto_sistema


def firmar(payload_str: str, secreto: str = "") -> str:
    """wrapper de compatibilidad: firma un payload json string.
    usa firmar_payload y extrae la firma."""
    import json as _json
    payload_dict = _json.loads(payload_str) if isinstance(payload_str, str) else payload_str
    _s = str(secreto) if secreto else ""
    resultado = firmar_payload(payload_dict, secreto_override=_s)
    return resultado.get("signature", "")


def verificar_firma(payload_str: str, firma_esperada: str, secreto: str = "") -> bool:
    """wrapper de compatibilidad: verifica firma de un payload json string."""
    import json as _json
    try:
        payload_dict = _json.loads(payload_str) if isinstance(payload_str, str) else payload_str
        ts = str(payload_dict.get("timestamp", ""))
        if not ts:
            return False
        _s = str(secreto) if secreto else ""
        payload_con_firma = dict(payload_dict)
        payload_con_firma["signature"] = firma_esperada
        return verificar_payload(payload_con_firma, secreto_override=_s)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# comandos de alto nivel
# ---------------------------------------------------------------------------
async def comando_asignar(
    pcbot_id: str,
    cantidad: int,
    url: str,
    duracion_min: int = 60,
    comentarios_activos: bool = False,
    streamer: str = "",
) -> dict:
    """
    asigna una url a uno o varios perfiles en un pcbot.
    formato: "asignar <cant> url <url> duracion <min>"
    """
    from orchestrator import crear_comando
    parametros = {
        "cantidad": cantidad,
        "url": url,
        "duracion_min": duracion_min,
        "comentarios_activos": comentarios_activos,
    }

    # registrar url asignada en la db
    url_id = ejecutar_insercion(
        """insert into urls_asignadas (url, streamer, perfiles_asignados, duracion_min,
           comentarios_activos, estado, fecha_asignacion, pcbot_id)
           values (?, ?, ?, ?, ?, 'activa', ?, ?)""",
        (url, streamer, cantidad, duracion_min, 1 if comentarios_activos else 0, _ahora_str(), pcbot_id),
    )

    resultado = await crear_comando("asignar", parametros, pcbot_id)
    if resultado.get("exito"):
        resultado["url_id"] = url_id
    return resultado


async def comando_comentarios_activar(pcbot_id: str, url: str) -> dict:
    """activa comentarios en una url ya asignada."""
    from orchestrator import crear_comando
    url_existente = ejecutar_sql_unico(
        "select * from urls_asignadas where url = ? and pcbot_id = ? and estado = 'activa'",
        (url, pcbot_id),
    )
    if not url_existente:
        return {"exito": False, "error": "url no encontrada o no esta activa"}

    ejecutar_sql("update urls_asignadas set comentarios_activos = 1 where id = ?", (url_existente["id"],))

    return await crear_comando("comentarios_activar", {"url": url}, pcbot_id)


async def comando_detener(pcbot_id: str, url: str) -> dict:
    """detiene la actividad en una url especifica."""
    from orchestrator import crear_comando
    ejecutar_sql(
        "update urls_asignadas set estado = 'detenida', fecha_fin = ? where url = ? and pcbot_id = ?",
        (_ahora_str(), url, pcbot_id),
    )
    return await crear_comando("detener", {"url": url}, pcbot_id)


async def comando_estado(pcbot_id: str) -> dict:
    """solicita el estado actual del pcbot."""
    from orchestrator import crear_comando
    return await crear_comando("estado", {}, pcbot_id)


async def comando_open_url(pcbot_id: str, url: str, perfil_ids: list = None) -> dict:
    """abre una url en perfiles especificos del pcbot."""
    from orchestrator import crear_comando
    parametros = {
        "url": url,
        "perfil_ids": perfil_ids or [],
    }
    return await crear_comando("open_url", parametros, pcbot_id)


# ---------------------------------------------------------------------------
# obtener info de un pcbot
# ---------------------------------------------------------------------------
def obtener_info_pcbot(pcbot_id: str) -> dict:
    """devuelve la info en memoria de un pcbot conectado."""
    from orchestrator import _pcbot_info
    return _pcbot_info.get(pcbot_id, {})


def listar_pcbots_conectados() -> list:
    """lista todos los pcbots actualmente conectados."""
    from orchestrator import _pcbot_info
    return [
        {
            "pcbot_id": pcbot_id,
            "hostname": info.get("hostname", ""),
            "ip_wan": info.get("ip_wan", ""),
            "perfiles_activos": info.get("perfiles_activos", 0),
            "kbt_acumulados": info.get("kbt_acumulados", 0),
            "ultimo_heartbeat": info.get("ultimo_heartbeat", ""),
            "estado": info.get("estado", "desconocido"),
        }
        for pcbot_id, info in _pcbot_info.items()
    ]


def listar_comandos_pendientes(pcbot_id: str = None) -> list:
    """lista comandos pendientes en la base de datos."""
    if pcbot_id:
        return ejecutar_sql(
            "select * from comandos where pcbot_id = ? and estado = 'pendiente' order by fecha_creacion",
            (pcbot_id,),
        )
    return ejecutar_sql("select * from comandos where estado = 'pendiente' order by fecha_creacion")


# ---------------------------------------------------------------------------
# broadcast a todos los pcbots
# ---------------------------------------------------------------------------
async def broadcast_comando(tipo: str, parametros: dict) -> dict:
    """envia un comando a todos los pcbots conectados."""
    from orchestrator import crear_comando, _conexiones_ws
    resultados = {}
    for pcbot_id in list(_conexiones_ws.keys()):
        resultado = await crear_comando(tipo, parametros, pcbot_id)
        resultados[pcbot_id] = resultado
    return {"exito": True, "resultados": resultados}


# ---------------------------------------------------------------------------
# alias de compatibilidad para server.py
# ---------------------------------------------------------------------------
def _ahora_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


async def procesar_mensaje_ws(pcbot_id: str, mensaje: dict) -> dict:
    """procesa un mensaje recibido via websocket desde un pcbot.
    wrapper de compatibilidad para server.py.
    v2 centralizado: usa procesar_heartbeat_eventos en vez de _procesar_heartbeat."""
    from orchestrator import (
        _conexiones_ws, _pcbot_info, _cola_comandos, _pending_commands,
        _procesar_respuesta, _procesar_alerta, _enviar_pendientes,
    )
    tipo = mensaje.get("tipo", "")

    if tipo == "heartbeat":
        logger.info("[HB-DEBUG] Heartbeat recibido de %s, eventos=%s",
                     pcbot_id, len(mensaje.get("eventos", [])))
        # actualizar heartbeat_cache
        if "perfiles" in mensaje:
            mensaje["perfiles"] = mensaje["perfiles"]
        heartbeat_cache.registrar_heartbeat(pcbot_id, mensaje)
        logger.info("[HB] Heartbeat recibido de %s, procesando eventos", pcbot_id)
        logger.info("[DIAG-ORCH] heartbeat procesado, vigilante llamado: NO se llama (el vigilante corre en bucle independiente desde server.py)")
        # nuevo modelo: eventos -> vigilante -> match
        import procesador_cola
        await procesar_heartbeat_eventos(pcbot_id, mensaje)

        # el vigilante se ejecuta en bucle independiente (desde server.py)
        # ya no se llama bajo demanda aqui para evitar doble ejecucion
        await procesador_cola.ejecutar_ciclo_match()

        await _enviar_pendientes(pcbot_id)
    elif tipo == "respuesta_recargar_perfiles":
        req_id = mensaje.get("comando_id")
        logger.info("[DIAG-005] !Respuesta recargar_perfiles detectada! request_id=%s", req_id)
        logger.info(f"[WS-PEND] req_id={req_id}, presente en _pending_commands? {req_id in _pending_commands}")
        if req_id and req_id in _pending_commands:
            _pending_commands[req_id].set_result(mensaje)
            logger.info("[DIAG-006] Futuro encontrado, resolviendo")
        else:
            logger.warning("[DIAG-007] request_id no encontrado en pendientes")
        return {"tipo": "ack_recargar", "pcbot_id": pcbot_id, "timestamp": _ahora_str()}
    elif tipo == "respuesta":
        await _procesar_respuesta(pcbot_id, mensaje)
    elif tipo == "alerta":
        await _procesar_alerta(pcbot_id, mensaje)
    elif tipo == "info_sistema":
        _pcbot_info[pcbot_id] = {
            "hostname": mensaje.get("hostname", pcbot_id),
            "ip_local": mensaje.get("ip_local", ""),
            "ip_tailscale": mensaje.get("ip_tailscale", ""),
            "ip_wan": mensaje.get("ip_wan", ""),
            "perfiles": mensaje.get("perfiles", []),
            "navegadores": mensaje.get("navegadores", []),
            "ultima_conexion": _ahora_str(),
        }

    return {"tipo": "ack", "pcbot_id": pcbot_id, "timestamp": _ahora_str()}


async def enviar_comando_asignar(usuario_id: int, parametros: dict) -> dict:
    """envia un comando 'asignar' al pcbot del usuario via ws_manager.
    wrapper de alto nivel para api_pedidos."""
    from ws_manager import enviar_comando_al_pcbot
    comando = {
        "tipo": "asignar",
        "parametros": parametros,
        "comando_id": parametros.get("comando_id", ""),
    }
    return await enviar_comando_al_pcbot(usuario_id, comando)


async def enviar_comando_pcbot(usuario_id: int, comando: dict) -> bool:
    """envia un comando al pcbot conectado del usuario."""
    from ws_manager import ws_connections
    conn = ws_connections.get(str(usuario_id))
    if not conn:
        return False
    try:
        ws = conn.get("ws") if isinstance(conn, dict) else conn
        await ws.send_json(comando)
        return True
    except:
        return False


async def procesar_heartbeat_eventos(pcbot_id: str, datos: dict):
    """procesa un heartbeat del nuevo modelo basado solo en eventos.
    v2 centralizado: no recorre perfiles, solo procesa eventos explicitos.
    luego dispara el match de planificacion."""
    from db import ejecutar_sql_unico
    from procesador_cola import ejecutar_ciclo_match

    eventos = datos.get("eventos", [])
    logger.info("[HB-EVENTOS] heartbeat de %s con %s eventos", pcbot_id, len(eventos))

    for evento in eventos:
        try:
            await _procesar_evento_perfil(pcbot_id, evento)
        except Exception as e:
            logger.error("[HB-EVENTOS] error procesando evento %s: %s",
                         evento.get("tipo"), str(e)[:200])

    # reactivar todos los perfiles de este pcbot (soluciona reinicio del servidor)
    ejecutar_sql(
        "update perfiles_roxy set activo = 1 where pcbot_id = ?",
        (pcbot_id,),
    )

    # disparar el match de planificacion justo despues de procesar eventos
    await ejecutar_ciclo_match()


async def _procesar_evento_perfil(pcbot_id: str, evento: dict):
    """procesa un evento individual del heartbeat.
    tipos soportados: perfil_caido, nuevo_perfil, reinicio, liberacion_anticipada"""
    from db import ejecutar_sql, ejecutar_insercion

    tipo = evento.get("tipo", "")
    perfil_id = evento.get("perfil_id", "")
    ahora_str = _ahora_str()

    if tipo == "perfil_caido":
        if not perfil_id:
            logger.warning("[HB-EVENTOS] perfil_caido sin perfil_id en %s", pcbot_id)
            return
        logger.info("[HB-EVENTOS] perfil_caido: %s en pcbot %s", perfil_id, pcbot_id)
        # marcar perfil como inactivo
        ejecutar_sql(
            "update perfiles_roxy set activo = 0, url_actual = null "
            "where hash = ? and pcbot_id = ?",
            (perfil_id, pcbot_id),
        )
        # marcar asignaciones activas como fallidas
        ejecutar_sql(
            "update pedido_asignaciones set estado = 'fallido', fin = ? "
            "where perfil_id = ? and pcbot_id = ? and estado = 'ejecutando'",
            (ahora_str, perfil_id, pcbot_id),
        )

    elif tipo == "nuevo_perfil":
        if not perfil_id:
            logger.warning("[HB-EVENTOS] nuevo_perfil sin perfil_id en %s", pcbot_id)
            return
        logger.info("[HB-EVENTOS] nuevo_perfil: %s en pcbot %s", perfil_id, pcbot_id)
        # verificar si ya existe
        existe = ejecutar_sql_unico(
            "select id from perfiles_roxy where hash = ? and pcbot_id = ?",
            (perfil_id, pcbot_id),
        )
        if not existe:
            nombre = evento.get("nombre", "") or f"perfil_{perfil_id[:8]}"
            ejecutar_insercion(
                """insert into perfiles_roxy
                   (hash, pcbot_id, nombre, activo, ultimo_heartbeat)
                   values (?, ?, ?, 1, ?)""",
                (perfil_id, pcbot_id, nombre, ahora_str),
            )
            logger.info("[HB-EVENTOS] nuevo perfil %s registrado en bd", perfil_id)
        else:
            # ya existe, solo actualizar estado
            ejecutar_sql(
                "update perfiles_roxy set activo = 1, "
                "ultimo_heartbeat = ? where hash = ? and pcbot_id = ?",
                (ahora_str, perfil_id, pcbot_id),
            )

    elif tipo == "reinicio":
        logger.info("[HB-EVENTOS] reinicio en pcbot %s", pcbot_id)
        perfiles_actuales = evento.get("perfiles_actuales", [])
        if perfiles_actuales:
            contador = 0
            for phash in perfiles_actuales:
                existe = ejecutar_sql_unico(
                    "select id from perfiles_roxy where hash = ? and pcbot_id = ?",
                    (phash, pcbot_id),
                )
                if existe:
                    ejecutar_sql(
                        "update perfiles_roxy set activo = 1 where hash = ? and pcbot_id = ?",
                        (phash, pcbot_id),
                    )
                else:
                    nombre = f"perfil_{phash[:8]}"
                    ejecutar_insercion(
                        """insert into perfiles_roxy
                           (hash, pcbot_id, nombre, activo)
                           values (?, ?, ?, 1)""",
                        (phash, pcbot_id, nombre),
                    )
                contador += 1
            logger.info(
                "evento reinicio: %d perfiles activados/insertados en perfiles_roxy para pcbot %s",
                contador, pcbot_id,
            )
        else:
            logger.warning(
                "evento reinicio: sin lista de perfiles_actuales para pcbot %s", pcbot_id,
            )

    elif tipo == "evento_perfil":
        perfil = evento.get("perfil", {})
        pid = perfil.get("profile_id")
        activo = perfil.get("activo", False)
        url = perfil.get("url", "")
        if not pid:
            logger.warning("[HB-EVENTOS] evento_perfil sin profile_id en %s", pcbot_id)
            return
        if activo:
            ejecutar_sql(
                "update perfiles_roxy set url_actual = ?, activo = 1 where hash = ? and pcbot_id = ?",
                (url, pid, pcbot_id),
            )
            logger.info("[DIAG-EVENTO] url_actual actualizada para perfil %s: %s", pid, url)
        else:
            ejecutar_sql(
                "update perfiles_roxy set activo = 0, url_actual = ? where hash = ? and pcbot_id = ?",
                (url, pid, pcbot_id),
            )
            logger.info("[DIAG-EVENTO] perfil %s marcado inactivo, url_actual=%s", pid, url)

    elif tipo == "liberacion_anticipada":
        if not perfil_id:
            logger.warning("[HB-EVENTOS] liberacion_anticipada sin perfil_id en %s", pcbot_id)
            return
        logger.info("[HB-EVENTOS] liberacion_anticipada: %s en pcbot %s", perfil_id, pcbot_id)
        # liberar el perfil antes de lo previsto
        ejecutar_sql(
            "update perfiles_roxy set activo = 0, liberacion_estimada = null "
            "where hash = ? and pcbot_id = ?",
            (perfil_id, pcbot_id),
        )
        # completar la asignacion activa
        ejecutar_sql(
            "update pedido_asignaciones set estado = 'completado', fin = ? "
            "where perfil_id = ? and pcbot_id = ? and estado = 'ejecutando'",
            (ahora_str, perfil_id, pcbot_id),
        )

    else:
        logger.debug("[HB-EVENTOS] tipo de evento desconocido: %s en pcbot %s",
                     tipo, pcbot_id)


async def enviar_recargar_perfiles(pcbot_id: str, roxy_api_key: str) -> dict:
    """envia comando recargar_perfiles a un pcbot especifico."""
    from orchestrator import _conexiones_ws, _cola_comandos, _enviar_a_pcbot
    if pcbot_id not in _conexiones_ws:
        return {"exito": False, "error": "pcbot no conectado", "pcbot_id": pcbot_id}
    comando_id = str(uuid.uuid4())[:12]
    comando = {
        "comando_id": comando_id,
        "tipo": "recargar_perfiles",
        "parametros": {"roxy_api_key": roxy_api_key},
        "pcbot_id": pcbot_id,
        "estado": "pendiente",
    }
    _cola_comandos[comando_id] = comando
    try:
        ok = await _enviar_a_pcbot(pcbot_id, comando)
        return {"exito": ok, "comando_id": comando_id, "pcbot_id": pcbot_id}
    except Exception as e:
        return {"exito": False, "error": str(e), "pcbot_id": pcbot_id}


async def enviar_comando_recargar_perfiles(pcbot_id: str, api_key: str) -> dict:
    """envia comando recargar_perfiles al pcbot y espera respuesta."""
    from orchestrator import _conexiones_ws, _pending_commands
    logger.info("[DIAG-100] Enviando comando a %s", pcbot_id)

    if pcbot_id not in _conexiones_ws:
        return {"ok": False, "error": "pcbot no conectado"}

    conexion = _conexiones_ws[pcbot_id]
    ws = conexion.get("ws") if isinstance(conexion, dict) else conexion
    if not ws:
        return {"ok": False, "error": "websocket no encontrado"}

    request_id = str(uuid.uuid4())
    futuro = asyncio.Future()
    _pending_commands[request_id] = futuro

    logger.info("[DIAG-101] WebSocket obtenido, id=%s", request_id)

    try:
        comando = {
            "tipo": "recargar_perfiles",
            "comando_id": request_id,
            "parametros": {"roxy_api_key": api_key},
        }
        await ws.send_json(comando)
        logger.info(f"[COMANDO] Enviado correctamente a {pcbot_id}, esperando futuro {request_id}")
        logger.info("[DIAG-102] Comando enviado, esperando respuesta...")
        respuesta = await asyncio.wait_for(futuro, timeout=30)
        logger.info("[DIAG-104] Respuesta recibida correctamente")
        return respuesta
    except asyncio.TimeoutError:
        logger.error("[DIAG-103] Timeout despues de 30s")
        return {"ok": False, "error": "timeout esperando respuesta del pcbot"}
    finally:
        logger.info(f"[FINAL] Limpiando futuro {request_id}")
        _pending_commands.pop(request_id, None)