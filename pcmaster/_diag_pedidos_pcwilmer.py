# _diag_pedidos_pcwilmer.py - diagnostico de pedidos para PCWILMER
# roxymaster v8.3 - utf-8 sin bom

import sqlite3
import json
import os

db_path = os.path.join(os.path.dirname(__file__), "data", "roxymaster.db")
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=" * 70)
print("1. ESQUEMA DE TABLA pedidos")
print("=" * 70)
cur.execute("PRAGMA table_info(pedidos)")
for r in cur.fetchall():
    print(dict(r))

print()
print("=" * 70)
print("2. TODOS LOS PEDIDOS (ultimos 30)")
print("=" * 70)
cur.execute("SELECT * FROM pedidos ORDER BY id DESC LIMIT 30")
rows = cur.fetchall()
if rows:
    for r in rows:
        d = dict(r)
        print(f"  id={d.get('id')} | usuario_id={d.get('usuario_id')} | url={d.get('url','')[:40]} | estado={d.get('estado')} | fecha={d.get('fecha_creacion')} | comando_id={d.get('comando_id')}")
else:
    print("  (vacio)")

print()
print("=" * 70)
print("3. COMANDOS PARA PCWILMER")
print("=" * 70)
cur.execute("SELECT * FROM comandos WHERE pcbot_id = 'PCWILMER' ORDER BY fecha_creacion DESC")
rows = cur.fetchall()
if rows:
    for r in rows:
        d = dict(r)
        print(f"  cmd_id={d.get('comando_id')} | tipo={d.get('tipo')} | estado={d.get('estado')} | fecha={d.get('fecha_creacion')} | params={str(d.get('parametros',''))[:80]}")
else:
    print("  (vacio)")

print()
print("=" * 70)
print("4. USUARIO ASOCIADO A PCWILMER")
print("=" * 70)
cur.execute("SELECT id, username, email, pcbot_id, modo FROM usuarios WHERE pcbot_id = 'PCWILMER'")
rows = cur.fetchall()
if rows:
    for r in rows:
        print(dict(r))
else:
    print("  (ninguno)")
    # buscar en computadoras
    cur.execute("SELECT * FROM computadoras WHERE pcbot_id = 'PCWILMER'")
    cr = cur.fetchall()
    if cr:
        for c in cr:
            print(f"  computadoras: {dict(c)}")

print()
print("=" * 70)
print("5. PCWILMER EN pcbots_registrados")
print("=" * 70)
cur.execute("SELECT pcbot_id, hostname, estado, modo, ultima_conexion, perfiles_activos FROM pcbots_registrados WHERE pcbot_id = 'PCWILMER'")
rows = cur.fetchall()
if rows:
    for r in rows:
        print(dict(r))
else:
    print("  (no registrado)")

print()
print("=" * 70)
print("6. COMANDOS PENDIENTES PARA PCWILMER (estado='pendiente')")
print("=" * 70)
cur.execute("SELECT * FROM comandos WHERE pcbot_id = 'PCWILMER' AND estado = 'pendiente' ORDER BY fecha_creacion")
rows = cur.fetchall()
if rows:
    for r in rows:
        d = dict(r)
        print(f"  cmd_id={d.get('comando_id')} | tipo={d.get('tipo')} | fecha={d.get('fecha_creacion')} | params={str(d.get('parametros',''))[:100]}")
else:
    print("  (ninguno)")

print()
print("=" * 70)
print("7. TODOS LOS COMANDOS (todas las pcbots)")
print("=" * 70)
cur.execute("SELECT pcbot_id, comando_id, tipo, estado, fecha_creacion FROM comandos ORDER BY fecha_creacion DESC LIMIT 20")
rows = cur.fetchall()
if rows:
    for r in rows:
        d = dict(r)
        print(f"  pcbot={d.get('pcbot_id')} | cmd={d.get('comando_id')} | tipo={d.get('tipo')} | estado={d.get('estado')} | fecha={d.get('fecha_creacion')}")
else:
    print("  (vacio)")

conn.close()