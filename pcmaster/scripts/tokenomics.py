# tokenomics.py - logica economica completa kbt: genesis, minado, quema/recoleccion,
# referidos, retiros, happy hour, proyecciones. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

import json
import math
from datetime import datetime, timedelta
from db import ejecutar_sql, ejecutar_sql_unico, ejecutar_insercion, get_db
from variables_globales import (
    k, fx, p_token, h, e, g_default, hh_mult_default,
    comision_marketplace, comision_referido,
    comision_retiro_0_30, comision_retiro_31_60, comision_retiro_61_90, comision_retiro_90_plus,
    limite_retiro_mensual_usd, limite_perfiles_por_pc, mins_validacion_consecutivos,
    bloques_por_perfil_mes, cronograma_g, w_bronce, w_plata, w_oro,
    uptime_niveles, tasa_recoleccion_mensual,
    re_limite_intervencion_mensual, re_excedente_retirable_mensual, re_colchon_estabilidad,
    obtener_variables,
)

# ---------------------------------------------------------------------------
# funciones auxiliares de tiempo
# ---------------------------------------------------------------------------
def _ahora_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _mes_sistema() -> int:
    """calcula el mes del sistema desde la fecha de lanzamiento (2026-06-01)."""
    lanzamiento = datetime(2026, 6, 1)
    delta = datetime.now() - lanzamiento
    return max(1, int(delta.days / 30.44) + 1)

def _g_actual() -> float:
    """devuelve el g actual segun el cronograma."""
    m = _mes_sistema()
    for (ini, fin), valor in cronograma_g.items():
        if ini <= m <= fin:
            return valor
    return 6.0

def _peso_fiabilidad(nivel: str) -> float:
    return uptime_niveles.get(nivel, {}).get("w", w_bronce)

# ---------------------------------------------------------------------------
# distribucion de tokens al streamer (formula p_sys)
# ---------------------------------------------------------------------------
def p_sys_por_seguidores(seguidores: int) -> float:
    """calcula el pago al streamer (p_sys) segun numero de seguidores."""
    from variables_globales import niveles_streamer
    for nivel, data in sorted(niveles_streamer.items(), key=lambda x: x[1]["min"]):
        if data["min"] <= seguidores <= data["max"]:
            return data["p_sys"]
    return 16.0

# ---------------------------------------------------------------------------
# recompensa por granjero (minado de tokens)
# formula: tokens_i = (h_i_ponderadas / suma_ponderadas) * (B * G * FX)
# h_i_ponderadas = w_i * (h_i_normal + HH_mult * h_i_HH)
# ---------------------------------------------------------------------------
def calcular_recompensa_granjero(
    usuario_id: int,
    horas_normales: float,
    horas_hh: float = 0.0,
    hh_mult: float = None,
    g_valor: float = None,
    beta: float = 0.0,
) -> dict:
    """calcula los tokens kbt minados por un granjero en un ciclo (bloque)."""
    if hh_mult is None:
        hh_mult = hh_mult_default
    if g_valor is None:
        g_valor = _g_actual()

    # obtener nivel de fiabilidad del usuario
    usuario = ejecutar_sql_unico("select nivel_fiabilidad from usuarios where id = ?", (usuario_id,))
    nivel = usuario["nivel_fiabilidad"] if usuario else "bronce"
    w = _peso_fiabilidad(nivel)

    # horas ponderadas individuales
    h_ponderadas = w * (horas_normales + hh_mult * horas_hh)

    # obtener suma de horas ponderadas de todos los granjeros activos
    total = ejecutar_sql_unico("select coalesce(sum(horas_conexion), 0) as total from perfiles where estado = 'activo'")
    suma_ponderadas = float(total["total"]) if total else 0.0
    if suma_ponderadas < 0.01:
        suma_ponderadas = horas_normales + horas_hh  # evitar division por cero

    # bloque B = bloques_por_perfil_mes (0.72 por defecto)
    b = bloques_por_perfil_mes
    tokens_crudos = (h_ponderadas / suma_ponderadas) * (b * g_valor * fx)

    # aplicar beta (fraccion en kbt, el resto en fiat) - redundant review
    tokens_netos = tokens_crudos * (1.0 - beta) if beta > 0 else tokens_crudos

    # comision de referido si el usuario fue referido
    referidor = ejecutar_sql_unico("select referido_por, referido_cambiado from usuarios where id = ?", (usuario_id,))
    comision_ref = 0.0
    if referidor and referidor["referido_por"] != "pcmaster" and not referidor["referido_cambiado"]:
        comision_ref = tokens_netos * comision_referido
        # acreditar al referidor
        ref_usuario = ejecutar_sql_unico(
            "select id from usuarios where codigo_referido = ?", (referidor["referido_por"],)
        )
        if ref_usuario:
            ejecutar_sql(
                "update wallets set balance = balance + ? where usuario_id = ?",
                (comision_ref, ref_usuario["id"]),
            )
            ejecutar_insercion(
                "insert into transacciones (origen_id, destino_id, tipo, monto, concepto) values (?, ?, 'comision_referido', ?, ?)",
                (usuario_id, ref_usuario["id"], comision_ref, f"comision referido de usuario {usuario_id}"),
            )
        tokens_netos -= comision_ref

    return {
        "tokens": round(tokens_netos, 8),
        "h_ponderadas": round(h_ponderadas, 4),
        "suma_ponderadas": round(suma_ponderadas, 4),
        "w": w,
        "g": g_valor,
        "comision_referido": round(comision_ref, 8),
    }

