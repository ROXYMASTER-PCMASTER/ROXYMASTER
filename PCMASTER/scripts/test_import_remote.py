"""Crea test en PCMASTER y lo ejecuta para diagnosticar imports."""
import paramiko
import sys
import io
sys.stdout.reconfigure(encoding='utf-8')

PASSWORD = r"Abc123$_"
HOST = "192.168.1.17"
USER = "PCMASTER"
BASE_SCRIPTS = r"Desktop\ROXYMASTER\PCMASTER\scripts"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASSWORD, timeout=10, look_for_keys=False, allow_agent=False)

# Subir script de test
test_py = """import sys, os, traceback
sys.path.insert(0, r'C:\\Users\\PCMASTER\\Desktop\\ROXYMASTER\\PCMASTER\\scripts')
os.chdir(r'C:\\Users\\PCMASTER\\Desktop\\ROXYMASTER\\PCMASTER\\scripts')
try:
    exec(open('server.py', encoding='utf-8').read())
    print('OK: server.py carga sin errores')
except SystemExit as e:
    print(f'OK: server.py usa asyncio.run() - normal (exit code={e.code})')
except Exception as e:
    print('ERROR:')
    traceback.print_exc()
"""
sftp = c.open_sftp()
sftp.putfo(io.BytesIO(test_py.encode()), f"{BASE_SCRIPTS}\\test_import.py")
sftp.close()

# Ejecutar
print("=== EJECUTANDO test_import.py ===")
stdin, stdout, stderr = c.exec_command(f'cd "C:\\Users\\PCMASTER\\{BASE_SCRIPTS}" && python -u test_import.py 2>&1', timeout=15)
out = stdout.read().decode('cp437', errors='replace')
err = stderr.read().decode('cp437', errors='replace')
print(out)
if err.strip():
    print(f"STDERR: {err}")

# También ver el log del servidor reciente
print("\n=== LOG DEL SERVIDOR ===")
stdin, stdout, stderr = c.exec_command(f'type "{BASE_SCRIPTS}\\server_output.log"', timeout=10)
log = stdout.read().decode('cp437', errors='replace')
if log.strip():
    for line in log.strip().split('\n')[-40:]:
        print(line)
else:
    print("(vacio)")

c.close()