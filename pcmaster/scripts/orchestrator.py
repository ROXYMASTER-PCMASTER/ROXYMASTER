# orchestrator.py - cola de comandos y ws con pcbot. roxymaster v8.3
# parte principal del modulo; funciones auxiliares en orchestrator_ext.py
# todos los nombres en minusculas, utf-8 sin bom

import asyncio
import json
import time
import uuid
import logging
logger = logging.getLogger(__name__)
from datetime import datetime

import heartbeat_cache
from comentarios_analizador import procesar_chat
from db import ejecutar_sql, ejecutar_sql_unico, ejecutar_insercion, get_db_context
from shs import firmar_payload, verificar_payload, secreto_bytes as secreto_sistema, generar_secreto_pcbot

# ---------------------------------------------------------------------------
# constantes
# ---------------------------------------------------------------------------
_secreto = secreto_sistema
_reconexion_delay = 5
_heartbeat_interval = 30


def _ahora_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ts() -> str:
    return str(int(time.time()))


# ---------------------------------------------------------------------------
# cola de comandos interna (dict en memoria)
# ---------------------------------------------------------------------------
_cola_comandos: dict = {}  # {comando_id: {tipo, parametros, pcbot_id, futuro}}
_conexiones_ws: dict = {}  # {pcbot_id: websocket}
_pcbot_info: dict = {}  # {pcbot_id: {hostname, ip, perfiles, ...}}
_pending_commands: dict = {}  # {comando_id: asyncio.Future} para esperar respuestas
_secreto_pcbot_actual: str = ""  # secreto shs del pcbot conectado actualmente


# ---------------------------------------------------------------------------
# crear comando y encolarlo
# ---------------------------------------------------------------------------
async def crear_comando(tipo: str, parametros: dict, pcbot_id: str = None, comando_id: str = None) -> dict:
    """
    crea un comando en la base de datos y lo encola para envio.
    tipos soportados: asignar, comentarios_activar, detener, estado, open_url.
    si se proporciona comando_id, se usa ese; si no, se genera uno nuevo.
    """
    if not comando_id:
        comando_id = str(uuid.uuid4())[:12]
    params_json = json.dumps(parametros, ensure_ascii=False)

    cmd_id_db = ejecutar_insercion(
        """insert into comandos (comando_id, tipo, parametros, estado, fecha_creacion, pcbot_id)
           values (?, ?, ?, 'pendiente', ?, ?)""",
        (comando_id, tipo, params_json, _ahora_str(), pcbot_id),
    )

    if not cmd_id_db:
        return {"exito": False, "error": "no se pudo crear el comando en la base de datos"}

    comando = {
        "comando_id": comando_id,
        "tipo": tipo,
        "parametros": parametros,
        "pcbot_id": pcbot_id,
        "estado": "pendiente",
        "fecha_creacion": _ahora_str(),
    }

    _cola_comandos[comando_id] = comando

    logger.info(f"[ORCH-DIAG] crear_comando: comando_id={comando_id} tipo={tipo} pcbot_id='{pcbot_id}' _conexiones_ws keys={list(_conexiones_ws.keys())}")

    # intentar enviar inmediatamente si hay conexion activa
    enviado = False
    if pcbot_id:
        if pcbot_id in _conexiones_ws:
            logger.info(f"[ORCH-DIAG] pcbot_id '{pcbot_id}' encontrado en _conexiones_ws, intentando enviar")
            try:
                ok = await _enviar_a_pcbot(pcbot_id, comando)
                logger.info(f"[ORCH-DIAG] _enviar_a_pcbot resultado={ok}")
                if ok:
                    enviado = True
            except Exception as e:
                logger.warning(f"[ORCH-DIAG] _enviar_a_pcbot exception: {e}")
        else:
            logger.info(f"[ORCH-DIAG] pcbot_id='{pcbot_id}' NO encontrado en _conexiones_ws. keys disponibles: {list(_conexiones_ws.keys())}")

        # fallback 2: intentar via ws_manager (busca el ws fresco por usuario)
        if not enviado:
            try:
                from ws_manager import obtener_ws_por_pcbot
                ws_mgr = obtener_ws_por_pcbot(pcbot_id)
                if ws_mgr and not ws_mgr.closed:
                    logger.info(f"[ORCH-DIAG] pcbot_id '{pcbot_id}' encontrado en ws_manager, intentando enviar directo")
                    mensaje = {
                        "tipo": comando["tipo"],
                        "comando_id": comando["comando_id"],
                        "parametros": comando["parametros"],
                    }
                    await ws_mgr.send_json(mensaje)
                    _conexiones_ws[pcbot_id] = {"ws": ws_mgr, "ultimo_heartbeat": time.time()}
                    ejecutar_sql(
                        "update comandos set estado = 'enviado', fecha_ejecucion = ? where comando_id = ?",
                        (_ahora_str(), comando_id),
                    )
                    enviado = True
                    logger.info(f"[ORCH-DIAG] enviado OK a {pcbot_id} via ws_manager directo en crear_comando")
                else:
                    logger.info(f"[ORCH-DIAG] ws_manager: ws_mgr={'None' if not ws_mgr else 'closed'} para {pcbot_id}")
            except Exception as e:
                logger.warning(f"[ORCH-DIAG] fallback ws_manager en crear_comando exception: {e}")

    return {"exito": True, "comando_id": comando_id, "estado": "enviado" if enviado else "pendiente"}


