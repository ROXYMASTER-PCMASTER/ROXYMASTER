"""script temporal para reiniciar el servidor en pcmaster."""
import subprocess, sys, os

print("[1] verificando sintaxis de server.py...")
server_path = r"C:\users\pcmaster\desktop\roxymaster\pcmaster\scripts\server.py"
try:
    import py_compile
    py_compile.compile(server_path, doraise=True)
    print("    sintaxis ok")
except py_compile.PyCompileError as e:
    print(f"    error de sintaxis: {e}")
    sys.exit(1)

print("[2] verificando sintaxis de auth.py...")
auth_path = r"C:\users\pcmaster\desktop\roxymaster\pcmaster\scripts\auth.py"
try:
    py_compile.compile(auth_path, doraise=True)
    print("    sintaxis ok")
except py_compile.PyCompileError as e:
    print(f"    error de sintaxis: {e}")
    sys.exit(1)

print("[3] matando procesos python previos...")
os.system("taskkill /f /im python.exe 2>nul")

print("[4] comprobando que el puerto 8086 este libre...")
result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
if ":8086" in result.stdout and "LISTENING" in result.stdout:
    print("    advertencia: puerto 8086 sigue ocupado")

print("[5] iniciando servidor...")
os.chdir(r"C:\users\pcmaster\desktop\roxymaster\pcmaster")
os.system("start /b python scripts\main.py > server.log 2>&1")

print("[6] esperando 6 segundos...")
import time
time.sleep(6)

print("[7] verificando puertos...")
result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
if ":8086" in result.stdout:
    print("    puerto 8086: listening")
else:
    print("    puerto 8086: NO RESPONDE - mostrando log:")
    try:
        with open(r"C:\users\pcmaster\desktop\roxymaster\pcmaster\server.log", "r") as f:
            log = f.read()
            print(log[:2000] if log else "(log vacio)")
    except:
        print("    no se pudo leer el log")

print("[8] listo.")