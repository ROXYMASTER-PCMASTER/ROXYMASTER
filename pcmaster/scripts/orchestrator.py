# orchestrator.py - cola de comandos y ws con pcbot. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

import asyncio
import json
import time
import uuid
import logging
logger = logging.getLogger(__name__)
from datetime import datetime

from db import ejecutar_sql, ejecutar_sql_unico, ejecutar_insercion, get_db_context
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
        # reconstruir mensaje como si fuera un payload firmado
        ts = str(payload_dict.get("timestamp", ""))
        if not ts:
            return False
        _s = str(secreto) if secreto else ""
        # crear dict temporal con timestamp+signature para verificar_payload
        payload_con_firma = dict(payload_dict)
        payload_con_firma["signature"] = firma_esperada
        return verificar_payload(payload_con_firma, secreto_override=_s)
    except Exception:
        return False
_reconexion_delay = 5  # segundos entre reintentos
_heartbeat_interval = 30  # segundos


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
    if pcbot_id and pcbot_id in _conexiones_ws:
        logger.info(f"[ORCH-DIAG] pcbot_id '{pcbot_id}' encontrado en _conexiones_ws, intentando enviar")
        try:
            ok = await _enviar_a_pcbot(pcbot_id, comando)
            logger.info(f"[ORCH-DIAG] _enviar_a_pcbot resultado={ok}")
        except Exception as e:
            logger.warning(f"[ORCH-DIAG] _enviar_a_pcbot exception: {e}")
    else:
        logger.info(f"[ORCH-DIAG] pcbot_id='{pcbot_id}' NO encontrado en _conexiones_ws. keys disponibles: {list(_conexiones_ws.keys())}")

    return {"exito": True, "comando_id": comando_id, "estado": "pendiente"}


# ---------------------------------------------------------------------------
# enviar comando a un pcbot via ws
# ---------------------------------------------------------------------------
async def _enviar_a_pcbot(pcbot_id: str, comando: dict) -> bool:
    """envia un comando directamente (json plano) a un pcbot conectado via websocket."""
    conexion = _conexiones_ws.get(pcbot_id)
    if not conexion:
        return False
    ws = conexion.get("ws") if isinstance(conexion, dict) else conexion
    if not ws:
        return False
    try:
        mensaje = {
            "tipo": comando["tipo"],
            "comando_id": comando["comando_id"],
            "parametros": comando["parametros"],
        }
        logger.info(f"[ORCH-DIAG] _enviar_a_pcbot: enviando a {pcbot_id} tipo={comando.get('tipo')} comando_id={comando.get('comando_id')}")
        await ws.send_json(mensaje)
        # marcar como enviado en db
        ejecutar_sql(
            "update comandos set estado = 'enviado', fecha_ejecucion = ? where comando_id = ?",
            (_ahora_str(), comando["comando_id"]),
        )
        logger.info(f"[ORCH-DIAG] _enviar_a_pcbot: enviado OK a {pcbot_id}")
        return True
    except Exception as e:
        logger.warning(f"[ORCH-DIAG] _enviar_a_pcbot: EXCEPTION a {pcbot_id}: {e}")
        return False


