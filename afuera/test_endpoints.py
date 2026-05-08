"""test_endpoints.py - verifica todos los endpoints del dashboard publico"""

import sys, os, json, urllib.request, urllib.error

sys.path.insert(0, os.path.dirname(__file__))
base = "http://localhost:8086"

def req(method, path, data=None, token=None):
    url = base + path
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(data).encode() if data else None
    r = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        resp = urllib.request.urlopen(r, timeout=5)
        return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body) if body else str(e)
        except:
            return e.code, body[:100] if body else str(e)
    except Exception as e:
        return 0, str(e)

def req_html(method, path, token=None):
    """para archivos estaticos html - solo verifica status, no parsea json."""
    url = base + path
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(url, method=method, headers=headers)
    try:
        resp = urllib.request.urlopen(r, timeout=5)
        return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return 0, str(e)

def testear():
    ok = 0
    fail = 0
    results = []

    def check(nombre, status_esperado, method="GET", path="", data=None, token=None):
        nonlocal ok, fail
        codigo, resp = req(method, path, data, token)
        if codigo == status_esperado:
            ok += 1
            results.append(f"  [ok] {nombre} -> {codigo}")
        else:
            fail += 1
            results.append(f"  [fail] {nombre} -> esperado {status_esperado}, recibido {codigo}: {str(resp)[:80]}")

    # 1. login con prueba1 y obtener token
    codigo_login, resp_login = req("POST", "/api/login", {"email": "prueba1@roxymaster.local", "password": "12345678"})
    if codigo_login == 200:
        results.append(f"  [ok] login prueba1 -> {codigo_login}")
        ok += 1
        token = resp_login.get("token") or resp_login.get("access_token")
        if token:
            results.append(f"  [ok] token obtenido: {token[:30]}...")
            ok += 1
        else:
            results.append(f"  [warn] login ok pero no se encontro token en respuesta: {str(resp_login)[:100]}")
    else:
        results.append(f"  [fail] login prueba1 -> {codigo_login}: {str(resp_login)[:80]}")
        fail += 1
        token = None

    # 2. health check
    check("api/health", 200, "GET", "/api/health")
    check("api/sistema/version", 200, "GET", "/api/sistema/version")
    check("api/endpoints", 200, "GET", "/api/endpoints")

    # 3. html publicos - solo verificamos status, no parseamos json
    for nombre, ruta in [
        ("login.html", "/publico/login.html"),
        ("dashboard_publico.html", "/publico/dashboard_publico.html"),
        ("perfiles.html", "/publico/perfiles.html"),
        ("marketplace.html", "/publico/marketplace.html"),
    ]:
        cod, _ = req_html("GET", ruta)
        if cod == 200:
            ok += 1
            results.append(f"  [ok] {nombre} -> 200")
        else:
            fail += 1
            results.append(f"  [fail] {nombre} -> esperado 200, recibido {cod}")

    # 4. api endpoints que requieren token (sin token -> 401)
    check("api/marketplace/ordenes (sin token)", 401, "GET", "/api/marketplace/ordenes")
    check("api/marketplace/libro (sin token)", 401, "GET", "/api/marketplace/libro")
    check("api/referidos/estadisticas (sin token)", 401, "GET", "/api/referidos/estadisticas")
    check("api/kbt/estadisticas (sin token)", 401, "GET", "/api/kbt/estadisticas")
    check("api/kbt/tasa (sin token)", 401, "GET", "/api/kbt/tasa")
    check("api/precios_marketplace (sin token)", 401, "GET", "/api/precios_marketplace")

    # 5. endpoints con token (autenticados)
    if token:
        check("api/mis_perfiles", 200, "GET", "/api/mis_perfiles", token=token)
        check("api/marketplace/mis_ordenes", 200, "GET", "/api/marketplace/mis_ordenes", token=token)
        check("api/kbt/balance", 200, "GET", "/api/kbt/balance", token=token)
        check("api/mis_pcs", 200, "GET", "/api/mis_pcs", token=token)
        check("api/mi_estado", 200, "GET", "/api/mi_estado", token=token)
        check("api/dashboard", 200, "GET", "/api/dashboard", token=token)
        check("api/transacciones", 200, "GET", "/api/transacciones", token=token)
        check("api/notificaciones", 200, "GET", "/api/notificaciones", token=token)
        # /api/usuario solo acepta POST segun logs del server, 405 es esperado con GET
        cod, resp = req("GET", "/api/usuario", token=token)
        if cod == 405:
            ok += 1
            results.append(f"  [ok] api/usuario -> 405 (esperado, solo acepta POST)")
        else:
            fail += 1
            results.append(f"  [fail] api/usuario -> esperado 405, recibido {cod}")
    else:
        results.append("  [skip] endpoints con token (no se obtuvo token de login)")

    # resumen
    print("=" * 50)
    print(f"TEST DE ENDPOINTS DEL DASHBOARD PUBLICO")
    print("=" * 50)
    for r in results:
        print(r)
    print("-" * 50)
    print(f"total: {ok + fail}  |  ok: {ok}  |  fail: {fail}")
    if fail == 0:
        print("todos los endpoints funcionan correctamente")
    else:
        print(f"hay {fail} endpoints con problemas")

if __name__ == "__main__":
    testear()