from db import ejecutar_sql
# Ver asignaciones que bloquean los perfiles
bloqueos = ejecutar_sql("""
    SELECT pa.id, pa.perfil_id, pa.estado, pa.pedido_id, pr.hash
    FROM pedido_asignaciones pa
    JOIN perfiles_roxy pr ON pa.perfil_id = pr.hash
    WHERE pr.pcbot_id = 'PCWILMER'
      AND pr.activo = 1
      AND pa.estado IN ('planificado', 'ejecutando')
""")
print('Asignaciones bloqueantes:', bloqueos)

# Liberarlas
if bloqueos:
    ejecutar_sql("""
        UPDATE pedido_asignaciones SET estado = 'fallido'
        WHERE id IN (
            SELECT pa.id FROM pedido_asignaciones pa
            JOIN perfiles_roxy pr ON pa.perfil_id = pr.hash
            WHERE pr.pcbot_id = 'PCWILMER'
              AND pr.activo = 1
              AND pa.estado IN ('planificado', 'ejecutando')
        )
    """)
    print('Asignaciones bloqueantes marcadas como fallidas.')
else:
    print('No hay asignaciones bloqueantes.')
