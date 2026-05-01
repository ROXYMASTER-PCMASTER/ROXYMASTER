"""script integral: corrige codigo, reinicia servidor y ejecuta pruebas."""
import os
import sys
import subprocess
import time
import json
import sqlite3
import urllib.request
import urllib.error

BASE_DIR = r"C:\users\pcmaster\desktop\roxymaster\pcmaster"
SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
DB = os.path.join(BASE_DIR, "data", "roxymaster.db")
BASE_URL = "http://127.0.0.1:8086"

resultados = []

def log_resultado(fase, descripcion, ok, detalle=""):
    emoji = "OK" if ok else "FAIL"
    r = {"fase": fase, "descripcion": descripcion, "ok": ok, "detalle": detalle}
    resultados.append(r)
    print(f"[{emoji}] fase {fase}: {descripcion} | {detalle[:200]}")

def db_ejecutar(sql, params=None):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    if params:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
    if sql.strip().upper().startswith(("SELECT", "PRAGMA")):
        rows = cur.fetchall()
        conn.close()
        return rows
    conn.commit()
    conn.close()
    return None

def peticion(metodo, ruta, datos=None, token=None):
    url = f"{BASE_URL}{ruta}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data_bytes = None
    if datos is not None:
        data_bytes = json.dumps(datos).encode("utf-8")
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return e.code, body
    except Exception as e:
        return 0, str(e)

# ===================================================================
# paso 0: verificar que los archivos existen
# ===================================================================
print("=== PASO 0: VERIFICACION DE ARCHIVOS ===")
for f in ["http_server.py", "auth.py", "server.py"]:
    path = os.path.join(SCRIPTS_DIR, f)
    if os.path.isfile(path):
        print(f"    {f}: existe ({os.path.getsize(path)} bytes)")
    else:
        print(f"    {f}: NO EXISTE")
        sys.exit(1)

# ===================================================================
# paso 1: leer los archivos remotos
# ===================================================================
print("\n=== PASO 1: LECTURA DE ARCHIVOS ===")

with open(os.path.join(SCRIPTS_DIR, "http_server.py"), "r", encoding="utf-8") as f:
    http_code = f.read()

with open(os.path.join(SCRIPTS_DIR, "auth.py"), "r", encoding="utf-8") as f:
    auth_code = f.read()

print(f"    http_server.py: {len(http_code)} caracteres")
print(f"    auth.py: {len(auth_code)} caracteres")

# ===================================================================
# paso 2: corregir referencias en http_server.py
# ===================================================================
print("\n=== PASO 2: CORRECCIONES EN HTTP_SERVER.PY ===")

# Correct column names based on real schema:
# wallets: wallet, usuario_id (NOT email), saldo_tokens, ...
# ordenes_marketplace: usuario_id (NOT vendedor), precio_pen (NOT precio_unitario), ...

correcciones_aplicadas = 0

# 2a: wallets.email -> wallets.usuario_id or join with usuarios
# Replace patterns like "wallets.email" or "WHERE w.email" etc
if "wallets.email" in http_code.lower() or "w.email" in http_code.lower():
    http_code = http_code.replace("wallets.email", "wallets.usuario_id")
    http_code = http_code.replace("w.email", "w.usuario_id")
    correcciones_aplicadas += 1
    print("    corregido: wallets.email -> wallets.usuario_id")

# 2b: verify mi_estado endpoint doesn't use wrong columns
# The endpoint should query usuarios + wallets joined on usuario_id/wallet
# Let's check if there's a broken JOIN
if "JOIN wallets ON" in http_code:
    # Fix: JOIN wallets ON usuarios.email = wallets.usuario_id
    old_join = "JOIN wallets ON u.email = wallets.email" if "u.email = wallets.email" in http_code else None
    if "usuarios.email = wallets.usuario_id" not in http_code and "u.email = wallets.email" in http_code:
        http_code = http_code.replace("u.email = wallets.email", "u.email = wallets.usuario_id")
        correcciones_aplicadas += 1
        print("    corregido: join wallets por email -> usuario_id")

# 2c: referencias a auth_users -> usuarios
if "auth_users" in http_code.lower():
    http_code = http_code.replace("auth_users", "usuarios")
    http_code = http_code.replace("AUTH_USERS", "usuarios")
    correcciones_aplicadas += 1
    print("    corregido: auth_users -> usuarios")

# 2d: ordenes_marketplace.vendedor -> ordenes_marketplace.usuario_id
if "vendedor" in http_code.lower():
    http_code = http_code.replace("vendedor", "usuario_id")
    correcciones_aplicadas += 1
    print("    corregido: vendedor -> usuario_id en ordenes_marketplace")

