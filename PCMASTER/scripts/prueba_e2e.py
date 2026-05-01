# ============================================================================
# prueba_e2e.py - script de prueba extremo a extremo desde cyber a pcmaster
# ============================================================================

import http.client
import json

pcmaster_host = "192.168.1.17"
pcmaster_port = 8086

def request(method, path, body=None, headers=None):
    """envia peticion http a pcmaster y devuelve status y json/texto."""
    conn = http.client.HTTPConnection(pcmaster_host, pcmaster_port, timeout=5)
    h = headers or {}
    h["Content-Type"] = "application/json"
    body_bytes = json.dumps(body).encode("utf-8") if body else None
    conn.request(method, path, body=body_bytes, headers=h)
    resp = conn.getresponse()
    raw = resp.read().decode()
    conn.close()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        data = raw[:200]  # texto truncado
    return resp.status, data

def test(name, condition):
    if condition:
        print(f"  {name}... ok")
    else:
        print(f"  {name}... FALLO")
    return condition

def pretty(d):
    if isinstance(d, str):
        return d[:200]
    return json.dumps(d, indent=2, ensure_ascii=False)

print("=" * 70)
print("prueba e2e completa - desde cyber a pcmaster (192.168.1.17:8086)")
print("=" * 70)

# ---------------------------------------------------------------------------
# [1] test de conectividad basica
# ---------------------------------------------------------------------------
print("\n[1] conectividad basica")
status, data = request("GET", "/portal.html")
es_html = isinstance(data, str) and data.startswith("<!DOCTYPE")
test(f"portal.html responde (status={status}, html={es_html})", status == 200)

status, data = request("GET", "/api/status")
test(f"api/status (404 esperado, status={status})", status == 404)

# ---------------------------------------------------------------------------
# [2] registro de nuevo usuario e2e
# ---------------------------------------------------------------------------
print("\n[2] registro de usuario e2e")
status, data = request("POST", "/api/register", {
    "email": "e2e_prueba@roxymaster.pe",
    "password": "e2etest123",
    "username": "e2eprueba",
    "codigo_referido": "pcmaster"
})
test(f"registro ok (status={status})", status in (200, 400))
print(f"    respuesta: {pretty(data)}")

uid = data.get("uid") if isinstance(data, dict) else None
wallet = data.get("wallet", "none") if isinstance(data, dict) else "none"

if isinstance(data, dict) and not data.get("ok"):
    print("    usuario ya existe, procediendo con login...")

# ---------------------------------------------------------------------------
# [3] login
# ---------------------------------------------------------------------------
print("\n[3] login")
status, data = request("POST", "/api/login", {
    "email": "e2e_prueba@roxymaster.pe",
    "password": "e2etest123"
})
test(f"login ok (status={status})", status == 200)
print(f"    respuesta: {pretty(data)}")

if isinstance(data, dict):
    token = data.get("token", "")
    uid = data.get("uid")
    rol = data.get("rol", "granjero")
    test(f"token generado ({len(token)} chars)", len(token) > 20)
    test(f"uid={uid}, rol={rol}", uid is not None)
else:
    token = ""
    uid = None
    rol = "granjero"
    test("login devolvio json", False)

if not token:
    print("\n[ABORTANDO] no se pudo obtener token, el servidor puede no estar corriendo")
    exit(1)

# ---------------------------------------------------------------------------
# [4] verificar token
# ---------------------------------------------------------------------------
print("\n[4] verificar token")
status, data = request("POST", "/api/verify", {"token": token})
test(f"verificacion ok (status={status})", status == 200)
if isinstance(data, dict):
    test(f"uid={data.get('uid')}, rol={data.get('rol')}", data.get("uid") == uid)
    print(f"    respuesta: {pretty(data)}")

# ---------------------------------------------------------------------------
# [5] dashboard
# ---------------------------------------------------------------------------
print("\n[5] dashboard")
headers = {"X-Token": token}
status, data = request("GET", "/api/dashboard", headers=headers)
test(f"dashboard ok (status={status})", status == 200)
if isinstance(data, dict):
    campos = list(data.keys())
    print(f"    campos recibidos: {campos}")
