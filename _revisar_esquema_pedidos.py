# _revisar_esquema_pedidos.py - revisa esquema de tabla pedidos
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'pcmaster', 'scripts'))
from db import ejecutar_sql
rows = ejecutar_sql('PRAGMA table_info(pedidos)')
for r in rows:
    print(r)