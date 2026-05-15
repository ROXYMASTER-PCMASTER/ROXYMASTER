from db import ejecutar_sql
# Marcar como fallidas todas las asignaciones activas del PCBot
resultado = ejecutar_sql(
    "UPDATE pedido_asignaciones SET estado = 'fallido' "
    "WHERE perfil_id IN (SELECT hash FROM perfiles_roxy WHERE pcbot_id = 'PCWILMER') "
    "AND estado IN ('ejecutando', 'planificado')"
)
print(f"Asignaciones liberadas: {resultado}")
