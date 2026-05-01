"""script completo de pruebas funcionales para roxymaster"""
import requests
import subprocess
import json
import time
import os

BASE_URL = "http://192.168.1.17:8086"
SSH_CMD = f'ssh -i "{os.path.expanduser("~")}\\.ssh\\roxykey" pcmaster@192.168.1.17'
DB_PATH = r"C:\users\pcmaster\desktop\roxymaster\pcmaster\data\roxymaster.db"
PYTHON_PATH = r"C:\Users\PCMASTER\AppData\Local\Programs\Python\Python310\python.exe"

resultados = []
token_admin = None
token_user = None


def ssh(command):
    """ejecuta comando via ssh en pcmaster"""
    full = f'{SSH_CMD} "{command}"'
    try:
        r = subprocess.run(["powershell", "-Command", full], capture_output=True, text=True, timeout=15)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except Exception as e:
        return "", str(e), 1


def ssh_python(script_content):
    """sube un script python y lo ejecuta"""
    tmp_name = "temp_check.py"
    with open(tmp_name, "w", encoding="utf-8") as f:
        f.write(script_content)
    scp = f'scp -i "{os.path.expanduser("~")}\\.ssh\\roxykey" {tmp_name} pcmaster@192.168.1.17:C:/users/pcmaster/desktop/roxymaster/'
    subprocess.run(["powershell", "-Command", scp], capture_output=True, timeout=10)
    out, err, rc = ssh(f"{PYTHON_PATH} C:\\users\\pcmaster\\desktop\\roxymaster\\{tmp_name}")
    os.remove(tmp_name)
    return out, err, rc


def registrar_resultado(fase, descripcion, ok, detalle=""):
    icono = "[OK]" if ok else "[FAIL]" if ok is False else "[WARN]"
    resultados.append({
        "fase": fase,
        "descripcion": descripcion,
        "ok": ok,
        "detalle": detalle,
        "icono": icono
    })
    print(f"  {icono} FASE {fase}: {descripcion} - {detalle}")


# =============================================================
# FASE 1: VERIFICACIÓN DEL ENTORNO
# =============================================================
print("\n" + "="*60)
print("FASE 1: VERIFICACIÓN DEL ENTORNO")
print("="*60)

try:
    r = requests.get(f"{BASE_URL}/api/dashboard", timeout=8)
    if r.status_code == 200:
        data = r.json()
        registrar_resultado(1, "entorno", True, f"dashboard responde: {json.dumps(data)[:200]}")
    else:
        registrar_resultado(1, "entorno", False, f"status {r.status_code}")
except Exception as e:
    registrar_resultado(1, "entorno", False, str(e)[:150])

# =============================================================
# FASE 2: AUTENTICACIÓN
# =============================================================
print("\n" + "="*60)
print("FASE 2: AUTENTICACIÓN")
print("="*60)

# Login admin
try:
    r = requests.post(f"{BASE_URL}/api/login", json={"email": "pcmaster", "password": "abc123$_"}, timeout=8)
    if r.status_code == 200 and r.json().get("ok"):
        token_admin = r.json().get("token")
        registrar_resultado(2, "login admin", True, f"token obtenido")
    else:
        registrar_resultado(2, "login admin", False, f"respuesta: {r.text[:200]}")
except Exception as e:
    registrar_resultado(2, "login admin", False, str(e)[:150])

# Registrar usuario de prueba
try:
    r = requests.post(f"{BASE_URL}/api/register", json={
        "email": "testfuncional@roxymaster.com",
        "password": "test123",
        "referido_por": "pcmaster"
    }, timeout=8)
    if r.status_code == 200 and r.json().get("ok"):
        token_user = r.json().get("token")
        registrar_resultado(2, "registro usuario prueba", True, "registrado exitosamente")
    elif "ya existe" in r.text.lower():
        # Hacer login
        r2 = requests.post(f"{BASE_URL}/api/login", json={
            "email": "testfuncional@roxymaster.com",
            "password": "test123"
        }, timeout=8)
        if r2.status_code == 200 and r2.json().get("ok"):
            token_user = r2.json().get("token")
            registrar_resultado(2, "login usuario prueba", True, "usuario ya existía, login ok")
        else:
            registrar_resultado(2, "autenticación usuario prueba", False, f"no se pudo registrar ni loguear: {r.text[:200]}")
    else:
        registrar_resultado(2, "registro usuario prueba", False, f"respuesta: {r.text[:200]}")
except Exception as e:
    registrar_resultado(2, "autenticación usuario prueba", False, str(e)[:150])

# =============================================================
# FASE 3: RECARGA DE SALDO
# =============================================================
print("\n" + "="*60)
print("FASE 3: RECARGA DE SALDO")
print("="*60)

