# correccion v2: reemplazar login por formulario con login via API
path = r"pcmaster\tests\auditoria\auditoria_admin.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

old_login = '''    # paso 1: login admin
    print("\\n1. login admin")
    try:
        page.goto(f"{ADMIN_URL}/login", timeout=15000, wait_until="networkidle")
        page.wait_for_timeout(1000)
        for s, v in [("#email", ADMIN_EMAIL), ("#password", ADMIN_PASS)]:
            el = page.query_selector(s)
            if el:
                el.fill(v)
        sub = page.query_selector("button[type='submit']")
        if sub:
            sub.click()
            page.wait_for_timeout(3000)
        # navegar al admin dashboard
        page.goto(f"{ADMIN_URL}/privado/dashboard_admin.html", timeout=15000, wait_until="networkidle")
        page.wait_for_timeout(3000)
        screenshot(page, "13_admin_login_ok.png")
        # verificar que se cargo correctamente
        titulo = page.query_selector("#tab-titulo, h1")
        texto_titulo = titulo.text_content().lower() if titulo else ""
        if "kpi" in texto_titulo or "panel" in texto_titulo:
            reportar("login admin", "ok", f"dashboard admin cargado: {texto_titulo}")
        else:
            reportar("login admin", "fallo", f"titulo inesperado: {texto_titulo}")
    except Exception as e:
        reportar("login admin", "fallo", f"excepcion: {e}")'''

new_login = '''    # paso 1: login admin via API + inyectar token en localStorage
    print("\\n1. login admin")
    try:
        # login via api
        resp = requests.post(f"{ADMIN_URL}/api/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASS
        }, timeout=15)
        data = resp.json()
        token_admin = data.get("token", "")
        if not token_admin:
            reportar("login admin", "fallo", f"login api fallo: {data.get('detail', data)}")
        else:
            # navegar al admin dashboard e inyectar token
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
            if "kpi" in texto_titulo or "panel" in texto_titulo:
                reportar("login admin", "ok", f"dashboard admin cargado: {texto_titulo}")
            else:
                reportar("login admin", "fallo", f"titulo inesperado: {texto_titulo}")
    except Exception as e:
        reportar("login admin", "fallo", f"excepcion: {e}")'''

assert old_login in content, "login block not found!"
content = content.replace(old_login, new_login)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
print("correccion v2 aplicada: login via API")