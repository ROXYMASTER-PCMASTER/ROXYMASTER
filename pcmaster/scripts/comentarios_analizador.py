# comentarios_analizador.py - analizador de contexto de streamers y generacion de frases
# roxymaster v8.3 - utf-8 sin bom, nombres en minusculas
# modulo para analizar chats de streamers usando ollama, con cache de hash
# para evitar llamadas innecesarias cuando el chat no cambio.

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone

import aiohttp

from db import ejecutar_sql, ejecutar_insercion, ejecutar_sql_unico
from config_loader import jarvis_api_url, jarvis_modelo
from ws_manager import enviar_comando_al_pcbot

logger = logging.getLogger("comentarios_analizador")

TIMEOUT_OLLAMA = 30  # segundos timeout para llamada a ollama
TIMEOUT_COMENTAR = 5  # segundos timeout para respuesta del pcbot
PROMPT_GENERICO = (
    "analiza el tono, los emojis frecuentes y las frases comunes del siguiente "
    "chat de stream. genera un contexto y 5 frases similares pero originales."
)


# ---------------------------------------------------------------------------
# funciones de hash (punto 7)
# ---------------------------------------------------------------------------
def _calcular_hash_lineas(lineas: list) -> str:
    """calcula md5 de una lista de lineas de chat.
    las lineas se concatenan con salto de linea y se hashean."""
    contenido = "\n".join(lineas) + "\n"
    return hashlib.md5(contenido.encode("utf-8")).hexdigest()


def _comparar_hash(url: str, hash_actual: str) -> bool:
    """compara el hash calculado con el almacenado en contextos_streamer.
    devuelve true si son iguales (el chat no cambio)."""
    resultado = ejecutar_sql_unico(
        "select cache_hash from contextos_streamer where url = ?",
        (url,),
    )
    if not resultado or not resultado.get("cache_hash"):
        return False
    return resultado["cache_hash"] == hash_actual


def _actualizar_cache_hash(url: str, nuevo_hash: str):
    """actualiza el cache_hash y ultimo_analisis en contextos_streamer."""
    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    ejecutar_sql(
        "update contextos_streamer set cache_hash = ?, ultimo_analisis = ? "
        "where url = ?",
        (nuevo_hash, ahora, url),
    )


# ---------------------------------------------------------------------------
# generacion de prompt (punto 10)
# ---------------------------------------------------------------------------
def _generar_prompt_ollama(personalidad_base: str = None) -> str:
    """genera el prompt para ollama segun exista o no personalidad_base.

    si personalidad_base esta vacia o es '{}', usa prompt generico.
    si existe, la incluye para mantener consistencia."""
    if not personalidad_base or personalidad_base.strip() in ("{}", "", "null"):
        return PROMPT_GENERICO
    return (
        f"{PROMPT_GENERICO}\n\n"
        f"contexto previo (manten consistencia): {personalidad_base}"
    )


# ---------------------------------------------------------------------------
# llamada a ollama (punto 7)
# ---------------------------------------------------------------------------
async def _llamar_ollama(prompt: str) -> dict:
    """llama a ollama via http y devuelve la respuesta parseada.
    devuelve dict con keys: contexto, frases.
    en caso de error devuelve dict vacio {'contexto': '', 'frases': []}."""
    url_ollama = f"{jarvis_api_url}/api/generate"
    payload = {
        "model": jarvis_modelo,
        "prompt": prompt,
        "stream": False,
    }
    try:
        timeout = aiohttp.ClientTimeout(total=TIMEOUT_OLLAMA)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url_ollama, json=payload) as resp:
                if resp.status != 200:
                    texto = await resp.text()
                    logger.error("[OLLAMA] error http %s: %s", resp.status, texto[:300])
                    return {"contexto": "", "frases": []}
                data = await resp.json()
                respuesta = data.get("response", "")
                return _parsear_respuesta_ollama(respuesta)
    except asyncio.TimeoutError:
        logger.error("[OLLAMA] timeout tras %ss", TIMEOUT_OLLAMA)
        return {"contexto": "", "frases": []}
    except Exception as e:
        logger.error("[OLLAMA] error conexion: %s", str(e)[:300])
        return {"contexto": "", "frases": []}


