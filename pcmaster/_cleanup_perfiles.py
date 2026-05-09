import sqlite3, os

db_path = os.path.join(os.path.dirname(__file__), 'data', 'roxymaster.db')
if not os.path.exists(db_path):
    print('DB NOT FOUND at ' + db_path)
    exit(1)

conn = sqlite3.connect(db_path)
c = conn.cursor()

# contar basura antes
c.execute("""
    SELECT COUNT(*) FROM perfiles
    WHERE nombre_perfil LIKE '%8ce112f7ebbb0fb%'
       OR nombre_perfil GLOB '[0-9]*'
       OR length(nombre_perfil) < 4
""")
count_before = c.fetchone()[0]
print(f'Garbage rows found: {count_before}')

# eliminar basura
c.execute("""
    DELETE FROM perfiles
    WHERE nombre_perfil LIKE '%8ce112f7ebbb0fb%'
       OR nombre_perfil GLOB '[0-9]*'
       OR length(nombre_perfil) < 4
""")
deleted = c.rowcount
conn.commit()

print(f'Deleted {deleted} garbage rows')

# verificar restantes
c.execute('SELECT id, nombre_perfil, hash_id, pcbot_id, estado FROM perfiles ORDER BY pcbot_id, id')
rows = c.fetchall()
conn.close()
print(f'Remaining profiles: {len(rows)}')
for r in rows:
    print(f'  id={r[0]} nombre={str(r[1])[:30]} hash={str(r[2])[:16]} pcbot={r[3]} estado={r[4]}')