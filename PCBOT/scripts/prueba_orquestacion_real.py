"""
PRUEBA COMPLETA DE ORQUESTACIÓN — ROXYMASTER v6.1
Flujo: perfiles → asignar 2 a kick.com/payasitazing → comentarios → portal básico
"""
import socket
import time
from datetime import datetime

PCMASTER = "100.111.179.65"
TCP_PORT = 5007
TIMEOUT = 20

def enviar_comando(cmd, espera_extra=True):
    """Envía comando vía TCP Admin y recibe respuesta"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)
        sock.connect((PCMASTER, TCP_PORT))
        sock.sendall((cmd + "\n").encode())
        
        resp = b""
        sock.settimeout(8)
        while True:
            try:
                chunk = sock.recv(8192)
                if not chunk:
                    break
                resp += chunk
            except socket.timeout:
                break
        
        sock.close()
        return resp.decode("utf-8", errors="replace").strip()
    except Exception as e:
        return f"[ERROR] {type(e).__name__}: {e}"

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

print("=" * 70)
print("ROXYMASTER v6.1 — PRUEBA DE ORQUESTACIÓN COMPLETA")
print(f"Servidor: {PCMASTER}:{TCP_PORT}")
print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

# =====================================================================
# PASO 1: Determinar cuántos perfiles están abiertos
# =====================================================================
print("\n" + "-" * 50)
print("PASO 1: Consultando perfiles disponibles")
print("-" * 50)
log("Enviando comando 'perfiles'...")
resp = enviar_comando("perfiles")
print(resp)

# Extraer perfiles
perfiles_libres = []
perfiles_ocupados = []
for linea in resp.split("\n"):
    linea = linea.strip()
    if ":" in linea and "LIBRE" in linea:
        perfiles_libres.append(linea.split(":")[0].strip())
    elif ":" in linea and "OCUPADO" in linea:
        perfiles_ocupados.append(linea.split(":")[0].strip())

total_perfiles = len(perfiles_libres) + len(perfiles_ocupados)
log(f"TOTAL PERFILES: {total_perfiles} (Libres: {len(perfiles_libres)}, Ocupados: {len(perfiles_ocupados)})")

if total_perfiles == 0:
    log("⚠ No hay perfiles conectados. ABORTANDO.")
    exit(1)

if len(perfiles_libres) < 2:
    log(f"⚠ Solo {len(perfiles_libres)} perfil(es) libre(s). Se necesitan 2.")
    # Usar libres + ocupados si necesario
    todos = perfiles_libres + perfiles_ocupados
    perfiles_a_usar = todos[:2]
    log(f"Usando: {perfiles_a_usar}")
else:
    perfiles_a_usar = perfiles_libres[:2]
    log(f"Perfiles seleccionados: {perfiles_a_usar}")

time.sleep(1)

# =====================================================================
# PASO 2: Consultar estado general
# =====================================================================
print("\n" + "-" * 50)
print("PASO 2: Estado general del sistema")
print("-" * 50)
resp = enviar_comando("estado")
print(resp)
time.sleep(1)

# =====================================================================
# PASO 3: Asignar 2 perfiles a kick.com/payasitazing por 5 minutos
# =====================================================================
URL_STREAM = "https://kick.com/payasitazing"
DURACION = 5  # minutos
NIVEL = "alto"  # comentarios frecuentes

print("\n" + "-" * 50)
print(f"PASO 3: Asignando 2 perfiles a {URL_STREAM}")
print(f"       Duración: {DURACION} min | Nivel: {NIVEL}")
print("-" * 50)

cmd_asignar = f"asignar 2 url {URL_STREAM} duracion {DURACION} nivel {NIVEL}"
log(f"Comando: {cmd_asignar}")
resp = enviar_comando(cmd_asignar)
print(resp)
time.sleep(2)

# Verificar que la asignación se realizó
print("\nVerificando grupos activos...")
resp = enviar_comando("grupos")
print(resp)

asignacion_ok = "payasitazing" in resp.lower()
log(f"Asignación {'EXITOSA ✅' if asignacion_ok else 'FALLIDA ❌'}")

# =====================================================================
# PASO 4: Monitorear comentarios generados durante 2 minutos
# =====================================================================
print("\n" + "-" * 50)
print("PASO 4: Monitoreando generación de comentarios (2 min)")
print("-" * 50)
log("Esperando 120 segundos mientras JARVIS genera comentarios...")
log("(Los comentarios se envían automáticamente según el nivel 'alto' = cada 8s)")

for i in range(6):
    time.sleep(20)
    resp = enviar_comando("estado")
    # Extraer stats de JARVIS
    for linea in resp.split("\n"):
        if "JARVIS" in linea.upper() or "comentarios" in linea.lower():
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] {linea.strip()}")
    log(f"Minuto { (i+1)*20//60 + 1 } de monitoreo...")

# Estado intermedio
print("\nEstado después de 2 minutos:")
resp = enviar_comando("estado")
print(resp)

# =====================================================================
# PASO 5: Detener grupo y redireccionar al portal básico
# =====================================================================
print("\n" + "-" * 50)
print("PASO 5: Deteniendo grupo en kick.com/payasitazing")
print("-" * 50)
resp = enviar_comando(f"detener url {URL_STREAM}")
print(resp)
time.sleep(2)

# Verificar que se detuvo
resp = enviar_comando("grupos")
print(resp)
log(f"Grupo detenido: {'payasitazing' not in resp.lower() if True else 'Verificar'}")

# =====================================================================
# PASO 6: Redireccionar a portal básico
# =====================================================================
URL_PORTAL = "https://raw.githack.com/payasitazing/portal-basico/main/index.html"

print("\n" + "-" * 50)
print(f"PASO 6: Redireccionando perfiles a portal básico")
print(f"       URL: {URL_PORTAL}")
print("-" * 50)

cmd_portal = f"asignar 2 url {URL_PORTAL} duracion 5 nivel bajo"
log(f"Comando: {cmd_portal}")
resp = enviar_comando(cmd_portal)
print(resp)
time.sleep(2)

# Verificar
resp = enviar_comando("grupos")
print(resp)

portal_ok = "raw.githack" in resp.lower() or "portal" in resp.lower()
log(f"Redirección a portal {'EXITOSA ✅' if portal_ok else 'FALLIDA ❌'}")

# =====================================================================
# RESUMEN FINAL
# =====================================================================
print("\n" + "=" * 70)
print("RESUMEN FINAL DE LA PRUEBA")
print("=" * 70)
print(f"  1. Perfiles totales: {total_perfiles}")
print(f"  2. Asignación a stream: {'✅' if asignacion_ok else '❌'}")
print(f"  3. Comentarios generados: Ver estado arriba")
print(f"  4. Redirección a portal: {'✅' if portal_ok else '❌'}")
print("=" * 70)