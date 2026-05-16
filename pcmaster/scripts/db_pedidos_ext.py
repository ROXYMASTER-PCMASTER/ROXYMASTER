# db_pedidos_ext.py - extension de esquema para agendamiento de pedidos por hora
# roxymaster v8.3 - utf-8 sin bom, nombres en minusculas
# parte del modulo db_pedidos_vigilante

import logging

from db import ejecutar_sql

logger = logging.getLogger("roxymaster.db_pedidos_ext")

def agregar_columna_fecha_fin():
    """agrega la columna fecha_fin a la tabla pedidos si no existe.
    necesaria para cerrar pedidos completados correctamente.
    el error 'no such column: fecha_fin' se produce cuando el procesador
    intenta escribirla pero no existe en el esquema."""
    try:
        resultado = ejecutar_sql(
            "select name from pragma_table_info('pedidos') "
            "where name = 'fecha_fin'"
        )
        if not resultado:
            logger.info("[DB_EXT] agregando columna fecha_fin a pedidos")
            ejecutar_sql(
                "alter table pedidos add column fecha_fin text"
            )
        else:
            logger.info("[DB_EXT] columna fecha_fin ya existe")
        return True
    except Exception as e:
        logger.error("[DB_EXT] error al agregar columna fecha_fin: %s", str(e)[:200])
        return False


def agregar_columna_fecha_inicio():
    """agrega la columna fecha_inicio a la tabla pedidos si no existe."""
    try:
        resultado = ejecutar_sql(
            "select name from pragma_table_info('pedidos') "
            "where name = 'fecha_inicio'"
        )
        if not resultado:
            logger.info("[DB_EXT] agregando columna fecha_inicio a pedidos")
            ejecutar_sql(
                "alter table pedidos add column fecha_inicio text"
            )
        else:
            logger.info("[DB_EXT] columna fecha_inicio ya existe")
        return True
    except Exception as e:
        logger.error("[DB_EXT] error al agregar columna fecha_inicio: %s", str(e)[:200])
        return False


def agregar_columnas_agendamiento():
    """agrega las columnas hora_inicio_programada y hora_fin_programada
    a la tabla pedidos si no existen.
    tambien agrega fecha_inicio y fecha_fin si no existen."""
    # primero asegurar fecha_inicio y fecha_fin (necesarias para el procesador de cola)
    agregar_columna_fecha_inicio()
    agregar_columna_fecha_fin()

    try:
        # verificar si las columnas ya existen
        resultado = ejecutar_sql(
            "select name from pragma_table_info('pedidos') "
            "where name = 'hora_inicio_programada'"
        )
        if not resultado:
            logger.info("[DB_EXT] agregando columna hora_inicio_programada a pedidos")
            ejecutar_sql(
                "alter table pedidos add column hora_inicio_programada text"
            )
        else:
            logger.info("[DB_EXT] columna hora_inicio_programada ya existe")

        resultado = ejecutar_sql(
            "select name from pragma_table_info('pedidos') "
            "where name = 'hora_fin_programada'"
        )
        if not resultado:
            logger.info("[DB_EXT] agregando columna hora_fin_programada a pedidos")
            ejecutar_sql(
                "alter table pedidos add column hora_fin_programada text"
            )
        else:
            logger.info("[DB_EXT] columna hora_fin_programada ya existe")

        logger.info("[DB_EXT] columnas de agendamiento verificadas/agregadas correctamente")
        return True
    except Exception as e:
        logger.error("[DB_EXT] error al agregar columnas de agendamiento: %s", str(e)[:200])
        return False


def agregar_columna_timeout():
    """agrega la columna timeout a la tabla pedido_asignaciones si no existe.
    la columna timeout almacena la fecha-hora iso en que expira una reserva.
    cuando un perfil se asigna pero aun no se confirma por el pcbot,
    se marca como 'reservado' con un timeout. si el timeout expira,
    el procesador de cola libera la reserva."""
    try:
        resultado = ejecutar_sql(
            "select name from pragma_table_info('pedido_asignaciones') "
            "where name = 'timeout'"
        )
        if not resultado:
            logger.info("[DB_EXT] agregando columna timeout a pedido_asignaciones")
            ejecutar_sql(
                "alter table pedido_asignaciones add column timeout text"
            )
        else:
            logger.info("[DB_EXT] columna timeout ya existe en pedido_asignaciones")
        return True
    except Exception as e:
        logger.error("[DB_EXT] error al agregar columna timeout: %s", str(e)[:200])
        return False


