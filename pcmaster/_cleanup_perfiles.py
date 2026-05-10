import sqlite3
conn = sqlite3.connect('pcmaster/data/roxymaster.db')

uid = 30  # prueba1@roxymaster.local

# listar basura
basura = conn.execute(
    "select id, nombre_perfil from perfiles where usuario_id=? "
    "and (nombre_perfil='8ce112f7ebbb0fba6e9e290194f8e117' "
    "or nombre_perfil='324' "
    "or nombre_perfil='23' "
    "or nombre_perfil='5345345' "
    "or nombre_perfil='23424' "
    "or length(nombre_perfil)<4)",
    (uid,)
).fetchall()
print('Basura a eliminar:', [(b[0], b[1]) for b in basura])

conn.execute(
    "delete from perfiles where usuario_id=? "
    "and (nombre_perfil='8ce112f7ebbb0fba6e9e290194f8e117' "
    "or nombre_perfil='324' "
    "or nombre_perfil='23' "
    "or nombre_perfil='5345345' "
    "or nombre_perfil='23424' "
    "or length(nombre_perfil)<4)",
    (uid,)
)
conn.commit()

quedan = conn.execute(
    "select id, nombre_perfil, estado, hash_id, tipo from perfiles where usuario_id=?",
    (uid,)
).fetchall()
print('Perfiles restantes:', [(q[0], q[1], q[2], q[3]) for q in quedan])
conn.close()