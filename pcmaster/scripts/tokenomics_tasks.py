# tokenomics_tasks.py - funciones de tareas periodicas delegadas desde tokenomics.
# roxymaster v8.3 - todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

import logging
from datetime import datetime, timedelta

from db import ejecutar_sql, ejecutar_sql_unico
from variables_globales import (
    tasa_recoleccion_mensual,
    uptime_niveles,
    w_bronce,
    w_plata,
    w_oro,
)

logger = logging.getLogger("roxymaster.tokenomics_tasks")


# ---------------------------------------------------------------------------
# quema diaria por inactividad en todos los usuarios
# ---------------------------------------------------------------------------
def ejecutar_quema_diaria() -> dict:
    """ejecuta la quema diaria de kbt para todos los usuarios inactivos."""
    usuarios = ejecutar_sql(
        "select u.id, w.balance, u.uptime_horas "
        "from usuarios u join wallets w on w.usuario_id = u.id "
        "where u.activo = 1 and w.balance > 0"
    )
    total_quemado = 0.0
    usuarios_afectados = 0
    for u in usuarios:
        horas_inactivo = max(0, 24 - float(u.get("uptime_horas", 0)))
        if horas_inactivo < 11:
            continue
        balance = float(u.get("balance", 0))
        tasa_diaria = (tasa_recoleccion_mensual / 100.0) / 30.0
        quema = round(balance * tasa_diaria * min(1.0, horas_inactivo / 720.0), 8)
        if quema > 0 and balance >= quema:
            ejecutar_sql(
                "update wallets set balance = balance - ?, recolectado_total = recolectado_total + ? "
                "where usuario_id = ?",
                (quema, quema, u["id"]),
            )
            ejecutar_sql("update reserva set tokens = tokens + ? where id = 1", (quema,))
            ejecutar_sql(
                "insert into transacciones (origen_id, destino_id, tipo, monto, concepto) "
                "values (?, null, 'recoleccion', ?, ?)",
                (u["id"], quema, f"quema diaria por inactividad: {quema} kbt"),
            )
            total_quemado += quema
            usuarios_afectados += 1
    logger.info(f"quema diaria: {total_quemado} tokens quemados de {usuarios_afectados} usuarios")
    return {"tokens_quemados": round(total_quemado, 8), "usuarios_afectados": usuarios_afectados}


# ---------------------------------------------------------------------------
# recoleccion de excedente del fondo de reserva
# ---------------------------------------------------------------------------
def ejecutar_recoleccion_excedente() -> dict:
    """ejecuta la recoleccion de excedente del fondo de estabilizacion."""
    reserva = ejecutar_sql_unico("select * from reserva where id = 1")
    if not reserva:
        return {"exito": False, "error": "reserva no encontrada"}
    tokens = float(reserva.get("tokens", 0))
    soles = float(reserva.get("soles", 0))
    return {
        "exito": True,
        "tokens_reserva": round(tokens, 8),
        "soles_reserva": round(soles, 2),
    }


# ---------------------------------------------------------------------------
# actualizacion de niveles de fiabilidad basado en uptime
# ---------------------------------------------------------------------------
def actualizar_fiabilidad_usuarios() -> dict:
    """recalcula niveles de fiabilidad (bronce, plata, oro) basado en uptime_horas."""
    usuarios = ejecutar_sql(
        "select id, uptime_horas, nivel_fiabilidad from usuarios where activo = 1"
    )
    actualizados = {"bronce": 0, "plata": 0, "oro": 0}
    for u in usuarios:
        horas = float(u.get("uptime_horas", 0))
        nuevo_nivel = "bronce"
        if horas >= uptime_niveles["oro"]["min_horas"]:
            nuevo_nivel = "oro"
        elif horas >= uptime_niveles["plata"]["min_horas"]:
            nuevo_nivel = "plata"
        actual = u.get("nivel_fiabilidad", "bronce")
        if nuevo_nivel != actual:
            ejecutar_sql(
                "update usuarios set nivel_fiabilidad = ? where id = ?",
                (nuevo_nivel, u["id"]),
            )
            actualizados[nuevo_nivel] += 1
    logger.info(f"fiabilidad actualizada: {actualizados}")
    return actualizados


# ---------------------------------------------------------------------------
# sincronizacion de la reserva de estabilizacion
# ---------------------------------------------------------------------------
def sincronizar_reserva() -> dict:
    """sincroniza la reserva con las variables globales de estabilizacion."""
    reserva = ejecutar_sql_unico("select * from reserva where id = 1")
    if not reserva:
        ejecutar_sql("insert into reserva (id, tokens, soles) values (1, 0, 0)")
        return {"exito": True, "accion": "reserva creada"}
    tokens = float(reserva.get("tokens", 0))
    # verificar si hay genesis pendiente por liberar
    ahora = datetime.now().strftime("%Y-%m-%d")
    genesis_pendiente = ejecutar_sql(
        "select * from genesis where liberado = 0 and fecha_liberacion <= ?", (ahora,)
    )
    for etapa in genesis_pendiente:
        ejecutar_sql("update genesis set liberado = 1 where id = ?", (etapa["id"],))
        ejecutar_sql("update reserva set tokens = tokens + ? where id = 1", (etapa["tokens"],))
        tokens += float(etapa["tokens"])
        logger.info(f"genesis etapa {etapa['etapa']} liberada: {etapa['tokens']} tokens")
    return {"exito": True, "tokens_reserva": round(tokens, 8)}