def agregar_columna_rol():
    """agrega la columna rol a la tabla pedido_asignaciones si no existe.
    la columna rol almacena 'observador' para perfiles designados como
    segundos observadores en pedidos sin contexto."""
    try:
        resultado = ejecutar_sql(
            "select name from pragma_table_info('pedido_asignaciones') "
            "where name = 'rol'"
        )
        if not resultado:
            logger.info("[DB_EXT] agregando columna rol a pedido_asignaciones")
            ejecutar_sql(
                "alter table pedido_asignaciones add column rol text default null"
            )
        else:
            logger.info("[DB_EXT] columna rol ya existe en pedido_asignaciones")
        return True
    except Exception as e:
        logger.error("[DB_EXT] error al agregar columna rol: %s", str(e)[:200])
        return False


def agregar_columna_cache_hash():
    """agrega la columna cache_hash a la tabla contextos_streamer si no existe.
    almacena el hash md5 del ultimo lote de chat procesado para evitar
    llamadas innecesarias a ollama."""
    try:
        resultado = ejecutar_sql(
            "select name from pragma_table_info('contextos_streamer') "
            "where name = 'cache_hash'"
        )
        if not resultado:
            logger.info("[DB_EXT] agregando columna cache_hash a contextos_streamer")
            ejecutar_sql(
                "alter table contextos_streamer add column cache_hash text default ''"
            )
        else:
            logger.info("[DB_EXT] columna cache_hash ya existe en contextos_streamer")
        return True
    except Exception as e:
        logger.error("[DB_EXT] error al agregar columna cache_hash: %s", str(e)[:200])
        return False


def crear_tabla_contextos_streamer():
    """crea la tabla contextos_streamer si no existe.
    almacena el contexto de personalidad y frases de cada streamer."""
    try:
        ejecutar_sql(
            "create table if not exists contextos_streamer ("
            "id integer primary key autoincrement, "
            "url text unique not null, "
            "personalidad_base text default '{}', "
            "contexto_actual text default '{}', "
            "frases_pool text default '[]', "
            "frases_usadas integer default 0, "
            "ultimo_analisis text, "
            "cache_hash text default '', "
            "activo integer default 1"
            ")"
        )
        logger.info("[DB_EXT] tabla contextos_streamer verificada/creada")
        return True
    except Exception as e:
        logger.error("[DB_EXT] error al crear tabla contextos_streamer: %s", str(e)[:200])
        return False


def agregar_columna_comentarios_ia():
    """agrega la columna comentarios_ia a la tabla pedidos si no existe.
    almacena 1 si el pedido tiene comentarista ia activado, 0 si no."""
    try:
        resultado = ejecutar_sql(
            "select name from pragma_table_info('pedidos') "
            "where name = 'comentarios_ia'"
        )
        if not resultado:
            logger.info("[DB_EXT] agregando columna comentarios_ia a pedidos")
            ejecutar_sql(
                "alter table pedidos add column comentarios_ia integer default 0"
            )
        else:
            logger.info("[DB_EXT] columna comentarios_ia ya existe")
        return True
    except Exception as e:
        logger.error("[DB_EXT] error al agregar columna comentarios_ia: %s", str(e)[:200])
        return False


def agregar_todas_las_columnas():
    """ejecuta todas las migraciones de esquema pendientes.
    esta funcion se llama durante el inicio del servidor para asegurar
    que todas las columnas necesarias existan en la base de datos."""
    agregar_columnas_agendamiento()
    agregar_columna_timeout()
    agregar_columna_rol()
    agregar_columna_cache_hash()
    agregar_columna_comentarios_ia()