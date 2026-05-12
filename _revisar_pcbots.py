import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'pcmaster', 'scripts'))
from db import ejecutar_sql
for tabla in ['pcbots_registrados', 'perfiles_roxy', 'usuarios']:
    print(f"--- {tabla} ---")
    for r in ejecutar_sql(f'PRAGMA table_info({tabla})'):
        print(r)
    print()