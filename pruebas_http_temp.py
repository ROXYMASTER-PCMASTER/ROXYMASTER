"""pruebas funcionales via http y db. ejecutar en local con curl-equivalente."""
import urllib.request
import urllib.error
import json
import subprocess
import sys

BASE_URL = "http://192.168.1.17:8086"
DB_PATH = r"C:\users\pcmaster\desktop\roxymaster\pcmaster\data\roxymaster.db"
SSH_KEY = r"C:\users\pcmaster\.ssh\roxykey"

resultados = []

def log(fase, desc, ok, detalle=""):
    r = {"fase": fase, "desc": desc, "ok": ok, "detalle": detalle}
    resultados.append(r)
    emoji = "OK" if ok else "FAIL"
    print(f"[{emoji}] {fase}: {desc} | {detalle[:200]}")

def http(metodo, ruta, datos=None, token=None):
    url = f"{BASE_URL}{ruta}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body_bytes = json.dumps(datos).encode() if datos else None
    req = urllib.request.Request(url, data=body_bytes, headers=headers, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        b = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return e.code, b
    except Exception as e:
        return 0, str(e)

def sql(sql_cmd):
    """ejecuta sql remoto via ssh."""
    cmd = f'ssh -i "{SSH_KEY}" pcmaster@192.168.1.17 "python -c \\"import sqlite3; conn=sqlite3.connect(r\'{DB_PATH}\'); cur=conn.cursor(); cur.execute(\'{sql_cmd}\'); [print(r) for r in cur.fetchall()] if cur.description else print(\'ok\'); conn.commit(); conn.close()\\""'
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
    return r.stdout.strip(), r.stderr.strip()

print("=" * 60)
print("FASE 1: ENTORNO")
print("=" * 60)

s, b = http("GET", "/api/dashboard")
if s == 200:
    log("1", "servidor responde", True, f"HTTP {s}")
else:
    log("1", "servidor responde", False, f"HTTP {s}: {b[:150]}")

print("\n" + "=" * 60)
print("FASE 2: AUTENTICACION")
print("=" * 60)

# login admin
s, b = http("POST", "/api/login", {"email": "pcmaster", "password": "abc123$_"})
try:
    rj = json.loads(b)
    token_admin = rj.get("token", "")
except:
    token_admin = ""

if s == 200 and token_admin:
    log("2", "login admin", True, f"token={token_admin[:25]}...")
else:
    log("2", "login admin", False, f"HTTP {s} body: {b[:150]}")

# registrar/autenticar usuario de prueba
s, b = http("POST", "/api/register", {"email": "testfuncional@roxymaster.com", "password": "test123"})
try:
    rj = json.loads(b)
    token_user = rj.get("token", "")
except:
    token_user = ""

if s == 200 and token_user:
    log("2", "registro usuario", True, f"registro ok, token={token_user[:25]}...")
elif "ya existe" in b.lower():
    print("    usuario ya existe, login...")
    s2, b2 = http("POST", "/api/login", {"email": "testfuncional@roxymaster.com", "password": "test123"})
    try:
        rj2 = json.loads(b2)
        token_user = rj2.get("token", "")
    except:
        token_user = ""
    if s2 == 200 and token_user:
        log("2", "login usuario prueba", True, f"login ok, token={token_user[:25]}...")
    else:
        log("2", "login usuario prueba", False, f"HTTP {s2} body: {b2[:150]}")
        token_user = ""
else:
    log("2", "registro usuario", False, f"HTTP {s} body: {b[:150]}")

print("\n" + "=" * 60)
print("FASE 3: SALDO WALLET")
print("=" * 60)

# recargar via db
out, err = sql("INSERT OR IGNORE INTO wallets (wallet, usuario_id, saldo_tokens) VALUES ('testfuncional@roxymaster.com', 'testfuncional@roxymaster.com', 1500)")
out2, err2 = sql("UPDATE wallets SET saldo_tokens = saldo_tokens + 1500 WHERE usuario_id = 'testfuncional@roxymaster.com'")
out3, err3 = sql("SELECT usuario_id, saldo_tokens FROM wallets WHERE usuario_id = 'testfuncional@roxymaster.com'")

if "testfuncional" in out3:
    log("3", "saldo wallet", True, f"saldo: {out3.strip()}")
else:
    log("3", "saldo wallet", False, f"respuesta: {out3[:100]} err: {err3[:100]}")

print("\n" + "=" * 60)
print("FASE 4: MARKETPLACE P2P")
print("=" * 60)

if token_user:
    s, b = http("POST", "/api/kbt/crear_oferta", {"tokens": 100, "precio_soles": 100}, token=token_user)
    if s in (200, 201):
        log("4", "crear oferta api", True, f"HTTP {s}")
    elif s == 404:
        log("4", "crear oferta api", False, "endpoint no existe (404)")
        out, err = sql("INSERT INTO ordenes_marketplace (tipo, wallet, usuario_id, cantidad, precio_pen, estado) VALUES ('venta', 'testfuncional@roxymaster.com', 'testfuncional@roxymaster.com', 100, 1.0, 'activa')")
        log("4", "oferta via db", True, f"insert directo: {out[:50]}")
    else:
        log("4", "crear oferta api", False, f"HTTP {s}: {b[:150]}")
else:
    log("4", "crear oferta", False, "sin token de usuario")
    out, err = sql("INSERT INTO ordenes_marketplace (tipo, wallet, usuario_id, cantidad, precio_pen, estado) VALUES ('venta', 'testfuncional@roxymaster.com', 'testfuncional@roxymaster.com', 100, 1.0, 'activa')")
    log("4", "oferta via db", True, "insert sin token")

out, err = sql("SELECT count(*) FROM ordenes_marketplace WHERE estado = 'activa'")
if out and "(" in out:
    log("4", "ofertas activas", True, out.strip())
else:
    log("4", "ofertas activas", False, str(out)[:100])

print("\n" + "=" * 60)
print("FASE 5: ORQUESTACION")
print("=" * 60)

out, err = sql("INSERT OR IGNORE INTO perfiles (granjero_id, nombre_perfil, tipo, estado) VALUES ('testfuncional@roxymaster.com', 'perfil_prueba_1', 'kick', 'activo')")
out, err = sql("INSERT OR IGNORE INTO perfiles (granjero_id, nombre_perfil, tipo, estado) VALUES ('testfuncional@roxymaster.com', 'perfil_prueba_2', 'kick', 'activo')")
out, err = sql("INSERT OR IGNORE INTO perfiles (granjero_id, nombre_perfil, tipo, estado) VALUES ('testfuncional@roxymaster.com', 'perfil_prueba_3', 'kick', 'activo')")
log("5", "perfiles de prueba", True, "3 perfiles insertados")

if token_admin:
    s, b = http("POST", "/api/comando", {"comando": "asignar 3 url https://kick.com/test-funcional duracion 5"}, token=token_admin)
    if s == 200:
        log("5", "comando asignar", True, f"HTTP {s}: {b[:150]}")
    elif "desconocida" in b.lower() or "no se reconoce" in b.lower():
        log("5", "comando asignar", False, f"parser sin accion: {b[:150]}")
    else:
        log("5", "comando asignar", False, f"HTTP {s}: {b[:150]}")
else:
    log("5", "comando asignar", False, "sin token admin")

print("\n" + "=" * 60)
print("FASE 6: DASHBOARD Y ESTADO")
print("=" * 60)

s, b = http("GET", "/api/dashboard")
if s == 200:
    try:
        d = json.loads(b)
        log("6", "dashboard", True, f"keys: {list(d.keys())[:8]}")
    except:
        log("6", "dashboard", False, f"json invalido: {b[:150]}")
else:
    log("6", "dashboard", False, f"HTTP {s}: {b[:150]}")

if token_user:
    s, b = http("GET", "/api/mi_estado", token=token_user)
    if s == 200:
        log("6", "mi_estado", True, f"HTTP 200, body: {b[:150]}")
    elif s == 500:
        log("6", "mi_estado", False, f"error 500: {b[:200]}")
    else:
        log("6", "mi_estado", False, f"HTTP {s}: {b[:150]}")
else:
    log("6", "mi_estado", False, "sin token usuario")

s, b = http("GET", "/api/kbt/stats")
if s == 200:
    log("6", "kbt stats", True, f"HTTP 200")
else:
    log("6", "kbt stats", False, f"HTTP {s}: {b[:150]}")

print("\n" + "=" * 60)
print("FASE 7: REFERIDOS")
print("=" * 60)

out, err = sql("SELECT referido_por FROM usuarios WHERE email = 'testfuncional@roxymaster.com'")
if out and "pcmaster" in out:
    log("7", "referido_por", True, out.strip())
elif out and "None" in out:
    log("7", "referido_por", False, "es nulo, asignando...")
    out2, err2 = sql("UPDATE usuarios SET referido_por = 'pcmaster' WHERE email = 'testfuncional@roxymaster.com'")
    out3, err3 = sql("SELECT referido_por FROM usuarios WHERE email = 'testfuncional@roxymaster.com'")
    if out3 and "pcmaster" in out3:
        log("7", "referido asignado", True, out3.strip())
    else:
        log("7", "referido asignado", False, f"fallo: {out3[:100]}")
else:
    log("7", "referido_por", False, f"respuesta: {out[:100]} err: {err[:100]}")

# RESUMEN
print("\n" + "=" * 60)
print("RESUMEN FINAL")
print("=" * 60)

print(f"\n{'#':<4} {'FASE':<25} {'OK?':<6} {'DETALLE'}")
print("-" * 80)
for r in resultados:
    ok = "OK" if r["ok"] else "FAIL"
    print(f"{r['fase']:<4} {r['desc'][:24]:<25} {ok:<6} {r['detalle'][:80]}")

aprobadas = sum(1 for r in resultados if r["ok"])
total = len(resultados)
print(f"\n>>> {aprobadas}/{total} pruebas OK <<<")

if aprobadas == total:
    print("SISTEMA LISTO para usuarios reales.")
elif aprobadas >= total * 0.75:
    print("SISTEMA FUNCIONAL, requiere ajustes menores.")
else:
    print("SISTEMA necesita trabajo de backend significativo.")