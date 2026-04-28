"""Verifica y fuerza el uso de server_corregido.py en PCMASTER."""
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

# 2. VERIFICAR QUE EL ARCHIVO ES REALMENTE MI VERSION
print("=== VERIFICACION CRUZADA DEL ARCHIVO ===")
checks = [
    ('v6.2', 'version 6.2'),
    ('tcp_admin_listener', 'funcion tcp_admin_listener'),
    ('EOFError', 'manejo de EOFError'),
    ('sin TTY', 'comentario sin TTY'),
    ('ADMIN TCP activo', 'log de admin TCP'),
    ('asyncio.Lock', 'usando asyncio.Lock'),
]
for term, desc in checks:
    stdin, stdout, stderr = c.exec_command(f'findstr /C:"{term}" "{BASE_SCRIPTS}\\server.py"', timeout=5)
    out = stdout.read().decode('cp437', errors='replace')
    if out.strip():
        print(f"[OK] {desc}: ENCONTRADO")
    else:
        print(f"[FAIL] {desc}: NO ENCONTRADO")

# 3. Verificar si hay otro server.py en otro lado
print("\n=== BUSCANDO OTROS server.py ===")
stdin, stdout, stderr = c.exec_command('dir /S /B server.py 2>nul', timeout=10)
out = stdout.read().decode('cp437', errors='replace')
print(out if out.strip() else "Solo uno (o ninguno)")

# 4. Limpiar __pycache__ RECURSIVAMENTE
print("\n=== LIMPIEZA PROFUNDA ===")
c.exec_command('rmdir /S /Q "__pycache__" 2>nul', timeout=5)
c.exec_command(f'rmdir /S /Q "{BASE_SCRIPTS}\\__pycache__" 2>nul', timeout=5)
c.exec_command(f'del /Q "{BASE_SCRIPTS}\\*.pyc" 2>nul', timeout=5)
time.sleep(1)
print("[OK] Cache eliminado")

# 5. Volver a subir el archivo para estar SEGUROS
print("\n=== RESUBIENDO server.py ===")
sftp = c.open_sftp()
sftp.put(r"C:\Users\CYBER\Desktop\server_corregido.py", f"{BASE_SCRIPTS}\\server.py")
size = sftp.stat(f"{BASE_SCRIPTS}\\server.py").st_size
sftp.close()
print(f"[OK] Resubido: {size} bytes")

# 6. Verificar que ahora sí tiene "v6.2"
stdin, stdout, stderr = c.exec_command(f'findstr /C:"v6.2" "{BASE_SCRIPTS}\\server.py"', timeout=5)
out = stdout.read().decode('cp437', errors='replace')
print(f"Verificacion v6.2: {'ENCONTRADO' if out.strip() else 'NO ENCONTRADO'}")

# 7. Lanzar el servidor DIRECTO con python -u y stdin redirigido a NUL
print("\n=== LANZANDO SERVIDOR (DIRECTO) ===")
# Usar cmd /c con redireccion para que no espere input
launcher_cmd = f'cd /d "C:\\Users\\PCMASTER\\{BASE_SCRIPTS}" && python -u server.py < NUL > server_output_NEW.log 2>&1'
print(f"CMD: {launcher_cmd}")

# Usar exec_command directamente (esto corre y termina)
stdin, stdout, stderr = c.exec_command(launcher_cmd, timeout=20)
# No esperamos el output porque se va al log
time.sleep(8)

# 8. Verificar puertos
print("\n=== PUERTOS ===")
stdin, stdout, stderr = c.exec_command('netstat -ano | findstr ":5006 :5007"', timeout=10)
out = stdout.read().decode('cp437', errors='replace')
if out.strip():
    print(f"[OK] Puertos detectados:\n{out}")
else:
    print("[WARN] Sin puertos detectados - revisando log nuevo...")
    stdin, stdout, stderr = c.exec_command(f'type "C:\\Users\\PCMASTER\\{BASE_SCRIPTS}\\server_output_NEW.log"', timeout=10)
    log = stdout.read().decode('cp437', errors='replace')
    print(log[-2000:] if log else "(vacio)")

# 9. Ver si python sigue corriendo
print("\n=== PROCESOS PYTHON ACTIVOS ===")
stdin, stdout, stderr = c.exec_command('tasklist /FI "IMAGENAME eq python.exe" 2>&1', timeout=10)
print(stdout.read().decode('cp437', errors='replace'))

c.close()
print("\nVERIFICACION COMPLETADA")