# orchestrator.py - cola de comandos y ws con pcbot. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

import asyncio
import json
import time
import uuid
from datetime import datetime

from db import ejecutar_sql, ejecutar_sql_unico, ejecutar_insercion, get_db_context
from shs import firmar, verificar_firma, secreto_sistema


# ---------------------------------------------------------------------------
# constantes
# ---------------------------------------------------------------------------
_secreto = secreto_sistema
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
    """envia un comando firmado a un pcbot conectado via websocket."""
    ws = _conexiones_ws.get(pcbot_id)
    if not ws:
        return False

    try:
        ts = _ts()
        payload = {
            "tipo": "comando",
            "comando_id": comando["comando_id"],
            "accion": comando["tipo"],
            "parametros": comando["parametros"],
            "timestamp": ts,
        }
        payload_json = json.dumps(payload, ensure_ascii=False)
        firma = firmar(payload_json, _secreto)

        mensaje = {
            "payload": payload_json,
            "firma": firma,
            "timestamp": ts,
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
    _conexiones_ws[pcbot_id] = websocket
    print(f"[orchestrator] pcbot conectado: {pcbot_id}")

    try:
        # handshake inicial
        datos_raw = await asyncio.wait_for(websocket.receive_text(), timeout=10)
        datos = json.loads(datos_raw)

        # verificar firma
        if not verificar_firma(datos.get("payload", ""), datos.get("firma", ""), _secreto):
            await websocket.send_json({"error": "firma invalida"})
            await websocket.close()
            del _conexiones_ws[pcbot_id]
            return

        info_sistema = json.loads(datos.get("payload", "{}"))
        _pcbot_info[pcbot_id] = {
            "hostname": info_sistema.get("hostname", pcbot_id),
            "ip_local": info_sistema.get("ip_local", ""),
            "ip_tailscale": info_sistema.get("ip_tailscale", ""),
            "ip_wan": info_sistema.get("ip_wan", ""),
            "perfiles": info_sistema.get("perfiles", []),
            "navegadores": info_sistema.get("navegadores", []),
            "ultima_conexion": _ahora_str(),
        }

        # enviar comandos pendientes para este pcbot
        await _enviar_pendientes(pcbot_id)

        # bucle de heartbeats y comandos
        while True:
            try:
                msg_raw = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                msg = json.loads(msg_raw)

                if not verificar_firma(msg.get("payload", ""), msg.get("firma", ""), _secreto):
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
