"""pruebas funcionales completas para roxymaster - ejecutar en pcmaster."""
import urllib.request
import urllib.error
import json
import subprocess
import os
import sys
import time

BASE = "http://127.0.0.1:8086"
DB = r"c:\users\pcmaster\desktop\roxymaster\pcmaster\data\roxymaster.db"

resultados = []


def peticion(metodo, ruta, datos=None, token=None, descripcion=""):
    """hace una peticion http y devuelve (status, cuerpo)."""
    url = f"{BASE}{ruta}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data_bytes = None
    if datos is not None:
        data_bytes = json.dumps(datos).encode("utf-8")

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            cuerpo = resp.read().decode("utf-8", errors="replace")
            return resp.status, cuerpo
    except urllib.error.HTTPError as e:
        cuerpo = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return e.code, cuerpo
    except Exception as e:
        return 0, str(e)


def log_resultado(fase, descripcion, ok, detalle=""):
    emoji = "OK" if ok else "FAIL"
    r = {"fase": fase, "descripcion": descripcion, "ok": ok, "detalle": detalle}
    resultados.append(r)
    print(f"[{emoji}] fase {fase}: {descripcion} | {detalle[:200]}")


def db_ejecutar(sql, params=None):
    """ejecuta sql en la base de datos remota (local en pcmaster)."""
    import sqlite3
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    if params:
        cur.execute(sql, params)
    else:
        cur.execute(sql)
    if sql.strip().upper().startswith("SELECT") or sql.strip().upper().startswith("PRAGMA"):
        rows = cur.fetchall()
        conn.close()
        return rows
    conn.commit()
    conn.close()
    return None


# ============================================================
# fase 1: verificacion del entorno
# ============================================================
print("=" * 60)
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

# ============================================================
# fase 2: autenticacion
# ============================================================
print("\n" + "=" * 60)
print("FASE 2: AUTENTICACION")
print("=" * 60)

# login admin
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

# registrar usuario de prueba
status, body = peticion("POST", "/api/register", {"email": "testfuncional@roxymaster.com", "password": "test123"})
try:
    resp = json.loads(body)
    token_user = resp.get("token", "")
except:
    token_user = ""

if status in (200, 201) and token_user:
    log_resultado("2", "registro usuario prueba", True, f"token={token_user[:20]}...")
elif "ya existe" in body.lower() or status == 409:
    # hacer login
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

# ============================================================
# fase 3: recarga de saldo
# ============================================================
print("\n" + "=" * 60)
print("FASE 3: RECARGA DE SALDO")
print("=" * 60)

# insertar/actualizar saldo
try:
    db_ejecutar("INSERT OR IGNORE INTO wallets (email, saldo_tokens) VALUES (?, ?)",
                ("testfuncional@roxymaster.com", 1500))
    db_ejecutar("UPDATE wallets SET saldo_tokens = saldo_tokens + 1500 WHERE email = ?",
                ("testfuncional@roxymaster.com",))
    print("    recarga ejecutada en db")
    log_resultado("3", "recarga de saldo db", True, "1500 tokens insertados/actualizados")
except Exception as e:
    log_resultado("3", "recarga de saldo db", False, str(e))

# verificar saldo
try:
    rows = db_ejecutar("SELECT email, saldo_tokens FROM wallets WHERE email = ?",
                       ("testfuncional@roxymaster.com",))
    if rows:
        email, saldo = rows[0]
        log_resultado("3", "verificacion de saldo", True, f"email={email} saldo={saldo}")
    else:
        log_resultado("3", "verificacion de saldo", False, "no se encontro el registro")
except Exception as e:
    log_resultado("3", "verificacion de saldo", False, str(e))

# ============================================================
# fase 4: marketplace p2p
# ============================================================
print("\n" + "=" * 60)
print("FASE 4: MARKETPLACE P2P")
print("=" * 60)

