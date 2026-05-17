# heartbeat_cache.py - cache minimo de ultimo heartbeat y eventos. roxymaster v8.3
# en el nuevo modelo centralizado, el heartbeat solo transporta eventos.
# este modulo almacena timestamp y eventos para diagnostico.
# utf-8 sin bom, nombres en minusculas

import logging
from datetime import datetime

logger = logging.getLogger("roxymaster.heartbeat_cache")

# cache: {pcbot_id: {"ultimo_hb": str, "eventos": list, "recibido_en": str}}
_cache: dict = {}


def registrar_heartbeat(pcbot_id: str, datos: dict) -> None:
    """almacena el timestamp, eventos y perfiles del ultimo heartbeat de un pcbot.
    en el nuevo modelo, datos["eventos"] es una lista de eventos explicitos
    y datos["perfiles"] es un dict con el estado actual de los perfiles."""
    if not pcbot_id or not datos:
        return

    eventos = datos.get("eventos", [])
    entry = _cache.get(pcbot_id, {})
    entry["ultimo_hb"] = datetime.now().isoformat()
    if "perfiles" in datos:
        entry["perfiles"] = datos["perfiles"]
    entry["recibido_en"] = datetime.now().isoformat()
    entry["pcbot_id"] = pcbot_id

    if eventos:
        entry["eventos"] = list(eventos)  # copia superficial
        logger.debug("heartbeat cache: pcbot %s recibio %d eventos",
                     pcbot_id, len(eventos))
    else:
        entry["eventos"] = []
        logger.debug("heartbeat cache: pcbot %s heartbeat sin eventos", pcbot_id)

    # si no hay perfiles en este heartbeat, mantener los anteriores
    if "perfiles" not in entry:
        entry["perfiles"] = []

    _cache[pcbot_id] = entry


def obtener_heartbeat(pcbot_id: str) -> dict:
    """devuelve el dict del ultimo heartbeat o dict vacio."""
    return _cache.get(pcbot_id, {})


def ultimo_evento(pcbot_id: str) -> list:
    """devuelve la lista de eventos del ultimo heartbeat."""
    hb = _cache.get(pcbot_id, {})
    return hb.get("eventos", [])


def obtener_estado_perfil(pcbot_id: str, profile_id: str) -> str:
    """consulta el estado de un perfil en perfiles_roxy.
    retorna 'activo', 'inactivo' o 'caido'.
    si el perfil no existe en la bd (row is none), retorna 'inactivo'."""
    from db import ejecutar_sql_unico
    row = ejecutar_sql_unico(
        "select activo from perfiles_roxy where hash = ? and pcbot_id = ? and activo = 1",
        (profile_id, pcbot_id),
    )
    if row is None:
        return "inactivo"
    return "activo"


def obtener_perfiles_activos(pcbot_id: str) -> list:
    """devuelve lista de dicts con profile_id y url de perfiles activos en perfiles_roxy."""
    from db import ejecutar_sql
    rows = ejecutar_sql(
        "select hash as profile_id, url_actual as url from perfiles_roxy "
        "where pcbot_id = ? and activo = 1",
        (pcbot_id,),
    )
    return rows if rows else []


def obtener_url_perfil(pcbot_id: str, profile_id: str) -> str:
    """devuelve la url actual de un perfil desde perfiles_roxy."""
    from db import ejecutar_sql_unico
    row = ejecutar_sql_unico(
        "select url_actual from perfiles_roxy where hash = ? and pcbot_id = ? and activo = 1",
        (profile_id, pcbot_id),
    )
    return row["url_actual"] if row and row.get("url_actual") else ""


def obtener_perfiles_libres(pcbot_id: str) -> list:
    """devuelve lista de dicts con profile_id de perfiles libres en perfiles_roxy.
    un perfil esta libre si activo=1 y no tiene asignaciones activas."""
    from db import ejecutar_sql
    rows = ejecutar_sql(
        """select pr.hash as profile_id, pr.pcbot_id
           from perfiles_roxy pr
           where pr.pcbot_id = ?
             and pr.activo = 1
             and not exists (
                 select 1 from pedido_asignaciones pa
                 where pa.perfil_id = pr.hash
                    and pa.estado in ('planificado', 'ejecutando', 'activo', 'enviado', 'pendiente', 'reservado')
             )""",
        (pcbot_id,),
    )
    return rows if rows else []


def limpiar_cache(pcbot_id: str = None) -> None:
    """elimina un pcbot del cache, o todo el cache si no se especifica."""
    if pcbot_id:
        _cache.pop(pcbot_id, None)
    else:
        _cache.clear()


def test_cache():
    """funcion de prueba manual."""
    datos = {
        "tipo": "heartbeat",
        "pcbot_id": "PCWILMER",
        "eventos": [
            {"tipo": "perfil_caido", "perfil_id": "abc123"},
            {"tipo": "nuevo_perfil", "perfil_id": "def456"},
        ],
    }
    registrar_heartbeat("PCWILMER", datos)
    print("cache:", _cache.get("PCWILMER"))
    print("eventos:", ultimo_evento("PCWILMER"))

    # heartbeat sin eventos
    datos_sin_eventos = {
        "tipo": "heartbeat",
        "pcbot_id": "PCWILMER",
        "eventos": [],
    }
    registrar_heartbeat("PCWILMER", datos_sin_eventos)
    print("ultimo hb:", obtener_heartbeat("PCWILMER"))
    print("eventos:", ultimo_evento("PCWILMER"))


if __name__ == "__main__":
    test_cache()