# db_pedidos_ext.py - extension de esquema para agendamiento de pedidos por hora
# roxymaster v8.3 - utf-8 sin bom, nombres en minusculas
# parte del modulo db_pedidos_vigilante

import logging

from db import ejecutar_sql

logger = logging.getLogger("roxymaster.db_pedidos_ext")

def agregar_columnas_agendamiento():
    """agrega las columnas hora_inicio_programada y hora_fin_programada
    a la tabla pedidos si no existen."""
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