# ---------------------------------------------------------------------------
# enviar comando a un pcbot via ws
# ---------------------------------------------------------------------------
async def _enviar_a_pcbot(pcbot_id: str, comando: dict) -> bool:
    """envia un comando directamente (json plano) a un pcbot conectado via websocket.
    v2: incluye diagnostico de ws.closed y fallback via ws_manager."""
    conexion = _conexiones_ws.get(pcbot_id)
    if not conexion:
        logger.info(f"[ORCH-DIAG] _enviar_a_pcbot: pcbot_id='{pcbot_id}' NO encontrado en _conexiones_ws")
        return False
    ws = conexion.get("ws") if isinstance(conexion, dict) else conexion
    if not ws:
        logger.info(f"[ORCH-DIAG] _enviar_a_pcbot: websocket es None para {pcbot_id}")
        return False

    try:
        ws_closed = ws.closed if hasattr(ws, 'closed') else 'unknown'
        logger.info(f"[ORCH-DIAG] _enviar_a_pcbot: ws.closed={ws_closed} para {pcbot_id}")
    except Exception as e:
        logger.info(f"[ORCH-DIAG] _enviar_a_pcbot: no se pudo leer ws.closed: {e}")

    mensaje = {
        "tipo": comando["tipo"],
        "comando_id": comando["comando_id"],
        "parametros": comando["parametros"],
    }
    logger.info(f"[ORCH-DIAG] _enviar_a_pcbot: enviando a {pcbot_id} tipo={comando.get('tipo')} comando_id={comando.get('comando_id')}")

    # intento 1: ws directo
    try:
        await ws.send_json(mensaje)
        ejecutar_sql(
            "update comandos set estado = 'enviado', fecha_ejecucion = ? where comando_id = ?",
            (_ahora_str(), comando["comando_id"]),
        )
        logger.info(f"[ORCH-DIAG] _enviar_a_pcbot: enviado OK a {pcbot_id} via ws directo")
        return True
    except Exception as e:
        logger.warning(f"[ORCH-DIAG] _enviar_a_pcbot: EXCEPTION ws directo a {pcbot_id}: {e}")

    # intento 2: fallback via ws_manager
    logger.info(f"[ORCH-DIAG] _enviar_a_pcbot: intentando fallback via ws_manager para {pcbot_id}")
    try:
        from ws_manager import obtener_ws_por_pcbot
        ws_fallback = obtener_ws_por_pcbot(pcbot_id)
        if ws_fallback:
            ws_closed_fb = ws_fallback.closed if hasattr(ws_fallback, 'closed') else 'unknown'
            logger.info(f"[ORCH-DIAG] _enviar_a_pcbot: ws_fallback.closed={ws_closed_fb} para {pcbot_id}")
            if not ws_fallback.closed:
                await ws_fallback.send_json(mensaje)
                _conexiones_ws[pcbot_id] = {"ws": ws_fallback, "ultimo_heartbeat": time.time()}
                ejecutar_sql(
                    "update comandos set estado = 'enviado', fecha_ejecucion = ? where comando_id = ?",
                    (_ahora_str(), comando["comando_id"]),
                )
                logger.info(f"[ORCH-DIAG] _enviar_a_pcbot: enviado OK a {pcbot_id} via ws_manager fallback")
                return True
        else:
            logger.info(f"[ORCH-DIAG] _enviar_a_pcbot: ws_manager no tiene ws para {pcbot_id}")
    except Exception as e2:
        logger.warning(f"[ORCH-DIAG] _enviar_a_pcbot: EXCEPTION fallback ws_manager a {pcbot_id}: {e2}")

    return False