def _parsear_respuesta_ollama(respuesta: str) -> dict:
    """parsea la respuesta de ollama extrayendo contexto y frases.
    espera formato json con keys 'contexto' y 'frases'.
    si no se puede parsear, extrae heuristicamente."""
    respuesta = respuesta.strip()
    # intentar parsear como json
    try:
        data = json.loads(respuesta)
        if isinstance(data, dict):
            contexto = data.get("contexto", "")
            frases = data.get("frases", [])
            if isinstance(frases, list):
                return {"contexto": contexto, "frases": frases}
    except (json.JSONDecodeError, TypeError):
        pass

    # fallback: extraer heuristicamente
    contexto = ""
    frases = []
    lineas = respuesta.split("\n")
    en_frases = False
    for linea in lineas:
        linea_strip = linea.strip()
        if not linea_strip:
            continue
        if "contexto" in linea_strip.lower() and ":" in linea_strip:
            contexto = linea_strip.split(":", 1)[1].strip()
            continue
        if "frases" in linea_strip.lower():
            en_frases = True
            continue
        if en_frases:
            # limpiar numeracion
            frase = linea_strip.lstrip("0123456789.-) ")
            if frase:
                frases.append(frase)

    if not contexto and frases:
        # si no hay contexto pero hay frases, usar primera frase como contexto
        pass

    return {"contexto": contexto, "frases": frases}


# ---------------------------------------------------------------------------
# funcion principal de procesamiento de chat (punto 7)
# ---------------------------------------------------------------------------
async def procesar_chat(url: str, lineas_chat: list) -> dict:
    """procesa las lineas de chat de un streamer.

    paso 1: calcula hash md5 de las lineas recibidas.
    paso 2: compara con cache_hash almacenado en contextos_streamer.
    paso 3: si son identicas, no llama a ollama. solo actualiza ultimo_analisis.
    paso 4: si cambiaron, genera prompt, llama a ollama y actualiza cache_hash.

    si la url no existe en contextos_streamer, la crea.

    returns:
        dict con keys: 'cambio' (bool, si se proceso o no), 'contexto', 'frases'
    """
    if not url or not lineas_chat:
        logger.warning("[ANALIZADOR] url o lineas_chat vacios")
        return {"cambio": False, "contexto": "", "frases": []}

    hash_lineas = _calcular_hash_lineas(lineas_chat)

    # punto 7: verificar si el chat cambio
    if _comparar_hash(url, hash_lineas):
        logger.info("[ANALIZADOR] chat sin cambios para %s, saltando ollama", url)
        # actualizar solo ultimo_analisis
        ahora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        ejecutar_sql(
            "update contextos_streamer set ultimo_analisis = ? where url = ?",
            (ahora, url),
        )
        # devolver datos actuales
        datos = ejecutar_sql_unico(
            "select contexto_actual, frases_pool from contextos_streamer where url = ?",
            (url,),
        )
        contexto = ""
        frases = []
        if datos:
            try:
                contexto = json.loads(datos.get("contexto_actual", "{}"))
            except (json.JSONDecodeError, TypeError):
                pass
            try:
                frases = json.loads(datos.get("frases_pool", "[]"))
            except (json.JSONDecodeError, TypeError):
                pass
        return {"cambio": False, "contexto": contexto, "frases": frases}

    # el chat cambio, proceder con analisis
    logger.info("[ANALIZADOR] chat cambio para %s, llamando a ollama", url)

    # punto 10: obtener o crear contexto en db
    datos_streamer = ejecutar_sql_unico(
        "select id, personalidad_base, contexto_actual, frases_pool "
        "from contextos_streamer where url = ?",
        (url,),
    )

    personalidad_base = None
    if datos_streamer:
        personalidad_base = datos_streamer.get("personalidad_base")

    prompt = _generar_prompt_ollama(personalidad_base)
    prompt_completo = f"{prompt}\n\nchat:\n" + "\n".join(lineas_chat[:200])

    # llamar a ollama
    resultado = await _llamar_ollama(prompt_completo)
    contexto = resultado.get("contexto", "")
    frases = resultado.get("frases", [])

    # actualizar base de datos
    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    contexto_json = json.dumps(contexto, ensure_ascii=False)
    frases_json = json.dumps(frases, ensure_ascii=False)

    if datos_streamer:
        # actualizar registro existente
        logger.info("[ANALIZADOR-DIAG] actualizando contextos_streamer EXISTENTE para url '%s'", url)
        logger.info("[ANALIZADOR-DIAG] UPDATE: contexto_json(%d chars), frases_json(%d chars), hash=%s",
                     len(contexto_json), len(frases_json), hash_lineas[:12])
        ejecutar_sql(
            "update contextos_streamer set contexto_actual = ?, frases_pool = ?, "
            "frases_usadas = 0, ultimo_analisis = ?, cache_hash = ? "
            "where url = ?",
            (contexto_json, frases_json, ahora, hash_lineas, url),
        )
        logger.info("[ANALIZADOR-DIAG] UPDATE ejecutado correctamente para url '%s'", url)
    else:
        # crear nuevo registro
        logger.info("[ANALIZADOR-DIAG] insertando NUEVO registro en contextos_streamer para url '%s'", url)
        nuevo_id = ejecutar_insercion(
            "insert into contextos_streamer "
            "(url, personalidad_base, contexto_actual, frases_pool, "
            "frases_usadas, ultimo_analisis, cache_hash, activo) "
            "values (?, ?, ?, ?, 0, ?, ?, 1)",
            (url, "{}", contexto_json, frases_json, ahora, hash_lineas),
        )
        logger.info("[ANALIZADOR-DIAG] INSERT ejecutado, nuevo_id=%s para url '%s'", nuevo_id, url)

    logger.info(
        "[ANALIZADOR] contexto actualizado para %s: %s frases generadas, hash=%s",
        url, len(frases), hash_lineas[:12],
    )

    return {"cambio": True, "contexto": contexto, "frases": frases}


