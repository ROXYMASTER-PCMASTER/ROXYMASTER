"""Inicia server.py en PCMASTER de forma DESPRENDIDA del SSH."""
import paramiko
import sys
import io
import time

sys.stdout.reconfigure(encoding='utf-8')

PASSWORD = r"Abc123$_"
HOST = "192.168.1.17"
USER = "PCMASTER"
BASE_SCRIPTS = r"Desktop\ROXYMASTER\PCMASTER\scripts"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASSWORD, timeout=10, look_for_keys=False, allow_agent=False)

# 1. Matar TODO python
print("=== MATANDO PROCESOS ===")
c.exec_command('taskkill /F /IM python.exe 2>nul', timeout=5)
c.exec_command('taskkill /F /IM pythonw.exe 2>nul', timeout=5)
time.sleep(3)

# 2. Resubir server.py por seguridad
print("=== RESUBIENDO server.py ===")
sftp = c.open_sftp()
sftp.put(r"C:\Users\CYBER\Desktop\server_corregido.py", f"{BASE_SCRIPTS}\\server.py")
size = sftp.stat(f"{BASE_SCRIPTS}\\server.py").st_size
sftp.close()
print(f"[OK] {size} bytes")

# 3. Limpiar caches
print("=== LIMPIANDO CACHES ===")
c.exec_command(f'rmdir /S /Q "{BASE_SCRIPTS}\\__pycache__" 2>nul', timeout=5)
c.exec_command(f'del /Q "{BASE_SCRIPTS}\\*.pyc" 2>nul', timeout=5)
time.sleep(1)

# 4. LIMPIAR el log viejo
print("=== LIMPIANDO LOGS ===")
c.exec_command(f'del /Q "{BASE_SCRIPTS}\\server_output.log" 2>nul', timeout=5)
c.exec_command(f'del /Q "{BASE_SCRIPTS}\\server_output2.log" 2>nul', timeout=5)
c.exec_command(f'del /Q "{BASE_SCRIPTS}\\server_output_NEW.log" 2>nul', timeout=5)
time.sleep(1)

# 5. Crear launcher Python en PCMASTER que se DESPRENDE del SSH
print("=== CREANDO LAUNCHER ===")
launcher_code = '''import subprocess, sys, os
os.chdir(os.path.expanduser(r"Desktop\\ROXYMASTER\\PCMASTER\\scripts"))
# Limpiar log
open("server_output.log", "w").close()
# Lanzar servidor en proceso independiente
p = subprocess.Popen(
    [sys.executable, "-u", "server.py"],
    stdin=subprocess.DEVNULL,
    stdout=open("server_output.log", "a"),
    stderr=subprocess.STDOUT,
    creationflags=0x00000008,  # DETACHED_PROCESS
    close_fds=True,
)
print(f"SERVIDOR_PID={p.pid}")
'''
sftp = c.open_sftp()
sftp.putfo(io.BytesIO(launcher_code.encode()), f"{BASE_SCRIPTS}\\launcher.py")
sftp.close()
print("[OK] launcher.py creado")

# 6. Ejecutar launcher (esto retorna rápido porque el proceso se desprende)
print("\n=== EJECUTANDO LAUNCHER ===")
stdin, stdout, stderr = c.exec_command(f'python "{BASE_SCRIPTS}\\launcher.py"', timeout=15)
out = stdout.read().decode('cp437', errors='replace')
err = stderr.read().decode('cp437', errors='replace')
print(f"STDOUT: {out.strip()}")
if err.strip():
    print(f"STDERR: {err.strip()}")

# 7. Esperar arranque
print("\n=== ESPERANDO ARRANQUE (8s) ===")
time.sleep(8)

# 8. Verificar puertos
print("\n=== PUERTOS ===")
stdin, stdout, stderr = c.exec_command('netstat -ano | findstr ":5006 :5007"', timeout=10)
out = stdout.read().decode('cp437', errors='replace')
if out.strip():
    print(f"[OK] Puertos detectados:\n{out}")
else:
    print("[WARN] Sin puertos")

# 9. Ver log
print("\n=== LOG DEL SERVIDOR ===")
stdin, stdout, stderr = c.exec_command(f'type "{BASE_SCRIPTS}\\server_output.log"', timeout=10)
log = stdout.read().decode('cp437', errors='replace')
for line in log.strip().split('\n'):
    line = line.strip()
    if line and 'Error:' not in line:
        print(line)
    elif 'Error:' in line:
        print(f"  [[ERROR]] {line[:120]}")

# 10. Probar TCP admin via Python
print("\n=== PRUEBA TCP ADMIN ===")
test_script = """import socket,time
s=socket.socket()
s.settimeout(5)
try:
 s.connect(('127.0.0.1',5007))
 s.sendall(b'estado\\n')
 time.sleep(0.5)
 resp=b''
 s.settimeout(1)
 while True:
  try:
   c=s.recv(4096)
   if not c:break
   resp+=c
  except:break
 print(resp.decode())
except Exception as e:
 print(f'Error: {e}')
finally:
 s.close()
"""
stdin, stdout, stderr = c.exec_command(f'python -c "{test_script}"', timeout=10)
result = stdout.read().decode('cp437', errors='replace')
err_out = stderr.read().decode('cp437', errors='replace')
if result.strip():
    print(f"[OK] Respuesta:\n{result}")
elif err_out.strip():
    print(f"[ERR] {err_out}")
else:
    print("[WARN] Sin respuesta")

# 11. Ver procesos
print("\n=== PROCESOS PYTHON ===")
stdin, stdout, stderr = c.exec_command('tasklist /FI "IMAGENAME eq python.exe" 2>&1', timeout=10)
print(stdout.read().decode('cp437', errors='replace'))

c.close()
print("\n=== INICIO COMPLETADO ===")