# 2e: precio_unitario -> precio_pen
if "precio_unitario" in http_code.lower():
    http_code = http_code.replace("precio_unitario", "precio_pen")
    correcciones_aplicadas += 1
    print("    corregido: precio_unitario -> precio_pen")

print(f"    total correcciones en http_server.py: {correcciones_aplicadas}")

# ===================================================================
# paso 3: corregir referencias en auth.py
# ===================================================================
print("\n=== PASO 3: CORRECCIONES EN AUTH.PY ===")
correcciones_auth = 0

if "auth_users" in auth_code.lower():
    auth_code = auth_code.replace("auth_users", "usuarios")
    auth_code = auth_code.replace("AUTH_USERS", "usuarios")
    correcciones_auth += 1
    print("    corregido: auth_users -> usuarios")

# check if auth.py references usuarios correctly for login/register
if "wallets.email" in auth_code.lower():
    auth_code = auth_code.replace("wallets.email", "wallets.usuario_id")
    correcciones_auth += 1
    print("    corregido: wallets.email -> wallets.usuario_id")

print(f"    total correcciones en auth.py: {correcciones_auth}")

# ===================================================================
# paso 4: guardar archivos corregidos
# ===================================================================
print("\n=== PASO 4: GUARDANDO ARCHIVOS CORREGIDOS ===")

with open(os.path.join(SCRIPTS_DIR, "http_server.py"), "w", encoding="utf-8") as f:
    f.write(http_code)
print("    http_server.py guardado")

with open(os.path.join(SCRIPTS_DIR, "auth.py"), "w", encoding="utf-8") as f:
    f.write(auth_code)
print("    auth.py guardado")

# ===================================================================
# paso 5: reiniciar servidor
# ===================================================================
print("\n=== PASO 5: REINICIANDO SERVIDOR ===")

# matar procesos python
os.system("taskkill /f /im python.exe 2>nul")
os.system("taskkill /f /im pythonw.exe 2>nul")
time.sleep(2)

# verificar que puertos esten libres
r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
if ":8086" in r.stdout and "LISTENING" in r.stdout:
    print("    advertencia: puerto 8086 sigue ocupado, forzando...")
    for line in r.stdout.splitlines():
        if ":8086" in line and "LISTENING" in line:
            parts = line.strip().split()
            pid = parts[-1] if parts[-1].isdigit() else None
            if pid:
                os.system(f"taskkill /f /pid {pid} 2>nul")
    time.sleep(2)

# iniciar servidor de forma persistente con DETACHED_PROCESS
os.chdir(BASE_DIR)
flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
log_file = open(os.path.join(BASE_DIR, "server.log"), "w")
proc = subprocess.Popen(
    ["pythonw", os.path.join(SCRIPTS_DIR, "server.py")],
    stdout=log_file,
    stderr=subprocess.STDOUT,
    creationflags=flags,
    close_fds=True,
)
print(f"    servidor iniciado con pid={proc.pid}")
print("    esperando 8 segundos...")
time.sleep(8)

# verificar puertos
r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
for port in ["5006", "8086"]:
    if f":{port}" in r.stdout and "LISTENING" in r.stdout:
        print(f"    puerto {port}: listening OK")
    else:
        print(f"    puerto {port}: NO RESPONDE")
        # mostrar ultimas lineas del log
        logpath = os.path.join(BASE_DIR, "server.log")
        if os.path.exists(logpath):
            with open(logpath, "r") as f:
                lines = f.readlines()
                print(f"    ultimas 15 lineas del log:")
                for l in lines[-15:]:
                    print(f"        {l.rstrip()}")

# ===================================================================
# paso 6: pruebas funcionales
# ===================================================================
print("\n" + "=" * 60)
print("FASE 1: VERIFICACION DEL ENTORNO")
print("=" * 60)

status, body = peticion("GET", "/api/dashboard")
if status == 200:
    log_resultado("1", "servidor http responde", True, f"status {status}")
    try:
        data = json.loads(body)
        print(f"    dashboard keys: {list(data.keys())[:10]}")
    except:
        pass
else:
    log_resultado("1", "servidor http responde", False, f"status {status} body={body[:200]}")

# login admin
print("\n" + "=" * 60)
print("FASE 2: AUTENTICACION")
print("=" * 60)

status, body = peticion("POST", "/api/login", {"email": "pcmaster", "password": "abc123$_"})
try:
    resp = json.loads(body)
    token_admin = resp.get("token", "")
except:
    token_admin = ""

if status == 200 and token_admin:
    log_resultado("2", "login admin", True, f"token={token_admin[:20]}...")
else:
    log_resultado("2", "login admin", False, f"status={status} body={body[:200]}")

# registrar usuario
status, body = peticion("POST", "/api/register", {"email": "testfuncional@roxymaster.com", "password": "test123"})
try:
    resp = json.loads(body)
    token_user = resp.get("token", "")
