"""Diagnostica y repara el servidor en PCMASTER."""
import paramiko
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

PASSWORD = r"Abc123$_"
HOST = "192.168.1.17"
USER = "PCMASTER"
BASE = r"Desktop\ROXYMASTER\PCMASTER\scripts"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASSWORD, timeout=10, look_for_keys=False, allow_agent=False)

# 1. Ver log del servidor
print("=== server_output.log (ultimas 60 lineas) ===")
stdin, stdout, stderr = c.exec_command(f'type "{BASE}\\server_output.log"', timeout=10)
log = stdout.read().decode('cp437', errors='replace')
lines = log.split('\n')
for line in lines[-60:]:
    print(line)

# 2. Ver si hay python corriendo
print("\n=== PROCESOS PYTHON ===")
stdin, stdout, stderr = c.exec_command('tasklist /FI "IMAGENAME eq python.exe" 2>&1', timeout=10)
print(stdout.read().decode('cp437', errors='replace'))

# 3. Intentar iniciar server.py con python.exe normal, no pythonw
print("\n=== REINICIANDO SERVIDOR ===")
c.exec_command('taskkill /F /IM python.exe 2>nul', timeout=5)
time.sleep(3)

# Usar start para lanzar en ventana separada
stdin, stdout, stderr = c.exec_command(f'cd /d "{BASE}" && start "ROXYMASTER" /MIN python server.py > server_output2.log 2>&1', timeout=10)
time.sleep(5)

# Verificar puertos
print("\n=== PUERTOS ===")
stdin, stdout, stderr = c.exec_command('netstat -ano | findstr ":5006 :5007"', timeout=10)
out = stdout.read().decode('cp437', errors='replace')
if out.strip():
    print(out)
else:
    print("NINGUN puerto detectado")

# 4. Revisar nuevo log
print("\n=== server_output2.log ===")
stdin, stdout, stderr = c.exec_command(f'type "{BASE}\\server_output2.log" 2>&1', timeout=10)
log = stdout.read().decode('cp437', errors='replace')
lines = log.split('\n')
for line in lines[-40:]:
    print(line)

# 5. Probar TCP admin via Python inline en PCMASTER
print("\n=== TEST TCP ADMIN (Python) ===")
test_script = """
import socket, time
try:
    s = socket.socket()
    s.settimeout(5)
    s.connect(('127.0.0.1', 5007))
    s.sendall(b'estado\\n')
    time.sleep(0.5)
    resp = s.recv(4096)
    print(resp.decode())
    s.close()
except Exception as e:
    print(f'Error: {e}')
"""
stdin, stdout, stderr = c.exec_command(f'python -c "{test_script}"', timeout=10)
print(stdout.read().decode('cp437', errors='replace'))
print(stderr.read().decode('cp437', errors='replace'))

c.close()