# ---------------------------------------------------------------------------
# acreditacion de minado
# ---------------------------------------------------------------------------
def acreditar_minado(usuario_id: int, tokens: float, perfil_id: int = None, concepto: str = "minado"):
    """acredita tokens minados a la wallet del usuario y registra la transaccion."""
    ejecutar_sql("update wallets set balance = balance + ?, minado_total = minado_total + ?, actualizado = ? where usuario_id = ?",
                 (tokens, tokens, _ahora_str(), usuario_id))
    ejecutar_insercion("insert into transacciones (origen_id, destino_id, tipo, monto, concepto) values (null, ?, ?, ?, ?)",
                       (usuario_id, concepto, tokens, f"minado: {tokens} kbt"))

# ---------------------------------------------------------------------------
# recoleccion / quema diaria por inactividad
# ---------------------------------------------------------------------------
def quemar_tokens_inactividad(usuario_id: int, horas_inactivo: float) -> float:
    """quema tokens de la wallet por inactividad (recoleccion). devuelve tokens quemados."""
    if horas_inactivo < 11:
        return 0.0
    wallet = ejecutar_sql_unico("select balance from wallets where usuario_id = ?", (usuario_id,))
    balance = wallet["balance"] if wallet else 0.0
    tasa = tasa_recoleccion_mensual / 100.0  # 5% mensual
    # proporcion diaria: tasa / 30
    quema = balance * (tasa / 30.0) * min(1.0, horas_inactivo / 720.0)
    quema = round(quema, 8)
    if quema > 0 and balance >= quema:
        ejecutar_sql("update wallets set balance = balance - ?, recolectado_total = recolectado_total + ? where usuario_id = ?",
                     (quema, quema, usuario_id))
        # enviar al fondo de recoleccion
        ejecutar_sql("update reserva set tokens = tokens + ? where id = 1", (quema,))
        ejecutar_insercion("insert into transacciones (origen_id, destino_id, tipo, monto, concepto) values (?, null, 'recoleccion', ?, ?)",
                           (usuario_id, quema, f"recoleccion por inactividad: {quema} kbt"))
    return quema

