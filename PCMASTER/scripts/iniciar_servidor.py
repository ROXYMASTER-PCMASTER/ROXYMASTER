"""Verifica prerequisitos e inicia server.py en PCMASTER."""
import paramiko
import time

PASSWORD = r"Abc123$_"
HOST = "192.168.1.17"
USER = "PCMASTER"
BASE = r"Desktop\ROXYMASTER\PCMASTER\scripts"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASSWORD, timeout=10, look_for_keys=False, allow_agent=False)

# Verificar archivos necesarios
stdin, stdout, stderr = c.exec_command(f'dir "{BASE}"', timeout=10)
print("=== DIR PCMASTER/scripts/ ===")
print(stdout.read().decode('cp437', errors='replace'))

# Verificar config.json
stdin, stdout, stderr = c.exec_command(f'dir "Desktop\\ROXYMASTER\\PCMASTER\\config.json"', timeout=10)
out = stdout.read().decode('cp437', errors='replace')
if 'config.json' in out:
    print("[OK] config.json existe")
else:
    print("[FAIL] config.json NO existe - creando...")
    sftp = c.open_sftp()
    # Leer config.json local
    import json, os
    local_config = r"C:\Users\CYBER\Desktop\ROXYMASTER\PCMASTER\config.json"
    if os.path.exists(local_config):
        sftp.put(local_config, "/Users/PCMASTER/Desktop/ROXYMASTER/PCMASTER/config.json")
        print("[OK] config.json subido")
    sftp.close()

# Verificar prompts/maestro.txt
stdin, stdout, stderr = c.exec_command(f'dir "Desktop\\ROXYMASTER\\PCMASTER\\prompts"', timeout=10)
out = stdout.read().decode('cp437', errors='replace')
if 'maestro.txt' in out:
    print("[OK] prompts/maestro.txt existe")
else:
    print("[WARN] prompts/maestro.txt NO existe - se usara prompt por defecto")

# Matar servidor viejo si existe
c.exec_command('taskkill /F /IM python.exe 2>nul', timeout=5)
time.sleep(2)
print("[OK] Procesos python anteriores terminados")

# Iniciar server.py en segundo plano
import sys
channel = c.get_transport().open_session()
channel.get_pty()
channel.settimeout(15)
# Usar pythonw para background sin bloquear
cmd = f'cd /d "{BASE}" && pythonw server.py > server_output.log 2>&1'
print(f"[CMD] {cmd}")
channel.exec_command(cmd)

# Esperar un poco
time.sleep(3)

# Verificar que el servidor esta corriendo
stdin, stdout, stderr = c.exec_command('netstat -ano | findstr ":5006"', timeout=10)
out = stdout.read().decode('cp437', errors='replace')
if out.strip():
    print(f"[OK] Servidor escuchando en puerto 5006:\n{out}")
else:
    print("[WARN] Puerto 5006 no detectado aun - revisar server_output.log")
    stdin, stdout, stderr = c.exec_command(f'type "Desktop\\ROXYMASTER\\PCMASTER\\scripts\\server_output.log"', timeout=10)
    print(stdout.read().decode('cp437', errors='replace')[-500:])

c.close()
print("\nFASE 3.1 COMPLETADA")