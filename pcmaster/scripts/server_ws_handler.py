# server_ws_handler.py - handler de websocket para pcbots. roxymaster v8.3
# extraido de server.py para mantener limite de 400/600 lineas
# todos los nombres en minusculas, utf-8 sin bom

import asyncio
import logging
from datetime import datetime

logger = logging.getLogger("roxymaster.server.ws_handler")


async def manejar_websocket_pcbot(websocket, pcbot_id: str, gestor_websockets: dict):
    """endpoint websocket para comunicacion con pcbots.
    sin hmac. la autenticacion se basa en que la conexion via tailscale
    ya provee cifrado e integridad. se valida que el pcbot_id exista
    y se persiste la informacion en la base de datos."""
    await websocket.accept()
    logger.info(f"pcbot conectado via ws: {pcbot_id}")

    # registrar en gestor legacy
    gestor_websockets[pcbot_id] = {
        "ws": websocket,
        "conectado_desde": datetime.now().isoformat(),
        "ultimo_heartbeat": datetime.now().isoformat(),
    }

    # registrar en ws_manager (nuevo sistema por usuario)
    from ws_manager import registrar_conexion
    _usuario_registrado_ws = None

    # actualizar estado del usuario en db
    try:
        from db import ejecutar_sql
        ejecutar_sql(
            "update usuarios set modo = 'conectado', pcbot_id = ? where pcbot_id = ?",
            (pcbot_id, pcbot_id),
        )
    except Exception:
        pass

    try:
        while True:
            # recibir mensaje del pcbot (json plano, sin firma)
            data = await websocket.receive_json()

            # --- SINCRONIZACION FORZADA: refrescar _conexiones_ws en CADA mensaje ---
            try:
                import orchestrator as _orch_refresh
                if pcbot_id not in _orch_refresh._conexiones_ws:
                    _orch_refresh._conexiones_ws[pcbot_id] = {
                        "ws": websocket,
                        "ultimo_heartbeat": datetime.now().isoformat(),
                    }
                    logger.info(f"[DIAG-SYNC-EACH] _conexiones_ws[{pcbot_id}] poblado por mensaje entrante tipo={data.get('tipo')}")
                else:
                    _orch_refresh._conexiones_ws[pcbot_id]["ws"] = websocket
                    _orch_refresh._conexiones_ws[pcbot_id]["ultimo_heartbeat"] = datetime.now().isoformat()
            except Exception as e:
                logger.warning(f"[DIAG-SYNC-EACH] error refrescando _conexiones_ws: {e}")

            # --- REGISTRO EN WS_MANAGER EN CADA MENSAJE ---
            if _usuario_registrado_ws is None:
                try:
                    from db import ejecutar_sql_unico as _sql_unico
                    _user = _sql_unico(
                        "select id from usuarios where pcbot_id = ?", (pcbot_id,)
                    )
                    if not _user:
                        _conn = _sql_unico(
                            "select usuario_id from computadoras where pcbot_id = ?",
                            (pcbot_id,)
                        )
                        if _conn:
                            _uid = _conn["usuario_id"]
                            from db import ejecutar_sql as _sql_upd
                            _sql_upd(
                                "update usuarios set pcbot_id = ?, modo = 'conectado' where id = ?",
                                (pcbot_id, _uid)
                            )
                            _user = {"id": _uid}
                            logger.info(f"[DIAG-SYNC-WS] usuario {_uid} actualizado con pcbot_id={pcbot_id} via computadoras")
                    if _user:
                        _usuario_registrado_ws = _user["id"]
                        registrar_conexion(_user["id"], pcbot_id, websocket)
                        logger.info(f"[DIAG-SYNC-WS] usuario {_user['id']} registrado en ws_manager via mensaje tipo={data.get('tipo')}")
                    else:
                        logger.warning(f"[DIAG-SYNC-WS] NO SE ENCONTRO usuario para pcbot {pcbot_id}")
                except Exception as e:
                    logger.warning(f"[DIAG-SYNC-WS] error registrando en ws_manager: {e}")

            # persistir datos del pcbot si es identify
            if data.get("tipo") == "identify":
                logger.info(f"identify recibido de {pcbot_id}")
                try:
                    import json as _json
                    from db import ejecutar_sql, ejecutar_insercion, ejecutar_sql_unico
                    info = data
                    perfiles_r = _json.dumps(info.get("perfiles_roxy", []), ensure_ascii=False)
                    perfiles_v = _json.dumps(info.get("perfiles_vip", []), ensure_ascii=False)
                    navs = _json.dumps(info.get("navegadores", []), ensure_ascii=False)

                    existente = ejecutar_sql_unico(
                        "select id from pcbots_registrados where pcbot_id = ?", (pcbot_id,)
                    )

                    if existente:
                        ejecutar_sql(
                            """update pcbots_registrados set hostname=?, usuario=?, ip_local=?, ip_tailscale=?, ip_wan=?,
                               perfiles_roxy=?, perfiles_vip=?, navegadores=?, modo=?, estado='conectado',
                               ultima_conexion=? where pcbot_id=?""",
                            (info.get("pcbot_id", pcbot_id), info.get("usuario", ""),
                             info.get("ip_local", ""), info.get("ip_tailscale", ""),
                             info.get("ip_wan", ""), perfiles_r, perfiles_v, navs,
                             info.get("modo", ""), datetime.now().isoformat(), pcbot_id))
                    else:
                        ejecutar_insercion(
                            """insert into pcbots_registrados
                               (pcbot_id, hostname, usuario, ip_local, ip_tailscale, ip_wan,
                                perfiles_roxy, perfiles_vip, navegadores, modo, estado, ultima_conexion)
                               values (?,?,?,?,?,?,?,?,?,?,'conectado',?)""",
                            (pcbot_id, info.get("pcbot_id", pcbot_id), info.get("usuario", ""),
                             info.get("ip_local", ""), info.get("ip_tailscale", ""),
                             info.get("ip_wan", ""), perfiles_r, perfiles_v, navs,
                             info.get("modo", ""), datetime.now().isoformat()))
                except Exception as e:
                    logger.warning(f"error persistir pcbot {pcbot_id}: {e}")

                # responder identify_ok
                await websocket.send_json({"tipo": "identify_ok", "pcbot_id": pcbot_id})
                logger.info(f"identify_ok enviado a {pcbot_id}")

                # enviar comandos pendientes al pcbot recien conectado
                try:
                    from orchestrator import _enviar_pendientes
                    await _enviar_pendientes(pcbot_id)
                    logger.info(f"comandos pendientes enviados a {pcbot_id}")
                except Exception as e:
                    logger.warning(f"error enviando pendientes a {pcbot_id}: {e}")

                # sincronizar con orchestrator._conexiones_ws
                try:
                    import orchestrator as _orch
                    _orch._conexiones_ws[pcbot_id] = {"ws": websocket, "ultimo_heartbeat": datetime.now().isoformat()}
                    logger.info(f"[DIAG-SYNC] orchestrator._conexiones_ws[{pcbot_id}] poblado. keys={list(_orch._conexiones_ws.keys())}")
                except Exception as e:
                    logger.warning(f"[DIAG-SYNC] error poblando orchestrator._conexiones_ws: {e}")

                # registrar en ws_manager por usuario
                try:
                    from db import ejecutar_sql_unico as _sql_unico
                    _user = _sql_unico(
                        "select id from usuarios where pcbot_id = ?", (pcbot_id,)
                    )
                    if not _user:
                        _conn = _sql_unico(
                            "select usuario_id from computadoras where pcbot_id = ?",
                            (pcbot_id,)
                        )
                        if _conn:
                            _uid = _conn["usuario_id"]
                            from db import ejecutar_sql as _sql_upd
                            _sql_upd(
                                "update usuarios set pcbot_id = ?, modo = 'conectado' where id = ?",
                                (pcbot_id, _uid)
                            )
                            _user = {"id": _uid}
                            logger.info(f"[DIAG-SYNC] usuario {_uid} actualizado con pcbot_id={pcbot_id} via computadoras")
                    if _user:
                        _usuario_registrado_ws = _user["id"]
                        registrar_conexion(_user["id"], pcbot_id, websocket)
                        logger.info(f"[DIAG-SYNC] usuario {_user['id']} registrado en ws_manager via pcbot {pcbot_id}")
                    else:
                        logger.warning(f"[DIAG-SYNC] NO SE ENCONTRO usuario para pcbot {pcbot_id}")
                except Exception as e:
                    logger.warning(f"[DIAG-SYNC] error registrando en ws_manager: {e}")

                # actualizar heartbeat
                gestor_websockets[pcbot_id]["ultimo_heartbeat"] = datetime.now().isoformat()
                continue

            # procesar mensaje normalmente (heartbeat, respuesta, alerta, etc.)
            from orchestrator import procesar_mensaje_ws
            respuesta = await procesar_mensaje_ws(pcbot_id, data)
            if respuesta:
                await websocket.send_json(respuesta)

            # actualizar heartbeat
            gestor_websockets[pcbot_id]["ultimo_heartbeat"] = datetime.now().isoformat()

    except Exception as e:
        logger.error(f"error en ws de {pcbot_id}: {e}")
    finally:
        logger.info(f"pcbot desconectado: {pcbot_id}")
        gestor_websockets.pop(pcbot_id, None)
        # actualizar estado en db
        try:
            from db import ejecutar_sql
            ejecutar_sql(
                "update usuarios set modo = 'desconectado' where pcbot_id = ?",
                (pcbot_id,),
            )
        except Exception:
            pass
        # limpiar ws_manager
        try:
            from ws_manager import eliminar_conexion
            eliminar_conexion(pcbot_id=pcbot_id)
        except Exception:
            pass