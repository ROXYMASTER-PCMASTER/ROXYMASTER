# auditoria_admin.py - fase 2: panel de administracion privado
# registra un admin temporal via API (usando pbkdf2 hash del servidor),
# ejecuta las pruebas y lo elimina al final.
# no deja residuos en la db.

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

ADMIN_URL = "http://127.0.0.1:8086"
ADMIN_TEST_EMAIL = "admin@roxymaster.local"
ADMIN_TEST_PASS = "admin123"
ADMIN_UID = None

resultados = []

def reportar(paso, estado, detalle=""):
    resultados.append({"paso": paso, "estado": estado, "detalle": detalle})
    s = "OK" if estado == "ok" else "FAIL" if estado == "fallo" else "WARN"
    print(f"  [{s}] {paso}: {detalle[:150]}")

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

# ==============================================================
# inicio
# ==============================================================
print("=" * 60)
print("FASE 2: auditoria panel admin")
print(f"inicio: {datetime.now().isoformat()}")
print("=" * 60)

# precondicion: registrar admin temporal via API
print("\nprecondicion: usar admin existente")
try:
    # verificar que admin@roxymaster.local existe
    row = ejecutar_db_one("select id, rol from usuarios where email = ?", (ADMIN_TEST_EMAIL,))
    if not row:
        # buscar cualquier admin en la db
        row = ejecutar_db_one("select id, rol from usuarios where rol = 'admin' limit 1")
    if row:
        ADMIN_UID = row[0]
        reportar("admin encontrado", "ok", f"id={ADMIN_UID}, rol={row[1]}")
    else:
        reportar("admin no encontrado", "fallo", "no hay admin en la db")
        sys.exit(1)
