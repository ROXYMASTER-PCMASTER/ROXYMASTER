# db_pedidos_vigilante.py - tablas para asignacion centralizada
# roxymaster v8.3 - utf-8 sin bom, nombres en minusculas
# parte del modulo de vigilante de pedidos
# crea/actualiza tablas: pedido_asignaciones y migraciones de esquema

import logging
from db import ejecutar_sql

logger = logging.getLogger("roxymaster.db_pedidos_vigilante")

# ---- estados validos ----
# pedidos.estado: 'agendado', 'programado', 'pendiente', 'en_progreso', 'completado', 'fallido'
# pedido_asignaciones.estado: 'planificado', 'ejecutando', 'completado', 'fallido', 'reservado', 'activo'


async def crear_tablas_vigilante():
    """crea/actualiza las tablas para el nuevo modelo de asignacion centralizada.

    tabla pedido_asignaciones registra cada perfil asignado a un pedido,
    con estados extendidos para planificacion centralizada.
    """
    # crea tabla si no existe
    ejecutar_sql("""
        create table if not exists pedido_asignaciones (
            id integer primary key autoincrement,
            pedido_id integer not null,
            pcbot_id text not null,
            perfil_id text not null default '',
            url text not null,
            duracion_seg integer not null,
            inicio text,
            fin text,
            estado text not null default 'planificado',
            comando_id text,
            timeout text,
            liberacion_estimada text,
            foreign key (pedido_id) references pedidos(id)
        )
    """)
    logger.info("tabla pedido_asignaciones verificada/creada")

    # migraciones para esquemas anteriores --------------------------------
    _migrar_agregar_columna("pedido_asignaciones", "liberacion_estimada")
    _migrar_agregar_columna("pedido_asignaciones", "timeout")
    _migrar_agregar_columna("pedido_asignaciones", "inicio")
    _migrar_agregar_columna("pedido_asignaciones", "fin")

    # crear pedido_asignaciones_pedido_id_idx si no existe
    _migrar_crear_indice(
        "pedido_asignaciones_pedido_id_idx",
        "create index if not exists pedido_asignaciones_pedido_id_idx on pedido_asignaciones(pedido_id)",
    )
    _migrar_crear_indice(
        "pedido_asignaciones_estado_idx",
        "create index if not exists pedido_asignaciones_estado_idx on pedido_asignaciones(estado)",
    )

    # migrar estado 'activo' -> 'ejecutando' (si hay registros viejos)
    _migrar_actualizar_estados()

    logger.info("migraciones de pedido_asignaciones completadas")


def _migrar_agregar_columna(tabla: str, columna: str):
    """agrega una columna a la tabla si no existe (sqlite no tiene if not exists para add column)."""
    try:
        ejecutar_sql(f"alter table {tabla} add column {columna} text")
        logger.info("columna %s agregada a %s", columna, tabla)
    except Exception:
        # la columna ya existe (error esperado)
        pass


def _migrar_crear_indice(nombre: str, sql: str):
    """crea un indice si no existe."""
    try:
        ejecutar_sql(sql)
        logger.info("indice %s verificado/creado", nombre)
    except Exception as e:
        logger.warning("error creando indice %s: %s", nombre, str(e)[:200])


def _migrar_actualizar_estados():
    """actualiza estados viejos a los nuevos del modelo centralizado.
    - 'activo' -> 'ejecutando' (ahora se usa 'ejecutando' para asignaciones en marcha)
    - 'reservado' se mantiene (compatible hacia atras)
    """
    try:
        ejecutar_sql(
            "update pedido_asignaciones set estado = 'ejecutando' "
            "where estado = 'activo'"
        )
    except Exception as e:
        logger.warning("error actualizando estados viejos: %s", str(e)[:200])


async def migrar_pedidos_agendado():
    """agrega el estado 'agendado' como valor permitido en pedidos.
    sqlite no tiene check constraints por defecto, asi que solo se asegura
    de que la columna estado exista y se documenta el nuevo estado.
    no hay migracion de datos necesaria."""
    try:
        # agregar columna hora_inicio_programada si no existe
        _migrar_agregar_columna("pedidos", "hora_inicio_programada")
        _migrar_agregar_columna("pedidos", "hora_fin_programada")
        logger.info("migracion de pedidos para agendado completada")
    except Exception as e:
        logger.warning("error en migracion de pedidos: %s", str(e)[:200])


async def migrar_perfiles_roxy():
    """agrega columna liberacion_estimada a perfiles_roxy si es necesario."""
    _migrar_agregar_columna("perfiles_roxy", "liberacion_estimada")
    logger.info("migracion de perfiles_roxy: liberacion_estimada verificada")


async def actualizar_todo():
    """ejecuta todas las migraciones en orden."""
    await crear_tablas_vigilante()
    await migrar_pedidos_agendado()
    await migrar_perfiles_roxy()
    logger.info("migraciones completadas: pedido_asignaciones + pedidos + perfiles_roxy")