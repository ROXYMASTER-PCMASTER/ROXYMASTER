"""corrige codigo y reinicia servidor. no hace pruebas."""
import os
import sys
import subprocess
import time

BASE_DIR = r"C:\users\pcmaster\desktop\roxymaster\pcmaster"
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")

print("=== LEYENDO ARCHIVOS ===")

with open(os.path.join(SCRIPTS_DIR, "http_server.py"), "r", encoding="utf-8") as f:
    http_code = f.read()

with open(os.path.join(SCRIPTS_DIR, "auth.py"), "r", encoding="utf-8") as f:
    auth_code = f.read()

print(f"http_server.py: {len(http_code)} chars")
print(f"auth.py: {len(auth_code)} chars")

# correcciones
print("\n=== CORRIGIENDO ===")
cambios = 0

# auth_users -> usuarios
if "auth_users" in http_code.lower():
    http_code = http_code.replace("auth_users", "usuarios")
    http_code = http_code.replace("AUTH_USERS", "usuarios")
    cambios += 1
    print("  auth_users -> usuarios (http_server)")

if "auth_users" in auth_code.lower():
    auth_code = auth_code.replace("auth_users", "usuarios")
    auth_code = auth_code.replace("AUTH_USERS", "usuarios")
    cambios += 1
    print("  auth_users -> usuarios (auth)")

# wallets.email -> wallets.usuario_id
if "wallets.email" in http_code.lower():
    http_code = http_code.replace("wallets.email", "wallets.usuario_id")
    cambios += 1
    print("  wallets.email -> wallets.usuario_id")

if "wallets.email" in auth_code.lower():
    auth_code = auth_code.replace("wallets.email", "wallets.usuario_id")
    cambios += 1
    print("  wallets.email -> wallets.usuario_id (auth)")

# vendedor -> usuario_id
if "vendedor" in http_code.lower():
    http_code = http_code.replace("vendedor", "usuario_id")
    cambios += 1
    print("  vendedor -> usuario_id")

# precio_unitario -> precio_pen
if "precio_unitario" in http_code.lower():
    http_code = http_code.replace("precio_unitario", "precio_pen")
    cambios += 1
    print("  precio_unitario -> precio_pen")

# fix JOIN wallets ON ... email = wallets.email
if "u.email = wallets.email" in http_code:
    http_code = http_code.replace("u.email = wallets.email", "u.email = wallets.usuario_id")
    cambios += 1
    print("  join wallets.email -> usuario_id")

if "u.email = w.email" in http_code:
    http_code = http_code.replace("u.email = w.email", "u.email = w.usuario_id")
    cambios += 1
    print("  join w.email -> w.usuario_id")

print(f"total cambios: {cambios}")

# guardar
print("\n=== GUARDANDO ===")
with open(os.path.join(SCRIPTS_DIR, "http_server.py"), "w", encoding="utf-8") as f:
    f.write(http_code)
with open(os.path.join(SCRIPTS_DIR, "auth.py"), "w", encoding="utf-8") as f:
    f.write(auth_code)
print("archivos guardados.")

# reiniciar servidor
print("\n=== REINICIANDO SERVIDOR ===")

# matar solo procesos pythonw que tengan server.py (evitar matar este mismo)
r = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True)
for line in r.stdout.splitlines():
    if "python" in line.lower():
        # no matar nada por si acaso, solo avisar
        pass

# matar procesos escuchando en 8086 y 5006
r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
pids_to_kill = set()
for line in r.stdout.splitlines():
    if (":8086" in line or ":5006" in line) and "LISTENING" in line:
        parts = line.strip().split()
        pid = parts[-1] if parts[-1].isdigit() else None
        if pid:
            pids_to_kill.add(pid)

for pid in pids_to_kill:
    print(f"matando pid {pid}...")
    os.system(f"taskkill /f /pid {pid} 2>nul")

time.sleep(2)

# iniciar
os.chdir(BASE_DIR)
flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
log = open(os.path.join(BASE_DIR, "server.log"), "w")
proc = subprocess.Popen(
    ["pythonw", os.path.join(SCRIPTS_DIR, "server.py")],
    stdout=log,
    stderr=subprocess.STDOUT,
    creationflags=flags,
    close_fds=True,
)
print(f"servidor iniciado pid={proc.pid}")
print("esperando 8 segundos...")
time.sleep(8)

# verificar
r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
for port in ["5006", "8086"]:
    if f":{port}" in r.stdout and "LISTENING" in r.stdout:
        print(f"  puerto {port}: LISTENING OK")
    else:
        print(f"  puerto {port}: NO RESPONDE")
        break

print("\nlisto. servidor reiniciado.")