import sys, os
sys.path.insert(0, r'C:\Users\PCMASTER\Desktop\roxymaster\pcmaster\scripts')
from db import ejecutar_sql, ejecutar_sql_unico
from datetime import datetime, timedelta

pcbot = 'PCWILMER'
ahora = datetime.utcnow()

# 1. Perfiles en BD
perfiles = ejecutar_sql("SELECT hash, activo FROM perfiles_roxy WHERE pcbot_id = ?", (pcbot,))
print('Perfiles en BD:', perfiles)

# 2. Asignaciones activas que podrían bloquear
asig_activas = ejecutar_sql("SELECT pa.id, pa.perfil_id, pa.estado, pa.pedido_id FROM pedido_asignaciones pa WHERE pa.perfil_id IN (SELECT hash FROM perfiles_roxy WHERE pcbot_id = ?) AND pa.estado IN ('planificado', 'ejecutando')", (pcbot,))
print('Asignaciones activas:', asig_activas)

# 3. Simular _obtener_perfiles_libres (misma lógica)
libres = []
for p in perfiles:
    hash_p = p['hash']
    activo = p['activo']
    # si activo=0, no se considera (debe estar conectado)
    if activo == 0:
        continue
    # comprobar que no tenga asignaciones activas
    bloqueo = ejecutar_sql_unico("SELECT 1 FROM pedido_asignaciones WHERE perfil_id = ? AND estado IN ('planificado', 'ejecutando')", (hash_p,))
    if not bloqueo:
        libres.append(hash_p)

print('Perfiles libres según lógica:', libres)

# 4. Verificar heartbeat_cache
import importlib
spec = importlib.util.spec_from_file_location("heartbeat_cache", r"C:\Users\PCMASTER\Desktop\roxymaster\pcmaster\scripts\heartbeat_cache.py")
hc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hc)
hb = hc.obtener_heartbeat(pcbot)
print('Heartbeat cache para', pcbot, ':', hb)