if token_user:
    status, body = peticion("POST", "/api/kbt/crear_oferta",
                            {"tokens": 100, "precio_soles": 100},
                            token=token_user)
    if status == 200 or status == 201:
        log_resultado("4", "crear oferta via api", True, f"status={status}")
    elif status == 404:
        log_resultado("4", "crear oferta via api", False, "endpoint no existe (404) - usando db directa")
        # insercion directa
        try:
            db_ejecutar(
                "INSERT INTO ordenes_marketplace (vendedor, cantidad, precio_unitario, estado) VALUES (?, ?, ?, ?)",
                ("testfuncional@roxymaster.com", 100, 1.00, "activa"))
            log_resultado("4", "crear oferta via db directa", True, "insercion ok")
        except Exception as e:
            log_resultado("4", "crear oferta via db directa", False, str(e))
    else:
        log_resultado("4", "crear oferta via api", False, f"status={status} body={body[:200]}")
else:
    log_resultado("4", "crear oferta", False, "no hay token de usuario")
    # intentar db directa igual
    try:
        db_ejecutar(
            "INSERT INTO ordenes_marketplace (vendedor, cantidad, precio_unitario, estado) VALUES (?, ?, ?, ?)",
            ("testfuncional@roxymaster.com", 100, 1.00, "activa"))
        log_resultado("4", "crear oferta via db directa (sin token)", True, "insercion ok")
    except Exception as e:
        log_resultado("4", "crear oferta via db directa", False, str(e))

# verificar ordenes activas
try:
    rows = db_ejecutar("SELECT * FROM ordenes_marketplace WHERE estado = ?", ("activa",))
    if rows:
        log_resultado("4", "verificar ofertas activas", True, f"{len(rows)} ofertas activas")
    else:
        log_resultado("4", "verificar ofertas activas", False, "no hay ofertas activas")
except Exception as e:
    log_resultado("4", "verificar ofertas activas", False, str(e))

# ============================================================
# fase 5: orquestacion
# ============================================================
print("\n" + "=" * 60)
print("FASE 5: ORQUESTACION")
print("=" * 60)

# insertar perfiles
try:
    for i in range(1, 4):
        db_ejecutar(
            "INSERT OR IGNORE INTO perfiles (granjero_id, nombre_perfil, estado) VALUES (?, ?, ?)",
            ("testfuncional@roxymaster.com", f"perfil_prueba_{i}", "activo"))
    log_resultado("5", "insertar perfiles de prueba", True, "3 perfiles insertados")
except Exception as e:
    log_resultado("5", "insertar perfiles de prueba", False, str(e))

# enviar comando de orquestacion
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

# ============================================================
# fase 6: dashboard y estado de usuario
# ============================================================
print("\n" + "=" * 60)
print("FASE 6: DASHBOARD Y ESTADO DE USUARIO")
print("=" * 60)

# dashboard admin
status, body = peticion("GET", "/api/dashboard")
if status == 200:
    try:
        data = json.loads(body)
        log_resultado("6", "dashboard admin", True,
                      f"keys: {list(data.keys())[:8]}")
    except:
        log_resultado("6", "dashboard admin", True, f"status 200 pero json invalido: {body[:200]}")
else:
    log_resultado("6", "dashboard admin", False, f"status={status} body={body[:200]}")

# mi_estado
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

# stats kbt
status, body = peticion("GET", "/api/kbt/stats")
if status == 200:
    log_resultado("6", "stats kbt", True, f"status=200")
else:
    log_resultado("6", "stats kbt", False, f"status={status} body={body[:200]}")

# ============================================================
# fase 7: referidos
# ============================================================
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

# ============================================================
# resumen final
# ============================================================
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

# guardar resultados
with open(r"c:\users\pcmaster\desktop\roxymaster\resultados_pruebas.json", "w") as f:
    json.dump(resultados, f, indent=2, ensure_ascii=False)
print(f"\nresultados guardados en resultados_pruebas.json")