"""Transfiere server parcheado y reinicia servidor en PCMASTER."""
import paramiko
import os
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

PASSWORD = r"Abc123$_"
HOST = "192.168.1.17"
USER = "PCMASTER"
REMOTE_BASE = "/Users/PCMASTER/Desktop/ROXYMASTER/PCMASTER/scripts"

ARCHIVOS = [
    (r"C:\Users\CYBER\Desktop\server_corregido.py", f"{REMOTE_BASE}/server.py"),
]

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASSWORD, timeout=10, look_for_keys=False, allow_agent=False)

sftp = c.open_sftp()

# 1. Subir server.py parcheado
for local_path, remote_path in ARCHIVOS:
    try:
        if os.path.exists(local_path):
            sftp.put(local_path, remote_path)
            size = sftp.stat(remote_path).st_size
            print(f"[OK] Subido: {os.path.basename(local_path)} -> {remote_path} ({size} bytes)")
        else:
            print(f"[FAIL] No existe local: {local_path}")
    except Exception as e:
        print(f"[FAIL] Error subiendo {os.path.basename(local_path)}: {e}")

sftp.close()

# 2. Matar procesos python anteriores
c.exec_command('taskkill /F /IM python.exe 2>nul', timeout=5)
time.sleep(2)
print("[OK] Procesos python anteriores terminados")

# 3. Iniciar server.py en background (python normal, no pythonw - la consola ahora no usa input)
channel = c.get_transport().open_session()
channel.get_pty()
channel.settimeout(15)
cmd = f'cd /d "{REMOTE_BASE}" && python server.py > server_output.log 2>&1'
print(f"[CMD] {cmd}")
channel.exec_command(cmd)

# 4. Esperar y verificar
time.sleep(5)

# 5. Verificar puerto 5006 (WebSocket)
stdin, stdout, stderr = c.exec_command('netstat -ano 2>nul | findstr ":5006"', timeout=10)
out = stdout.read().decode('cp437', errors='replace')
if out.strip():
    print(f"[OK] WebSocket en puerto 5006:\n{out}")
else:
    print("[WARN] Puerto 5006 no detectado")

# 6. Verificar puerto 5007 (TCP Admin)
stdin, stdout, stderr = c.exec_command('netstat -ano 2>nul | findstr ":5007"', timeout=10)
out = stdout.read().decode('cp437', errors='replace')
if out.strip():
    print(f"[OK] TCP Admin en puerto 5007:\n{out}")
else:
    print("[WARN] Puerto 5007 no detectado")

# 7. Probar comando estado vía TCP
time.sleep(2)
stdin, stdout, stderr = c.exec_command('echo estado | nc 127.0.0.1 5007 2>&1', timeout=10)
out = stdout.read().decode('cp437', errors='replace')
err = stderr.read().decode('cp437', errors='replace')
print(f"\n--- TEST ADMIN TCP (estado) ---")
if out.strip():
    print(out)
elif err.strip():
    print(f"[ERR] {err}")
else:
    # Revisar log del servidor
    stdin, stdout, stderr = c.exec_command(f'type "{REMOTE_BASE}\\server_output.log"', timeout=10)
    log = stdout.read().decode('cp437', errors='replace')
    print(log[-1000:])

c.close()
print("\nFASE 3 COMPLETADA - SERVIDOR INICIADO")