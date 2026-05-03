"""verifica que todos los archivos del pcbot compilen correctamente."""
import py_compile, os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
FILES = [
    'cargador_secretos.py', 'shs.py', 'config_loader.py',
    'deteccion_perfiles.py', 'roxybrowser_api.py', 'variables_globales.py',
    'core/__init__.py', 'core/profile_manager.py',
    'core/state_tracker.py', 'core/token_engine.py',
    'api/__init__.py', 'api/ws_client.py', 'api/roxybrowser_api.py',
    'http_portal.py', 'orchestrator_local.py', 'main.py', 'auto_detect.py',
]

ok = []
fail = []
missing = []

for f in FILES:
    fp = os.path.join(BASE, f)
    if not os.path.exists(fp):
        missing.append(f)
        continue
    try:
        py_compile.compile(fp, doraise=True)
        ok.append(f)
    except py_compile.PyCompileError as e:
        fail.append((f, str(e)))

print("=" * 60)
print(f"  Pcbot - verificacion de compilacion")
print("=" * 60)
print(f"  archivos: {len(ok)} ok, {len(fail)} fallos, {len(missing)} faltantes")
if ok:
    print(f"  ok:")
    for f in ok:
        print(f"    [ok] {f}")
if fail:
    print(f"  errores:")
    for f, e in fail:
        print(f"    [fail] {f}: {e[:120]}")
if missing:
    print(f"  faltantes:")
    for f in missing:
        print(f"    [missing] {f}")

print(f"  lineas totales:", sum(
    len(open(os.path.join(BASE, f)).read().splitlines())
    for f in FILES if os.path.exists(os.path.join(BASE, f))
))
print("=" * 60)

sys.exit(1 if fail else 0)