# _fix_pcbot_id.py - corrige comandos y usuarios con pcbot_id nulo
# ejecutar con: python _fix_pcbot_id.py

import sqlite3
import os

# buscar db: primero en pcmaster/data/roxymaster.db
ruta_directa = os.path.join(os.path.dirname(__file__), "data", "roxymaster.db")
ruta_scripts = os.path.join(os.path.dirname(__file__), "scripts", "data", "roxymaster.db")

if os.path.exists(ruta_directa):
    db_path = ruta_directa
elif os.path.exists(ruta_scripts):
    db_path = ruta_scripts
else:
    # ultimo recurso: buscar
    db_path = ""
    for guess in [
        "pcmaster/data/roxymaster.db",
        "data/roxymaster.db",
        "scripts/data/roxymaster.db",
    ]:
        if os.path.exists(guess):
            db_path = guess
            break

if not db_path or not os.path.exists(db_path):
    print("ERROR: no se encuentra roxymaster.db")
    exit(1)

print(f"usando db: {db_path}")

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
c = conn.cursor()

# 1. comandos con pcbot_id null
c.execute("select count(*) as cnt from comandos where pcbot_id is null or pcbot_id = ''")
r = c.fetchone()
nulos = r["cnt"]
print(f"comandos con pcbot_id null/vacio: {nulos}")

if nulos > 0:
    c.execute("select id, comando_id, tipo, pcbot_id from comandos where pcbot_id is null or pcbot_id = ''")
    for r in c.fetchall():
        print(f"  id={r['id']} comando_id={r['comando_id']} tipo={r['tipo']} pcbot_id={repr(r['pcbot_id'])}")

    c.execute("update comandos set pcbot_id = 'PCWILMER' where (pcbot_id is null or pcbot_id = '')")
    conn.commit()
    print(f"actualizados: {c.rowcount} comandos a PCWILMER")

# 2. usuarios con pcbot_id null
c.execute("select count(*) as cnt from usuarios where pcbot_id is null or pcbot_id = ''")
r = c.fetchone()
nulos_u = r["cnt"]
print(f"usuarios con pcbot_id null/vacio: {nulos_u}")

if nulos_u > 0:
    c.execute(
        "select u.id from usuarios u "
        "inner join computadoras c on c.usuario_id = u.id "
        "where (u.pcbot_id is null or u.pcbot_id = '')"
    )
    for r in c.fetchall():
        c.execute("select pcbot_id from computadoras where usuario_id = ? limit 1", (r["id"],))
        comp = c.fetchone()
        if comp and comp["pcbot_id"]:
            c.execute(
                "update usuarios set pcbot_id = ?, modo = 'conectado' where id = ?",
                (comp["pcbot_id"], r["id"]),
            )
            print(f"  actualizado usuario {r['id']} pcbot_id={comp['pcbot_id']}")
    conn.commit()

conn.close()
print("done.")