# tasks.py - tareas periodicas del sistema. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

import asyncio
import logging
from datetime import datetime, timedelta

from db import ejecutar_sql, ejecutar_sql_unico, get_db
from tokenomics_tasks import (
    ejecutar_quema_diaria,
    ejecutar_recoleccion_excedente,
    actualizar_fiabilidad_usuarios,
)

logger = logging.getLogger("roxymaster.tasks")


# ---------------------------------------------------------------------------
# configuracion de intervalos
# ---------------------------------------------------------------------------
intervalo_quema_diaria = 86400  # 24 horas
intervalo_limpieza_sesiones = 3600  # 1 hora
intervalo_verificacion_fiabilidad = 43200  # 12 horas
intervalo_actualizacion_uptime = 600  # 10 minutos


# ---------------------------------------------------------------------------
# tareas individuales
# ---------------------------------------------------------------------------
async def tarea_quema_diaria():
    """ejecuta la quema diaria de kbt segun tokenomics."""
    try:
        resultado = ejecutar_quema_diaria()
        logger.info(f"quema diaria ejecutada: {resultado}")
    except Exception as e:
        logger.error(f"error en quema diaria: {e}")


async def tarea_limpieza_sesiones():
    """elimina sesiones expiradas de la base de datos."""
    try:
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        filas = ejecutar_sql(
            "delete from sesiones where fecha_expiracion < ?", (ahora,)
        )
        if filas:
            logger.info(f"limpieza de sesiones: {len(filas) if hasattr(filas, '__len__') else '?'} sesiones eliminadas")
    except Exception as e:
        logger.error(f"error en limpieza de sesiones: {e}")


async def tarea_actualizacion_fiabilidad():
    """recalcula niveles de fiabilidad de usuarios basado en uptime."""
    try:
        actualizar_fiabilidad_usuarios()
        logger.info("fiabilidad de usuarios actualizada")
    except Exception as e:
        logger.error(f"error en actualizacion de fiabilidad: {e}")


async def tarea_actualizacion_uptime():
    """actualiza uptime_horas de usuarios activos."""
    try:
        # sumar 10 minutos (intervalo/3600 horas) a usuarios con sesion activa
        incremento = intervalo_actualizacion_uptime / 3600.0
        ejecutar_sql(
            "update usuarios set uptime_horas = uptime_horas + ? "
            "where modo = 'conectado' and activo = 1",
            (incremento,),
        )
    except Exception as e:
        logger.error(f"error en actualizacion de uptime: {e}")


async def tarea_limpieza_comandos_antiguos():
    """marca como fallidos comandos pendientes con mas de 7 dias."""
    try:
        fecha_limite = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        ejecutar_sql(
            "update comandos set estado = 'expirado', resultado = 'comando expirado tras 7 dias' "
            "where estado = 'pendiente' and fecha_creacion < ?",
            (fecha_limite,),
        )
    except Exception as e:
        logger.error(f"error en limpieza de comandos antiguos: {e}")


async def tarea_sincronizacion_reserva():
    """sincroniza la reserva de estabilizacion."""
    try:
        from tokenomics_tasks import sincronizar_reserva
        sincronizar_reserva()
        logger.info("reserva sincronizada")
    except Exception as e:
        logger.error(f"error en sincronizacion de reserva: {e}")


# ---------------------------------------------------------------------------
# bucle principal de tareas
# ---------------------------------------------------------------------------
async def iniciar_tareas_periodicas():
    """inicia el bucle de tareas periodicas en segundo plano."""
    logger.info("iniciando tareas periodicas...")

    contador_quema = 0
    contador_fiabilidad = 0

    while True:
        try:
            # tareas de alta frecuencia
            await tarea_limpieza_sesiones()
            await tarea_actualizacion_uptime()

            # quema diaria (cada 24h)
            contador_quema += intervalo_limpieza_sesiones
            if contador_quema >= intervalo_quema_diaria:
                await tarea_quema_diaria()
                await tarea_sincronizacion_reserva()
                await tarea_limpieza_comandos_antiguos()
                contador_quema = 0

            # fiabilidad (cada 12h)
            contador_fiabilidad += intervalo_limpieza_sesiones
            if contador_fiabilidad >= intervalo_verificacion_fiabilidad:
                await tarea_actualizacion_fiabilidad()
                contador_fiabilidad = 0

        except Exception as e:
            logger.error(f"error en bucle de tareas: {e}")

        await asyncio.sleep(intervalo_limpieza_sesiones)


# ---------------------------------------------------------------------------
# inicializacion de la base de datos de tareas
# ---------------------------------------------------------------------------
def inicializar_registros_tareas():
    """crea registros iniciales para las tareas si no existen."""
    # asegurar que la tabla variables_globales tenga el estado de tareas
    tareas_default = {
        "ultima_quema_diaria": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ultima_limpieza_sesiones": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ultima_fiabilidad": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tareas_activas": "1",
    }
    for clave, valor in tareas_default.items():
        existente = ejecutar_sql_unico(
            "select valor from variables_globales where clave = ?", (clave,)
        )
        if not existente:
            ejecutar_sql(
                "insert or ignore into variables_globales (clave, valor) values (?, ?)",
                (clave, valor),
            )

    logger.info("registros de tareas inicializados")