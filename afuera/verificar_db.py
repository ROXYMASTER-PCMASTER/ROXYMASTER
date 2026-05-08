# verificar_db.py - verifica los datos insertados

from db import ejecutar_sql

# contar registros en cada tabla
tablas = ['usuarios', 'wallets', 'perfiles', 'codigos_referido', 'sesiones', 'referidos', 'ordenes_p2p', 'transacciones', 'variables_globales', 'comandos', 'urls_asignadas', 'sesiones_activas', 'eventos_seguridad', 'mensajes', 'pcbots_registrados', 'retiros', 'happy_hour']
for t in tablas:
    try:
        r = ejecutar_sql(f'select count(*) as total from {t}')
        print(f'  {t:20} {r[0]["total"]} registros')
    except Exception as e:
        print(f'  {t:20} error: {e}')

print()
u = ejecutar_sql('select u.id, u.email, u.rol, u.nivel_fiabilidad, u.wallet, u.codigo_referido, u.uptime_horas, u.modo, w.balance from usuarios u left join wallets w on w.usuario_id = u.id order by u.id')
for row in u:
    print(f'  id={row["id"]:>2} {row["email"]:35} rol={row["rol"]:10} nivel={row["nivel_fiabilidad"]:8} balance={row["balance"]:>8.2f}')
print(f'\ntotal usuarios: {len(u)}')