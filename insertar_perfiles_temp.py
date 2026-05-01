import sqlite3
conn = sqlite3.connect('c:/users/pcmaster/desktop/roxymaster/pcmaster/data/roxymaster.db')
for i in range(1,4):
    conn.execute(
        "insert into perfiles (granjero_id, nombre_perfil, tipo, estado) values (?, ?, ?, ?)",
        ('testfuncional@roxymaster.com', f'perfil_prueba_{i}', 'local', 'activo')
    )
conn.commit()
# verificar
rows = conn.execute("select * from perfiles").fetchall()
print(f"cantidad de perfiles: {len(rows)}")
for r in rows:
    print(r)
conn.close()