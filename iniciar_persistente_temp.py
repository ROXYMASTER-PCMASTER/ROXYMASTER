"""lanza el servidor de forma persistente detectando el interprete pythonw si existe."""
import subprocess, os, sys, time

base = r"C:\users\pcmaster\desktop\roxymaster\pcmaster"
scripts = os.path.join(base, "scripts")
os.chdir(base)

# intentar pythonw primero (no necesita ventana cmd)
python_exe = None
for candidate in ["pythonw", "python", "python3"]:
    try:
        r = subprocess.run(["where", candidate], capture_output=True, text=True, timeout=3)
        if r.returncode == 0 and r.stdout.strip():
            python_exe = candidate
            break
    except:
        pass

python_exe = python_exe or "python"
print(f"[*] usando interprete: {python_exe}")

# usar DETACHED_PROCESS para independizar el proceso
print("[*] iniciando servidor...")
flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
proc = subprocess.Popen(
    [python_exe, os.path.join(scripts, "server.py")],
    stdout=open(os.path.join(base, "server.log"), "w"),
    stderr=subprocess.STDOUT,
    creationflags=flags,
    close_fds=True,
)

print(f"[*] pid: {proc.pid}")
print("[*] esperando 5s...")
time.sleep(5)

# verificar puertos
r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
for port in ["5006", "8086"]:
    if f":{port}" in r.stdout and "LISTENING" in r.stdout:
        print(f"    puerto {port}: listening OK")
    else:
        print(f"    puerto {port}: NO RESPONDE")

# mostrar ultimas lineas del log
logpath = os.path.join(base, "server.log")
if os.path.exists(logpath):
    with open(logpath, "r") as f:
        lines = f.readlines()
        print("\n[log] ultimas 10 lineas:")
        for l in lines[-10:]:
            print(f"    {l.rstrip()}")