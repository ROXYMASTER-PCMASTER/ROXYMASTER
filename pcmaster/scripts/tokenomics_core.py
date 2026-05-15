# tokenomics_core.py - parte principal del modulo tokenomics. roxymaster v8.3
# economia completa kbt con mineria, pedidos, retiros, referidos
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

import json
import math
import logging
from datetime import datetime, timedelta

from db import ejecutar_sql, ejecutar_sql_unico, ejecutar_insercion

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# variables globales (hardcodeadas, editables por dueno via db tabla variables_globales)
# ---------------------------------------------------------------------------
ECONOMY_PARAMS = {
    "K": "20.0",
    "P_farm": "6.0",        # usd por cada 1000 espectadores-hora
    "mu": "0.0222",         # tokens/h-perfil (derivado de P_farm / P_token / T_cambio)
    "P_token": "1.0",       # soles/token
    "c_elec": "0.65",       # s/kwh
    "w": "0.005",           # kw por perfil
    "T_cambio": "3.7",      # s/usd
    "bonus_120": "0.05",    # 5% bonus por retiros a 120 dias
    "porcentaje_referido": "0.10",  # 10% para el referidor
    "ciclo_verificacion_minutos": "62",
    "tasa_impuesto": "0.08",
    "limite_max_venta_hora": "0.10",
    "limite_caida_precio": "0.30",
    "alpha_levels": json.dumps([
        [0, 5000, 0.45],
        [5000, 15000, 0.50],
        [15000, 50000, 0.55],
        [50000, 500000, 0.60],
        [500000, 1000000, 0.65],
        [1000000, 999999999, 0.70],
    ]),
    "comisiones_retiro": json.dumps({
        "0": 0.33,
        "15": 0.25,
        "30": 0.15,
        "60": 0.05,
        "90": 0.0,
    }),
}

# ---------------------------------------------------------------------------
# recargos configurables para pedidos
# ---------------------------------------------------------------------------
RECARGO_COMENTARISTA_IA = 1.15  # 15% extra por comentarista ia
RECARGO_PROGRAMACION = 1.10     # 10% extra por programacion horaria

# ---------------------------------------------------------------------------
# cache en memoria para evitar consultas repetitivas a db
# ---------------------------------------------------------------------------
_params_cache = None
_params_cache_time = 0

def _invalidar_cache():
    """invalidate cache forzar recarga en proxima llamada."""
    global _params_cache, _params_cache_time
    _params_cache = None
    _params_cache_time = 0

# ---------------------------------------------------------------------------
# carga parametros desde bd (sobrescribe valores hardcodeados)
# ---------------------------------------------------------------------------
def _cargar_params() -> dict:
    """carga variables_globales desde db y las mezcla con ECONOMY_PARAMS.
    usa cache de 60 segundos para no saturar db."""
    global _params_cache, _params_cache_time
    ahora = datetime.now().timestamp()
    if _params_cache is not None and ahora - _params_cache_time < 60:
        return _params_cache
    params = dict(ECONOMY_PARAMS)
    try:
        rows = ejecutar_sql("select clave, valor from variables_globales")
        for r in rows:
            params[r["clave"]] = r["valor"]
    except Exception as e:
        logger.warning(f"no se pudieron cargar variables_globales: {e}")
    _params_cache = params
    _params_cache_time = ahora
    return params

def _get_param(clave: str, tipo=float):
    """obtiene un parametro, casteado al tipo indicado."""
    p = _cargar_params()
    val = p.get(clave, ECONOMY_PARAMS.get(clave, "0"))
    if tipo == float:
        return float(val)
    elif tipo == int:
        return int(float(val))
    return val

def _ahora_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ---------------------------------------------------------------------------
# alpha: factor segun tabla de seguidores
# ---------------------------------------------------------------------------
def alpha(seguidores: int) -> float:
    """devuelve el factor alpha segun el numero de seguidores del streamer.
    los intervalos son [min, max) excepto el ultimo que es [min, inf]."""
    levels_json = _get_param("alpha_levels", str)
    try:
        levels = json.loads(levels_json)
    except:
        levels = [[0, 5000, 0.45], [5000, 15000, 0.50], [15000, 50000, 0.55],
                  [50000, 500000, 0.60], [500000, 1000000, 0.65],
                  [1000000, 999999999, 0.70]]
    for mini, maxi, factor in levels:
        # ultimo rango: incluimos el maximo
        if maxi == 999999999:
            if seguidores >= mini:
                return float(factor)
        # rangos intermedios: [mini, maxi)
        elif mini <= seguidores < maxi:
            return float(factor)
    return 0.45

# ---------------------------------------------------------------------------
# p_sys: pago al streamer (por cada 1000 seguidores-hora)
# ---------------------------------------------------------------------------
def P_sys(seguidores: int) -> float:
    """retorna el pago al streamer por cada 1000 seguidores-hora: k * alpha(seguidores)."""
    k = _get_param("K")
    return k * alpha(seguidores)

