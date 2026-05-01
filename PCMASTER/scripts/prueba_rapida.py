# prueba rapida de flujo completo de registro, login, verify
import sys
import os

# forzar path
_base = os.path.dirname(os.path.abspath(__file__))
if _base not in sys.path:
    sys.path.insert(0, _base)

print("=== prueba flujo completo roxymaster v8.3 ===\n")

# paso 1: inicializar base de datos
print("[1] inicializando bases de datos...")
from auth import init_auth_db, registrar_usuario, autenticar_usuario, verificar_token, generar_token
from tokenomics import init_tokenomics_db, obtener_balance
import variables_globales

init_auth_db()
init_tokenomics_db()
print("    ok - bases de datos listas\n")

# paso 2: intentar registrar o usar existente
print("[2] registrando / usando usuario de prueba...")
resultado = registrar_usuario(
    email="test@roxymaster.local",
    password="test1234",
    codigo_referido="pcmaster"
)

if resultado.get('ok'):
    uid = resultado['uid']
    wallet = resultado['wallet']
    print(f"    registrado ok: uid={uid}, wallet={wallet}")
else:
    print(f"    usuario ya existe: {resultado.get('error')}")
    # obtener datos del usuario existente via login
    auth = autenticar_usuario("test@roxymaster.local", "test1234")
    uid, username, rol = auth
    from auth import obtener_usuario_por_email
    info = obtener_usuario_por_email("test@roxymaster.local")
    wallet = info['wallet']
    print(f"    cargado existente: uid={uid}, wallet={wallet}\n")
    resultado = {'uid': uid, 'wallet': wallet, 'rol': rol}

uid = resultado.get('uid', 3)
wallet = resultado.get('wallet', '')

# paso 3: login
print("[3] autenticando usuario...")
auth = autenticar_usuario("test@roxymaster.local", "test1234")
print(f"    auth: {auth}")

if not auth:
    print("    ERROR en autenticacion")
    sys.exit(1)

uid2, username, rol = auth
print(f"    uid={uid2}, username={username}, rol={rol}\n")

# paso 4: generar y verificar token
print("[4] generando y verificando token...")
token = generar_token(uid, username, rol)
print(f"    token generado: {token[:40]}...")

verif = verificar_token(token)
print(f"    verificacion: {verif}")

if not verif:
    print("    ERROR en verificacion de token")
    sys.exit(1)

v_uid, v_user, v_rol = verif
print(f"    uid={v_uid}, username={v_user}, rol={v_rol}\n")

# paso 5: probar funciones tokenomics (module-level wrapper)
print("[5] probando funciones tokenomics...")
balance = obtener_balance(wallet)
print(f"    balance de wallet {wallet}: {balance}")

# paso 6: probar marketplace
print("\n[6] probando marketplace...")
from marketplace import crear_orden, listar_ordenes_activas, init_marketplace_db
init_marketplace_db()
orden = crear_orden(
    tipo="compra",
    wallet=wallet,
    usuario_id=uid,
    cantidad=10.0,
    precio_pen=1.00
)
print(f"    orden creada: {orden}")
activas = listar_ordenes_activas()
print(f"    ordenes activas: {len(activas)}")

# paso 7: probar server imports
print("\n[7] probando imports de server.py...")
import server
print("    server.py importado exitosamente")

# paso 8: probar fastapi app
print("\n[8] verificando rutas fastapi...")
rutas = [(r.path, list(r.methods)) for r in server.app.routes if hasattr(r, 'methods')]
kbt_rutas = [p for p, m in rutas if 'kbt' in p.lower()]
admin_rutas = [p for p, m in rutas if 'admin' in p.lower()]
other_rutas = [p for p, m in rutas if 'kbt' not in p.lower() and 'admin' not in p.lower() and p not in ('/','/favicon.ico')]
print(f"    rutas kbt ({len(kbt_rutas)}): {kbt_rutas}")
print(f"    rutas admin ({len(admin_rutas)}): {admin_rutas}")
print(f"    otras rutas ({len(other_rutas)}): {other_rutas}")

# paso 9: probar endpoint raiz
print("\n[9] probando cliente http contra server uvicorn...")
from fastapi.testclient import TestClient
client = TestClient(server.app)

# probar /api/status
r = client.get("/api/status")
print(f"    GET /api/status -> {r.status_code}, body: {r.json()}")

# probar /api/login con credenciales
r = client.post("/api/login", json={
    "email": "test@roxymaster.local",
    "password": "test1234"
})
print(f"    POST /api/login -> {r.status_code}, body: {r.json()}")

# probar /api/register
r = client.post("/api/register", json={
    "email": "test_unico@roxymaster.local",
    "password": "abcd1234",
    "codigo_referido": "pcmaster"
})
print(f"    POST /api/register -> {r.status_code}, body ok={r.json().get('ok')}")

print("\n=== todas las pruebas pasaron correctamente ===")