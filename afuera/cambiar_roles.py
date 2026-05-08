# cambiar roles - todas las cuentas a usuario, excepto superadmin

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from db import ejecutar_sql

# cambiar todas las cuentas (excepto superadmin) a rol usuario
ejecutar_sql(
    "update usuarios set rol = 'usuario' where rol != 'superadmin'"
)

# verificar resultado
rows = ejecutar_sql("select email, rol from usuarios order by id")
print("roles actualizados:")
for r in rows:
    print(f'  {r["email"]:40} {r["rol"]}')