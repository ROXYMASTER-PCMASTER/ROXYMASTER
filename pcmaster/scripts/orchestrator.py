import asyncio, time, json, logging, sqlite3, os
from datetime import datetime
from config import DATA_DIR

DB_PATH = os.path.join(DATA_DIR, "roxymaster.db")
logger = logging.getLogger("orchestrator")

# estado interno
grupos = {}  # url -> {perfiles, inicio, duracion, comentarios, streamer, pcbot_id}
ws_server_ref = None
comandos_db = []  # historial en memoria
pendientes_db = {}

# referencias a objetos globales del servidor (lazy)
_pcbots = {}
_perfiles_map = {}
_enviar_fn = None

def _get_ws_state():
    """obtiene referencias a los objetos globales del servidor ws."""
    global _pcbots, _perfiles_map, _enviar_fn
    try:
        from ws_handler import pcbots, perfiles_map, enviar as _env
        _pcbots = pcbots
        _perfiles_map = perfiles_map
        _enviar_fn = _env
    except ImportError:
        try:
            from server import pcbots, perfiles_map, enviar as _env
            _pcbots = pcbots
            _perfiles_map = perfiles_map
            _enviar_fn = _env
        except ImportError:
            logger.warning("no se pudo importar ws_handler ni server para ws state")

def init_orchestrator_db():
    """inicializa las tablas del orquestador."""
    conn = sqlite3.connect(DB_PATH)
    conn.executescript('''
        create table if not exists comandos (
            id integer primary key autoincrement,
            comando_id text unique not null,
            tipo text not null,
            parametros text,
            estado text default 'pendiente',
            fecha_creacion text default (datetime('now','localtime')),
            fecha_ejecucion text,
            resultado text,
            streamer text,
            pcbot_id text
        );
        create table if not exists urls_asignadas (
            id integer primary key autoincrement,
            url text not null,
            streamer text,
            perfiles_asignados integer default 0,
            duracion_min integer default 60,
            comentarios_activos integer default 0,
            estado text default 'activa',
            fecha_asignacion text default (datetime('now','localtime')),
            fecha_fin text,
            pcbot_id text
        );
        create table if not exists sesiones_activas (
            id integer primary key autoincrement,
            perfil_id text not null,
            url text,
            streamer text,
            estado text default 'activo',
            inicio text default (datetime('now','localtime')),
            fin text
        );
    ''')
    conn.commit()
    conn.close()

def set_ws_server(server):
    global ws_server_ref
    ws_server_ref = server

async def enviar_comando(pcbot_id, tipo, datos):
    """envia un comando a un pcbot especifico."""
    _get_ws_state()
    if pcbot_id in _pcbots:
        try:
            msg = json.dumps({"type": tipo, "data": datos})
            await _pcbots[pcbot_id].send(msg)
            return {"ok": True}
        except Exception as e:
            logger.error(f"error enviando comando a {pcbot_id}: {e}")
            return {"ok": False, "error": str(e)}
    return {"ok": False, "error": "pcbot no conectado"}

async def broadcast_comando(tipo, datos):
    """envia un comando a todos los pcbots conectados."""
    _get_ws_state()
    resultados = {}
    for pid in list(_pcbots.keys()):
        try:
            msg = json.dumps({"type": tipo, "data": datos})
            await _pcbots[pid].send(msg)
            resultados[pid] = "enviado"
        except Exception as e:
            resultados[pid] = f"error: {e}"
    return {"ok": True, "resultados": resultados}

async def asignar_url(url, streamer, perfiles=1, duracion=60, comentarios=False, pcbot_id=None):
    """asigna una url para ser vista por perfiles."""
    import secrets
    comando_id = secrets.token_hex(8)

    # buscar perfiles libres
    _get_ws_state()
    libres = [k for k, v in _perfiles_map.items() if v.get("estado", "desconocido") != "activo"]
    if pcbot_id:
        libres = [k for k in libres if _perfiles_map[k].get("pcbot") == pcbot_id]
    seleccionados = libres[:perfiles]

    if not seleccionados:
        return {"ok": False, "error": "no hay perfiles libres disponibles"}

    # crear grupo
    grupos[url] = {
        "perfiles": seleccionados,
        "inicio": time.time(),
        "duracion": duracion * 60,
        "comentarios": comentarios,
        "streamer": streamer,
        "pcbot_id": pcbot_id,
        "comando_id": comando_id,
    }

    # guardar en db
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "insert into comandos (comando_id, tipo, parametros, estado, streamer, pcbot_id) values (?,?,?,?,?,?)",
        (comando_id, "asignar_url", json.dumps({"url": url, "perfiles": len(seleccionados), "duracion": duracion, "comentarios": comentarios}),
         "ejecutado", streamer, pcbot_id)
    )
    conn.execute(
        "insert into urls_asignadas (url, streamer, perfiles_asignados, duracion_min, comentarios_activos, estado, pcbot_id) values (?,?,?,?,?,?,?)",
        (url, streamer, len(seleccionados), duracion, 1 if comentarios else 0, "activa", pcbot_id)
    )
    conn.commit()
    conn.close()

    # enviar a pcbots
    for key in seleccionados:
        info = _perfiles_map[key]
        await enviar(info["pcbot"], "open_url", {"url": url, "profile": info["name"], "dirId": info.get("dirId", "")})
        await asyncio.sleep(1)

    return {"ok": True, "asignados": len(seleccionados), "url": url, "duracion": duracion, "comando_id": comando_id}