# ---------------------------------------------------------------------------
# manejar conexion websocket de un pcbot
# ---------------------------------------------------------------------------
async def manejar_conexion_pcbot(websocket, pcbot_id: str):
    """
    maneja el ciclo de vida de una conexion ws con un pcbot.
    verifica firma, recibe heartbeats, envia comandos pendientes.
    al desconectar, limpia asignaciones activas de ese pcbot.
    """
    global _secreto_pcbot_actual
    logger.info("[DIAG-001] Nueva conexion de pcbot: %s", pcbot_id)
    _conexiones_ws[pcbot_id] = {"ws": websocket, "ultimo_heartbeat": time.time()}
    logger.info(f"[CONEXION] Nueva conexion de pcbot: {pcbot_id}, estructura guardada: {_conexiones_ws[pcbot_id].keys()}")
    logger.info(f"pcbot conectado via ws: {pcbot_id}")

    try:
        # handshake inicial
        datos_raw = await asyncio.wait_for(websocket.receive_text(), timeout=10)
        datos = json.loads(datos_raw)

        if "payload" not in datos:
            datos_con_envelope = datos
            datos = {"payload": json.dumps(datos_con_envelope), "firma": ""}
            payload_str = datos["payload"]
            firma_recibida = ""
        else:
            payload_str = datos.get("payload", "")
            firma_recibida = datos.get("firma", "")

        if not firma_recibida:
            try:
                payload_temp = json.loads(payload_str)
                es_bootstrap = payload_temp.get("solicitar_secreto", False)
            except (json.JSONDecodeError, TypeError):
                es_bootstrap = False
            if es_bootstrap:
                firma_valida = True
                logger.info(f"handshake bootstrap aceptado para {pcbot_id}")
            else:
                firma_valida = False
        else:
            firma_valida = verificar_firma(payload_str, firma_recibida, _secreto)
            if not firma_valida:
                secreto_pcbot = ejecutar_sql_unico(
                    "select secreto_shs from pcbots_registrados where pcbot_id = ? and secreto_shs != ''",
                    (pcbot_id,),
                )
                if secreto_pcbot:
                    firma_valida = verificar_firma(
                        payload_str,
                        firma_recibida,
                        secreto_pcbot["secreto_shs"],
                    )
                    if firma_valida:
                        _secreto_pcbot_actual = secreto_pcbot["secreto_shs"]

        if not firma_valida:
            await websocket.send_json({"error": "firma invalida"})
            await websocket.close()
            del _conexiones_ws[pcbot_id]
            return

        # actualizar pcbot_id en users si ya existe asociacion en computadoras
        try:
            with get_db_context() as conn:
                row = conn.execute(
                    "SELECT usuario_id FROM computadoras WHERE pcbot_id = ?",
                    (pcbot_id,)
                ).fetchone()
                if row:
                    usuario_id = row[0]
                    conn.execute(
                        "UPDATE usuarios SET pcbot_id = ? WHERE id = ?",
                        (pcbot_id, usuario_id)
                    )
                    conn.commit()
                    logger.info(f"actualizado pcbot_id en users para usuario {usuario_id} a {pcbot_id}")
        except Exception as e:
            logger.warning(f"no se pudo actualizar pcbot_id en users: {e}")

        # ws_manager: registrar conexion post-handshake
        try:
            from ws_manager import registrar_conexion
            _user_row = ejecutar_sql_unico(
                "select id from usuarios where pcbot_id = ?", (pcbot_id,)
            )
            if _user_row:
                registrar_conexion(_user_row["id"], pcbot_id, websocket)
                logger.info(f"[ORCH-DIAG] usuario {_user_row['id']} registrado en ws_manager via orchestrator (handshake)")
        except Exception as e:
            logger.warning(f"[ORCH-DIAG] error registrando ws_manager en orchestrator: {e}")

        # handshake exitoso
        await websocket.send_json({"tipo": "handshake_ok", "pcbot_id": pcbot_id})
        logger.info("[DIAG-002] Handshake completado, entrando al bucle de mensajes")

        # bucle principal de recepcion de mensajes
        while True:
            try:
                logger.info(f"[DEBUG] Ciclo vivo, websocket.closed={websocket.closed}")
                if websocket.closed:
                    logger.warning(f"[DEBUG] websocket cerrado para {pcbot_id}, saliendo del bucle")
                    break
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=120)
                logger.info(f"[DEBUG] Mensaje RAW recibido: {raw[:200]}")
                logger.info(f"[WS-RECV] Mensaje recibido de {pcbot_id}: {raw[:200]}")
                logger.info(f"[WS-STATE] websocket.closed = {websocket.closed}, remote_address = {websocket.remote_address}")
                logger.info("[DIAG-003] Mensaje RECIBIDO (longitud %d): %s", len(raw), raw[:200])
                datos = json.loads(raw)
                logger.info(f"[WS-TIPO] tipo = {datos.get('tipo')}")
                logger.info("[DIAG-004] Tipo de mensaje: %s", datos.get("tipo"))

                if datos.get("tipo") == "respuesta_recargar_perfiles":
                    req_id = datos.get("comando_id")
                    logger.info("[DIAG-005] !Respuesta recargar_perfiles detectada! request_id=%s", req_id)
                    logger.info(f"[WS-PEND] req_id={req_id}, presente en _pending_commands? {req_id in _pending_commands}")
                    if req_id and req_id in _pending_commands:
                        _pending_commands[req_id].set_result(datos)
                        logger.info("[DIAG-006] Futuro encontrado, resolviendo")
                    else:
                        logger.warning("[DIAG-007] request_id no encontrado en pendientes")
                    continue

                if datos.get("tipo") == "heartbeat":
                    _conexiones_ws[pcbot_id]["ultimo_heartbeat"] = time.time()
                    heartbeat_cache.registrar_heartbeat(pcbot_id, datos)
                    import procesador_cola
                    await procesador_cola.ejecutar_ciclo_match()
                    # nuevo modelo centralizado: procesar eventos y disparar match
                    from orchestrator_ext import procesar_heartbeat_eventos
                    await procesar_heartbeat_eventos(pcbot_id, datos)
                    await _enviar_pendientes(pcbot_id)
                    await websocket.send_json({"tipo": "ack"})
                    continue

                if datos.get("tipo") == "chat_capturado":
                    logger.info("[CHAT-DEBUG] ENTRO en el bloque chat_capturado. datos=%s", str(datos)[:300])
                    # recepcion de chat capturado desde el pcbot
                    url = datos.get("url", "")
                    lineas = datos.get("lineas", [])
                    num_lineas = len(lineas) if isinstance(lineas, list) else 0
                    logger.info(
                        "[CHAT-DIAG] chat_capturado recibido de pcbot %s para url '%s' (%d lineas)",
                        pcbot_id, url, num_lineas,
                    )
                    logger.info("[CHAT-DIAG] primeras 3 lineas: %s", lineas[:3] if isinstance(lineas, list) else 'no es lista')
                    try:
                        logger.info("[CHAT-DIAG] llamando a procesar_chat(url='%s', lineas=%d)", url, num_lineas)
                        resultado = await procesar_chat(url, lineas)
                        logger.info("[CHAT-DIAG] procesar_chat resultado: cambio=%s, frases=%d", 
                                     resultado.get('cambio'), len(resultado.get('frases', [])))
                    except ImportError:
                        logger.warning("[CHAT-DIAG] modulo comentarios_analizador no disponible")
                    except Exception as e:
                        logger.error("[CHAT-DIAG] error procesando chat_capturado: %s", str(e)[:500])
                        import traceback
                        logger.error("[CHAT-DIAG] traceback: %s", traceback.format_exc()[:2000])
                    await websocket.send_json({"tipo": "ack_chat"})
                    logger.info("[CHAT-DIAG] ack_chat enviado a pcbot %s", pcbot_id)
                    continue

                logger.debug(f"Mensaje no manejado de {pcbot_id}: {datos.get('tipo')}")

            except asyncio.TimeoutError:
                logger.warning(f"[WS-TIMEOUT] No se recibio ningun mensaje en los ultimos 60 segundos de {pcbot_id}")
                try:
                    await websocket.send_json({"tipo": "ping"})
                except:
                    break
            except websockets.ConnectionClosed:
                break
            except json.JSONDecodeError:
                logger.warning(f"Mensaje json invalido de {pcbot_id}")
                continue

    except asyncio.TimeoutError:
        logger.warning(f"Timeout en handshake de {pcbot_id}")
    except websockets.ConnectionClosed:
        pass
    except Exception as e:
        logger.error(f"Error en conexion con {pcbot_id}: {e}")
    finally:
        # limpiar conexion
        _conexiones_ws.pop(pcbot_id, None)
        # limpiar ws_manager
        try:
            from ws_manager import eliminar_conexion
            eliminar_conexion(pcbot_id=pcbot_id)
        except Exception:
            pass
        # TAREA 2: marcar asignaciones en ejecucion como fallido al desconectarse el pcbot
        try:
            ahora = _ahora_str()
            ejecutar_sql(
                "UPDATE pedido_asignaciones SET estado = 'fallido', fin = ? WHERE pcbot_id = ? AND estado = 'ejecutando'",
                (ahora, pcbot_id)
            )
            logger.info(f"asignaciones ejecutando de {pcbot_id} marcadas como fallido por desconexion")
        except Exception as e:
            logger.warning(f"error limpiando asignaciones de {pcbot_id}: {e}")
        logger.info(f"pcbot desconectado: {pcbot_id}")


