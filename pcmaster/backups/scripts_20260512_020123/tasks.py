# tasks.py - tareas periodicas del sistema. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

import asyncio
import logging
from datetime import datetime, timedelta

from db import ejecutar_sql, ejecutar_sql_unico, ejecutar_insercion, get_db_context
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
intervalo_mineria = 3720  # 62 minutos


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
            logger.info(f"limpieza de sesiones: eliminadas")
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
# tarea de mineria: calcular tokens basados en tiempo reportado en heartbeats
# ---------------------------------------------------------------------------
async def tarea_mineria():
    """recorre perfiles activos, calcula tokens minados desde ultimo pago y acredita.
    se ejecuta cada 62 minutos (intervalo_mineria).
    cada perfil con activo=1 obtiene mu tokens por hora de conexion."""
    try:
        ahora = datetime.now()
        ahora_str = ahora.strftime("%Y-%m-%d %H:%M:%S")

        # obtener mu de economia_params (con fallback)
        mu = 0.0222
        try:
            row = ejecutar_sql_unico(
                "select valor from variables_globales where clave = 'mu'"
            )
            if row:
                mu = float(row["valor"])
        except Exception:
            pass

        # obtener perfiles activos con su ultimo pago
        perfiles = ejecutar_sql(
            """select pr.id, pr.usuario_id, pr.tiempo_activo_seg, pr.ultimo_pago,
                      pr.activo, pr.pcbot_id
               from perfiles_roxy pr
               where pr.activo = 1"""
        )

        acreditados = 0
        for perfil in perfiles:
            try:
                perfil_id = perfil["id"]
                usuario_id = perfil["usuario_id"]
                tiempo_activo_seg = perfil["tiempo_activo_seg"] or 0
                ultimo_pago = perfil["ultimo_pago"]

                # calcular segundos desde ultimo pago
                if ultimo_pago:
                    try:
                        ultimo = datetime.strptime(str(ultimo_pago), "%Y-%m-%d %H:%M:%S")
                        delta_seg = (ahora - ultimo).total_seconds()
                    except Exception:
                        delta_seg = tiempo_activo_seg  # fallback: usar tiempo_activo_seg total
                else:
                    # primer pago: usar tiempo_activo_seg acumulado
                    delta_seg = tiempo_activo_seg

                # no pagar si no hay tiempo nuevo
                if delta_seg <= 0:
                    continue

                # convertir a horas y calcular tokens
                horas = delta_seg / 3600.0
                tokens_minados = mu * horas

                # acreditar al usuario en kbt_balances
                if tokens_minados > 0:
                    # verificar si existe balance
                    balance = ejecutar_sql_unico(
                        "select id from kbt_balances where usuario_id = ?", (usuario_id,)
                    )
                    if balance:
                        ejecutar_sql(
                            "update kbt_balances set balance = balance + ? where usuario_id = ?",
                            (tokens_minados, usuario_id),
                        )
                    else:
                        ejecutar_insercion(
                            "insert into kbt_balances (usuario_id, balance, congelado) values (?, ?, 0)",
                            (usuario_id, tokens_minados),
                        )

                    # registrar transaccion
                    ejecutar_insercion(
                        """insert into transacciones_kbt
                           (usuario_id, tipo, cantidad, saldo_resultante, descripcion, fecha)
                           select ?, 'mineria', ?, balance, ?, ?
                           from kbt_balances where usuario_id = ?""",
                        (usuario_id, tokens_minados,
                         f"mineria perfil {perfil_id}", ahora_str, usuario_id),
                    )

                    # actualizar ultimo_pago
                    ejecutar_sql(
                        "update perfiles_roxy set ultimo_pago = ? where id = ?",
                        (ahora_str, perfil_id),
                    )

                    acreditados += 1
                    logger.debug(
                        f"mineria: perfil {perfil_id} -> usuario {usuario_id}: "
                        f"{tokens_minados:.6f} tokens ({delta_seg:.0f}s)"
                    )

            except Exception as e:
                logger.warning(f"error minando perfil {perfil.get('id', '?' )}: {e}")

        logger.info(f"mineria completada: {acreditados} perfiles acreditados")

    except Exception as e:
        logger.error(f"error en tarea de mineria: {e}")


