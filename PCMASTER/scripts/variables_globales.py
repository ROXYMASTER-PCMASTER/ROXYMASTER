# ============================================================================
# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# variables_globales.py - constantes del sistema roxymaster v8.3
# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# todas las variables economicas, ips, puertos, parametros kbt
# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# ============================================================================

import os
import json
import sqlite3
from pathlib import Path

# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# ---------------------------------------------------------------------------
# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# rutas dinamicas
# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# ---------------------------------------------------------------------------
base_dir = Path(__file__).parent.parent.absolute()
data_dir = base_dir / "data"
scripts_dir = base_dir / "scripts"
prompts_dir = base_dir / "prompts"
config_path = base_dir / "config.json"
db_path = data_dir / "roxymaster.db"

# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# asegurar directorios
data_dir.mkdir(parents=True, exist_ok=True)
prompts_dir.mkdir(parents=True, exist_ok=True)

# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# ---------------------------------------------------------------------------
# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# ips y puertos (nombres que espera server.py)
# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# ---------------------------------------------------------------------------
WS_HOST = "0.0.0.0"
WS_PORT = 5006
HTTP_HOST = "0.0.0.0"
HTTP_PORT = 8086

# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# alias legacy para otros modulos
pcmaster_ip_local = "192.168.1.17"
pcmaster_ip_tailscale = "100.111.179.65"
pcmaster_ws_port = WS_PORT
pcmaster_http_port = HTTP_PORT

# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# ---------------------------------------------------------------------------
# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# seguridad
# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# ---------------------------------------------------------------------------
SECRETO_SISTEMA = "r0xym4st3r_s3cr3t0_k3y_v83"
TOKEN_ADMIN = "admin_root_token_v83_roxymaster"

# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# ---------------------------------------------------------------------------
# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# jarvis / ollama
# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# ---------------------------------------------------------------------------
jarvis_modelo = "llama3.2"
jarvis_api_url = "http://localhost:11434"
contexto_segundos = 30
prompt_maestro_path = prompts_dir / "maestro.txt"

# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# ---------------------------------------------------------------------------
# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# economia kbt - constantes exportadas con los nombres que server.py espera
# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# ---------------------------------------------------------------------------
K = 20.00                       # usd que kick paga al streamer por 1000 espectadores-hora
FX = 3.70                       # pen por usd (tipo de cambio)
P_TOKEN = 1.00                  # precio ancla del token en pen
G_DEFAULT = 9.00                # pago a granjeros por bloque (usd) - valor inicial
BETA_DEFAULT = 0.0              # fraccion de pagos de streamers en kbt
HH_MULT_DEFAULT = 2.0           # multiplicador de happy hour

COMISION_MARKETPLACE = 0.15     # 15% para el dueno en cada transaccion p2p
COMISIONES_RETIRO = {
    "0_30": 0.33,               # retiro en primeros 30 dias
    "31_60": 0.25,              # retiro entre 31-60 dias
    "61_90": 0.15,              # retiro entre 61-90 dias
    "90_plus": 0.00,            # retiro despues de 90 dias
}
LIMITE_RETIRO_USD = 999.0       # limite mensual de retiro por cuenta
COMISION_REFERIDO = 0.10        # 10% de tokens minados del referido

# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# niveles de streamer (seguidores -> p_sys en usd)
NIVELES_STREAMER = {
    0: {"min": 0,        "max": 4999,      "p_sys": 9.00},
    1: {"min": 5000,     "max": 14999,     "p_sys": 10.00},
    2: {"min": 15000,    "max": 49999,     "p_sys": 11.00},
    3: {"min": 50000,    "max": 499999,    "p_sys": 12.00},
    4: {"min": 500000,   "max": 999999,    "p_sys": 14.00},
    5: {"min": 1000000,  "max": 999999999, "p_sys": 16.00},
}

# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# niveles de fiabilidad (uptime)
UPTIME_NIVELES = {
    "bronce": {"min": 0.90, "w": 1.1},
    "plata":  {"min": 0.95, "w": 1.2},
    "oro":    {"min": 0.99, "w": 1.3},
}

# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# cronograma de g (pago a granjeros en usd segun mes del sistema)
CRONOGRAMA_G = {
    (1, 3): 9.00,    # mes 1-3: atraccion agresiva
    (4, 6): 7.50,    # mes 4-6: transicion
    (7, 999): 6.00,  # mes 7+: equilibrio
}

# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# parametros completos (diccionario para el dashboard de admin)
parametros_kbt_predeterminados = {
    "k": K,
    "fx": FX,
    "p_token": P_TOKEN,
    "banda_min": 0.94,
    "banda_max": 1.06,
    "h": 720,
    "e": 0.005,
    "g_mes_1_3": 9.00,
    "g_mes_4_6": 7.50,
    "g_mes_7_adelante": 6.00,
    "beta": BETA_DEFAULT,
    "alfa_nuevo": 0.5,
    "gamma": 0.5,
    "comision_marketplace": COMISION_MARKETPLACE,
    "comision_retiro_0_30": 0.33,
    "comision_retiro_31_60": 0.25,
    "comision_retiro_61_90": 0.15,
    "comision_retiro_90_plus": 0.00,
    "comision_referido": COMISION_REFERIDO,
    "limite_retiro_mensual_usd": LIMITE_RETIRO_USD,
    "limite_perfiles_por_pc": 5,
    "hh_mult": HH_MULT_DEFAULT,
    "hh_duracion_min": 60,
    "hh_duracion_max": 240,
    "hh_anuncio_horas": 24,
    "nivel_bronce_uptime": 0.90,
    "nivel_plata_uptime": 0.95,
    "nivel_oro_uptime": 0.99,
    "w_bronce": 1.1,
    "w_plata": 1.2,
    "w_oro": 1.3,
    "penalizacion_inactividad_porcentaje": 0.05,
    "tolerancia_reinicio_minutos": 30,
    "ventana_penalizacion_dias": 7,
    "horas_inactividad_dispara": 11,
    "mins_validacion_consecutivos": 62,
    "gracia_oro_desconexion_min": 30,
    "duracion_penalizacion_dias": 30,
    "staking_recompensa_anual": 0.05,
    "re_limite_intervencion_mensual": 0.10,
    "re_excedente_retirable_mensual": 0.01,
    "re_colchon_estabilidad": 0.20,
    "niveles_streamer": NIVELES_STREAMER,
    "bloques_por_perfil_mes": 0.72,
}

# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# ---------------------------------------------------------------------------
# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# cargar configuracion desde config.json (si existe)
# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# ---------------------------------------------------------------------------
def cargar_config():
    """carga config.json y lo fusiona con los parametros predeterminados."""
    config = {
        "pcmaster_ip": pcmaster_ip_local,
        "ws_port": pcmaster_ws_port,
        "http_port": pcmaster_http_port,
        "ollama_url": jarvis_api_url,
        "modelo": jarvis_modelo,
    }
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            config.update({k.lower(): v for k, v in data.items()})
        except (json.JSONDecodeError, IOError):
            pass
    return config


def guardar_config(config):
    """guarda configuracion en config.json."""
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# ---------------------------------------------------------------------------
# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# gestion dinamica de variables (para el dashboard admin)
# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# ---------------------------------------------------------------------------

def obtener_variables() -> dict:
    """devuelve todas las variables kbt desde la base de datos o predeterminadas."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("select clave, valor from variables_globales")
    rows = {r["clave"]: r["valor"] for r in c.fetchall()}
    conn.close()
    # fusionar con predeterminados
    resultado = dict(parametros_kbt_predeterminados)
    for k, v in rows.items():
        try:
            resultado[k] = json.loads(v)
        except (json.JSONDecodeError, TypeError):
            resultado[k] = v
    return resultado


def actualizar_variable(clave: str, valor) -> bool:
    """actualiza una variable global en la base de datos."""
    try:
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        c.execute(
            "insert or replace into variables_globales (clave, valor) values (?, ?)",
            (clave, json.dumps(valor) if not isinstance(valor, str) else valor),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def restablecer_variables_predeterminadas() -> bool:
    """restablece todas las variables a sus valores predeterminados."""
    try:
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        c.execute("delete from variables_globales")
        for clave, valor in parametros_kbt_predeterminados.items():
            c.execute(
                "insert into variables_globales (clave, valor) values (?, ?)",
                (clave, json.dumps(valor) if not isinstance(valor, str) else valor),
            )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def init_variables_db():
    """crea la tabla de variables globales si no existe."""
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    c.execute('''
        create table if not exists variables_globales (
            clave text primary key,
            valor text not null
        )
    ''')
    conn.commit()
    conn.close()


# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# ---------------------------------------------------------------------------
# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# helper: obtener ruta dinamica del usuario
# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# ---------------------------------------------------------------------------
def ruta_usuario():
    """devuelve el home del usuario actual en minusculas."""
    return os.path.expandvars("%userprofile%").lower()


def ruta_escritorio():
    """devuelve la ruta del escritorio en minusculas."""
    return os.path.join(ruta_usuario(), "desktop")


# --- Carga automática de secretos externos ---
import os, json
_secrets_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "roxymaster_secrets", "config_sensible.json")
if os.path.exists(_secrets_path):
    with open(_secrets_path, "r", encoding="utf-8-sig") as _f:
        _secrets = json.load(_f)
    ROXY_API_TOKEN = _secrets.get("roxy_api_token", ROXY_API_TOKEN)
    ROXY_WORKSPACE_ID = _secrets.get("roxy_workspace_id", ROXY_WORKSPACE_ID)
# inicializar base de datos de variables al importar
init_variables_db()