# ---------------------------------------------------------------------------
# calcular_costo_streamer: costo total en usd, soles y tokens
# ---------------------------------------------------------------------------
def calcular_costo_streamer(seguidores: int, perfiles: int, horas: float) -> dict:
    """calcula el costo de un pedido de servicio para un streamer.
    p_sys es usd por cada 1000 seguidores-hora.
    devuelve {usd, soles, tokens}."""
    p_sys_val = P_sys(seguidores)
    # costo usd = p_sys * perfiles * horas / 1000  (porque p_sys es por 1000 seguidores-hora)
    costo_usd = p_sys_val * perfiles * horas / 1000.0
    t_cambio = _get_param("T_cambio")
    p_token = _get_param("P_token")
    costo_soles = costo_usd * t_cambio
    costo_tokens = costo_soles / p_token if p_token > 0 else 0
    return {
        "usd": round(costo_usd, 2),
        "soles": round(costo_soles, 2),
        "tokens": round(costo_tokens, 8),
    }

# ---------------------------------------------------------------------------
# mineria para granjeros
# ---------------------------------------------------------------------------
def minar(perfiles: int, horas: float) -> float:
    """calcula tokens minados: mu * perfiles * horas."""
    mu = _get_param("mu")
    return round(mu * perfiles * horas, 8)

# ---------------------------------------------------------------------------
# costo electrico
# ---------------------------------------------------------------------------
def costo_electrico(perfiles: int, horas: float) -> float:
    """calcula el costo electrico en soles."""
    c_elec = _get_param("c_elec")
    w = _get_param("w")
    return round(c_elec * w * perfiles * horas, 6)

# ---------------------------------------------------------------------------
# ganancia neta del granjero
# ---------------------------------------------------------------------------
def ganancia_neta_granjero(perfiles: int, horas: float) -> float:
    """calcula la ganancia neta en soles del granjero."""
    tokens = minar(perfiles, horas)
    p_token = _get_param("P_token")
    ingreso = tokens * p_token
    costo = costo_electrico(perfiles, horas)
    return round(ingreso - costo, 6)

# ---------------------------------------------------------------------------
# comision de retiro segun dias
# ---------------------------------------------------------------------------
def comision_retiro(dias: int) -> float:
    """devuelve la comision segun el plazo en dias."""
    comisiones_json = _get_param("comisiones_retiro", str)
    try:
        comisiones = json.loads(comisiones_json)
    except:
        comisiones = {"0": 0.33, "15": 0.25, "30": 0.15, "60": 0.05, "90": 0.0}
    # ordenar umbrales de mayor a menor
    umbrales = sorted([int(k) for k in comisiones.keys()], reverse=True)
    for u in umbrales:
        if dias >= u:
            return float(comisiones[str(u)])
    return 0.33

# ---------------------------------------------------------------------------
# calcular retiro: monto neto en soles
# ---------------------------------------------------------------------------
def calcular_retiro(tokens: float, dias: int) -> dict:
    """calcula el monto neto de un retiro tras aplicar comision, impuesto y bonificacion.
    devuelve dict con monto_bruto_soles, comision_soles, impuesto_soles,
    bonificacion_soles, monto_neto_soles, comision_pct."""
    p_token = _get_param("P_token")
    tasa_impuesto = _get_param("tasa_impuesto")
    bonus_120 = _get_param("bonus_120")

    comision_pct = comision_retiro(dias)
    monto_bruto_soles = tokens * p_token
    comision_soles = round(monto_bruto_soles * comision_pct, 2)
    subtotal = round(monto_bruto_soles - comision_soles, 2)
    impuesto_soles = round(subtotal * tasa_impuesto, 2)

    # bonificacion por 120+ dias
    bonificacion_soles = 0.0
    if dias >= 120:
        bonificacion_soles = round(subtotal * bonus_120, 2)

    # impuesto se aplica sobre (subtotal + bonificacion)
    base_impuesto = subtotal + bonificacion_soles
    impuesto_soles = round(base_impuesto * tasa_impuesto, 2)

    monto_neto_soles = round(base_impuesto - impuesto_soles, 2)
    return {
        "monto_bruto_soles": monto_bruto_soles,
        "comision_soles": comision_soles,
        "impuesto_soles": impuesto_soles,
        "bonificacion_soles": bonificacion_soles,
        "monto_neto_soles": monto_neto_soles,
        "comision_pct": comision_pct,
    }

# ---------------------------------------------------------------------------
# obtener balance de usuario
# ---------------------------------------------------------------------------
def obtener_balance(usuario_id: int) -> dict:
    """obtiene balance de wallets."""
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