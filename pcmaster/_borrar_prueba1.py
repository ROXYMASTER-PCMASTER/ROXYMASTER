# _borrar_prueba1.py - elimina usuario prueba1 y todos sus datos asociados
import sqlite3, os

db_path = os.path.join(os.path.dirname(__file__), 'data', 'roxymaster.db')
print('db path:', db_path)
print('exists:', os.path.exists(db_path))

conn = sqlite3.connect(db_path)
conn.execute('PRAGMA foreign_keys=OFF')

# 1. verificar que existe
row = conn.execute("SELECT id, email FROM usuarios WHERE email = 'prueba1@roxymaster.local'").fetchone()
if row:
    print(f'1. usuario encontrado: id={row[0]}, email={row[1]}')
    uid = row[0]
else:
    print('1. usuario NO encontrado')
    uid = None

if uid:
    tablas = [
        ('perfiles_roxy', f'DELETE FROM perfiles_roxy WHERE usuario_id = {uid}'),
        ('computadoras', f"DELETE FROM computadoras WHERE usuario_id = {uid} OR pcbot_id = 'pcbot_prueba1'"),
        ('comandos', f"DELETE FROM comandos WHERE pcbot_id = 'pcbot_prueba1'"),
        ('urls_asignadas', f"DELETE FROM urls_asignadas WHERE pcbot_id = 'pcbot_prueba1'"),
        ('perfiles', f'DELETE FROM perfiles WHERE usuario_id = {uid}'),
        ('sessions', f'DELETE FROM sessions WHERE usuario_id = {uid}'),
    ]
    # tablas opcionales
    for tname in ['wallets', 'apikeys_roxybrowser', 'perfiles_roxy_ext']:
        try:
            conn.execute(f"SELECT 1 FROM {tname} LIMIT 1")
            tablas.append((tname, f'DELETE FROM {tname} WHERE usuario_id = {uid}'))
        except:
            print(f'  tabla {tname} no existe, saltando')

    for nombre, sql in tablas:
        try:
            # contar primero
            where_part = sql.split('DELETE FROM')[1].strip()
            count_sql = f"SELECT COUNT(*) FROM {where_part}"
            antes = conn.execute(count_sql).fetchone()[0]
            conn.execute(sql)
            print(f'  {nombre}: {antes} registros eliminados')
        except Exception as e:
            print(f'  {nombre}: error - {e}')

    # eliminar el usuario
    conn.execute('DELETE FROM usuarios WHERE id = ?', (uid,))
    print(f'  11. usuario id={uid} eliminado')

conn.commit()
print()
print('=== VERIFICACION POST-ELIMINACION ===')
checks = [
    ("SELECT COUNT(*) FROM usuarios WHERE email = 'prueba1@roxymaster.local'", 'usuarios'),
    ("SELECT COUNT(*) FROM computadoras WHERE pcbot_id = 'pcbot_prueba1'", 'computadoras'),
    (f"SELECT COUNT(*) FROM perfiles_roxy WHERE usuario_id = {uid}", 'perfiles_roxy'),
    (f"SELECT COUNT(*) FROM perfiles WHERE usuario_id = {uid}", 'perfiles'),
    ("SELECT COUNT(*) FROM comandos WHERE pcbot_id = 'pcbot_prueba1'", 'comandos'),
    ("SELECT COUNT(*) FROM urls_asignadas WHERE pcbot_id = 'pcbot_prueba1'", 'urls_asignadas'),
    (f"SELECT COUNT(*) FROM sessions WHERE usuario_id = {uid}", 'sessions'),
]
for sql, nombre in checks:
    try:
        res = conn.execute(sql).fetchone()[0]
        print(f'  {nombre}: {res} registros (debe ser 0)')
    except Exception as e:
        print(f'  {nombre}: error - {e}')

conn.close()
print('=== LIMPIEZA COMPLETADA ===')
input('presiona enter para salir...')