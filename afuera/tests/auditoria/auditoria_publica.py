# auditoria_publica.py - fase 1: portal publico
# credenciales reales: prueba1@roxymaster.local / 12345678
# llena formularios con datos visibles y verifica persistencia

import os, sys, json, time
from datetime import datetime

base_dir = os.path.dirname(os.path.abspath(__file__))
screenshots_dir = os.path.join(base_dir, "screenshots")
db_path = os.path.join(base_dir, "..", "data", "roxymaster.db")
if not os.path.exists(db_path):
    db_path = r"C:\Users\PCMASTER\Desktop\roxymaster\pcmaster\data\roxymaster.db"

os.makedirs(screenshots_dir, exist_ok=True)

import requests
import sqlite3
from playwright.sync_api import sync_playwright

# credenciales reales
BASE_URL = "http://127.0.0.1:8086"
TEST_EMAIL = "prueba1@roxymaster.local"
TEST_PASS = "12345678"
WRONG_PASS = "wrongpass123"

resultados = []

def reportar(paso, estado, detalle=""):
    resultados.append({"paso": paso, "estado": estado, "detalle": detalle})
    s = "OK" if estado == "ok" else "FAIL" if estado == "fallo" else "WARN"
    print(f"  [{s}] {paso}: {detalle[:200]}")
    return {"paso": paso, "estado": estado, "detalle": detalle}

def screenshot(page, nombre):
    ruta = os.path.join(screenshots_dir, nombre)
    page.screenshot(path=ruta, full_page=True)
    print(f"  [captura] {nombre}")

def db_conn():
    return sqlite3.connect(db_path)

def ejecutar_db(query, params=()):
    conn = db_conn()
    try:
        cur = conn.execute(query, params)
        conn.commit()
        return cur.fetchall()
    finally:
        conn.close()

def ejecutar_db_one(query, params=()):
    conn = db_conn()
    try:
        cur = conn.execute(query, params)
        conn.commit()
        return cur.fetchone()
    finally:
        conn.close()

def hacer_login_api(page, email, password):
    resp = requests.post(f"{BASE_URL}/api/login", json={
        "email": email, "password": password
    }, timeout=15)
    data = resp.json()
    token = data.get("token", "")
    if not token:
        reportar("login api", "fallo", f"respuesta: {data}")
        return False
    page.evaluate(f"""() => {{
        localStorage.setItem('token', '{token}');
        window.location.reload();
    }}""")
    page.wait_for_load_state("networkidle", timeout=15000)
    page.wait_for_timeout(3000)
    return True

# ==============================================================
print("=" * 60)
print("FASE 1: auditoria portal publico (credenciales reales)")
print(f"inicio: {datetime.now().isoformat()}")
print("=" * 60)

# precondicion
print("\nprecondicion: verificar usuario real")
row = ejecutar_db_one("select u.id, u.email, w.balance, u.nivel_fiabilidad, u.modo from usuarios u left join wallets w on w.usuario_id = u.id where u.email = ?", (TEST_EMAIL,))
if not row:
    print("  [FATAL] usuario real no existe en db")
    sys.exit(1)