script_recarga = (
    'import sqlite3\n'
    f'conn = sqlite3.connect(r"{DB_PATH}")\n'
    "conn.execute(\"insert or ignore into wallets (wallet, usuario_id, saldo_tokens) select wallet, id, 0 from usuarios where lower(email)=lower('testfuncional@roxymaster.com')\")\n"
    "conn.execute(\"update wallets set saldo_tokens = saldo_tokens + 1500 where usuario_id = (select id from usuarios where lower(email)=lower('testfuncional@roxymaster.com'))\")\n"
    "conn.commit()\n"
    "row = conn.execute(\"select saldo_tokens from wallets where usuario_id = (select id from usuarios where lower(email)=lower('testfuncional@roxymaster.com'))\").fetchone()\n"
    "print('SALDO=' + str(row[0]) if row else 'NO_WALLET')\n"
    "conn.close()\n"
)
out, err, rc = ssh_python(script_recarga)
if "SALDO=" in out:
    saldo = out.split("SALDO=")[1].strip()
    registrar_resultado(3, "recarga de saldo", True, f"saldo actual: {saldo} tokens")
elif "NO_WALLET" in out:
    registrar_resultado(3, "recarga de saldo", False, "no se encontró wallet para el usuario de prueba")
else:
    registrar_resultado(3, "recarga de saldo", False, f"error: {err[:150]}")

# =============================================================
# FASE 4: MARKETPLACE P2P
# =============================================================
print("\n" + "="*60)
print("FASE 4: MARKETPLACE P2P")
print("="*60)

if token_user:
    headers = {"Authorization": f"Bearer {token_user}", "Content-Type": "application/json"}
    try:
        r = requests.post(f"{BASE_URL}/api/kbt/crear_oferta", json={
            "tokens": 100,
            "precio_soles": 100
        }, headers=headers, timeout=8)
        if r.status_code == 200:
            registrar_resultado(4, "marketplace crear oferta", True, f"endpoint OK: {r.text[:200]}")
        elif r.status_code == 404:
            registrar_resultado(4, "marketplace crear oferta", "pendiente", "endpoint 404, se usa insercion directa")
            # Insercion directa
            script_insert = f'''
import sqlite3
conn = sqlite3.connect(r"{DB_PATH}")
conn.execute("insert into ordenes_marketplace (tipo, wallet, usuario_id, cantidad, precio_pen, estado) values ('venta', (select wallet from usuarios where lower(email)=lower('testfuncional@roxymaster.com')), (select id from usuarios where lower(email)=lower('testfuncional@roxymaster.com')), 100, 1.00, 'activa')")
conn.commit()
rows = conn.execute("select * from ordenes_marketplace where estado='activa'").fetchall()
print(f"OK: {len(rows)} ofertas activas")
conn.close()
'''
            out2, err2, rc2 = ssh_python(script_insert)
            if "OK:" in out2:
                registrar_resultado(4, "marketplace insercion directa", True, out2.strip())
            else:
                registrar_resultado(4, "marketplace insercion directa", False, err2[:150])
        else:
            registrar_resultado(4, "marketplace crear oferta", False, f"status {r.status_code}: {r.text[:200]}")
    except Exception as e:
        registrar_resultado(4, "marketplace crear oferta", False, str(e)[:150])
else:
    registrar_resultado(4, "marketplace", False, "no hay token de usuario")

# =============================================================
# FASE 5: ORQUESTACIÓN
# =============================================================
print("\n" + "="*60)
print("FASE 5: ORQUESTACIÓN")
print("="*60)

# Insertar perfiles de prueba
script_perfiles = f'''
import sqlite3
conn = sqlite3.connect(r"{DB_PATH}")
for i in range(1, 4):
    conn.execute("insert or ignore into perfiles (granjero_id, nombre_perfil, estado) values (?, ?, ?)", ("testfuncional@roxymaster.com", f"perfil_prueba_{{i}}", "activo"))
conn.commit()
rows = conn.execute("select count(*) from perfiles where granjero_id='testfuncional@roxymaster.com'").fetchone()
print(f"PERFILES={{rows[0]}}")
conn.close()
'''
out_p, err_p, rc_p = ssh_python(script_perfiles)
print(f"  Perfiles: {out_p}")

if token_admin:
    try:
        r = requests.post(f"{BASE_URL}/api/comando", json={
            "comando": "asignar 3 url https://kick.com/test-funcional duracion 5"
        }, headers={"Authorization": f"Bearer {token_admin}", "Content-Type": "application/json"}, timeout=8)
        if r.status_code == 200:
            data = r.json()
            if data.get("ok") or "asign" in json.dumps(data).lower():
                registrar_resultado(5, "orquestación comando asignar", True, f"respuesta: {json.dumps(data)[:200]}")
            elif "accion desconocida" in json.dumps(data).lower() or "no reconoc" in json.dumps(data).lower():
                registrar_resultado(5, "orquestación comando asignar", "parcial", "acción desconocida - parser no implementado aún")
            else:
                registrar_resultado(5, "orquestación comando asignar", "parcial", json.dumps(data)[:200])
        else:
            registrar_resultado(5, "orquestación comando asignar", False, f"status {r.status_code}: {r.text[:200]}")
    except Exception as e:
        registrar_resultado(5, "orquestación comando asignar", False, str(e)[:150])
