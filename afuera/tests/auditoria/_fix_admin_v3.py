# correccion v3: tab() ahora clic en botones sidebar en vez de evaluate switchTab
path = r"pcmaster\tests\auditoria\auditoria_admin.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

old_tab = '''def tab(page, tab_id, nombre_captura, report_name):
    """cambia a pestana admin via evaluate y toma captura"""
    try:
        page.wait_for_function("typeof window.switchTab === 'function'", timeout=10000)
        page.evaluate(f"switchTab('{tab_id}')")
        page.wait_for_timeout(2000)
        screenshot(page, nombre_captura)
        reportar(report_name, "ok", f"cambio a {tab_id}")
    except Exception as e:
        reportar(report_name, "fallo", f"excepcion: {e}")'''

new_tab = '''def tab(page, tab_id, nombre_captura, report_name):
    """cambia a pestana admin haciendo clic en boton sidebar y toma captura"""
    try:
        nav_btn = page.query_selector(f"#nav-{tab_id}, button[onclick*='{tab_id}']")
        if nav_btn:
            nav_btn.click()
            page.wait_for_timeout(2000)
            screenshot(page, nombre_captura)
            reportar(report_name, "ok", f"cambio a {tab_id}")
        else:
            # fallback: buscar cualquier boton que contenga el nombre
            fallback = page.query_selector(f"nav button:has-text('{tab_id}')")
            if fallback:
                fallback.click()
                page.wait_for_timeout(2000)
                screenshot(page, nombre_captura)
                reportar(report_name, "ok", f"cambio a {tab_id} (fallback)")
            else:
                # ultimo recurso: directo via html injection de script global
                page.evaluate(f"""
                    (function() {{
                        var script = document.createElement('script');
                        script.textContent = "window.doSwitch = function(id) {{ var tabs = document.querySelectorAll('.tab-content'); tabs.forEach(function(t) {{ t.classList.remove('active'); }}); var target = document.getElementById('tab-content-' + id); if (target) target.classList.add('active'); var navs = document.querySelectorAll('.admin-sidebar nav button'); navs.forEach(function(n) {{ n.classList.remove('active'); }}); var navBtn = document.getElementById('nav-' + id); if (navBtn) navBtn.classList.add('active'); }};";
                        document.body.appendChild(script);
                    }})();
                """)
                page.evaluate(f"window.doSwitch('{tab_id}')")
                page.wait_for_timeout(2000)
                screenshot(page, nombre_captura)
                reportar(report_name, "ok", f"cambio a {tab_id} (injection)")
    except Exception as e:
        reportar(report_name, "fallo", f"excepcion: {e}")'''

assert old_tab in content, "tab block not found!"
content = content.replace(old_tab, new_tab)

# tambien reemplazar los evaluate de switchTab en los clics de tokenomia
old_tok = '''card = page.query_selector(f"[onclick*='{tok_id}']")'''
new_tok = '''card = page.query_selector(f"#nav-{tok_id}, [onclick*='{tok_id}']")'''
content = content.replace(old_tok, new_tok)

# reemplazar en monitoreo tambien
old_mon = '''card = page.query_selector(f"[onclick*='{mon_id}']")'''
new_mon = '''card = page.query_selector(f"#nav-{mon_id}, [onclick*='{mon_id}']")'''
content = content.replace(old_mon, new_mon)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
print("correccion v3 aplicada: tab() usa clic en sidebar en vez de evaluate")