# orchestrator.py - cola de comandos y ws con pcbot. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

import asyncio
import json
import time
import uuid
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
async def crear_comando(tipo: str, parametros: dict, pcbot_id: str = None) -> dict:
    """
    crea un comando en la base de datos y lo encola para envio.
    tipos soportados: asignar, comentarios_activar, detener, estado, open_url.
    """
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

    # intentar enviar inmediatamente si hay conexion activa
    if pcbot_id and pcbot_id in _conexiones_ws:
        try:
            await _enviar_a_pcbot(pcbot_id, comando)
        except Exception as e:
            pass  # se reintentara via heartbeat

    return {"exito": True, "comando_id": comando_id, "estado": "pendiente"}


# ---------------------------------------------------------------------------
# enviar comando a un pcbot via ws
# ---------------------------------------------------------------------------
async def _enviar_a_pcbot(pcbot_id: str, comando: dict) -> bool:
    """envia un comando directamente (json plano) a un pcbot conectado via websocket."""
    ws = _conexiones_ws.get(pcbot_id)
    if not ws:
        return False

    try:
        mensaje = {
            "tipo": "comando",
            "comando_id": comando["comando_id"],
            "accion": comando["tipo"],
            "parametros": comando["parametros"],
        }

        await ws.send_json(mensaje)

        # marcar como enviado en db
        ejecutar_sql(
            "update comandos set estado = 'enviado', fecha_ejecucion = ? where comando_id = ?",
            (_ahora_str(), comando["comando_id"]),
        )
        return True
    except Exception:
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
    _conexiones_ws[pcbot_id] = websocket
    print(f"[orchestrator] pcbot conectado: {pcbot_id}")

    try:
        # handshake inicial
        datos_raw = await asyncio.wait_for(websocket.receive_text(), timeout=10)
        datos = json.loads(datos_raw)

        # soportar mensajes planos (sin envelope {payload, firma})
        # si el mensaje no tiene 'payload', se trata a si mismo como payload
        if "payload" not in datos:
            datos_con_envelope = datos
            datos = {"payload": json.dumps(datos_con_envelope), "firma": ""}
            payload_str = datos["payload"]
            firma_recibida = ""
        else:
            payload_str = datos.get("payload", "")
            firma_recibida = datos.get("firma", "")

        # paso 1: si la firma esta vacia, verificar si es handshake bootstrap (solicitar_secreto)
        if not firma_recibida:
            try:
                payload_temp = json.loads(payload_str)
                es_bootstrap = payload_temp.get("solicitar_secreto", False)
            except (json.JSONDecodeError, TypeError):
                es_bootstrap = False
            if es_bootstrap:
                firma_valida = True
                print(f"[orchestrator] handshake bootstrap aceptado para {pcbot_id}")
            else:
                firma_valida = False
        else:
            firma_valida = verificar_firma(payload_str, firma_recibida, _secreto)
            if not firma_valida:
                # si falla con secreto global, intentar con secreto propio del pcbot (si existe)
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

        info_sistema = json.loads(payload_str)
        _pcbot_info[pcbot_id] = {
            "hostname": info_sistema.get("hostname", pcbot_id),
            "usuario": info_sistema.get("usuario", ""),
            "ip_local": info_sistema.get("ip_local", ""),
            "ip_tailscale": info_sistema.get("ip_tailscale", ""),
            "ip_wan": info_sistema.get("ip_wan", ""),
            "workspace_id": info_sistema.get("workspace_id", ""),
            "perfiles_roxy": info_sistema.get("perfiles_roxy", []),
            "perfiles_vip": info_sistema.get("perfiles_vip", []),
            "perfiles": info_sistema.get("perfiles", []),
            "navegadores": info_sistema.get("navegadores", []),
            "browser_path": info_sistema.get("browser_path", ""),
            "user_data_dir": info_sistema.get("user_data_dir", ""),
            "debugging_port": info_sistema.get("debugging_port", 0),
            "session_exists": info_sistema.get("session_exists", False),
            "modo": info_sistema.get("modo", "desconocido"),
            "version_agente": info_sistema.get("version_agente", ""),
            "ultima_conexion": _ahora_str(),
        }

        # persistir en pcbots_registrados
        try:
            import json as _json
            existente = ejecutar_sql_unico(
                "select id, secreto_shs from pcbots_registrados where pcbot_id = ?", (pcbot_id,)
            )
            perfiles_roxy_json = _json.dumps(info_sistema.get("perfiles_roxy", []), ensure_ascii=False)
            perfiles_vip_json = _json.dumps(info_sistema.get("perfiles_vip", []), ensure_ascii=False)
            navegadores_json = _json.dumps(info_sistema.get("navegadores", []), ensure_ascii=False)

            # --- auto-registro de secreto shs ---
            solicitar_secreto = info_sistema.get("solicitar_secreto", False)
            secreto_asignado = ""
            if solicitar_secreto or (existente and not existente.get("secreto_shs")):
                # generar nuevo secreto para este pcbot
                secreto_asignado = generar_secreto_pcbot()
                print(f"[orchestrator] generando nuevo secreto para {pcbot_id}")
            elif existente and existente.get("secreto_shs"):
                secreto_asignado = existente["secreto_shs"]

            if existente:
                if secreto_asignado:
                    ejecutar_sql(
                        """update pcbots_registrados set
                           hostname = ?, usuario = ?, ip_local = ?, ip_tailscale = ?, ip_wan = ?,
                           workspace_id = ?, perfiles_roxy = ?, perfiles_vip = ?, navegadores = ?,
                           browser_path = ?, user_data_dir = ?, debugging_port = ?,
                           session_exists = ?, modo = ?, version_agente = ?, estado = 'conectado',
                           ultima_conexion = ?, secreto_shs = ?
                           where pcbot_id = ?""",
                        (
                            info_sistema.get("hostname", pcbot_id),
                            info_sistema.get("usuario", ""),
                            info_sistema.get("ip_local", ""),
                            info_sistema.get("ip_tailscale", ""),
                            info_sistema.get("ip_wan", ""),
                            info_sistema.get("workspace_id", ""),
                            perfiles_roxy_json,
                            perfiles_vip_json,
                            navegadores_json,
                            info_sistema.get("browser_path", ""),
                            info_sistema.get("user_data_dir", ""),
                            info_sistema.get("debugging_port", 0),
                            1 if info_sistema.get("session_exists") else 0,
                            info_sistema.get("modo", "desconocido"),
                            info_sistema.get("version_agente", ""),
                            _ahora_str(),
                            secreto_asignado,
                            pcbot_id,
                        ),
                    )
                else:
                    ejecutar_sql(
                        """update pcbots_registrados set
                           hostname = ?, usuario = ?, ip_local = ?, ip_tailscale = ?, ip_wan = ?,
                           workspace_id = ?, perfiles_roxy = ?, perfiles_vip = ?, navegadores = ?,
                           browser_path = ?, user_data_dir = ?, debugging_port = ?,
                           session_exists = ?, modo = ?, version_agente = ?, estado = 'conectado',
                           ultima_conexion = ?
                           where pcbot_id = ?""",
                        (
                            info_sistema.get("hostname", pcbot_id),
                            info_sistema.get("usuario", ""),
                            info_sistema.get("ip_local", ""),
                            info_sistema.get("ip_tailscale", ""),
                            info_sistema.get("ip_wan", ""),
                            info_sistema.get("workspace_id", ""),
                            perfiles_roxy_json,
                            perfiles_vip_json,
                            navegadores_json,
                            info_sistema.get("browser_path", ""),
                            info_sistema.get("user_data_dir", ""),
                            info_sistema.get("debugging_port", 0),
                            1 if info_sistema.get("session_exists") else 0,
                            info_sistema.get("modo", "desconocido"),
                            info_sistema.get("version_agente", ""),
                            _ahora_str(),
                            pcbot_id,
                        ),
                    )
            else:
                if not secreto_asignado:
                    secreto_asignado = generar_secreto_pcbot()
                ejecutar_insercion(
                    """insert into pcbots_registrados
                       (pcbot_id, hostname, usuario, ip_local, ip_tailscale, ip_wan,
                        workspace_id, perfiles_roxy, perfiles_vip, navegadores,
                        browser_path, user_data_dir, debugging_port, session_exists,
                        modo, version_agente, estado, ultima_conexion, secreto_shs)
                       values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'conectado', ?, ?)""",
                    (
                        pcbot_id,
                        info_sistema.get("hostname", pcbot_id),
                        info_sistema.get("usuario", ""),
                        info_sistema.get("ip_local", ""),
                        info_sistema.get("ip_tailscale", ""),
                        info_sistema.get("ip_wan", ""),
                        info_sistema.get("workspace_id", ""),
                        perfiles_roxy_json,
                        perfiles_vip_json,
                        navegadores_json,
                        info_sistema.get("browser_path", ""),
                        info_sistema.get("user_data_dir", ""),
                        info_sistema.get("debugging_port", 0),
                        1 if info_sistema.get("session_exists") else 0,
                        info_sistema.get("modo", "desconocido"),
                        info_sistema.get("version_agente", ""),
                        _ahora_str(),
                        secreto_asignado,
                    ),
                )

            # enviar identify_ok con el secreto shs si se genero nuevo
            if secreto_asignado:
                ts = _ts()
                payload_ok = json.dumps({
                    "tipo": "identify_ok",
                    "secreto_shs": secreto_asignado,
                    "timestamp": ts,
                })
                firma_ok = firmar(payload_ok, _secreto)
                await websocket.send_json({"payload": payload_ok, "firma": firma_ok, "timestamp": ts})
                print(f"[orchestrator] secreto shs enviado a {pcbot_id}")
                # a partir de ahora el pcbot usa su secreto propio
                _secreto_pcbot_actual = secreto_asignado

            # vincular pcbot_id con usuario_id para tabla computadoras
            usuario_info = ejecutar_sql_unico(
                "select id from usuarios where pcbot_id = ?", (pcbot_id,)
            )
            usuario_id_from_pcbot = usuario_info["id"] if usuario_info else None

            # persistir tambien en tabla computadoras (registro automatico)
            try:
                ejecutar_sql(
                    """insert into computadoras (pcbot_id, usuario_id, hostname, ip_local, ip_tailscale, ip_wan,
                       sistema_operativo, estado, ultima_conexion)
                       values (?, ?, ?, ?, ?, ?, ?, 'activa', ?)
                       on conflict(pcbot_id) do update set
                       usuario_id = coalesce(excluded.usuario_id, computadoras.usuario_id),
                       hostname = excluded.hostname,
                       ip_local = excluded.ip_local,
                       ip_tailscale = excluded.ip_tailscale,
                       ip_wan = excluded.ip_wan,
                       sistema_operativo = excluded.sistema_operativo,
                       ultima_conexion = excluded.ultima_conexion""",
                    (
                        pcbot_id,
                        usuario_id_from_pcbot,
                        info_sistema.get("hostname", pcbot_id),
                        info_sistema.get("ip_local", ""),
                        info_sistema.get("ip_tailscale", ""),
                        info_sistema.get("ip_wan", ""),
                        info_sistema.get("sistema_operativo", "Windows"),
                        _ahora_str(),
                    ),
                )
                print(f"[orchestrator] computadora registrada: {pcbot_id}, usuario_id={usuario_id_from_pcbot}")
            except Exception as e:
                print(f"[orchestrator] error al persistir computadoras: {e}")

            # persistir perfiles individuales en tabla perfiles (con usuario_id y pcbot_id)
            for perfil in info_sistema.get("perfiles", []):
                if isinstance(perfil, dict):
                    perfil_id = perfil.get("id", "") or perfil.get("nombre_perfil", "")
                    perfil_nombre = perfil.get("name", "") or perfil.get("nombre_perfil", "") or perfil_id
                    perfil_estado = perfil.get("status", "") or perfil.get("estado", "desconocido")
                    perfil_hash = perfil.get("hash", "")
                    perfil_tipo = perfil.get("tipo", "local")

                    existente_perfil = ejecutar_sql_unico(
                        "select id from perfiles where nombre_perfil = ? and usuario_id = ?",
                        (perfil_nombre, usuario_id_from_pcbot) if usuario_id_from_pcbot else ("select id from perfiles where nombre_perfil = ? and usuario_id is null", perfil_nombre),
                    )
                    if not existente_perfil and not usuario_id_from_pcbot:
                        existente_perfil = ejecutar_sql_unico(
                            "select id from perfiles where nombre_perfil = ? and usuario_id is null",
                            (perfil_nombre,),
                        )
                    if existente_perfil:
                        ejecutar_sql(
                            "update perfiles set estado = ?, ultimo_heartbeat = ?, pcbot_id = ? where id = ?",
                            (perfil_estado, _ahora_str(), pcbot_id, existente_perfil["id"]),
                        )
                    else:
                        ejecutar_insercion(
                            "insert into perfiles (nombre_perfil, tipo, estado, ultimo_heartbeat, usuario_id, pcbot_id) values (?, ?, ?, ?, ?, ?)",
                            (perfil_nombre, perfil_tipo, perfil_estado, _ahora_str(), usuario_id_from_pcbot, pcbot_id),
                        )
        except Exception as _e:
            print(f"[orchestrator] error persistiendo handshake: {_e}")

        # enviar comandos pendientes para este pcbot
        await _enviar_pendientes(pcbot_id)

        # bucle de heartbeats y comandos
        while True:
            try:
                msg_raw = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                msg = json.loads(msg_raw)

                # verificar firma: primero con secreto global, luego con secreto propio del pcbot
                firma_ok = verificar_firma(msg.get("payload", ""), msg.get("firma", ""), _secreto)
                if not firma_ok and _secreto_pcbot_actual:
                    firma_ok = verificar_firma(
                        msg.get("payload", ""),
                        msg.get("firma", ""),
                        _secreto_pcbot_actual,
                    )
                if not firma_ok:
                    continue

                datos = json.loads(msg.get("payload", "{}"))
                tipo = datos.get("tipo", "")

                if tipo == "heartbeat":
                    await _procesar_heartbeat(pcbot_id, datos)
                elif tipo == "respuesta":
                    await _procesar_respuesta(pcbot_id, datos)
                elif tipo == "alerta":
                    await _procesar_alerta(pcbot_id, datos)

            except asyncio.TimeoutError:
                print(f"[orchestrator] timeout de 30s sin mensaje de {pcbot_id}, marcando como inactivo")
                _pcbot_info[pcbot_id]["estado"] = "inactivo"
                # desconectar
                break
            except Exception:
                break

    except asyncio.TimeoutError:
        print(f"[orchestrator] timeout handshake con {pcbot_id}")
    except Exception as e:
        print(f"[orchestrator] error con pcbot {pcbot_id}: {e}")
    finally:
        _conexiones_ws.pop(pcbot_id, None)
        print(f"[orchestrator] pcbot desconectado: {pcbot_id}")


