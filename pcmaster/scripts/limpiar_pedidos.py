from db import ejecutar_sql
print("Eliminando asignaciones...")
asig = ejecutar_sql("DELETE FROM pedido_asignaciones")
print(f"  Asignaciones eliminadas: {asig}")
print("Eliminando pedidos...")
peds = ejecutar_sql("DELETE FROM pedidos")
print(f"  Pedidos eliminados: {peds}")
print("Limpieza completada.")