# ---------------------------------------------------------------------------
# enviar comandos pendientes
# ---------------------------------------------------------------------------
async def _enviar_pendientes(pcbot_id: str):
    """envia todos los comandos pendientes para un pcbot especifico."""
    pendientes = ejecutar_sql(
        "select * from comandos where pcbot_id = ? and estado = 'pendiente' order by fecha_creacion",
        (pcbot_id,),
    )
    logger.info(f"[ORCH-DIAG] _enviar_pendientes: pcbot_id={pcbot_id} cantidad={len(pendientes)}")
    for cmd in pendientes:
        comando = {
            "comando_id": cmd["comando_id"],
            "tipo": cmd["tipo"],
            "parametros": json.loads(cmd["parametros"]) if cmd["parametros"] else {},
            "estado": cmd["estado"],
        }
        ok = await _enviar_a_pcbot(pcbot_id, comando)
        logger.info(f"[ORCH-DIAG] _enviar_pendientes: reenvio cmd {cmd['comando_id']} ok={ok}")


# ---------------------------------------------------------------------------
# heartbeat de control
# ---------------------------------------------------------------------------
async def _enviar_heartbeat_control(websocket):
    """envia un heartbeat de control al pcbot."""
    try:
        ts = _ts()
        payload = json.dumps({"tipo": "heartbeat_control", "timestamp": ts})
        firma = firmar(payload, _secreto)
        await websocket.send_json({"payload": payload, "firma": firma, "timestamp": ts})
    except Exception:
        pass


