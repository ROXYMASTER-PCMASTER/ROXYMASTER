# variables_globales.py - constantes del sistema y parametros kbt para roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom
# todas las variables economicas configurables desde el dashboard de administrador

import json
import sqlite3
from config_loader import ruta_db

# ---------------------------------------------------------------------------
# constantes kbt inmutables (segun documento oficial)
# ---------------------------------------------------------------------------
k = 20.00                        # usd que kick paga al streamer por 1000 espectadores-hora
fx = 3.70                        # pen por usd (tipo de cambio fijo)
p_token = 1.00                   # precio ancla del token en pen
h = 720                          # horas por mes estandar
e = 0.005                        # factor de emision mensual

# ---------------------------------------------------------------------------
# parametros economicos predeterminados (configurables via dashboard admin)
# ---------------------------------------------------------------------------
g_default = 9.00                 # pago a granjeros por bloque (usd) - valor inicial
beta_default = 0.0               # fraccion de pagos de streamers en kbt (0=todo fiat)
hh_mult_default = 2.0            # multiplicador de happy hour
alfa_nuevo = 0.5                 # fraccion de pago a streamer nuevo
gamma = 0.5                      # potencia de escala de seguidores

# comisiones del sistema
comision_marketplace = 0.15      # 15% para el sistema en transacciones p2p
comision_referido = 0.10         # 10% de tokens minados del referido acreditados al referidor

# comisiones de retiro escalonadas por antiguedad
comision_retiro_0_30 = 0.33      # retiro en primeros 30 dias
comision_retiro_31_60 = 0.25     # retiro entre 31-60 dias
comision_retiro_61_90 = 0.15     # retiro entre 61-90 dias
comision_retiro_90_plus = 0.00   # retiro despues de 90 dias
limite_retiro_mensual_usd = 999.0  # limite mensual de retiro por cuenta

# niveles de streamer (seguidores -> p_sys en usd)
niveles_streamer = {
    0: {"min": 0,        "max": 4999,      "p_sys": 9.00},
    1: {"min": 5000,     "max": 14999,     "p_sys": 10.00},
    2: {"min": 15000,    "max": 49999,     "p_sys": 11.00},
    3: {"min": 50000,    "max": 499999,    "p_sys": 12.00},
    4: {"min": 500000,   "max": 999999,    "p_sys": 14.00},
    5: {"min": 1000000,  "max": 999999999, "p_sys": 16.00},
}

# niveles de fiabilidad (uptime) y pesos asociados
w_bronce = 1.1
w_plata = 1.2
w_oro = 1.3

uptime_niveles = {
    "bronce": {"min": 0.90, "w": w_bronce},
    "plata":  {"min": 0.95, "w": w_plata},
    "oro":    {"min": 0.99, "w": w_oro},
}

# cronograma de g (pago a granjeros en usd segun mes del sistema)
cronograma_g = {
    (1, 3): 9.00,     # mes 1-3: atraccion agresiva
    (4, 6): 7.50,     # mes 4-6: transicion
    (7, 999): 6.00,   # mes 7+: equilibrio sostenible
}

# parametros de happy hour
hh_duracion_min = 60              # minutos minimos
hh_duracion_max = 240             # minutos maximos
hh_anuncio_horas = 24             # horas de anticipacion del anuncio

# recoleccion / penalizacion por inactividad
tasa_recoleccion_mensual = 5.0    # porcentaje mensual a recolectar por inactividad
penalizacion_inactividad_porcentaje = 0.05
tolerancia_reinicio_minutos = 30
ventana_penalizacion_dias = 7
horas_inactividad_dispara = 11
mins_validacion_consecutivos = 62
gracia_oro_desconexion_min = 30
duracion_penalizacion_dias = 30

# limites del sistema
limite_perfiles_por_pc = 5
bloques_por_perfil_mes = 0.72

# fondo de recoleccion (re_tokens / re_soles)
re_limite_intervencion_mensual = 0.10
re_excedente_retirable_mensual = 0.01
re_colchon_estabilidad = 0.20

# staking
staking_recompensa_anual = 0.05   # 5% anual