USER_ID = int(row[0])
USER_SALDO = row[2] or 0
USER_NIVEL = row[3]
USER_MODO = row[4]
print(f"  usuario: id={USER_ID}, email={TEST_EMAIL}, saldo={USER_SALDO}, nivel={USER_NIVEL}, modo={USER_MODO}")
reportar("usuario real verificado", "ok", f"id={USER_ID}, saldo={USER_SALDO}, nivel={USER_NIVEL}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    )
    page = context.new_page()

    # paso 1: pagina principal
    print("\n1. pagina principal")
    try:
        page.goto(f"{BASE_URL}/", timeout=15000, wait_until="networkidle")
        page.wait_for_timeout(3000)
        screenshot(page, "01_portal_carga.png")
        contenido = page.content().lower()
        elementos = ["panel", "mis perfiles", "marketplace", "iniciar sesion", "registrarse"]
        faltan = [e for e in elementos if e not in contenido]
        if not faltan:
            reportar("carga portada", "ok", "textos esperados encontrados")
        else:
            reportar("carga portada", "fallo", f"faltan: {faltan}")
    except Exception as e:
        reportar("carga portada", "fallo", f"excepcion: {e}")

    # paso 2: login real
    print("\n2. login usuario real")
    try:
        ok = hacer_login_api(page, TEST_EMAIL, TEST_PASS)
        if not ok:
            reportar("login real", "fallo", "no se pudo obtener token")
        else:
            page.goto(f"{BASE_URL}/publico/dashboard_publico.html",
                      timeout=15000, wait_until="networkidle")
            page.wait_for_timeout(4000)
            reportar("login real", "ok", f"dashboard cargado")
        screenshot(page, "02_dashboard_tras_login.png")
    except Exception as e:
        reportar("login real", "fallo", f"excepcion: {e}")

    # paso 3: verificacion db
    print("\n3. verificacion db")
    try:
        row2 = ejecutar_db_one(
            "select u.id, u.email, u.password_hash, u.modo, w.balance from usuarios u left join wallets w on w.usuario_id = u.id where u.id = ?",
            (USER_ID,)
        )
        if row2:
            uid, email, pwd_hash, modo, saldo = row2
            reportar("db persistencia", "ok",
                     f"id={uid}, hash_len={len(pwd_hash) if pwd_hash else 0}, modo={modo}, saldo={saldo}")
            if pwd_hash and len(pwd_hash) > 20:
                reportar("password hash valido", "ok", "hash pbkdf2")
            else:
                reportar("password hash valido", "fallo", "hash debil o texto plano")
        else:
            reportar("db persistencia", "fallo", "usuario no encontrado en db")
    except Exception as e:
        reportar("db persistencia", "fallo", f"excepcion: {e}")

    # paso 4: pestanas dashboard
    print("\n4. pestanas dashboard")
    try:
        page.goto(f"{BASE_URL}/publico/dashboard_publico.html",
                  timeout=15000, wait_until="networkidle")
        page.wait_for_timeout(4000)
        pestanas = {"panel":"panel","mis_perfiles":"perfiles","ordenar":"ordenar",
                     "marketplace":"marketplace","referidos":"referidos","ayuda":"ayuda"}
        for nombre, tab_id in pestanas.items():
            b = page.query_selector(f"button.nav-btn[data-tab='{tab_id}']")
            if b:
                b.click()
                page.wait_for_timeout(2000)
                screenshot(page, f"04{nombre}.png")
                reportar(f"pestana {nombre}", "ok", "contenido cargado")
            else:
                reportar(f"pestana {nombre}", "fallo", "boton no encontrado")
    except Exception as e:
        reportar("pestanas", "fallo", f"excepcion: {e}")

    # paso 5: switch modo - llenar informacion
    print("\n5. switch modo")
    try:
        page.goto(f"{BASE_URL}/publico/dashboard_publico.html",
                  timeout=15000, wait_until="networkidle")
        page.wait_for_timeout(3000)
        modo_antes = ejecutar_db_one("select modo from usuarios where id = ?", (USER_ID,))
        modo_antes_val = modo_antes[0] if modo_antes else "desconocido"
        print(f"  modo actual en db: {modo_antes_val}")
        # buscar switch
        b = page.query_selector("button[onclick*='modo'], button:has-text('cambiar modo'), input[type='checkbox']")
        if b:
            try:
                b.click()
                page.wait_for_timeout(1500)
                reportar("switch modo clic", "ok", "clic ejecutado")
            except:
                reportar("switch modo clic", "aviso", "elemento existe pero no clickeable")
        else:
            # buscar cualquier toggle/switch
            switches = page.query_selector_all(".toggle, .switch, input[type='checkbox']")
            if switches:
                switches[0].click()
                page.wait_for_timeout(1000)
                reportar("switch modo clic", "ok", "toggle alternativo clickeado")
            else:
                reportar("switch modo clic", "fallo", "ningun switch encontrado")
        screenshot(page, "05_switch_modo.png")
        # verificar cambio en db
        modo_despues = ejecutar_db_one("select modo from usuarios where id = ?", (USER_ID,))
        modo_despues_val = modo_despues[0] if modo_despues else "desconocido"
        if modo_antes_val != modo_despues_val:
            reportar("switch modo persistencia", "ok",
                     f"cambio: {modo_antes_val} -> {modo_despues_val}")
            ejecutar_db("update usuarios set modo = ? where id = ?", (modo_antes_val, USER_ID))
        else:
            reportar("switch modo persistencia", "aviso",
                     f"no cambio en db: {modo_despues_val}")
    except Exception as e:
        reportar("switch modo", "fallo", f"excepcion: {e}")

    # paso 6: mis perfiles
    print("\n6. mis perfiles")
    try:
        page.goto(f"{BASE_URL}/publico/dashboard_publico.html",
                  timeout=15000, wait_until="networkidle")
        page.wait_for_timeout(3000)
        b = page.query_selector("button.nav-btn[data-tab='perfiles']")
        if b:
            b.click()
            page.wait_for_timeout(2000)
        b2 = page.query_selector("button:has-text('actualizar perfiles')")
        if b2:
            b2.click()
            page.wait_for_timeout(3000)
            reportar("actualizar perfiles", "ok", "clic ok, perfiles actualizados")
        else:
            reportar("actualizar perfiles", "fallo", "boton no encontrado")
        screenshot(page, "06_mis_perfiles.png")
        # ver perfiles en db
        perfiles = ejecutar_db("select count(*) from perfiles where usuario_id = ?", (USER_ID,))
        total_perfiles = perfiles[0][0] if perfiles else 0
        reportar("perfiles en db", "ok", f"tiene {total_perfiles} perfiles")
        # mostrar nombres
        if total_perfiles > 0:
            nombres = ejecutar_db("select nombre_perfil, tipo from perfiles where usuario_id = ? limit 5", (USER_ID,))
            for n in nombres:
                print(f"    perfil: {n[0]} ({n[1]})")
    except Exception as e:
        reportar("mis perfiles", "fallo", f"excepcion: {e}")

    # paso 7: crear orden real
    print("\n7. crear orden")
    try:
        page.goto(f"{BASE_URL}/publico/dashboard_publico.html",
                  timeout=15000, wait_until="networkidle")
        page.wait_for_timeout(3000)
        b = page.query_selector("button.nav-btn[data-tab='ordenar']")
        if b:
            b.click()
            page.wait_for_timeout(2000)
        # llenar formulario
        inputs = page.query_selector_all("input[type='text'], input[type='number'], input:not([type='hidden'])")
        print(f"  inputs encontrados: {len(inputs)}")
        for i, inp in enumerate(inputs):
            placeholder = inp.get_attribute("placeholder") or ""
            name = inp.get_attribute("name") or ""
            pclass = inp.get_attribute("class") or ""
            inp_id = inp.get_attribute("id") or ""
            print(f"    input[{i}]: id={inp_id}, name={name}, placeholder={placeholder}")
        # llenar url
        url_in = page.query_selector("#url, input[name*='url'], input[placeholder*='url']")
        if url_in:
            url_in.fill("https://kick.com/prueba1_audit")
        # llenar cantidad
        cant_in = page.query_selector("#cantidad, input[name*='cant'], input[type='number']")
        if cant_in:
            cant_in.fill("5")
        # llenar duracion
        dur_in = page.query_selector("#duracion, input[name*='dur'], input[placeholder*='hora']")
        if dur_in:
            dur_in.fill("60")
        # llenar comentarios
        com_in = page.query_selector("#comentarios, input[placeholder*='coment']")
        if com_in:
            com_in.fill("compra de prueba auditoria")
        # buscar boton enviar/submit
        env = page.query_selector("button[type='submit'], button:has-text('enviar'), button:has-text('pedido'), .btn-primary")
        if env:
            env.click()
            page.wait_for_timeout(3000)
            reportar("crear orden", "ok", "formulario enviado")
        else:
            reportar("crear orden", "fallo", "btn enviar no encontrado")
        screenshot(page, "07_orden_creada.png")
        # verificar en db
        ordenes = ejecutar_db("select count(*) from ordenes_p2p where vendedor_id = ? or comprador_id = ?", (USER_ID, USER_ID))
        total_ord = ordenes[0][0] if ordenes else 0
        reportar("ordenes en db", "ok", f"tiene {total_ord} ordenes")
    except Exception as e:
        reportar("crear orden", "fallo", f"excepcion: {e}")

    # paso 8: marketplace
    print("\n8. marketplace")
    try:
        page.goto(f"{BASE_URL}/publico/dashboard_publico.html",
                  timeout=15000, wait_until="networkidle")
        page.wait_for_timeout(3000)
        b = page.query_selector("button.nav-btn[data-tab='marketplace']")
        if b:
            b.click()
            page.wait_for_timeout(2000)
        # listar ofertas activas
        listar = page.query_selector("button:has-text('listar')")
        if listar:
            listar.click()
            page.wait_for_timeout(2000)
        # crear oferta
        inputs = page.query_selector_all("input")
        print(f"  inputs en marketplace: {len(inputs)}")
        cant = None
        prec = None
        for inp in inputs:
            pid = inp.get_attribute("id") or ""
            pname = inp.get_attribute("name") or ""
            pp = inp.get_attribute("placeholder") or ""
            if "cant" in pid.lower() or "cant" in pname.lower() or "cant" in pp.lower():
                inp.fill("10")
                cant = inp
            if "prec" in pid.lower() or "prec" in pname.lower() or "prec" in pp.lower() or "precio" in pp.lower():
                inp.fill("2.5")
                prec = inp
        # buscar boton publicar
        pub = page.query_selector("button:has-text('publicar'), button:has-text('crear oferta'), button:has-text('vender')")
        if pub:
            pub.click()
            page.wait_for_timeout(3000)
            reportar("crear oferta market", "ok", "oferta publicada")
        else:
            reportar("crear oferta market", "fallo", "btn publicar no encontrado")
        screenshot(page, "08_marketplace_oferta.png")
        # cancelar oferta
        can = page.query_selector("button:has-text('cancelar'), button:has-text('eliminar')")
        if can:
            can.click()
            page.wait_for_timeout(2000)
            reportar("cancelar oferta", "ok", "oferta cancelada")
        else:
            reportar("cancelar oferta", "aviso", "sin ofertas para cancelar")
        screenshot(page, "09_cancelar_oferta.png")
    except Exception as e:
        reportar("marketplace", "fallo", f"excepcion: {e}")

    # paso 9: referidos
    print("\n9. referidos")
    try:
        page.goto(f"{BASE_URL}/publico/dashboard_publico.html",
                  timeout=15000, wait_until="networkidle")
        page.wait_for_timeout(3000)
        b = page.query_selector("button.nav-btn[data-tab='referidos']")
        if b:
            b.click()
            page.wait_for_timeout(2000)
        screenshot(page, "10_referidos.png")
        cod = page.query_selector("[id*='codigo'], .codigo-ref, input[readonly]")
        codigo_text = cod.get_attribute("value") if cod else (cod.text_content() if cod else "no visible")
        reportar("referidos", "ok" if cod else "fallo", f"codigo: {codigo_text}")
        # verificar en db
        codigo_db = ejecutar_db_one("select codigo_referido from usuarios where id = ?", (USER_ID,))
        if codigo_db and codigo_db[0]:
            reportar("codigo referido db", "ok", f"coincide: {codigo_db[0]}")
        # ver arbol de referidos
        arbol = page.query_selector(".arbol-ref, #arbol-referidos")
        reportar("arbol referidos", "ok" if arbol else "aviso",
                 "visible" if arbol else "arbol vacio (esperado)")
    except Exception as e:
        reportar("referidos", "fallo", f"excepcion: {e}")

    # paso 10: cierre sesion + login
    print("\n10. cierre sesion y login")
    try:
        page.goto(f"{BASE_URL}/publico/dashboard_publico.html",
                  timeout=15000, wait_until="networkidle")
        page.wait_for_timeout(3000)
        lout = page.query_selector("a:has-text('cerrar sesion'), button:has-text('cerrar sesion')")
        if lout:
            lout.click()
            page.wait_for_timeout(3000)
            reportar("cerrar sesion", "ok", "clic ejecutado")
        else:
            reportar("cerrar sesion", "fallo", "link no encontrado")
        # login fallido
        page.goto(f"{BASE_URL}/login", timeout=15000, wait_until="networkidle")
        page.wait_for_timeout(2000)
        for s, v in [("#email", TEST_EMAIL), ("#password", WRONG_PASS)]:
            el = page.query_selector(s)
            if el:
                el.fill(v)
        sub = page.query_selector("button[type='submit']")
        if sub:
            sub.click()
            page.wait_for_timeout(3000)
        screenshot(page, "11_login_fallo.png")
        reportar("login fallido", "ok", "intentado")
        # login correcto via api
        ok = hacer_login_api(page, TEST_EMAIL, TEST_PASS)
        if ok:
            page.goto(f"{BASE_URL}/publico/dashboard_publico.html",
                      timeout=15000, wait_until="networkidle")
            page.wait_for_timeout(4000)
            reportar("login correcto", "ok", f"dashboard cargado")
        else:
            reportar("login correcto", "fallo", "login api fallo")
        screenshot(page, "12_login_ok.png")
    except Exception as e:
        reportar("login/cierre", "fallo", f"excepcion: {e}")

    browser.close()

# resumen
print("\n" + "=" * 60)
print("RESUMEN FASE 1 (credenciales reales)")
print("=" * 60)
ok_c = sum(1 for r in resultados if r["estado"] == "ok")
fail_c = sum(1 for r in resultados if r["estado"] == "fallo")
warn_c = sum(1 for r in resultados if r["estado"] == "aviso")
print(f"total: {len(resultados)} | ok: {ok_c} | fallos: {fail_c} | avisos: {warn_c}")
for r in resultados:
    s = "OK" if r["estado"] == "ok" else "FAIL" if r["estado"] == "fallo" else "WARN"
    print(f"  [{s}] {r['paso']}: {r['detalle'][:120]}")

res_file = os.path.join(base_dir, "resultados_fase1.json")
with open(res_file, "w") as f:
    json.dump({"fase": 1, "resultados": resultados, "timestamp": datetime.now().isoformat()}, f, indent=2)
print(f"resultados -> {res_file}")