from db import ejecutar_sql
# Ver asignaciones activas (planificado + ejecutando)
asig = ejecutar_sql("SELECT id, pedido_id, perfil_id, estado, liberacion_estimada FROM pedido_asignaciones WHERE estado IN ('planificado', 'ejecutando') ORDER BY id DESC LIMIT 10")
print('Asignaciones activas:')
for a in (asig or []): print(a)
# Ver pedidos en progreso
peds = ejecutar_sql("SELECT id, estado, fecha_inicio, duracion_horas FROM pedidos WHERE estado IN ('en_progreso', 'agendado') ORDER BY id DESC LIMIT 5")
print('\nPedidos en progreso/agendados:')
for p in (peds or []): print(p)
