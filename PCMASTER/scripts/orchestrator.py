import asyncio, time, logging
from ws_handler import pcbots, perfiles_map, enviar
logger = logging.getLogger("orchestrator")
grupos = {}

async def ejecutar_asignar(cant, url, dur):
    libres = [k for k, v in perfiles_map.items() if v.get("estado") != "activo"]
    sel = libres[:cant]
    if url not in grupos:
        grupos[url] = {"perfiles": [], "inicio": time.time(), "duracion": dur * 60, "comentarios": False}
    for key in sel:
        grupos[url]["perfiles"].append(key)
        info = perfiles_map[key]
        await enviar(info["pcbot"], "open_url", {"url": url, "profile": info["name"], "dirId": info["dirId"]})
        await asyncio.sleep(2)
    return f"asignados {len(sel)} perfiles a {url} por {dur} min"

async def ejecutar_comentarios_activar(url, nivel):
    if url in grupos:
        grupos[url]["comentarios"] = True
        return f"comentarios activados para {url} (nivel {nivel})"
    return f"grupo no encontrado: {url}"

async def ejecutar_comentarios_desactivar(url):
    if url in grupos:
        grupos[url]["comentarios"] = False
        return f"comentarios desactivados para {url}"
    return f"grupo no encontrado: {url}"

async def ejecutar_detener(url):
    if url in grupos:
        del grupos[url]
        return f"grupo detenido: {url}"
    return f"grupo no encontrado: {url}"
