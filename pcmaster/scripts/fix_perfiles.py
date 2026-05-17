from db import ejecutar_sql
# Actualizar los perfiles con activo=0 que sí están libres
resultado = ejecutar_sql("UPDATE perfiles_roxy SET activo = 1 WHERE pcbot_id = 'PCWILMER' AND activo = 0")
print(f"Perfiles actualizados a activo=1: {resultado}")
