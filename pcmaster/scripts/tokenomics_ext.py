# tokenomics_ext.py - tareas periodicas de mineria y recompensas de referidos.
# roxymaster v8.3 - utf-8 sin bom, nombres en minusculas, <= 400 lineas

import logging
from datetime import datetime, timedelta
from db import ejecutar_sql, ejecutar_sql_unico, ejecutar_insercion
from tokenomics_core import minar, _cargar_params

logger = logging.getLogger("roxymaster.tokenomics_ext")


def _ahora_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# mineria: calcular tokens basados en tiempo reportado por heartbeat
# ---------------------------------------------------------------------------
def ejecutar_mineria_ciclo() -> dict:
    """recorre perfiles activos, calcula tokens minados desde ultimo pago y acredita."""
    params = _cargar_params()
    mu = params.get("mu", 0.0222)
    ciclo_minutos = params.get("ciclo_verificacion_minutos", 62)
    ahora = _ahora_str()
    total_acreditado = 0.0
    perfiles_procesados = 0

    perfiles = ejecutar_sql(
        """select pr.id, pr.usuario_id, pr.nombre, pr.tiempo_activo_seg, pr.ultimo_pago,
                  pr.pcbot_id
           from perfiles_roxy pr
           where pr.activo = 1"""
    )

    for p in perfiles:
        try:
            usuario_id = p["usuario_id"]
            segundos = int(p.get("tiempo_activo_seg", 0))
            ultimo_pago = p.get("ultimo_pago")

            if segundos <= 0:
                continue

            # si no hay ultimo_pago, pagar desde el inicio de la sesion
            # si hay ultimo_pago, calcular incremento desde entonces
            if ultimo_pago:
                try:
                    ultimo_dt = datetime.strptime(str(ultimo_pago), "%Y-%m-%d %H:%M:%S")
                    ahora_dt = datetime.now()
                    delta_seg = (ahora_dt - ultimo_dt).total_seconds()
                    if delta_seg < 60:
                        continue  # menos de 1 minuto, no pagar aun
                    segundos_a_pagar = min(delta_seg, segundos)
                except (ValueError, TypeError):
                    segundos_a_pagar = segundos
            else:
                segundos_a_pagar = segundos

            if segundos_a_pagar <= 0:
                continue

            horas = segundos_a_pagar / 3600.0
            tokens = round(mu * horas, 8)

            if tokens <= 0:
                continue

            # acreditar tokens al usuario
            ejecutar_sql(
                "update wallets set balance = balance + ?, minado_total = minado_total + ? "
                "where usuario_id = ?",
                (tokens, tokens, usuario_id),
            )

            # registrar transaccion de minado
            ejecutar_insercion(
                "insert into transacciones (origen_id, destino_id, tipo, monto, concepto, fecha) "
                "values (?, ?, 'minado', ?, ?, ?)",
                (usuario_id, usuario_id, tokens,
                 f"mineria perfil {p['nombre']}: {round(horas, 4)}h = {tokens} tokens",
                 ahora),
            )

            # actualizar ultimo_pago
            ejecutar_sql(
                "update perfiles_roxy set ultimo_pago = ? where id = ?",
                (ahora, p["id"]),
            )

            total_acreditado += tokens
            perfiles_procesados += 1
            logger.debug(f"mineria: usuario {usuario_id} perfil {p['nombre']} +{tokens} tokens ({round(horas,4)}h)")

        except Exception as e:
            logger.error(f"error mineria perfil {p.get('id')}: {e}")

    logger.info(f"mineria ciclo: {perfiles_procesados} perfiles, {round(total_acreditado, 8)} tokens acreditados")
    return {
        "perfiles_procesados": perfiles_procesados,
        "tokens_acreditados": round(total_acreditado, 8),
    }


# ---------------------------------------------------------------------------
# recompensas de referidos: 10% de tokens minados al referidor
# ---------------------------------------------------------------------------
def ejecutar_recompensas_referidos() -> dict:
    """por cada perfil referido que estuvo activo, da 10% de tokens al referidor."""
    ahora = _ahora_str()
    total_referido = 0.0
    relaciones_procesadas = 0

    # buscar perfiles que esten vinculados a un codigo de referido
    perfiles = ejecutar_sql(
        """select pr.id, pr.usuario_id as granjero_id, pr.nombre,
                  pr.tiempo_activo_seg, pr.ultimo_pago,
                  pf.referido_por_usuario_id as referidor_id
           from perfiles_roxy pr
           join perfiles_referidos pf on pf.perfil_id = pr.id
           where pr.activo = 1
             and pf.referido_por_usuario_id is not null"""
    )

    for p in perfiles:
        try:
            referidor_id = p["referidor_id"]
            granjero_id = p["granjero_id"]
            segundos = int(p.get("tiempo_activo_seg", 0))
            ultimo_pago = p.get("ultimo_pago")

            if segundos <= 0 or not referidor_id:
                continue

            if ultimo_pago:
                try:
                    ultimo_dt = datetime.strptime(str(ultimo_pago), "%Y-%m-%d %H:%M:%S")
                    ahora_dt = datetime.now()
                    delta_seg = (ahora_dt - ultimo_dt).total_seconds()
                    if delta_seg < 60:
                        continue
                    segundos_a_pagar = min(delta_seg, segundos)
                except (ValueError, TypeError):
                    segundos_a_pagar = segundos
            else:
                segundos_a_pagar = segundos

            if segundos_a_pagar <= 0:
                continue

            horas = segundos_a_pagar / 3600.0
            tokens_minados = minar(1, horas)
            tokens_referido = round(tokens_minados * 0.10, 8)

            if tokens_referido <= 0:
                continue

            # acreditar al referidor
            ejecutar_sql(
                "update wallets set balance = balance + ?, minado_total = minado_total + ? "
                "where usuario_id = ?",
                (tokens_referido, tokens_referido, referidor_id),
            )

            ejecutar_insercion(
                "insert into transacciones (origen_id, destino_id, tipo, monto, concepto, fecha) "
                "values (?, ?, 'referido', ?, ?, ?)",
                (granjero_id, referidor_id, tokens_referido,
                 f"recompensa referido perfil {p['nombre']}: {tokens_referido} tokens",
                 ahora),
            )

            total_referido += tokens_referido
            relaciones_procesadas += 1

        except Exception as e:
            logger.error(f"error recompensa referido perfil {p.get('id')}: {e}")

    logger.info(f"recompensas referidos: {relaciones_procesadas} relaciones, {round(total_referido, 8)} tokens")
    return {
        "relaciones_procesadas": relaciones_procesadas,
        "tokens_referidos": round(total_referido, 8),
    }