async def activar_comentarios(url, streamer=None, nivel=1):
    """activa comentarios en una url asignada."""
    if url in grupos:
        grupos[url]["comentarios"] = True
        # guardar en db
        conn = sqlite3.connect(DB_PATH)
        conn.execute("update urls_asignadas set comentarios_activos=1 where url=? and estado='activa'", (url,))
        conn.commit()
        conn.close()
        return {"ok": True, "mensaje": f"comentarios activados para {url}"}
    return {"ok": False, "error": f"url no encontrada: {url}"}

async def detener_url(url, pcbot_id=None):
    """detiene una url asignada y libera los perfiles."""
    if url in grupos:
        grupo = grupos.pop(url)
        # actualizar db
        conn = sqlite3.connect(DB_PATH)
        conn.execute("update urls_asignadas set estado='finalizada', fecha_fin=datetime('now','localtime') where url=? and estado='activa'", (url,))
        conn.commit()
        conn.close()
        return {"ok": True, "mensaje": f"url {url} detenida, {len(grupo['perfiles'])} perfiles liberados"}
    return {"ok": False, "error": f"url no encontrada: {url}"}

def cancelar_comando(comando_id):
    """cancela un comando pendiente."""
    if comando_id in pendientes_db:
        pendientes_db.pop(comando_id)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("update comandos set estado='cancelado' where comando_id=?", (comando_id,))
    cambios = conn.total_changes
    conn.commit()
    conn.close()
    if cambios == 0:
        return {"ok": False, "error": "comando no encontrado"}
    return {"ok": True, "mensaje": "comando cancelado"}

def obtener_comandos_pendientes():
    """obtiene comandos pendientes de ejecucion."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("select * from comandos where estado='pendiente' order by fecha_creacion desc").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def obtener_historial_comandos(limite=50):
    """obtiene el historial de comandos ejecutados."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("select * from comandos order by fecha_creacion desc limit ?", (limite,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def obtener_urls_asignadas(estado=None):
    """obtiene urls asignadas activas o todas."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if estado:
        rows = conn.execute("select * from urls_asignadas where estado=? order by fecha_asignacion desc", (estado,)).fetchall()
    else:
        rows = conn.execute("select * from urls_asignadas order by fecha_asignacion desc").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def obtener_sesiones_activas():
    """obtiene sesiones activas de perfiles."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("select * from sesiones_activas where estado='activo' order by inicio desc").fetchall()
    conn.close()
    return [dict(r) for r in rows]

