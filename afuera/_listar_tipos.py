# listar tipos de usuarios

from db import ejecutar_sql

print('tipos de usuarios en el sistema:')
print()
rows = ejecutar_sql('select rol, nivel_fiabilidad, count(*) as total from usuarios group by rol, nivel_fiabilidad order by rol, nivel_fiabilidad')
for r in rows:
    print(f'  rol={r["rol"]:12} nivel={r["nivel_fiabilidad"]:10} cantidad={r["total"]}')

print()
print('resumen por rol:')
rows2 = ejecutar_sql('select rol, count(*) as total from usuarios group by rol order by rol')
for r in rows2:
    print(f'  {r["rol"]:12} {r["total"]}')