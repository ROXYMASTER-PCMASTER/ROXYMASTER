# get schema of key tables for auditoria scripts
import sqlite3
conn = sqlite3.connect('pcmaster/data/roxymaster.db')
tables = ['usuarios','sesiones','ordenes_p2p','mensajes','perfiles','retiros','eventos_seguridad','transacciones','wallets']
for t in tables:
    print(f'=== {t} ===')
    cols = conn.execute(f'pragma table_info("{t}")').fetchall()
    for r in cols:
        print(f'  {r[1]} {r[2]}')
    print()