# ---------------------------------------------------------------------------
# retiros
# ---------------------------------------------------------------------------
def solicitar_retiro(usuario_id: int, cantidad_kbt: float) -> dict:
    """solicita un retiro de kbt a pen con comision escalonada."""
    if cantidad_kbt <= 0:
        return {"exito": False, "error": "cantidad invalida"}

    wallet = ejecutar_sql_unico("select balance from wallets where usuario_id = ?", (usuario_id,))
    if not wallet or wallet["balance"] < cantidad_kbt:
        return {"exito": False, "error": "saldo insuficiente"}

    # verificar limite mensual (999 usd equivalente)
    mes_actual = datetime.now().strftime("%Y-%m")
    retiros_mes = ejecutar_sql(
        "select coalesce(sum(cantidad_pen), 0) as total from retiros where usuario_id = ? and fecha_solicitud like ?",
        (usuario_id, f"{mes_actual}%"),
    )
    total_retirado_pen = float(retiros_mes[0]["total"]) if retiros_mes else 0.0
    valor_pen = cantidad_kbt * p_token
    if total_retirado_pen + valor_pen > limite_retiro_mensual_usd:
        return {"exito": False, "error": f"excede el limite mensual de {limite_retiro_mensual_usd} usd"}

    # calcular comision segun antiguedad
    usuario = ejecutar_sql_unico("select fecha_registro from usuarios where id = ?", (usuario_id,))
    dias = 0
    if usuario and usuario["fecha_registro"]:
        try:
            fecha_reg = datetime.strptime(usuario["fecha_registro"], "%Y-%m-%d %H:%M:%S")
            dias = max(0, (datetime.now() - fecha_reg).days)
        except:
            pass

    if dias <= 30:
        comision_pct = comision_retiro_0_30
    elif dias <= 60:
        comision_pct = comision_retiro_31_60
    elif dias <= 90:
        comision_pct = comision_retiro_61_90
    else:
        comision_pct = comision_retiro_90_plus

    comision = round(cantidad_kbt * comision_pct, 8)
    cantidad_neta = round(cantidad_kbt - comision, 8)
    cantidad_pen = round(cantidad_neta * p_token, 2)

    # debitar balance
    ejecutar_sql("update wallets set balance = balance - ?, retirado_total = retirado_total + ? where usuario_id = ?",
                 (cantidad_kbt, cantidad_kbt, usuario_id))
    # crear retiro pendiente
    ejecutar_insercion("insert into retiros (usuario_id, cantidad_kbt, cantidad_pen, comision) values (?, ?, ?, ?)",
                       (usuario_id, cantidad_kbt, cantidad_pen, comision))

    return {"exito": True, "cantidad_kbt": cantidad_kbt, "comision": comision, "cantidad_neta": cantidad_neta, "cantidad_pen": cantidad_pen}

# ---------------------------------------------------------------------------
# genesis - liberacion de etapas
# ---------------------------------------------------------------------------
def verificar_liberacion_genesis() -> list:
    """verifica si alguna etapa genesis debe ser liberada. devuelve lista de etapas liberadas."""
    ahora = datetime.now().strftime("%Y-%m-%d")
    etapas_pendientes = ejecutar_sql(
        "select * from genesis where liberado = 0 and fecha_liberacion <= ?", (ahora,)
    )
    liberadas = []
    for etapa in etapas_pendientes:
        ejecutar_sql("update genesis set liberado = 1 where id = ?", (etapa["id"],))
        ejecutar_sql("update reserva set tokens = tokens + ? where id = 1", (etapa["tokens"],))
        liberadas.append(dict(etapa))
    return liberadas

# ---------------------------------------------------------------------------
# happy hour
# ---------------------------------------------------------------------------
def iniciar_happy_hour(multiplicador: float = 2.0, duracion_horas: int = 2) -> dict:
    """inicia un happy hour con el multiplicador especificado."""
    ahora = datetime.now()
    fin = ahora + timedelta(hours=duracion_horas)
    hh_id = ejecutar_insercion(
        "insert into happy_hour (multiplicador, fecha_inicio, fecha_fin, activo) values (?, ?, ?, 1)",
        (multiplicador, ahora.strftime("%Y-%m-%d %H:%M:%S"), fin.strftime("%Y-%m-%d %H:%M:%S")),
    )
    return {"exito": True, "id": hh_id, "multiplicador": multiplicador, "fin": fin.strftime("%Y-%m-%d %H:%M:%S")}

def hh_activo() -> dict:
    """verifica si hay un happy hour activo. devuelve datos o None."""
    ahora = _ahora_str()
    hh = ejecutar_sql_unico(
        "select * from happy_hour where activo = 1 and fecha_inicio <= ? and fecha_fin >= ? order by id desc limit 1",
        (ahora, ahora),
    )
    return dict(hh) if hh else None

# ---------------------------------------------------------------------------
# fondo de recoleccion y estabilizacion
# ---------------------------------------------------------------------------
def estado_reserva() -> dict:
    """devuelve el estado actual del fondo de reserva."""
    reserva = ejecutar_sql_unico("select * from reserva where id = 1")
    return dict(reserva) if reserva else {"tokens": 0.0, "soles": 0.0}