# ---------------------------------------------------------------------------
# manejar conexion websocket de un pcbot
# ---------------------------------------------------------------------------
async def manejar_conexion_pcbot(websocket, pcbot_id: str):
    """
    maneja el ciclo de vida de una conexion ws con un pcbot.
    verifica firma, recibe heartbeats, envia comandos pendientes.
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

        # soportar mensajes planos (sin envelope {payload, firma})
        if "payload" not in datos:
            datos_con_envelope = datos
            datos = {"payload": json.dumps(datos_con_envelope), "firma": ""}
            payload_str = datos["payload"]
            firma_recibida = ""
        else:
            payload_str = datos.get("payload", "")
            firma_recibida = datos.get("firma", "")

        # verificar firma (handshake)
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

        # actualizar automaticamente el pcbot_id en la tabla users si ya existe asociacion en computadoras
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

        # Handshake exitoso
        await websocket.send_json({"tipo": "handshake_ok", "pcbot_id": pcbot_id})
        logger.info("[DIAG-002] Handshake completado, entrando al bucle de mensajes")

        # Bucle principal de recepción de mensajes
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

                # --- Manejo de respuestas de comandos ---
                if datos.get("tipo") == "respuesta_recargar_perfiles":
                    req_id = datos.get("comando_id")
                    logger.info("[DIAG-005] !Respuesta recargar_perfiles detectada! request_id=%s", req_id)
                    logger.info(f"[WS-PEND] req_id={req_id}, presente en _pending_commands? {req_id in _pending_commands}")
                    if req_id and req_id in _pending_commands:
                        _pending_commands[req_id].set_result(datos)
                        logger.info("[DIAG-006] Futuro encontrado, resolviendo")
                    else:
                        logger.warning("[DIAG-007] request_id no encontrado en pendientes")
                    continue  # no procesar como otro tipo de mensaje

                if datos.get("tipo") == "heartbeat":
                    # actualizar heartbeat
                    _conexiones_ws[pcbot_id]["ultimo_heartbeat"] = time.time()
                    await websocket.send_json({"tipo": "ack"})
                    continue

                # Otros comandos (asignar, detener, etc.) se manejarían aquí
                # Por ahora solo logueamos
                logger.debug(f"Mensaje no manejado de {pcbot_id}: {datos.get('tipo')}")

            except asyncio.TimeoutError:
                logger.warning(f"[WS-TIMEOUT] No se recibio ningun mensaje en los ultimos 60 segundos de {pcbot_id}")
                # Timeout en recepción, enviar heartbeat de control para verificar conexión
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
        # Limpiar conexión
        _conexiones_ws.pop(pcbot_id, None)
        # limpiar ws_manager
        try:
            from ws_manager import eliminar_conexion
            eliminar_conexion(pcbot_id=pcbot_id)
        except Exception:
            pass
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
# procesar heartbeat del pcbot
# ---------------------------------------------------------------------------
async def _procesar_heartbeat(pcbot_id: str, datos: dict):
    """procesa heartbeat del pcbot: actualiza info, perfiles y tokens minados."""
    _pcbot_info[pcbot_id] = _pcbot_info.get(pcbot_id, {})
    _pcbot_info[pcbot_id]["ultimo_heartbeat"] = _ahora_str()
    _pcbot_info[pcbot_id]["uptime_segundos"] = datos.get("uptime", 0)
    _pcbot_info[pcbot_id]["kbt_acumulados"] = datos.get("kbt_acumulados", 0)
    _pcbot_info[pcbot_id]["perfiles_activos"] = datos.get("perfiles_activos", 0)
    _pcbot_info[pcbot_id]["estado"] = datos.get("estado", "conectado")

    # persistir heartbeat en pcbots_registrados
    try:
        kbt = datos.get("kbt_acumulados", 0)
        perfiles_act = datos.get("perfiles_activos", 0)
        uptime = datos.get("uptime", 0)
        ejecutar_sql(
            """update pcbots_registrados set
               kbt_acumulados = ?, perfiles_activos = ?, uptime_segundos = ?,
               ultimo_heartbeat = ?, estado = ?
               where pcbot_id = ?""",
            (kbt, perfiles_act, uptime, _ahora_str(), datos.get("estado", "conectado"), pcbot_id),
        )
    except Exception as _he:
        print(f"[orchestrator] error persistiendo heartbeat: {_he}")

    # actualizar tabla perfiles_roxy con heartbeat y estado de perfiles
    # el pcbot envia "perfiles": [{"profile_id": ..., "activo": bool, "tiempo_conectado_seg": ...}]
    for perfil in datos.get("perfiles", []):
        perfil_id = perfil.get("profile_id", perfil.get("id", ""))
        activo = perfil.get("activo", 1)
        tiempo_seg = perfil.get("tiempo_conectado_seg", 0)
        if perfil_id:
            try:
                # verificar si existe en perfiles_roxy
                existente = ejecutar_sql_unico(
                    "select id from perfiles_roxy where id = ?", (perfil_id,)
                )
                if existente:
                    with get_db_context() as conn:
                        conn.execute(
                            """update perfiles_roxy set activo = ?, tiempo_activo_seg = ?,
                               ultimo_heartbeat = ?, pcbot_id = ? where id = ?""",
                            (1 if activo else 0, tiempo_seg, _ahora_str(), pcbot_id, perfil_id),
                        )
                        conn.commit()
                else:
                    # insertar perfil si aun no existe (asociar a usuario del pcbot)
                    usuario_id = _pcbot_info.get(pcbot_id, {}).get("usuario_id")
                    if not usuario_id:
                        user_row = ejecutar_sql_unico(
                            "select id from usuarios where pcbot_id = ? limit 1", (pcbot_id,)
                        )
                        usuario_id = user_row["id"] if user_row else None
                    if usuario_id:
                        with get_db_context() as conn:
                            conn.execute(
                                """insert or ignore into perfiles_roxy
                                   (id, usuario_id, nombre, activo, tiempo_activo_seg,
                                    ultimo_heartbeat, pcbot_id, creado_en)
                                   values (?, ?, ?, ?, ?, ?, ?, ?)""",
                                (perfil_id, usuario_id, f"perfil_{perfil_id}",
                                 1 if activo else 0, tiempo_seg,
                                 _ahora_str(), pcbot_id, _ahora_str()),
                            )
                            conn.commit()
            except Exception as e:
                logger.warning(f"error actualizando perfil {perfil_id}: {e}")

    # si no se enviaron perfiles, marcar los de este pcbot como inactivos
    if not datos.get("perfiles"):
        try:
            ejecutar_sql(
                "update perfiles_roxy set activo = 0 where pcbot_id = ? and ultimo_heartbeat < ?",
                (pcbot_id, (datetime.now().timestamp() - 180)),  # 3 min sin heartbeat = inactivo
            )
        except Exception as e:
            logger.warning(f"error marcando perfiles inactivos: {e}")


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

        # actualizar pedidos si el comando esta asociado a uno
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

    # resolver futuros pendientes para respuestas de recargar_perfiles
    if comando_id in _pending_commands:
        _pending_commands[comando_id].set_result(datos)

    # limpiar de cola si estaba
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
    # buscar url en db
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
    ejecutar_sql(
        "update urls_asignadas set estado = 'detenida', fecha_fin = ? where url = ? and pcbot_id = ?",
        (_ahora_str(), url, pcbot_id),
    )
    return await crear_comando("detener", {"url": url}, pcbot_id)


async def comando_estado(pcbot_id: str) -> dict:
    """solicita el estado actual del pcbot."""
    return await crear_comando("estado", {}, pcbot_id)


async def comando_open_url(pcbot_id: str, url: str, perfil_ids: list = None) -> dict:
    """abre una url en perfiles especificos del pcbot."""
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
    return _pcbot_info.get(pcbot_id, {})


def listar_pcbots_conectados() -> list:
    """lista todos los pcbots actualmente conectados."""
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
    resultados = {}
    for pcbot_id in list(_conexiones_ws.keys()):
        resultado = await crear_comando(tipo, parametros, pcbot_id)
        resultados[pcbot_id] = resultado
    return {"exito": True, "resultados": resultados}


# ---------------------------------------------------------------------------
# alias de compatibilidad para server.py
# ---------------------------------------------------------------------------
gestor_websockets = _conexiones_ws
cola_comandos = _cola_comandos


async def procesar_mensaje_ws(pcbot_id: str, mensaje: dict) -> dict:
    """procesa un mensaje recibido via websocket desde un pcbot.
    wrapper de compatibilidad para server.py."""
    tipo = mensaje.get("tipo", "")

    # DIAGNOSTICO: log de heartbeats
    if tipo == "heartbeat":
        logger.info("[HB-DEBUG] Heartbeat recibido de %s, datos=%s", pcbot_id, str(mensaje)[:150])
        logger.info("[HB] Heartbeat recibido de %s, enviando ack", pcbot_id)
        await _procesar_heartbeat(pcbot_id, mensaje)
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
    wrapper de alto nivel para api_pedidos.
    estructura: {"tipo": "asignar", "parametros": {...}}"""
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


async def enviar_recargar_perfiles(pcbot_id: str, roxy_api_key: str) -> dict:
    """envia comando recargar_perfiles a un pcbot especifico.
    devuelve dict con exito y comando_id si se pudo enviar."""
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
