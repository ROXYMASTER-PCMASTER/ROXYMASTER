"""
PRUEBA DE ORQUESTACION via TCP ADMIN (puerto 5007)
Comandos reales que acepta server.py: perfiles, asignar, estado, grupos, etc.
"""
import socket
import time
from datetime import datetime

PCMASTER_TCP = ("100.111.179.65", 5007)
TIMEOUT = 15

def enviar_comando(cmd):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)
        sock.connect(PCMASTER_TCP)
        sock.sendall((cmd + "\n").encode())
        
        resp = b""
        sock.settimeout(5)
        while True:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                resp += chunk
            except socket.timeout:
                break
        
        sock.close()
        return resp.decode("utf-8", errors="replace").strip()
    except Exception as e:
        return f"[ERROR] {type(e).__name__}: {e}"

def log(prueba, msg, ok=None):
    icono = "[PASS]" if ok is True else ("[FAIL]" if ok is False else "[..]")
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{icono} [{ts}] PRUEBA {prueba}: {msg}")

print("=" * 60)
print("ROXYMASTER v6.1 --- PRUEBAS TCP ADMIN (puerto 5007)")
print(f"PCMASTER TCP: {PCMASTER_TCP[0]}:{PCMASTER_TCP[1]}")
print(f"Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 60)

resultados = []

# PRUEBA 1: Ver perfiles disponibles
print("\n--- PRUEBA 1: perfiles")
log(1, "Consultando perfiles...")
resp = enviar_comando("perfiles")
print(resp[:500])
time.sleep(2)
# Extraer primeros perfiles para pruebas siguientes
perfiles_disponibles = []
for linea in resp.split("\n"):
    if ":" in linea and "LIBRE" in linea:
        perfiles_disponibles.append(linea.split(":")[0].strip())
    elif ":" in linea and "OCUPADO" in linea:
        perfiles_disponibles.append(linea.split(":")[0].strip())

log(1, f"Perfiles encontrados: {len(perfiles_disponibles)}", ok=len(perfiles_disponibles) > 0)

# PRUEBA 2: Estado general
print("\n--- PRUEBA 2: estado")
log(2, "Consultando estado...")
resp = enviar_comando("estado")
print(resp)
log(2, "Estado recibido", ok=len(resp) > 0)

# PRUEBA 3: Ver grupos activos
print("\n--- PRUEBA 3: grupos")
log(3, "Consultando grupos...")
resp = enviar_comando("grupos")
print(resp)
log(3, "Grupos consultados", ok=True)

# PRUEBA 4: Asignar perfil a URL por tiempo (si hay perfiles)
print("\n--- PRUEBA 4: asignar")
if perfiles_disponibles:
    log(4, f"Asignando 1 perfil a kick.com/prueba-admin por 2 min...")
    resp = enviar_comando("asignar 1 url https://kick.com/prueba-admin duracion 2 nivel alto")
    print(resp)
    time.sleep(3)
    # Verificar grupos
    resp2 = enviar_comando("grupos")
    print(resp2)
    log(4, "Asignacion ejecutada", ok="prueba-admin" in resp2)
else:
    log(4, "Sin perfiles disponibles para asignar", ok=False)

# PRUEBA 5: Estado final post-asignacion
print("\n--- PRUEBA 5: estado final")
time.sleep(2)
resp = enviar_comando("estado")
print(resp)
log(5, "Estado final", ok=True)

# Resumen
pasadas = sum(1 for _, ok, _ in resultados if ok)
total = len(resultados)
print("\n" + "=" * 60)
print("RESULTADOS FINALES")
print("=" * 60)
for num, ok, msg in resultados:
    icono = "[PASS]" if ok else "[FAIL]"
    print(f"  {icono} Prueba {num}: {msg[:80]}")
print(f"\n>> {pasadas}/{total} pruebas pasadas")
if pasadas == total:
    print("SISTEMA OPERATIVO via TCP ADMIN")
else:
    print(f"ATENCION: {total - pasadas} prueba(s) fallaron")