def estabilizar_precio():
    """logica de estabilizacion: si el precio se desvia de la banda [0.94, 1.06], interviene."""
    # por implementar con oracle de precios externo
    pass

def calcular_excedente_retirable() -> float:
    """calcula el excedente retirable mensual del fondo de recoleccion."""
    reserva = estado_reserva()
    return reserva["tokens"] * re_excedente_retirable_mensual

# ---------------------------------------------------------------------------
# proyecciones a 3, 9 y 18 meses
# ---------------------------------------------------------------------------
def generar_proyecciones() -> dict:
    """genera proyecciones de tokens minados y usuarios a 3, 9 y 18 meses."""
    ahora = datetime.now()
    proyecciones = {}
    for meses in (3, 9, 18):
        fecha_futura = ahora + timedelta(days=int(meses * 30.44))
        # estimar nuevos usuarios (tasa mensual 0.5%)
        usuarios_actuales = ejecutar_sql_unico("select count(*) as c from usuarios where activo = 1")["c"]
        usuarios_estimados = int(usuarios_actuales * (1 + 0.005) ** meses)

        # estimar tokens minados mensuales
        g_futuro = 6.0  # asumir regimen estable para proyecciones > 6 meses
        # usando formula simplificada: tokens_mes = usuarios * perfiles * B * G * FX * E
        perfiles_promedio = min(limite_perfiles_por_pc, 3)
        tokens_por_mes = usuarios_estimados * perfiles_promedio * bloques_por_perfil_mes * g_futuro * fx * e
        tokens_acumulados = tokens_por_mes * meses

        proyecciones[f"{meses}_meses"] = {
            "usuarios_estimados": usuarios_estimados,
            "tokens_minados_estimados": round(tokens_acumulados, 2),
            "tokens_por_mes_estimado": round(tokens_por_mes, 2),
            "fecha_proyeccion": fecha_futura.strftime("%Y-%m-%d"),
            "g_estimado": g_futuro,
        }
    return proyecciones

# ---------------------------------------------------------------------------
# estadisticas generales kbt
# ---------------------------------------------------------------------------
def estadisticas_kbt() -> dict:
    """devuelve estadisticas globales del ecosistema kbt."""
    try:
        with get_db() as conn:
            total_usuarios = conn.execute("select count(*) from usuarios").fetchone()[0]
            total_tokens_minados = conn.execute("select coalesce(sum(minado_total), 0) from wallets").fetchone()[0]
            total_recolectado = conn.execute("select coalesce(sum(recolectado_total), 0) from wallets").fetchone()[0]
            total_retirado = conn.execute("select coalesce(sum(retirado_total), 0) from wallets").fetchone()[0]
            total_staking = conn.execute("select coalesce(sum(staking_total), 0) from wallets").fetchone()[0]
            balance_total = conn.execute("select coalesce(sum(balance), 0) from wallets").fetchone()[0]
            reserva = conn.execute("select tokens from reserva where id = 1").fetchone()
            reserva_tokens = reserva[0] if reserva else 0.0
            total_comandos = conn.execute("select count(*) from comandos").fetchone()[0]
            perfiles_activos = conn.execute("select count(*) from perfiles where estado = 'activo'").fetchone()[0]
    except:
        return {}
    return {
        "total_usuarios": total_usuarios,
        "total_tokens_minados": round(total_tokens_minados, 2),
        "total_recolectado": round(total_recolectado, 2),
        "total_retirado": round(total_retirado, 2),
        "total_staking": round(total_staking, 2),
        "balance_total_sistema": round(balance_total, 2),
        "reserva_tokens": round(reserva_tokens, 2),
        "total_comandos": total_comandos,
        "perfiles_activos": perfiles_activos,
        "mes_sistema": _mes_sistema(),
        "g_actual": _g_actual(),
    }

# ---------------------------------------------------------------------------
# balance de usuario
# ---------------------------------------------------------------------------
def obtener_balance(usuario_id: int) -> dict:
    """obtiene el balance y estadisticas de un usuario especifico."""
    wallet = ejecutar_sql_unico("select * from wallets where usuario_id = ?", (usuario_id,))
    if not wallet:
        return {"balance": 0.0, "minado": 0.0, "recolectado": 0.0, "comprado": 0.0, "retirado": 0.0, "staking": 0.0}
    return {
        "balance": round(wallet["balance"], 8),
        "minado": round(wallet["minado_total"], 8),
        "recolectado": round(wallet["recolectado_total"], 8),
        "comprado": round(wallet["comprado_total"], 8),
        "retirado": round(wallet["retirado_total"], 8),
        "staking": round(wallet["staking_total"], 8),
    }