# ---------------------------------------------------------------------------
# diccionario completo de parametros para el dashboard admin
# ---------------------------------------------------------------------------
parametros_kbt_predeterminados = {
    "k": k,
    "fx": fx,
    "p_token": p_token,
    "banda_min": 0.94,
    "banda_max": 1.06,
    "h": h,
    "e": e,
    "g_default": g_default,
    "g_mes_1_3": 9.00,
    "g_mes_4_6": 7.50,
    "g_mes_7_adelante": 6.00,
    "beta": beta_default,
    "alfa_nuevo": alfa_nuevo,
    "gamma": gamma,
    "comision_marketplace": comision_marketplace,
    "comision_retiro_0_30": comision_retiro_0_30,
    "comision_retiro_31_60": comision_retiro_31_60,
    "comision_retiro_61_90": comision_retiro_61_90,
    "comision_retiro_90_plus": comision_retiro_90_plus,
    "comision_referido": comision_referido,
    "limite_retiro_mensual_usd": limite_retiro_mensual_usd,
    "limite_perfiles_por_pc": limite_perfiles_por_pc,
    "hh_mult": hh_mult_default,
    "hh_duracion_min": hh_duracion_min,
    "hh_duracion_max": hh_duracion_max,
    "hh_anuncio_horas": hh_anuncio_horas,
    "nivel_bronce_uptime": 0.90,
    "nivel_plata_uptime": 0.95,
    "nivel_oro_uptime": 0.99,
    "w_bronce": w_bronce,
    "w_plata": w_plata,
    "w_oro": w_oro,
    "penalizacion_inactividad_porcentaje": penalizacion_inactividad_porcentaje,
    "tolerancia_reinicio_minutos": tolerancia_reinicio_minutos,
    "ventana_penalizacion_dias": ventana_penalizacion_dias,
    "horas_inactividad_dispara": horas_inactividad_dispara,
    "mins_validacion_consecutivos": mins_validacion_consecutivos,
    "gracia_oro_desconexion_min": gracia_oro_desconexion_min,
    "duracion_penalizacion_dias": duracion_penalizacion_dias,
    "staking_recompensa_anual": staking_recompensa_anual,
    "re_limite_intervencion_mensual": re_limite_intervencion_mensual,
    "re_excedente_retirable_mensual": re_excedente_retirable_mensual,
    "re_colchon_estabilidad": re_colchon_estabilidad,
    "bloques_por_perfil_mes": bloques_por_perfil_mes,
    "tasa_recoleccion_mensual": tasa_recoleccion_mensual,
    "niveles_streamer": niveles_streamer,
}


# ---------------------------------------------------------------------------
# gestion dinamica de variables desde la base de datos (dashboard admin)
# ---------------------------------------------------------------------------
def obtener_variables() -> dict:
    """devuelve todas las variables kbt desde la base de datos, fusionadas con predeterminados."""
    resultado = dict(parametros_kbt_predeterminados)
    try:
        conn = sqlite3.connect(ruta_db)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("select clave, valor from variables_globales")
        rows = {r["clave"]: r["valor"] for r in cursor.fetchall()}
        conn.close()
        for k, v in rows.items():
            try:
                resultado[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                resultado[k] = v
    except sqlite3.OperationalError:
        pass  # tabla no existe aun, devolver predeterminados
    return resultado


def actualizar_variable(clave: str, valor) -> bool:
    """actualiza una variable global en la base de datos. devuelve True si tuvo exito."""
    try:
        conn = sqlite3.connect(ruta_db)
        cursor = conn.cursor()
        valor_serializado = json.dumps(valor) if not isinstance(valor, str) else valor
        cursor.execute(
            "insert or replace into variables_globales (clave, valor) values (?, ?)",
            (clave, valor_serializado),
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.OperationalError:
        return False


def restablecer_variables_predeterminadas() -> bool:
    """restablece todas las variables a sus valores predeterminados. devuelve True si tuvo exito."""
    try:
        conn = sqlite3.connect(ruta_db)
        cursor = conn.cursor()
        cursor.execute("delete from variables_globales")
        for clave, valor in parametros_kbt_predeterminados.items():
            valor_serializado = json.dumps(valor) if not isinstance(valor, str) else valor
            cursor.execute(
                "insert into variables_globales (clave, valor) values (?, ?)",
                (clave, valor_serializado),
            )
        conn.commit()
        conn.close()
        return True
    except sqlite3.OperationalError:
        return False


def init_variables_db():
    """crea la tabla de variables globales si no existe."""
    try:
        conn = sqlite3.connect(ruta_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            create table if not exists variables_globales (
                clave text primary key,
                valor text not null
            )
            """
        )
        conn.commit()
        conn.close()
    except sqlite3.OperationalError:
        pass