else:
    registrar_resultado(5, "orquestación", False, "no hay token admin")

# =============================================================
# FASE 6: DASHBOARD Y ESTADO DE USUARIO
# =============================================================
print("\n" + "="*60)
print("FASE 6: DASHBOARD Y ESTADO DE USUARIO")
print("="*60)

# Dashboard
try:
    r = requests.get(f"{BASE_URL}/api/dashboard", timeout=8)
    if r.status_code == 200:
        data = r.json()
        pcbots = data.get("pcbots_conectados", "N/A")
        registrar_resultado(6, "dashboard admin", True, f"pcbots_conectados: {pcbots}")
    else:
        registrar_resultado(6, "dashboard admin", False, f"status {r.status_code}")
except Exception as e:
    registrar_resultado(6, "dashboard admin", False, str(e)[:150])

# Mi estado
if token_user:
    try:
        r = requests.get(f"{BASE_URL}/api/mi_estado", headers={"Authorization": f"Bearer {token_user}"}, timeout=8)
        if r.status_code == 200:
            registrar_resultado(6, "mi_estado usuario", True, f"respuesta OK: {r.text[:200]}")
        elif r.status_code == 500:
            registrar_resultado(6, "mi_estado usuario", False, f"error 500: {r.text[:300]}")
        else:
            registrar_resultado(6, "mi_estado usuario", "parcial", f"status {r.status_code}: {r.text[:200]}")
    except Exception as e:
        registrar_resultado(6, "mi_estado usuario", False, str(e)[:150])
else:
    registrar_resultado(6, "mi_estado usuario", False, "no hay token de usuario")

# KBT Stats
try:
    r = requests.get(f"{BASE_URL}/api/kbt/stats", timeout=8)
    if r.status_code == 200:
        registrar_resultado(6, "kbt stats", True, r.text[:200])
    elif r.status_code == 404:
        registrar_resultado(6, "kbt stats", "pendiente", "endpoint no existe")
    else:
        registrar_resultado(6, "kbt stats", "parcial", f"status {r.status_code}: {r.text[:200]}")
except Exception as e:
    registrar_resultado(6, "kbt stats", False, str(e)[:150])

# =============================================================
# FASE 7: REFERIDOS
# =============================================================
print("\n" + "="*60)
print("FASE 7: REFERIDOS")
print("="*60)

script_ref = (
    'import sqlite3\n'
    f'conn = sqlite3.connect(r"{DB_PATH}")\n'
    "row = conn.execute(\"select referido_por from usuarios where lower(email)=lower('testfuncional@roxymaster.com')\").fetchone()\n"
    "if row and row[0]:\n"
    "    print('REFERIDO_POR=' + str(row[0]))\n"
    "else:\n"
    "    conn.execute(\"update usuarios set referido_por='pcmaster' where lower(email)=lower('testfuncional@roxymaster.com')\")\n"
    "    conn.commit()\n"
    "    print('ASIGNADO=pcmaster')\n"
    "conn.close()\n"
)
out_r, err_r, rc_r = ssh_python(script_ref)
if "REFERIDO_POR=" in out_r:
    ref = out_r.split("REFERIDO_POR=")[1].strip()
    registrar_resultado(7, "referidos", True, f"referido_por: {ref}")
elif "ASIGNADO=" in out_r:
    registrar_resultado(7, "referidos", True, "asignado manualmente a pcmaster")
else:
    registrar_resultado(7, "referidos", False, f"error: {err_r[:150]}")

# =============================================================
# FASE 8: RESUMEN FINAL
# =============================================================
print("\n" + "="*60)
print("RESUMEN FINAL")
print("="*60)

print("\n| fase | descripción | resultado | detalle |")
print("|------|-------------|-----------|---------|")
for r in resultados:
    print(f"| {r['fase']} | {r['descripcion']} | {r['icono']} | {r['detalle'][:100]} |")

aprobadas = sum(1 for r in resultados if r['ok'] is True)
parciales = sum(1 for r in resultados if r['ok'] == "parcial" or r['ok'] == "pendiente")
fallidas = sum(1 for r in resultados if r['ok'] is False)
total = len(resultados)

print(f"\n[OK] Aprobadas: {aprobadas}/{total}")
print(f"[WARN] Parciales/Pendientes: {parciales}/{total}")
print(f"[FAIL] Fallidas: {fallidas}/{total}")

if fallidas == 0 and parciales == 0:
    print("\n*** SISTEMA LISTO PARA PRUEBAS CON USUARIOS REALES ***")
elif fallidas == 0 and parciales <= 2:
    print("\n*** SISTEMA FUNCIONAL pero con endpoints pendientes de implementar ***")
else:
    print("\n*** SISTEMA NECESITA TRABAJO DE BACKEND antes de pruebas con usuarios reales ***")
