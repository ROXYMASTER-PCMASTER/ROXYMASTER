# db_pedidos_ext.py - extension de esquema para agendamiento de pedidos por hora
# roxymaster v8.3 - utf-8 sin bom, nombres en minusculas
# parte del modulo db_pedidos_vigilante

import logging

from db import ejecutar_sql

logger = logging.getLogger("roxymaster.db_pedidos_ext")

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
    tambien agrega fecha_inicio si no existe."""
    # primero asegurar fecha_inicio (necesaria para el procesador de cola)
    agregar_columna_fecha_inicio()

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
            "activo integer default 1"
            ")"
        )
        logger.info("[DB_EXT] tabla contextos_streamer verificada/creada")
        return True
    except Exception as e:
        logger.error("[DB_EXT] error al crear tabla contextos_streamer: %s", str(e)[:200])
        return False