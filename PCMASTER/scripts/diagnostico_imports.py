"""Diagnostica imports del server en PCMASTER."""
import paramiko
import sys
sys.stdout.reconfigure(encoding='utf-8')

PASSWORD = r"Abc123$_"
HOST = "192.168.1.17"
USER = "PCMASTER"
BASE_SCRIPTS = r"Desktop\ROXYMASTER\PCMASTER\scripts"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username=USER, password=PASSWORD, timeout=10, look_for_keys=False, allow_agent=False)

# 1. Listar scripts
print("=== ARCHIVOS EN scripts/ ===")
stdin, stdout, stderr = c.exec_command(f'dir /B "{BASE_SCRIPTS}"', timeout=10)
print(stdout.read().decode('cp437', errors='replace'))

# 2. Verificar config.json
print("=== config.json EXISTE? ===")
stdin, stdout, stderr = c.exec_command(f'if exist "{BASE_SCRIPTS}\\..\\config.json" (echo SI) else (echo NO)', timeout=10)
print(stdout.read().decode('cp437', errors='replace').strip())

# 3. Verificar prompts/
print("=== prompts/ EXISTE? ===")
stdin, stdout, stderr = c.exec_command(f'if exist "{BASE_SCRIPTS}\\..\\prompts" (echo SI) else (echo NO)', timeout=10)
print(stdout.read().decode('cp437', errors='replace').strip())

# 4. Probar import directo de server.py
print("\n=== PROBANDO IMPORT server.py ===")
test_script = f"""import sys,os,traceback
sys.path.insert(0, r'C:\\Users\\PCMASTER\\Desktop\\ROXYMASTER\\PCMASTER\\scripts')
os.chdir(r'C:\\Users\\PCMASTER\\Desktop\\ROXYMASTER\\PCMASTER\\scripts')
try:
    exec(open('server.py', encoding='utf-8').read())
    print('OK: server.py carga sin errores')
except SystemExit:
    print('OK: server.py usa asyncio.run() - normal')
except Exception as e:
    traceback.print_exc()
"""
stdin, stdout, stderr = c.exec_command(f'python -c "{test_script}"', timeout=15)
out = stdout.read().decode('cp437', errors='replace')
err = stderr.read().decode('cp437', errors='replace')
print(out if out.strip() else "(sin stdout)")
if err.strip():
    print(f"STDERR:\n{err}")

c.close()