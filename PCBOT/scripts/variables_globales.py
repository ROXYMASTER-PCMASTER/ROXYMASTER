# ============================================================================
# variables_globales.py - constantes del sistema pcbot v8.3
# todas las rutas, nombres y valores en minusculas
# ============================================================================

import os
import sys
import json
from pathlib import Path

# ---------------------------------------------------------------------------
# rutas base (dinamicas, en minusculas)
# ---------------------------------------------------------------------------
_base = Path(__file__).parent.parent.absolute()
_scripts_dir = _base / 'scripts'
_data_dir = _base / 'data'
_config_path = _base / 'config.json'

# ---------------------------------------------------------------------------
# conexion a pcmaster
# ---------------------------------------------------------------------------
pcmaster_ip = '100.111.179.65'   # ip tailscale de pcmaster (produccion)
pcmaster_local_ip = '192.168.1.17'  # ip local de pcmaster (desarrollo/ssh)
pcmaster_port = 5006

# ---------------------------------------------------------------------------
# puertos locales
# ---------------------------------------------------------------------------
ui_port = 8085       # websocket nicegui local
http_port = 8087     # http para portal.html y dashboard.html
portal_port = 8087   # mismo puerto para portal

# ---------------------------------------------------------------------------
# roxybrowser
# ---------------------------------------------------------------------------
roxybrowser_api_url = 'http://127.0.0.1:50000'
roxybrowser_timeout = 10  # segundos

# ---------------------------------------------------------------------------
# secreto compartido (debe coincidir con pcmaster)
# ---------------------------------------------------------------------------
secreto_sistema = 'r0xym4st3r_s3cr3t0_k3y_v83'

# ---------------------------------------------------------------------------
# constantes del sistema
# ---------------------------------------------------------------------------
version = '8.3.0'
max_perfiles_locales = 5  # sin roxybrowser
heartbeat_interval = 30   # segundos
reconnect_delay = 5       # segundos iniciales antes de reconectar
max_reconnect_delay = 300  # maximo delay de reconexion (5 min)
tiempo_validacion_perfil = 62 * 60  # 62 minutos en segundos
tiempo_colgado_timeout = 300  # 5 minutos sin actividad = colgado
tiempo_revision_colgados = 60  # revisar cada 60 segundos

# ---------------------------------------------------------------------------
# parametros economicos (valores predeterminados, se sincronizan con pcmaster)
# ---------------------------------------------------------------------------
k = 20.00              # pago de kick por 1000 espectadores-hora (usd)
fx = 3.70              # tipo de cambio pen/usd
p_token = 1.00         # precio ancla (pen)
g_default = 9.00       # pago a granjeros por bloque (usd) - fase inicial
e_cost = 0.005         # coste electrico (pen/hora-perfil)
beta_default = 0.0     # fraccion de bloques pagados en kbt (inicial)
hh_mult_default = 2.0  # multiplicador happy hour

# ---------------------------------------------------------------------------
# niveles de uptime y multiplicadores
# ---------------------------------------------------------------------------
uptime_niveles = {
    'bronce': {'min_porcentaje': 90, 'multiplicador': 1.1},
    'plata': {'min_porcentaje': 95, 'multiplicador': 1.2},
    'oro': {'min_porcentaje': 99, 'multiplicador': 1.3},
}


# ============================================================================
# funciones de configuracion
# ============================================================================

def cargar_config():
    """carga config.json si existe, con valores predeterminados."""
    config = {
        'pcmaster_ip': pcmaster_ip,
        'pcmaster_port': pcmaster_port,
        'roxybrowser_token': '',
        'workspace_id': '',
        'secreto_sistema': secreto_sistema,
    }

    if _config_path.exists():
        try:
            with open(_config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            config.update(data)
        except Exception:
            pass

    return config


def guardar_config(config):
    """guarda la configuracion en config.json."""
    _config_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(_config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f'error guardando config: {e}')
        return False


def obtener_variables():
    """devuelve todas las variables globales como diccionario."""
    return {
        'version': version,
        'pcmaster_ip': pcmaster_ip,
        'pcmaster_port': pcmaster_port,
        'ui_port': ui_port,
        'http_port': http_port,
        'max_perfiles_locales': max_perfiles_locales,
        'heartbeat_interval': heartbeat_interval,
        'tiempo_validacion_perfil': tiempo_validacion_perfil,
        'g_default': g_default,
        'beta_default': beta_default,
        'hh_mult_default': hh_mult_default,
        'k': k,
        'fx': fx,
        'p_token': p_token,
        'e_cost': e_cost,
        'uptime_niveles': uptime_niveles,
    }