# ---------------------------------------------------------------------------
# envio de comentario con verificacion de respuesta (punto 8)
# ---------------------------------------------------------------------------
async def enviar_comentario_y_verificar(
    usuario_id: int,
    pcbot_id: str,
    frase: str,
    comando_id: str = None,
) -> dict:
    """envia comando 'comentar' al pcbot y espera su respuesta.

    paso 1: construye comando 'comentar' con la frase.
    paso 2: envia al pcbot via ws_manager.
    paso 3: espera respuesta (timeout 5s).
    paso 4: si responde {"ok": true}, devuelve exito.
    paso 5: si responde {"ok": false} o hay timeout,
            devuelve la frase al pool (frases_usadas -= 1)
            y devuelve error para reintentar en siguiente ciclo.

    returns:
        dict con keys: 'exito' (bool), 'error' (str o none)
    """
    if not comando_id:
        import uuid
        comando_id = str(uuid.uuid4())

    comando = {
        "tipo": "comentar",
        "comando_id": comando_id,
        "parametros": {
            "frase": frase,
        },
    }

    logger.info("[COMENTAR] enviando comentario a pcbot %s: '%s'", pcbot_id, frase[:60])

    try:
        # enviar comando y esperar respuesta con timeout
        respuesta = await asyncio.wait_for(
            enviar_comando_al_pcbot(usuario_id, comando, pcbot_id),
            timeout=TIMEOUT_COMENTAR,
        )
    except asyncio.TimeoutError:
        logger.warning("[COMENTAR] timeout (%ss) esperando respuesta de pcbot %s",
                       TIMEOUT_COMENTAR, pcbot_id)
        # devolver frase al pool
        await _devolver_frase_al_pool(usuario_id, pcbot_id, frase)
        return {"exito": False, "error": "timeout esperando respuesta del pcbot"}
    except Exception as e:
        logger.error("[COMENTAR] error enviando comentario a pcbot %s: %s",
                     pcbot_id, str(e)[:200])
        # devolver frase al pool
        await _devolver_frase_al_pool(usuario_id, pcbot_id, frase)
        return {"exito": False, "error": str(e)[:200]}

    # procesar respuesta
    if isinstance(respuesta, dict) and respuesta.get("ok"):
        logger.info("[COMENTAR] pcbot %s confirmo comentario exitosamente", pcbot_id)
        return {"exito": True, "error": None}
    else:
        mensaje_error = "respuesta negativa del pcbot"
        if isinstance(respuesta, dict) and respuesta.get("error"):
            mensaje_error = respuesta["error"]
        elif isinstance(respuesta, str):
            mensaje_error = respuesta

        logger.warning("[COMENTAR] pcbot %s rechazo comentario: %s",
                       pcbot_id, mensaje_error)
        # devolver frase al pool
        await _devolver_frase_al_pool(usuario_id, pcbot_id, frase)
        return {"exito": False, "error": mensaje_error}


async def _devolver_frase_al_pool(usuario_id: int, pcbot_id: str, frase: str):
    """devuelve una frase al pool decrementando frases_usadas.
    se llama cuando falla el envio de un comentario al pcbot.

    busca el contexto activo para el usuario/pcbot y decrementa frases_usadas.
    """
    try:
        # buscar url activa donde esta frase pertenece
        # obtenemos la url mas reciente con asignaciones activas para este pcbot
        asignacion = ejecutar_sql_unico(
            """select pa.url
               from pedido_asignaciones pa
               where pa.pcbot_id = ?
                 and pa.estado in ('planificado', 'ejecutando')
                 and pa.rol is null
               order by pa.id desc
               limit 1""",
            (pcbot_id,),
        )
        if not asignacion or not asignacion.get("url"):
            logger.debug("[COMENTAR] no se encontro url activa para devolver frase al pool")
            return

        url = asignacion["url"]
        # decrementar frases_usadas
        ejecutar_sql(
            "update contextos_streamer set frases_usadas = "
            "case when frases_usadas > 0 then frases_usadas - 1 else 0 end "
            "where url = ?",
            (url,),
        )
        logger.info("[COMENTAR] frase devuelta al pool para url %s, frases_usadas decrementado",
                    url)
    except Exception as e:
        logger.error("[COMENTAR] error devolviendo frase al pool: %s", str(e)[:200])