# ---------------------------------------------------------------------------
# tarea de recompensa por referidos
# ---------------------------------------------------------------------------
async def tarea_recompensa_referidos():
    """cada 62 minutos, verifica perfiles referidos conectados >= 62 min
    y acredita 10% de tokens minados al referidor."""
    try:
        ahora = datetime.now()
        ahora_str = ahora.strftime("%Y-%m-%d %H:%M:%S")

        # obtener porcentaje_referido de variables_globales (default 0.10)
        prc_ref = 0.10
        try:
            row = ejecutar_sql_unico(
                "select valor from variables_globales where clave = 'porcentaje_referido'"
            )
            if row:
                prc_ref = float(row["valor"])
        except Exception:
            pass

        # obtener mu
        mu = 0.0222
        try:
            row = ejecutar_sql_unico(
                "select valor from variables_globales where clave = 'mu'"
            )
            if row:
                mu = float(row["valor"])
        except Exception:
            pass

        # buscar perfiles referidos activos con tiempo_activo_seg >= 3720 (62 min)
        perfiles_ref = ejecutar_sql(
            """select pr.id as perfil_id, pr.usuario_id as granjero_id,
                      pr.tiempo_activo_seg, pr.ultimo_pago,
                      pref.referido_por_usuario_id as referidor_id
               from perfiles_roxy pr
               join perfiles_referidos pref on pref.perfil_id = pr.id
               where pr.activo = 1
                 and pr.tiempo_activo_seg >= 3720"""
        )

        recompensados = 0
        for pf in perfiles_ref:
            try:
                perfil_id = pf["perfil_id"]
                referidor_id = pf["referidor_id"]

                # calcular tokens minados desde ultima recompensa
                ultimo_pago = pf["ultimo_pago"]
                if ultimo_pago:
                    try:
                        ultimo = datetime.strptime(str(ultimo_pago), "%Y-%m-%d %H:%M:%S")
                        delta_seg = (ahora - ultimo).total_seconds()
                    except Exception:
                        delta_seg = 3720  # fallback: 62 min
                else:
                    delta_seg = 3720

                if delta_seg <= 0:
                    delta_seg = 3720

                horas = delta_seg / 3600.0
                tokens_minados = mu * horas
                recompensa = tokens_minados * prc_ref

                if recompensa > 0:
                    # acreditar al referidor
                    balance_ref = ejecutar_sql_unico(
                        "select id from kbt_balances where usuario_id = ?", (referidor_id,)
                    )
                    if balance_ref:
                        ejecutar_sql(
                            "update kbt_balances set balance = balance + ? where usuario_id = ?",
                            (recompensa, referidor_id),
                        )
                    else:
                        ejecutar_insercion(
                            "insert into kbt_balances (usuario_id, balance, congelado) values (?, ?, 0)",
                            (referidor_id, recompensa),
                        )

                    # registrar transaccion
                    ejecutar_insercion(
                        """insert into transacciones_kbt
                           (usuario_id, tipo, cantidad, saldo_resultante, descripcion, fecha)
                           select ?, 'referido', ?, balance, ?, ?
                           from kbt_balances where usuario_id = ?""",
                        (referidor_id, recompensa,
                         f"recompensa referido perfil {perfil_id}", ahora_str, referidor_id),
                    )

                    recompensados += 1
                    logger.debug(
                        f"referido: perfil {perfil_id} -> referidor {referidor_id}: "
                        f"{recompensa:.6f} tokens"
                    )

            except Exception as e:
                logger.warning(f"error recompensa referido {pf.get('perfil_id', '?')}: {e}")

        logger.info(f"recompensa referidos completada: {recompensados} recompensas")

    except Exception as e:
        logger.error(f"error en tarea de recompensa referidos: {e}")


# ---------------------------------------------------------------------------
# bucle principal de tareas
# ---------------------------------------------------------------------------
async def iniciar_tareas_periodicas():
    """inicia el bucle de tareas periodicas en segundo plano."""
    logger.info("iniciando tareas periodicas...")

    contador_quema = 0
    contador_fiabilidad = 0
    contador_mineria = 0

    while True:
        try:
            # tareas de alta frecuencia (cada hora)
            await tarea_limpieza_sesiones()
            await tarea_actualizacion_uptime()

            # mineria cada 62 min (~3720s)
            contador_mineria += intervalo_limpieza_sesiones
            if contador_mineria >= intervalo_mineria:
                await tarea_mineria()
                await tarea_recompensa_referidos()
                contador_mineria = 0

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