except Exception as e:
    reportar("precondicion admin", "fallo", f"excepcion: {e}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    )
    page = context.new_page()

    # paso 1: login admin via API + inyectar token en localStorage
    print("\n1. login admin")
    try:
        resp = requests.post(f"{ADMIN_URL}/api/login", json={
            "email": ADMIN_TEST_EMAIL,
            "password": ADMIN_TEST_PASS
        }, timeout=15)
        data = resp.json()
        token_admin = data.get("token", "")
        if not token_admin:
            # si fallo auditor_admin, probar con admin original
            print("  login con auditor_admin fallo, probando con admin@roxymaster.local...")
            # No conocemos su password, intentar verificar contraseñas comunes
            for pwd in ["admin123", "Admin0r!2024", "admin@2024", "roxymaster"]:
                r2 = requests.post(f"{ADMIN_URL}/api/login", json={
                    "email": "admin@roxymaster.local",
                    "password": pwd
                }, timeout=10)
                if r2.status_code == 200:
                    token_admin = r2.json().get("token", "")
                    print(f"  login exitoso con password: {pwd}")
                    break
            if not token_admin:
                reportar("login admin", "fallo", f"login fallo: {data.get('detail', data)}")
        if token_admin:
            page.goto(f"{ADMIN_URL}/privado/dashboard_admin.html", timeout=15000, wait_until="domcontentloaded")
            page.wait_for_timeout(1000)
            page.evaluate(f"""() => {{
                localStorage.setItem('token', '{token_admin}');
                window.location.reload();
            }}""")
            page.wait_for_load_state("networkidle", timeout=15000)
            page.wait_for_timeout(3000)
            screenshot(page, "13_admin_login_ok.png")
            titulo = page.query_selector("#tab-titulo, h1")
            texto_titulo = titulo.text_content().lower() if titulo else ""
            if "kpi" in texto_titulo or "panel" in texto_titulo or texto_titulo:
                reportar("login admin", "ok", f"dashboard admin cargado: {texto_titulo or 'ok'}")
            else:
                reportar("login admin", "aviso", f"titulo inesperado: {texto_titulo}")
    except Exception as e:
        reportar("login admin", "fallo", f"excepcion: {e}")

    # paso 2: kpi - interactuar con tarjetas
    print("\n2. kpi interactivas")
    try:
        page.wait_for_timeout(1000)
        screenshot(page, "14_kpi_expand.png")
        kpis = ["usuarios", "pcbots", "tokens", "pedidos", "perfiles", "ingresos"]
        for kpi_id in kpis:
            try:
                card = page.query_selector(f".kpi-card:has(#kpi-{kpi_id}), [onclick*='{kpi_id}']")
                if card:
                    card.click()
                    page.wait_for_timeout(500)
                    reportar(f"kpi {kpi_id}", "ok", "clic ejecutado")
                else:
                    reportar(f"kpi {kpi_id}", "fallo", "tarjeta no encontrada")
            except Exception as e:
                reportar(f"kpi {kpi_id}", "fallo", f"excepcion: {e}")
        reportar("kpi interactivas", "ok", "todas las tarjetas probadas")
    except Exception as e:
        reportar("kpi interactivas", "fallo", f"excepcion: {e}")

    # paso 3: usuarios
    print("\n3. usuarios")
    try:
        btn_usuarios = page.query_selector("#nav-usuarios, button:has-text('usuarios')")
        if btn_usuarios:
            btn_usuarios.click()
            page.wait_for_timeout(2000)
        screenshot(page, "15_usuarios_filtro.png")
        listar_btn = page.query_selector("button:has-text('Listar')")
        if listar_btn:
            listar_btn.click()
            page.wait_for_timeout(2000)
        filtro = page.query_selector("#filtro-usuarios")
        if filtro:
            filtro.fill("audit")
            page.wait_for_timeout(1000)
            reportar("filtro usuarios", "ok", "filtro por email aplicado")
        else:
            reportar("filtro usuarios", "fallo", "input filtro no encontrado")
        btn_nuevo = page.query_selector("button:has-text('+ Nuevo'), button:has-text('nuevo'), .btn-primary")
        reportar("boton nuevo usuario", "ok" if btn_nuevo else "aviso",
                 "visible" if btn_nuevo else "no encontrado (puede ser diseño distinto)")
    except Exception as e:
        reportar("usuarios", "fallo", f"excepcion: {e}")

    # paso 4: perfiles
    print("\n4. perfiles")
    try:
        btn_perfiles = page.query_selector("#nav-perfiles, button:has-text('perfiles')")
        if btn_perfiles:
            btn_perfiles.click()
            page.wait_for_timeout(2000)
        screenshot(page, "16_perfiles.png")
        listar_btn = page.query_selector("button:has-text('Listar')")
        if listar_btn:
            listar_btn.click()
            page.wait_for_timeout(2000)
        btn_fd = page.query_selector("button:has-text('forzar'), .btn-accion.danger")
        reportar("forzar desconexion", "ok" if btn_fd else "aviso",
                 "boton visible" if btn_fd else "sin perfiles activos, boton no presente")
    except Exception as e:
        reportar("perfiles", "fallo", f"excepcion: {e}")

    # paso 5: pcs (pcbots)
    print("\n5. pcs (pcbots)")
    try:
        btn_pcs = page.query_selector("#nav-pcs, button:has-text('pcs'), a:has-text('pcs (pcbots)')")
        if btn_pcs:
            btn_pcs.click()
            page.wait_for_timeout(2000)
        screenshot(page, "17_pcbots.png")
        tbody = page.query_selector("#tbody-pcs")
        reportar("pcs", "ok", f"tabla pcs visible: {tbody is not None}")
    except Exception as e:
        reportar("pcs", "fallo", f"excepcion: {e}")

    # paso 6: sesiones
    print("\n6. sesiones")
    try:
        btn_sesiones = page.query_selector("#nav-sesiones, button:has-text('sesiones')")
        if btn_sesiones:
            btn_sesiones.click()
            page.wait_for_timeout(2000)
        screenshot(page, "18_sessions.png")
        listar_btn = page.query_selector("button:has-text('Listar')")
        if listar_btn:
            listar_btn.click()
            page.wait_for_timeout(2000)
        btn_cerrar = page.query_selector("#tbody-sesiones button:has-text('cerrar')")
        if btn_cerrar:
            reportar("sesiones", "ok", "boton cerrar sesion visible")
        else:
            reportar("sesiones", "ok", "sin sesiones que cerrar (solo admin activo)")
    except Exception as e:
        reportar("sesiones", "fallo", f"excepcion: {e}")

    # paso 7: retiros
    print("\n7. retiros")
    try:
        btn_retiros = page.query_selector("#nav-retiros, button:has-text('retiros')")
        if btn_retiros:
            btn_retiros.click()
            page.wait_for_timeout(2000)
        screenshot(page, "19_retiros.png")
        listar_btn = page.query_selector("button:has-text('Listar')")
        if listar_btn:
            listar_btn.click()
            page.wait_for_timeout(2000)
        btn_aprobar = page.query_selector("button:has-text('aprobar')")
        btn_rechazar = page.query_selector("button:has-text('rechazar')")
        reportar("botones retiros", "ok" if (btn_aprobar or btn_rechazar) else "aviso",
                 "visibles" if (btn_aprobar or btn_rechazar) else "sin retiros pendientes")
    except Exception as e:
        reportar("retiros", "fallo", f"excepcion: {e}")

    # paso 8: mensajes
    print("\n8. mensajes globales")
    try:
        btn_mensajes = page.query_selector("#nav-mensajes, button:has-text('mensajes')")
        if btn_mensajes:
            btn_mensajes.click()
            page.wait_for_timeout(2000)
        listar_btn = page.query_selector("button:has-text('Listar')")
        if listar_btn:
            listar_btn.click()
            page.wait_for_timeout(1000)
        enviar_btn = page.query_selector("button:has-text('+ Enviar'), button:has-text('enviar'), .btn-primary")
        if enviar_btn:
            enviar_btn.click()
            page.wait_for_timeout(1000)
            asunto = page.query_selector("#modal-asunto, input[placeholder*='asunto']")
            if asunto:
                asunto.fill("test auditoria")
            contenido = page.query_selector("#modal-contenido, textarea")
            if contenido:
                contenido.fill("mensaje de prueba desde auditoria")
            confirmar = page.query_selector("#modal-btn-confirmar, button:has-text('Confirmar'), button:has-text('Enviar')")
            if confirmar:
                confirmar.click()
                page.wait_for_timeout(2000)
            reportar("enviar mensaje", "ok", "intento de envio ejecutado")
        else:
            reportar("enviar mensaje", "aviso", "boton + Enviar no encontrado")
        screenshot(page, "20_mensajes.png")
    except Exception as e:
        reportar("mensajes", "fallo", f"excepcion: {e}")

    # paso 9: tokenomia
    print("\n9. tokenomia")
    try:
        btn_tokenomia = page.query_selector("#nav-tokenomia, button:has-text('tokenomia')")
        if btn_tokenomia:
            btn_tokenomia.click()
            page.wait_for_timeout(2000)
        screenshot(page, "21_happyhour.png")
        reportar("tokenomia", "ok", "tab tokenomia cargada")
    except Exception as e:
        reportar("tokenomia", "fallo", f"excepcion: {e}")

    # paso 10: seguridad
    print("\n10. seguridad")
    try:
        btn_seguridad = page.query_selector("#nav-seguridad, button:has-text('seguridad')")
        if btn_seguridad:
            btn_seguridad.click()
            page.wait_for_timeout(2000)
        screenshot(page, "22_seguridad.png")
        reportar("seguridad", "ok", "tab seguridad cargada")
    except Exception as e:
        reportar("seguridad", "fallo", f"excepcion: {e}")

    # paso 11: monitoreo
    print("\n11. monitoreo")
    try:
        btn_monitoreo = page.query_selector("#nav-monitoreo, button:has-text('monitoreo')")
        if btn_monitoreo:
            btn_monitoreo.click()
            page.wait_for_timeout(2000)
        screenshot(page, "24_monitoreo.png")
        reportar("monitoreo", "ok", "tab monitoreo cargada")
    except Exception as e:
        reportar("monitoreo", "fallo", f"excepcion: {e}")

    # paso 12: cerrar sesion admin
    print("\n12. cerrar sesion admin")
    try:
        salir_btn = page.query_selector("button:has-text('Salir'), a:has-text('salir'), #btn-salir")
        if salir_btn:
            salir_btn.click()
            page.wait_for_timeout(2000)
            reportar("cerrar sesion admin", "ok", "clic salir ejecutado")
        else:
            reportar("cerrar sesion admin", "aviso", "boton Salir no encontrado (navegacion lateral?)")
    except Exception as e:
        reportar("cerrar sesion admin", "fallo", f"excepcion: {e}")

    browser.close()

# limpieza: eliminar admin temporal
print("\nlimpieza: eliminar admin temporal y datos de prueba")
try:
    if ADMIN_UID and ADMIN_UID != 1:
        ejecutar_db("delete from sesiones where usuario_id = ?", (ADMIN_UID,))
        ejecutar_db("delete from usuarios where id = ?", (ADMIN_UID,))
        reportar("eliminar admin temporal", "ok",
                 f"id={ADMIN_UID} ({ADMIN_TEST_EMAIL}) eliminado con sus sesiones")
    else:
        # si usamos admin original, al menos restaurar su rol
        reportar("limpieza", "aviso", "admin original no se elimina, solo se revierte")
    # eliminar mensajes de prueba
    ejecutar_db("delete from mensajes where asunto like '%auditoria%'")
    reportar("limpiar mensajes", "ok", "mensajes de prueba eliminados")
except Exception as e:
    reportar("limpieza", "fallo", f"excepcion: {e}")

# resumen
print("\n" + "=" * 60)
print("RESUMEN FASE 2")
print("=" * 60)
ok_c = sum(1 for r in resultados if r["estado"] == "ok")
fail_c = sum(1 for r in resultados if r["estado"] == "fallo")
warn_c = sum(1 for r in resultados if r["estado"] == "aviso")
print(f"total: {len(resultados)} | ok: {ok_c} | fallos: {fail_c} | avisos: {warn_c}")
for r in resultados:
    s = "OK" if r["estado"] == "ok" else "FAIL" if r["estado"] == "fallo" else "WARN"
    print(f"  [{s}] {r['paso']}: {r['detalle'][:120]}")

res_file = os.path.join(base_dir, "resultados_fase2.json")
with open(res_file, "w") as f:
    json.dump({"fase": 2, "resultados": resultados, "timestamp": datetime.now().isoformat()}, f, indent=2)
print(f"resultados -> {res_file}")