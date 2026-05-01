import sqlite3
conn = sqlite3.connect('c:/users/pcmaster/desktop/roxymaster/pcmaster/data/roxymaster.db')
row = conn.execute("select referido_por from usuarios where email = 'referido@roxymaster.com'").fetchone()
if row:
    print("referido_por:", row[0])
    if row[0] is None or row[0] == '' or row[0] == 'NULL':
        print("campo vacio, actualizando...")
        conn.execute("update usuarios set referido_por = 'testfuncional@roxymaster.com' where email = 'referido@roxymaster.com'")
        conn.commit()
        print("actualizado ok")
else:
    print("no encontrado")
conn.close()