# ---------------------------------------------------------------------------
# staking
# ---------------------------------------------------------------------------
def iniciar_staking(usuario_id: int, cantidad: float) -> dict:
    """inicia staking por una cantidad de kbt."""
    wallet = ejecutar_sql_unico("select balance from wallets where usuario_id = ?", (usuario_id,))
    if not wallet or wallet["balance"] < cantidad:
        return {"exito": False, "error": "saldo insuficiente"}
    ejecutar_sql("update wallets set balance = balance - ?, staking_total = staking_total + ?, staking_desde = ? where usuario_id = ?",
                 (cantidad, cantidad, _ahora_str(), usuario_id))
    return {"exito": True, "staking": cantidad}

def finalizar_staking(usuario_id: int) -> dict:
    """finaliza el staking y devuelve tokens + recompensa."""
    wallet = ejecutar_sql_unico("select staking_total, staking_desde from wallets where usuario_id = ?", (usuario_id,))
    if not wallet or wallet["staking_total"] <= 0:
        return {"exito": False, "error": "sin staking activo"}
    # calcular recompensa
    desde = datetime.strptime(wallet["staking_desde"], "%Y-%m-%d %H:%M:%S")
    dias = max(0, (datetime.now() - desde).days)
    recompensa = wallet["staking_total"] * 0.05 * (dias / 365.0)
    total = wallet["staking_total"] + recompensa
    ejecutar_sql("update wallets set balance = balance + ?, staking_total = 0, staking_desde = null where usuario_id = ?",
                 (total, usuario_id))
    return {"exito": True, "tokens_devueltos": round(total, 8), "recompensa": round(recompensa, 8), "dias": dias}

# ---------------------------------------------------------------------------
# inicializacion del sistema tokenomics
# ---------------------------------------------------------------------------
def inicializar_tokenomics():
    """inicializa las variables economicas globales en la base de datos."""
    desde = datetime.strptime("2026-06-01", "%Y-%m-%d")
    meses = max(1, int((datetime.now() - desde).days / 30.44) + 1)
    g = _g_actual()
    defaults = {
        "K": "20",
        "FX": "3.70",
        "P_token": "1.00",
        "H": "720",
        "E": "0.005",
        "G": str(g),
        "mes_sistema": str(meses),
        "HH_mult": "2.0",
        "beta": "0.10",
        "comision_marketplace": "0.15",
        "limite_retiro_usd": "999",
        "banda_estabilizacion_min": "0.94",
        "banda_estabilizacion_max": "1.06",
        "tokens_genesis_total": "15000000",
    }
    for clave, valor in defaults.items():
        ejecutar_sql(
            "insert or ignore into variables_globales (clave, valor) values (?, ?)",
            (clave, valor),
        )
    # asegurar registro de reserva
    reserva = ejecutar_sql_unico("select id from reserva where id = 1")
    if not reserva:
        ejecutar_sql("insert into reserva (id, tokens, soles) values (1, 0, 0)")

# ---------------------------------------------------------------------------
# emision administrativa de kbt
# ---------------------------------------------------------------------------
def emitir_kbt_admin(usuario_id: int, cantidad: float, concepto: str = "emision_admin") -> dict:
    """emite kbt administrativamente a un usuario por id. solo para admin."""
    destino = ejecutar_sql_unico("select id from usuarios where id = ?", (usuario_id,))
    if not destino:
        return {"exito": False, "error": "usuario destino no encontrado"}
    ejecutar_sql(
        "update wallets set balance = balance + ?, comprado_total = comprado_total + ? where usuario_id = ?",
        (cantidad, cantidad, destino["id"]),
    )
    # registrar transaccion
    ejecutar_sql(
        "insert into transacciones (origen_id, destino_id, tipo, monto, concepto) values (?, ?, ?, ?, ?)",
        (None, destino["id"], "emision_admin", cantidad, concepto),
    )
    return {"exito": True, "destino_id": usuario_id, "cantidad": cantidad}
