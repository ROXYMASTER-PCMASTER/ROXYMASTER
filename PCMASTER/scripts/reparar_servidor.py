"""Limpia cache, verifica archivo e inicia servidor correctamente."""
import paramiko
import sys
import os
import time

sys.stdout.reconfigure(encoding='utf-8')

PASSWORD = r"Abc123$_"
HOST = "192.168.1.17"
USER = "PCMASTER"
BASE_SCRIPTS = r"Desktop\ROXYMASTER\PCMASTER\scripts"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASSWORD, timeout=10, look_for_keys=False, allow_agent=False)

# 1. Verificar que el archivo subido TIENE el parche (buscar tcp_admin_listener)
print("=== VERIFICANDO ARCHIVO SUBIDO ===")
stdin, stdout, stderr = c.exec_command(f'findstr /C:"tcp_admin_listener" "{BASE_SCRIPTS}\\server.py"', timeout=10)
out = stdout.read().decode('cp437', errors='replace')
if "tcp_admin_listener" in out:
    print("[OK] server.py contiene el parche TCP admin")
else:
    print("[FAIL] server.py NO contiene el parche - REVISAR")

stdin, stdout, stderr = c.exec_command(f'findstr /C:"EOFError" "{BASE_SCRIPTS}\\server.py"', timeout=10)
out = stdout.read().decode('cp437', errors='replace')
if "EOFError" in out:
    print("[OK] server.py maneja EOFError")
else:
    print("[WARN] server.py NO maneja EOFError")

# 2. Limpiar cache Python
print("\n=== LIMPIANDO CACHE ===")
c.exec_command(f'rmdir /S /Q "{BASE_SCRIPTS}\\__pycache__" 2>nul', timeout=5)
time.sleep(1)
print("[OK] __pycache__ eliminado")

# 3. Crear script launcher que redirige stdin a NUL
print("\n=== CREANDO LAUNCHER ===")
launcher = f"""@echo off
cd /d "{BASE_SCRIPTS}"
echo Iniciando ROXYMASTER server...
python server.py < nul > server_output.log 2>&1
echo Servidor detenido.
"""
sftp = c.open_sftp()
with open(r"C:\Users\CYBER\Desktop\_launcher.bat", "w") as f:
    f.write(launcher)
sftp.put(r"C:\Users\CYBER\Desktop\_launcher.bat", f"{BASE_SCRIPTS}\\start_server.bat")
sftp.close()
os.remove(r"C:\Users\CYBER\Desktop\_launcher.bat")
print("[OK] Launcher creado: start_server.bat")

# 4. Matar procesos
c.exec_command('taskkill /F /IM python.exe 2>nul', timeout=5)
time.sleep(2)

# 5. Iniciar usando start /B (background sin ventana)
print("\n=== INICIANDO SERVIDOR ===")
stdin, stdout, stderr = c.exec_command(f'start "" /B /MIN cmd /c "{BASE_SCRIPTS}\\start_server.bat"', timeout=10)
time.sleep(6)

# 6. Verificar puertos y log
print("\n=== PUERTOS ===")
stdin, stdout, stderr = c.exec_command('netstat -ano | findstr ":5006 :5007"', timeout=10)
out = stdout.read().decode('cp437', errors='replace')
if out.strip():
    print(out)
else:
    print("NINGUN puerto detectado aun")

print("\n=== LOG DEL SERVIDOR ===")
stdin, stdout, stderr = c.exec_command(f'type "{BASE_SCRIPTS}\\server_output.log"', timeout=10)
log = stdout.read().decode('cp437', errors='replace')
# Solo mostrar lineas utiles
for line in log.split('\n'):
    line = line.strip()
    if line and 'Error:' not in line and 'input(' not in line:
        print(line)

# 7. Test TCP admin via Python
print("\n=== TEST TCP ADMIN ===")
test_code = "import socket;s=socket.socket();s.settimeout(5);s.connect(('127.0.0.1',5007));s.sendall(b'estado\\n');import time;time.sleep(0.5);print(s.recv(4096).decode());s.close()"
stdin, stdout, stderr = c.exec_command(f'python -c "{test_code}"', timeout=10)
result = stdout.read().decode('cp437', errors='replace')
err = stderr.read().decode('cp437', errors='replace')
if result.strip():
    print(result)
if err.strip():
    print(f"STDERR: {err}")

c.close()
print("\nDIAGNOSTICO COMPLETADO")