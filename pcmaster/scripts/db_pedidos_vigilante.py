# db_pedidos_vigilante.py - crea tabla pedido_asignaciones para el vigilante de pedidos
# roxymaster v8.3 - utf-8 sin bom, nombres en minusculas
# parte del modulo de vigilante de pedidos (pedidos_vigilante)

import logging
from db import ejecutar_sql

logger = logging.getLogger("roxymaster.db_pedidos_vigilante")


async def crear_tablas_vigilante():
    """crea las tablas necesarias para el vigilante de pedidos.

    la tabla pedido_asignaciones registra cada perfil asignado a un pedido,
    permitiendo al vigilante rastrear perfiles activos, caidos y reemplazos.
    """
    ejecutar_sql("""
        create table if not exists pedido_asignaciones (
            id integer primary key autoincrement,
            pedido_id integer not null,
            pcbot_id text not null,
            perfil_id text not null default '',
            url text not null,
            duracion_seg integer not null,
            inicio text not null,
            fin text,
            estado text not null default 'activo',
            comando_id text,
            foreign key (pedido_id) references pedidos(id)
        )
    """)
    logger.info("tabla pedido_asignaciones verificada/creada")