# ---------------------------------------------------------------------------
# procesar respuesta del pcbot
# ---------------------------------------------------------------------------
async def _procesar_respuesta(pcbot_id: str, datos: dict):
    """procesa la respuesta de un comando ejecutado por el pcbot."""
    comando_id = datos.get("comando_id", "")
    resultado = datos.get("resultado", "")
    exito = datos.get("exito", False)

    if comando_id:
        ejecutar_sql(
            "update comandos set estado = ?, resultado = ?, fecha_ejecucion = ? where comando_id = ?",
            ("completado" if exito else "fallido", json.dumps(resultado, ensure_ascii=False), _ahora_str(), comando_id),
        )

        try:
            pedido = ejecutar_sql_unico(
                "select id from pedidos where comando_id = ?", (comando_id,)
            )
            if pedido:
                nuevo_estado = "completado" if exito else "fallido"
                ejecutar_sql(
                    "update pedidos set estado = ? where id = ?",
                    (nuevo_estado, pedido["id"]),
                )
                logger.info(f"pedido {pedido['id']} actualizado a {nuevo_estado} via comando {comando_id}")
        except Exception as e:
            logger.warning(f"error actualizando pedido por comando {comando_id}: {e}")

    if comando_id in _pending_commands:
        _pending_commands[comando_id].set_result(datos)

    _cola_comandos.pop(comando_id, None)


# ---------------------------------------------------------------------------
# procesar alerta del pcbot
# ---------------------------------------------------------------------------
async def _procesar_alerta(pcbot_id: str, datos: dict):
    """procesa alertas de seguridad o eventos del pcbot."""
    tipo = datos.get("tipo_alerta", "desconocido")
    detalle = datos.get("detalle", "")
    ip_origen = _pcbot_info.get(pcbot_id, {}).get("ip_wan", "")

    ejecutar_insercion(
        "insert into eventos_seguridad (tipo, pcbot_id, detalle, ip_origen) values (?, ?, ?, ?)",
        (tipo, pcbot_id, detalle, ip_origen),
    )
    print(f"[orchestrator] alerta de {pcbot_id}: {tipo} - {detalle}")


# re-exportar funciones de orchestrator_ext.py para compatibilidad
from orchestrator_ext import (
    listar_pcbots_conectados,
    listar_comandos_pendientes,
    procesar_mensaje_ws,
    comando_asignar,
    comando_comentarios_activar,
    comando_detener,
    comando_estado,
    comando_open_url,
    broadcast_comando,
    enviar_comando_asignar,
    enviar_comando_pcbot,
    enviar_recargar_perfiles,
    enviar_comando_recargar_perfiles,
    obtener_info_pcbot,
)

# alias de compatibilidad exportados
gestor_websockets = _conexiones_ws
cola_comandos = _cola_comandos