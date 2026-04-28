"""Inicia server.py en PCMASTER usando subprocess con stdin=DEVNULL."""
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

# 1. Matar procesos anteriores
c.exec_command('taskkill /F /IM python.exe 2>nul', timeout=5)
time.sleep(2)

# 2. Crear launcher Python que use subprocess.DEVNULL
launcher_py = r"""
import subprocess, sys, os
os.chdir(r'Desktop\ROXYMASTER\PCMASTER\scripts')
p = subprocess.Popen(
    [sys.executable, 'server.py'],
    stdin=subprocess.DEVNULL,
    stdout=open('server_output.log', 'a'),
    stderr=subprocess.STDOUT,
    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
)
print(f'PID: {p.pid}')
# Guardar PID para referencia
with open('server.pid', 'w') as f:
    f.write(str(p.pid))
"""

sftp = c.open_sftp()
sftp.putfo(io.BytesIO(launcher_py.encode()), f"{BASE_SCRIPTS}\\launcher_server.py")
sftp.close()

# 3. Ejecutar el launcher
print("=== EJECUTANDO LAUNCHER ===")
stdin, stdout, stderr = c.exec_command(f'python "{BASE_SCRIPTS}\\launcher_server.py"', timeout=15)
out = stdout.read().decode('cp437', errors='replace')
err = stderr.read().decode('cp437', errors='replace')
print(f"STDOUT: {out}")
print(f"STDERR: {err}")

# 4. Esperar inicio
time.sleep(5)

# 5. Verificar puertos
print("\n=== PUERTOS ===")
stdin, stdout, stderr = c.exec_command('netstat -ano | findstr ":5006 :5007"', timeout=10)
out = stdout.read().decode('cp437', errors='replace')
if out.strip():
    print(out)
else:
    print("NINGUN puerto detectado")

# 6. Ver log nuevo
print("\n=== LOG DEL SERVIDOR (ultimas 30 lineas) ===")
stdin, stdout, stderr = c.exec_command(f'type "{BASE_SCRIPTS}\\server_output.log"', timeout=10)
log = stdout.read().decode('cp437', errors='replace')
lines = log.strip().split('\n')
for line in lines[-30:]:
    print(line)

# 7. Test TCP admin
print("\n=== TEST TCP ADMIN (estado) ===")
test_code = "import socket;s=socket.socket();s.settimeout(5);s.connect(('127.0.0.1',5007));s.sendall(b'estado\\n');import time;time.sleep(1);resp=b'';s.settimeout(2);\nwhile True:\n try:\n  chunk=s.recv(4096);\n  if not chunk:break\n  resp+=chunk;\n except:break\nprint(resp.decode());s.close()"
stdin, stdout, stderr = c.exec_command(f'python -c "{test_code}"', timeout=10)
result = stdout.read().decode('cp437', errors='replace')
err = stderr.read().decode('cp437', errors='replace')
if result.strip():
    print(result)
if err.strip():
    print(f"STDERR: {err}")

c.close()
print("\nCOMPLETADO")