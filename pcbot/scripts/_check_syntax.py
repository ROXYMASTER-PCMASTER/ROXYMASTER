"""verificador de sintaxis para todos los modulos pcbot v8.3"""
import py_compile
import os
import sys

base = os.path.dirname(os.path.abspath(__file__))
modulos = [
    "main.py", "config_loader.py", "shs.py", "deteccion_perfiles.py",
    "http_portal.py", "cargador_secretos.py",
    "core/__init__.py", "core/profile_manager.py", "core/state_tracker.py",
    "core/token_engine.py", "core/orchestrator_local.py",
    "api/__init__.py", "api/ws_client.py", "api/roxybrowser_api.py",
    "api/commentador.py",
]

errores = 0
for m in modulos:
    ruta = os.path.join(base, m)
    if not os.path.exists(ruta):
        print(f"[no existe] {m}")
        continue
    try:
        py_compile.compile(ruta, doraise=True, quiet=1)
        print(f"[ok] {m}")
    except py_compile.PyCompileError as e:
        print(f"[error] {m}: {e}")
        errores += 1

print()
if errores:
    print(f"total errores: {errores}")
    sys.exit(1)
else:
    print("todos los modulos pasaron la verificacion de sintaxis.")