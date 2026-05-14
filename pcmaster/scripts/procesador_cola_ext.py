# procesador_cola_ext.py - parte extendida del modulo procesador_cola
# roxymaster v8.3 - utf-8 sin bom, nombres en minusculas
# contiene funciones auxiliares de comunicacion y gestion de pcbots
# importa explicitamente de procesador_cola cuando es necesario

import logging
from datetime import datetime, timezone

import heartbeat_cache
from ws_manager import (
    obtener_pcbots_de_usuario,
    obtener_pcbot_de_usuario,
    enviar_comando_al_pcbot,
)
from db import ejecutar_sql

logger = logging.getLogger("procesador_cola")


def _ahora_str() -> str:
    """devuelve timestamp utc en formato iso."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _ahora_dt() -> datetime:
    """devuelve datetime utc actual."""
    return datetime.now(timezone.utc)


async def _enviar_comando_seguro(usuario_id: int, comando: dict, pcbot_id: str = None) -> dict:
    """wrapper seguro para enviar_comando_al_pcbot.
    maneja excepciones y devuelve siempre dict con exito/error.
    si se proporciona pcbot_id, envia directamente a ese pcbot (v2)."""
    try:
        resultado = await enviar_comando_al_pcbot(usuario_id, comando, pcbot_id)
        if isinstance(resultado, dict):
            return resultado
        exito = bool(resultado)
        return {"exito": exito, "error": "" if exito else "resultado inesperado"}
    except Exception as e:
        logger.error("[COLA] error enviando comando: %s", str(e)[:200])
        return {"exito": False, "error": str(e)[:200]}


async def _liberar_reservas_caducadas():
    """libera reservas cuyo timeout haya expirado.
    ejecutado al inicio de cada ciclo del procesador.
    las asignaciones en 'reservado' con timeout < ahora se marcan como 'fallido'."""
    try:
        ahora = _ahora_str()
        liberadas = ejecutar_sql(
            "update pedido_asignaciones set estado = 'fallido' "
            "where estado = 'reservado' and timeout < ?",
            (ahora,),
        )
        # contar cuantas filas se actualizaron
        # sqlite no devuelve rowcount directamente, usamos una query separada
        if liberadas is not None:
            logger.info(
                "[COLA] liberadas %s reservas caducadas",
                len(liberadas) if isinstance(liberadas, (list, tuple)) else "?",
            )
    except Exception as e:
        logger.error("[COLA] error liberando reservas caducadas: %s", str(e)[:200])


# ---------------------------------------------------------------------------
# obtener pcbots del usuario (con fallbacks)
# ---------------------------------------------------------------------------
def _obtener_pcbots_usuario(usuario_id: int) -> list:
    """obtiene lista de pcbot_ids (strings) conectados para un usuario.
    fallback: si obtener_pcbots_de_usuario devuelve lista vacia,
    intenta con obtener_pcbot_de_usuario."""
    # intentar obtener todos los pcbots (nuevo formato multi-pcbot)
    try:
        pcbots_dicts = obtener_pcbots_de_usuario(int(usuario_id))
        if pcbots_dicts and isinstance(pcbots_dicts, list):
            ids = []
            for entry in pcbots_dicts:
                if isinstance(entry, dict):
                    pid = entry.get("pcbot_id")
                    if pid:
                        ids.append(pid)
                elif isinstance(entry, str):
                    ids.append(entry)
            if ids:
                return ids
    except Exception as e:
        logger.debug("[COLA] obtener_pcbots_de_usuario fallo: %s", str(e)[:100])

    # fallback: intentar con la version singular
    try:
        pcbot_unico = obtener_pcbot_de_usuario(int(usuario_id))
        if pcbot_unico:
            return [pcbot_unico]
    except Exception as e:
        logger.debug("[COLA] obtener_pcbot_de_usuario fallo: %s", str(e)[:100])

    # fallback 1: consultar usuarios.pcbot_id directamente
    try:
        usuarios = ejecutar_sql(
            "select pcbot_id from usuarios where id = ? and pcbot_id is not null",
            (usuario_id,),
        )
        if usuarios:
            ids = [u["pcbot_id"] for u in usuarios if u.get("pcbot_id")]
            if ids:
                return ids
    except Exception as e:
        logger.debug("[COLA] consulta usuarios bd fallo: %s", str(e)[:100])

    # fallback 2: buscar en computadoras.pcbot_id
    try:
        comps = ejecutar_sql(
            "select distinct pcbot_id from computadoras where usuario_id = ? and pcbot_id is not null",
            (usuario_id,),
        )
        if comps:
            ids = [c["pcbot_id"] for c in comps if c.get("pcbot_id")]
            if ids:
                return ids
    except Exception as e:
        logger.debug("[COLA] consulta computadoras bd fallo: %s", str(e)[:100])

    # fallback 3: buscar en perfiles_roxy.pcbot_id
    try:
        perfiles = ejecutar_sql(
            "select distinct pcbot_id from perfiles_roxy where usuario_id = ? and pcbot_id is not null",
            (usuario_id,),
        )
        if perfiles:
            ids = [p["pcbot_id"] for p in perfiles if p.get("pcbot_id")]
            if ids:
                return ids
    except Exception as e:
        logger.debug("[COLA] consulta perfiles_roxy bd fallo: %s", str(e)[:100])

    return []