async def procesar_respuesta_comando(comando_id, resultado):
    """procesa la respuesta de un comando enviado a pcbot."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "update comandos set estado='completado', fecha_ejecucion=datetime('now','localtime'), resultado=? where comando_id=?",
        (json.dumps(resultado) if isinstance(resultado, dict) else str(resultado), comando_id)
    )
    conn.commit()
    conn.close()
    if comando_id in pendientes_db:
        pendientes_db.pop(comando_id)
    logger.info(f"comando {comando_id} completado: {resultado}")


# ==================== parser de comandos por texto ====================

async def parsear_y_ejecutar(texto_comando):
    """parsea un comando en texto natural y lo ejecuta.
    formatos soportados:
    - asignar <cantidad> url <url> duracion <minutos> [pcbot <pcbot_id>] [streamer <nombre>]
    - detener url <url>
    - comentarios_activar url <url> nivel <nivel>
    - comentarios_desactivar url <url>
    - estado
    """
    txt = texto_comando.strip().lower()
    partes = txt.split()

    if not partes:
        return {"ok": False, "error": "comando vacio"}

    accion = partes[0]

    if accion == "asignar":
        try:
            idx_url = partes.index("url") if "url" in partes else -1
            idx_dur = partes.index("duracion") if "duracion" in partes else -1
            idx_pcbot = partes.index("pcbot") if "pcbot" in partes else -1
            idx_streamer = partes.index("streamer") if "streamer" in partes else -1

            cant = int(partes[1]) if len(partes) > 1 else 1
            url = partes[idx_url + 1] if idx_url >= 0 and idx_url + 1 < len(partes) else ""
            dur = int(partes[idx_dur + 1]) if idx_dur >= 0 and idx_dur + 1 < len(partes) else 60
            pcbot_id = partes[idx_pcbot + 1] if idx_pcbot >= 0 and idx_pcbot + 1 < len(partes) else None
            streamer = partes[idx_streamer + 1] if idx_streamer >= 0 and idx_streamer + 1 < len(partes) else "sistema"

            if not url:
                return {"ok": False, "error": "url requerida. formato: asignar <cant> url <url> duracion <min>"}

            return await asignar_url(url=url, streamer=streamer, perfiles=cant, duracion=dur, pcbot_id=pcbot_id)
        except (ValueError, IndexError) as e:
            return {"ok": False, "error": f"formato invalido: {e}. usar: asignar <cant> url <url> duracion <min>"}

    elif accion == "detener":
        try:
            idx_url = partes.index("url") if "url" in partes else -1
            url = partes[idx_url + 1] if idx_url >= 0 and idx_url + 1 < len(partes) else ""
            if not url:
                return {"ok": False, "error": "url requerida. formato: detener url <url>"}
            return await detener_url(url)
        except (ValueError, IndexError) as e:
            return {"ok": False, "error": f"formato invalido: {e}. usar: detener url <url>"}

    elif accion == "comentarios_activar":
        try:
            idx_url = partes.index("url") if "url" in partes else -1
            idx_nivel = partes.index("nivel") if "nivel" in partes else -1
            url = partes[idx_url + 1] if idx_url >= 0 and idx_url + 1 < len(partes) else ""
            nivel = int(partes[idx_nivel + 1]) if idx_nivel >= 0 and idx_nivel + 1 < len(partes) else 1
            if not url:
                return {"ok": False, "error": "url requerida. formato: comentarios_activar url <url> nivel <n>"}
            return await activar_comentarios(url, nivel=nivel)
        except (ValueError, IndexError) as e:
            return {"ok": False, "error": f"formato invalido: {e}"}

    elif accion == "comentarios_desactivar":
        try:
            idx_url = partes.index("url") if "url" in partes else -1
            url = partes[idx_url + 1] if idx_url >= 0 and idx_url + 1 < len(partes) else ""
            if not url:
                return {"ok": False, "error": "url requerida. formato: comentarios_desactivar url <url>"}
            if url in grupos:
                grupos[url]["comentarios"] = False
                return {"ok": True, "mensaje": f"comentarios desactivados para {url}"}
            return {"ok": False, "error": f"url no encontrada: {url}"}
        except (ValueError, IndexError) as e:
            return {"ok": False, "error": f"formato invalido: {e}"}

    elif accion == "estado":
        return {
            "ok": True,
            "grupos_activos": len(grupos),
            "perfiles_totales": len(_perfiles_map),
            "pcbots_conectados": len(_pcbots),
            "detalle_grupos": {url: {"perfiles": g["perfiles"], "duracion_restante": max(0, g["duracion"] - (time.time() - g["inicio"]))} for url, g in grupos.items()}
        }

    else:
        return {"ok": False, "error": f"accion desconocida: {accion}. comandos validos: asignar, detener, comentarios_activar, comentarios_desactivar, estado"}


# ==================== clases para api_endpoints.py ====================

class OrchestratorManager:
    def __init__(self):
        init_orchestrator_db()

    async def parsear_comando(self, texto):
        return await parsear_y_ejecutar(texto)

    def estado_actual(self):
        _get_ws_state()
        return {
            "pcbots": len(_pcbots),
            "perfiles": len(_perfiles_map),
            "grupos": len(grupos),
            "perfiles_lista": [{"key": k, "pcbot": v.get("pcbot"), "name": v.get("name"), "dirId": v.get("dirId")} for k, v in _perfiles_map.items()],
            "grupos_detalle": {url: {"perfiles": g["perfiles"], "streamer": g.get("streamer", ""), "duracion": g.get("duracion", 0), "comentarios": g.get("comentarios", False)} for url, g in grupos.items()}
        }