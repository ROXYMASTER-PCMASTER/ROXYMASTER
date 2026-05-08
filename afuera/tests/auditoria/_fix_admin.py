# correcciones para auditoria_admin.py
path = r"pcmaster\tests\auditoria\auditoria_admin.py"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. selector doble ##kpi -> #kpi (linea 141)
content = content.replace("##kpi-", "#kpi-")

# 2. wait_for_function antes de switchTab
old = '''def tab(page, tab_id, nombre_captura, report_name):
    """cambia a pestana admin via evaluate y toma captura"""
    try:
        page.evaluate(f"switchTab('{tab_id}')")
        page.wait_for_timeout(2000)
        screenshot(page, nombre_captura)
        reportar(report_name, "ok", f"cambio a {tab_id}")
    except Exception as e:
        reportar(report_name, "fallo", f"excepcion: {e}")'''

new = '''def tab(page, tab_id, nombre_captura, report_name):
    """cambia a pestana admin via evaluate y toma captura"""
    try:
        page.wait_for_function("typeof window.switchTab === 'function'", timeout=10000)
        page.evaluate(f"switchTab('{tab_id}')")
        page.wait_for_timeout(2000)
        screenshot(page, nombre_captura)
        reportar(report_name, "ok", f"cambio a {tab_id}")
    except Exception as e:
        reportar(report_name, "fallo", f"excepcion: {e}")'''

assert old in content, "old block not found!"
content = content.replace(old, new)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)

print("correcciones aplicadas exitosamente")