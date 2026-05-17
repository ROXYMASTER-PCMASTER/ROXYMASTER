"""seed computadoras con pcbot_id del usuario prueba1 (id=30).
Propaga tambien roxy_api_key desde usuarios a computadoras."""
import sqlite3

db_path = r'c:\Users\PCMASTER\Desktop\roxymaster\pcmaster\data\roxymaster.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# obtener datos del usuario
usuario = conn.execute(
    "select id, roxy_api_key, roxy_workspace_id from usuarios where id = ?", (30,)
).fetchone()

if not usuario:
    print("ERROR: usuario id=30 no encontrado")
    conn.close()
    exit(1)

print(f"Usuario: id={usuario['id']}, roxy_api_key={usuario['roxy_api_key']}")

# verificar si ya existe
existente = conn.execute(
    "select id from computadoras where pcbot_id = ?", ('pcbot_prueba1',)
).fetchone()

if existente:
    print(f"actualizando computadora existente id={existente['id']}")
    conn.execute(
        "UPDATE computadoras SET api_key_roxy=?, workspace_id=?, estado='activa', "
        "ultima_conexion=datetime('now','localtime') WHERE id=?",
        (usuario['roxy_api_key'] or '', usuario['roxy_workspace_id'] or '', existente['id'])
    )
else:
    print("insertando nueva computadora")
    conn.execute(
        "INSERT INTO computadoras (pcbot_id, usuario_id, api_key_roxy, workspace_id, estado, ultima_conexion) "
        "VALUES (?, ?, ?, ?, 'activa', datetime('now','localtime'))",
        ('pcbot_prueba1', 30, usuario['roxy_api_key'] or '', usuario['roxy_workspace_id'] or '')
    )
conn.commit()

# verificar resultados
comps = conn.execute(
    "select * from computadoras where usuario_id = ?", (30,)
).fetchall()
print(f"\ntotal computadoras para usuario_id=30: {len(comps)}")
for c in comps:
    print(f"  id={c['id']} pcbot_id={c['pcbot_id']} api_key_roxy={c['api_key_roxy']} "
          f"workspace_id={c['workspace_id']} estado={c['estado']} ultima_conexion={c['ultima_conexion']}")

conn.close()