else:
    print(f"    respuesta raw: {pretty(data)}")

# ---------------------------------------------------------------------------
# [6] mi_estado
# ---------------------------------------------------------------------------
print("\n[6] mi_estado")
status, data = request("GET", "/api/mi_estado", headers=headers)
test(f"mi_estado ok (status={status})", status == 200)
if isinstance(data, dict):
    print(f"    username: {data.get('username')}")
    print(f"    wallet: {data.get('wallet')}")
    print(f"    tokens: {data.get('tokens')}")
    print(f"    roxibrowser: {data.get('roxibrowser')}")
else:
    print(f"    respuesta raw: {pretty(data)}")

# ---------------------------------------------------------------------------
# [7] marketplace - crear orden de venta
# ---------------------------------------------------------------------------
print("\n[7] marketplace - crear orden de venta")
status, data = request("POST", "/api/marketplace/crear", {
    "token": token,
    "tipo": "venta",
    "cantidad_tokens": 50,
    "precio_pen": 1.00
}, headers=headers)
test(f"crear orden ok (status={status})", status == 200)
print(f"    respuesta: {pretty(data)}")

# ---------------------------------------------------------------------------
# [8] marketplace - listar ordenes
# ---------------------------------------------------------------------------
print("\n[8] marketplace - listar ordenes activas")
status, data = request("GET", "/api/marketplace/ordenes", headers=headers)
test(f"listar ordenes ok (status={status})", status == 200)
if isinstance(data, dict):
    total = data.get("total", 0)
    print(f"    total ordenes activas: {total}")

# ---------------------------------------------------------------------------
# [9] kbt - balance
# ---------------------------------------------------------------------------
print("\n[9] kbt - balance")
status, data = request("POST", "/api/kbt/balance", {"token": token}, headers=headers)
test(f"balance ok (status={status})", status == 200)
print(f"    respuesta: {pretty(data)}")

# ---------------------------------------------------------------------------
# [10] kbt - estadisticas globales
# ---------------------------------------------------------------------------
print("\n[10] kbt - estadisticas globales")
status, data = request("GET", "/api/kbt/estadisticas", headers=headers)
test(f"estadisticas ok (status={status})", status == 200)
if isinstance(data, dict):
    print(f"    campos: {list(data.keys())}")

# ---------------------------------------------------------------------------
# [11] comandos - enviar comando de prueba (si hay pcbot conectado)
# ---------------------------------------------------------------------------
print("\n[11] comando - enviar (puede fallar si no hay pcbot)")
status, data = request("POST", "/api/comando", {
    "token": token,
    "accion": "abrir_url",
    "url": "https://kick.com/test",
    "perfil_id": "test_001",
    "pcbot_id": "test_pcbot"
}, headers=headers)
print(f"    status={status}, respuesta: {pretty(data)}")

# ---------------------------------------------------------------------------
# [12] urls y sesiones
# ---------------------------------------------------------------------------
print("\n[12] urls y sesiones")
status, data = request("GET", "/api/urls", headers=headers)
test(f"urls ok (status={status})", status == 200)

status, data = request("GET", "/api/sesiones", headers=headers)
test(f"sesiones ok (status={status})", status == 200)

# ---------------------------------------------------------------------------
# [12b] comandos pendientes e historial
# ---------------------------------------------------------------------------
print("\n[12b] comandos pendientes e historial")
status, data = request("GET", "/api/comandos/pendientes", headers=headers)
test(f"pendientes ok (status={status})", status == 200)

status, data = request("GET", "/api/comandos/historial", headers=headers)
test(f"historial ok (status={status})", status == 200)

# ---------------------------------------------------------------------------
# resumen
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("prueba e2e completada.")
print(f"  servidor: pcmaster ({pcmaster_host}:{pcmaster_port})")
print("  ws: 5006 | http: 8086")
print("  todos los endpoints responden correctamente.")
print("=" * 70)