# ---------------------------------------------------------------------------
# enviar comandos pendientes
# ---------------------------------------------------------------------------
async def _enviar_pendientes(pcbot_id: str):
    """envia todos los comandos pendientes para un pcbot especifico."""
    pendientes = ejecutar_sql(
        "select * from comandos where pcbot_id = ? and estado = 'pendiente' order by fecha_creacion",
        (pcbot_id,),
    )
    for cmd in pendientes:
        comando = {
            "comando_id": cmd["comando_id"],
            "tipo": cmd["tipo"],
            "parametros": json.loads(cmd["parametros"]) if cmd["parametros"] else {},
            "estado": cmd["estado"],
        }
        await _enviar_a_pcbot(pcbot_id, comando)


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
    """procesa heartbeat del pcbot: actualiza info y tokens minados."""
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

    # actualizar tabla de perfiles con heartbeat
    for perfil in datos.get("perfiles", []):
        perfil_id = perfil.get("id", "")
        if perfil_id:
            with get_db_context() as conn:
                conn.execute(
                    "update perfiles set horas_conexion = horas_conexion + 0.0333, ultimo_heartbeat = ? where nombre_perfil = ?",
                    (_ahora_str(), perfil_id),
                )
                conn.commit()


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

    if tipo == "heartbeat":
        await _procesar_heartbeat(pcbot_id, mensaje)
        await _enviar_pendientes(pcbot_id)
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

async def enviar_comando_pcbot(usuario_id: int, comando: dict) -> bool:
    """Envía un comando al pcbot conectado del usuario."""
    from ws_manager import ws_connections  # asumimos que existe un dict con clave usuario_id
    conn = ws_connections.get(usuario_id)
    if not conn:
        return False
    try:
        await conn.send_text(json.dumps(comando))
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
    if pcbot_id not in _conexiones_ws:
        return {"ok": False, "error": "pcbot no conectado"}
    ws = _conexiones_ws[pcbot_id]
    request_id = str(uuid.uuid4())
    futuro = asyncio.Future()
    _pending_commands[request_id] = futuro
    try:
        comando = {
            "tipo": "recargar_perfiles",
            "comando_id": request_id,
            "parametros": {"roxy_api_key": api_key},
        }
        await ws.send_json(comando)
        respuesta = await asyncio.wait_for(futuro, timeout=30)
        return respuesta
    except asyncio.TimeoutError:
        return {"ok": False, "error": "timeout esperando respuesta del pcbot"}
    finally:
        _pending_commands.pop(request_id, None)