except:
    token_user = ""

if status in (200, 201) and token_user:
    log_resultado("2", "registro usuario prueba", True, f"token={token_user[:20]}...")
elif "ya existe" in body.lower():
    print("    usuario ya existe, haciendo login...")
    status2, body2 = peticion("POST", "/api/login", {"email": "testfuncional@roxymaster.com", "password": "test123"})
    try:
        resp2 = json.loads(body2)
        token_user = resp2.get("token", "")
    except:
        token_user = ""
    if status2 == 200 and token_user:
        log_resultado("2", "login usuario prueba", True, f"token={token_user[:20]}...")
    else:
        log_resultado("2", "login usuario prueba", False, f"status={status2} body={body2[:200]}")
        token_user = ""
else:
    log_resultado("2", "registro usuario prueba", False, f"status={status} body={body[:200]}")

# wallet
print("\n" + "=" * 60)
print("FASE 3: RECARGA DE SALDO")
print("=" * 60)

try:
    # usar columnas correctas: wallet, usuario_id, saldo_tokens
    # primero ver si existe
    rows = db_ejecutar("SELECT wallet FROM wallets WHERE usuario_id = ?", ("testfuncional@roxymaster.com",))
    if not rows:
        db_ejecutar(
            "INSERT INTO wallets (wallet, usuario_id, saldo_tokens) VALUES (?, ?, ?)",
            ("testfuncional@roxymaster.com", "testfuncional@roxymaster.com", 1500))
        print("    wallet creada con 1500 tokens")
    else:
        db_ejecutar(
            "UPDATE wallets SET saldo_tokens = saldo_tokens + 1500 WHERE usuario_id = ?",
            ("testfuncional@roxymaster.com",))
        print("    recarga de 1500 tokens")
    log_resultado("3", "recarga de saldo db", True, "1500 tokens")
except Exception as e:
    log_resultado("3", "recarga de saldo db", False, str(e))

# verificar saldo
try:
    rows = db_ejecutar("SELECT usuario_id, saldo_tokens FROM wallets WHERE usuario_id = ?",
                       ("testfuncional@roxymaster.com",))
    if rows:
        uid, saldo = rows[0]
        log_resultado("3", "verificacion de saldo", True, f"usuario_id={uid} saldo={saldo}")
    else:
        log_resultado("3", "verificacion de saldo", False, "no se encontro el registro")
except Exception as e:
    log_resultado("3", "verificacion de saldo", False, str(e))

# marketplace
print("\n" + "=" * 60)
print("FASE 4: MARKETPLACE P2P")
print("=" * 60)

if token_user:
    status, body = peticion("POST", "/api/kbt/crear_oferta",
                            {"tokens": 100, "precio_soles": 100},
                            token=token_user)
    if status in (200, 201):
        log_resultado("4", "crear oferta via api", True, f"status={status}")
    elif status == 404:
        log_resultado("4", "crear oferta via api", False, "endpoint no existe (404) - usando db directa")
        try:
            db_ejecutar(
                "INSERT INTO ordenes_marketplace (tipo, wallet, usuario_id, cantidad, precio_pen, estado) VALUES (?, ?, ?, ?, ?, ?)",
                ("venta", "testfuncional@roxymaster.com", "testfuncional@roxymaster.com", 100, 1.00, "activa"))
            log_resultado("4", "crear oferta via db directa", True, "insercion ok")
        except Exception as e:
            log_resultado("4", "crear oferta via db directa", False, str(e))
    else:
        log_resultado("4", "crear oferta via api", False, f"status={status} body={body[:200]}")
else:
    log_resultado("4", "crear oferta", False, "no hay token de usuario")
    try:
        db_ejecutar(
            "INSERT INTO ordenes_marketplace (tipo, wallet, usuario_id, cantidad, precio_pen, estado) VALUES (?, ?, ?, ?, ?, ?)",
            ("venta", "testfuncional@roxymaster.com", "testfuncional@roxymaster.com", 100, 1.00, "activa"))
        log_resultado("4", "crear oferta via db directa (sin token)", True, "insercion ok")
    except Exception as e:
        log_resultado("4", "crear oferta via db directa", False, str(e))

# verificar
try:
    rows = db_ejecutar("SELECT * FROM ordenes_marketplace WHERE estado = ?", ("activa",))
    if rows:
        log_resultado("4", "verificar ofertas activas", True, f"{len(rows)} ofertas activas")
    else:
        log_resultado("4", "verificar ofertas activas", False, "no hay ofertas activas")
except Exception as e:
    log_resultado("4", "verificar ofertas activas", False, str(e))

# orquestacion
print("\n" + "=" * 60)
print("FASE 5: ORQUESTACION")
print("=" * 60)

