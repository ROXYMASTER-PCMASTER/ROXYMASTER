# heartbeat_cache.py - cache en memoria del ultimo heartbeat de cada pcbot. roxymaster v8.3
# modulo intermedio para que el vigilante de pedidos acceda a datos de heartbeat
# sin depender de ws_manager ni de bd. utf-8 sin bom, <= 150 lineas

import logging
from datetime import datetime

logger = logging.getLogger("roxymaster.heartbeat_cache")

# ---------------------------------------------------------------------------
# cache en memoria: _cache[pcbot_id] = dict completo del ultimo heartbeat
# ---------------------------------------------------------------------------
_cache: dict = {}


def registrar_heartbeat(pcbot_id: str, datos: dict) -> None:
    """almacena el contenido completo del ultimo heartbeat de un pcbot.
    datos debe incluir "tipo", "pcbot_id", "uptime", "uptime_sec", "perfiles", etc.
    cada perfil puede incluir "state": "activo"|"libre"|"caido" ademas de
    "profile_id", "activo", "url", "tiempo_conectado_seg"."""
    if not pcbot_id or not datos:
        return
    perfiles_procesados = []
    for p in datos.get("perfiles", []):
        entry = {
            "profile_id": p.get("profile_id", p.get("id", "")),
            "activo": bool(p.get("activo", False)),
            "url": p.get("url", ""),
            "tiempo_conectado_seg": p.get("tiempo_conectado_seg", 0),
            "state": p.get("estado", p.get("state", "activo" if p.get("activo", False) else "libre")),
        }
        perfiles_procesados.append(entry)

    _cache[pcbot_id] = {
        "pcbot_id": pcbot_id,
        "uptime": datos.get("uptime", ""),
        "uptime_sec": datos.get("uptime_sec", 0),
        "perfiles": perfiles_procesados,
        "recibido_en": datetime.now().isoformat(),
    }
    logger.debug("heartbeat cache actualizado para pcbot %s (%d perfiles)",
                 pcbot_id, len(_cache[pcbot_id]["perfiles"]))


def obtener_heartbeat(pcbot_id: str) -> dict:
    """devuelve el dict completo del ultimo heartbeat, o dict vacio."""
    return _cache.get(pcbot_id, {})


def obtener_perfiles_activos(pcbot_id: str) -> list:
    """devuelve lista de perfiles con activo=true del ultimo heartbeat.
    cada elemento: {"profile_id", "activo", "url", "tiempo_conectado_seg", "state"}"""
    hb = _cache.get(pcbot_id, {})
    perfiles = hb.get("perfiles", [])
    return [
        {
            "profile_id": p.get("profile_id", ""),
            "activo": bool(p.get("activo", False)),
            "url": p.get("url", ""),
            "tiempo_conectado_seg": p.get("tiempo_conectado_seg", 0),
            "state": p.get("estado", p.get("state", "activo")),
        }
        for p in perfiles
        if p.get("activo", False)
    ]


def obtener_url_perfil(pcbot_id: str, profile_id: str) -> str:
    """busca un perfil en el cache del pcbot y devuelve su url.
    retorna string vacio si no lo encuentra."""
    hb = _cache.get(pcbot_id, {})
    for p in hb.get("perfiles", []):
        pid = p.get("profile_id", "")
        if pid == profile_id:
            return p.get("url", "")
    return ""


def obtener_estado_perfil(pcbot_id: str, profile_id: str) -> str:
    """busca un perfil en el cache del pcbot y devuelve su state.
    retorna 'libre' como fallback si no se encuentra perfil (backwards-compat)."""
    hb = _cache.get(pcbot_id, {})
    for p in hb.get("perfiles", []):
        pid = p.get("profile_id", "")
        if pid == profile_id:
            state = p.get("estado", p.get("state", ""))
            if state:
                return state
            # fallback si no tiene state: usar activo bool
            p_activo = p.get("activo", False)
            return "activo" if p_activo else "libre"
    return "libre"


def obtener_perfiles_libres(pcbot_id: str) -> list:
    """devuelve lista de profile_id que estan en el cache pero no activos.
    son candidatos a ser reasignados.
    nota: excluye perfiles con state='caido' (requieren intervencion manual)."""
    hb = _cache.get(pcbot_id, {})
    perfiles = hb.get("perfiles", [])
    libres = []
    for p in perfiles:
        pid = p.get("profile_id", "")
        activo = bool(p.get("activo", False))
        state = p.get("estado", p.get("state", ""))
        # excluir caidos
        if state == "caido":
            continue
        if not activo and pid:
            libres.append({
                "profile_id": pid,
                "url": p.get("url", ""),
                "tiempo_conectado_seg": p.get("tiempo_conectado_seg", 0),
                "state": state if state else "libre",
            })
    return libres


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
        "uptime": "22h 9m",
        "uptime_sec": 79751,
        "perfiles": [
            {"profile_id": "perf1", "activo": True, "url": "https://kick.com/canal1",
             "tiempo_conectado_seg": 1234, "state": "activo"},
            {"profile_id": "perf2", "activo": False, "url": "",
             "tiempo_conectado_seg": 0, "state": "caido"},
            {"profile_id": "perf3", "activo": False, "url": "",
             "tiempo_conectado_seg": 0, "state": "libre"},
            {"profile_id": "perf4", "activo": True, "url": "https://kick.com/canal3",
             "tiempo_conectado_seg": 567, "state": "activo"},
        ],
    }
    registrar_heartbeat("PCWILMER", datos)
    print("activos:", obtener_perfiles_activos("PCWILMER"))
    print("url perf1:", obtener_url_perfil("PCWILMER", "perf1"))
    print("estado perf2:", obtener_estado_perfil("PCWILMER", "perf2"))
    print("libres (no incluye caidos):", obtener_perfiles_libres("PCWILMER"))


if __name__ == "__main__":
    test_cache()