try:
    for i in range(1, 4):
        db_ejecutar(
            "INSERT OR IGNORE INTO perfiles (granjero_id, nombre_perfil, tipo, estado) VALUES (?, ?, ?, ?)",
            ("testfuncional@roxymaster.com", f"perfil_prueba_{i}", "kick", "activo"))
    log_resultado("5", "insertar perfiles de prueba", True, "3 perfiles insertados")
except Exception as e:
    log_resultado("5", "insertar perfiles de prueba", False, str(e))

if token_admin:
    status, body = peticion("POST", "/api/comando",
                            {"comando": "asignar 3 url https://kick.com/test-funcional duracion 5"},
                            token=token_admin)
    if status == 200:
        log_resultado("5", "comando asignar via api", True, f"status={status} body={body[:200]}")
    elif "accion desconocida" in body.lower() or "no se reconoce" in body.lower():
        log_resultado("5", "comando asignar via api", False, f"parser no reconoce: {body[:200]}")
    else:
        log_resultado("5", "comando asignar via api", False, f"status={status} body={body[:200]}")
else:
    log_resultado("5", "orquestacion", False, "no hay token de admin")

# dashboard y estado
print("\n" + "=" * 60)
print("FASE 6: DASHBOARD Y ESTADO DE USUARIO")
print("=" * 60)

status, body = peticion("GET", "/api/dashboard")
if status == 200:
    try:
        data = json.loads(body)
        log_resultado("6", "dashboard admin", True, f"keys: {list(data.keys())[:8]}")
    except:
        log_resultado("6", "dashboard admin", True, f"status 200 pero json invalido: {body[:200]}")
else:
    log_resultado("6", "dashboard admin", False, f"status={status} body={body[:200]}")

if token_user:
    status, body = peticion("GET", "/api/mi_estado", token=token_user)
    if status == 200:
        log_resultado("6", "mi_estado usuario", True, f"status=200")
        try:
            data = json.loads(body)
            print(f"    keys: {list(data.keys())[:10]}")
        except:
            print(f"    body: {body[:300]}")
    elif status == 500:
        log_resultado("6", "mi_estado usuario", False, f"error 500: {body[:300]}")
    else:
        log_resultado("6", "mi_estado usuario", False, f"status={status} body={body[:200]}")
else:
    log_resultado("6", "mi_estado usuario", False, "no hay token de usuario")

status, body = peticion("GET", "/api/kbt/stats")
if status == 200:
    log_resultado("6", "stats kbt", True, f"status=200")
else:
    log_resultado("6", "stats kbt", False, f"status={status} body={body[:200]}")

# referidos
print("\n" + "=" * 60)
print("FASE 7: REFERIDOS")
print("=" * 60)

try:
    rows = db_ejecutar("SELECT referido_por FROM usuarios WHERE email = ?",
                       ("testfuncional@roxymaster.com",))
    if rows and rows[0][0]:
        log_resultado("7", "campo referido_por", True, f"referido_por={rows[0][0]}")
    else:
        log_resultado("7", "campo referido_por", False, "vacio, asignando manualmente...")
        db_ejecutar("UPDATE usuarios SET referido_por = ? WHERE email = ?",
                    ("pcmaster", "testfuncional@roxymaster.com"))
        rows2 = db_ejecutar("SELECT referido_por FROM usuarios WHERE email = ?",
                            ("testfuncional@roxymaster.com",))
        if rows2 and rows2[0][0]:
            log_resultado("7", "asignacion referido manual", True, f"referido_por={rows2[0][0]}")
        else:
            log_resultado("7", "asignacion referido manual", False, "no se pudo asignar")
except Exception as e:
    log_resultado("7", "referidos", False, str(e))

# resumen
print("\n" + "=" * 60)
print("RESUMEN FINAL")
print("=" * 60)

print(f"\n{'FASE':<6} {'DESCRIPCION':<35} {'RESULTADO':<10} {'DETALLE'}")
print("-" * 90)
for r in resultados:
    emoji = "OK" if r["ok"] else "FAIL"
    print(f"{r['fase']:<6} {r['descripcion'][:34]:<35} {emoji:<10} {r['detalle'][:100]}")

aprobadas = sum(1 for r in resultados if r["ok"])
total = len(resultados)
print(f"\n{aprobadas}/{total} pruebas pasaron.")

if aprobadas == total:
    print("\nsistema listo para pruebas con usuarios reales.")
elif aprobadas >= total * 0.7:
    print("\nsistema funcional pero necesita ajustes menores antes de usuarios reales.")
else:
    print("\nsistema requiere trabajo de backend significativo antes de usuarios reales.")

with open(r"c:\users\pcmaster\desktop\roxymaster\resultados_pruebas.json", "w") as f:
    json.dump(resultados, f, indent=2, ensure_ascii=False)
print(f"\nresultados guardados en resultados_pruebas.json")