# bitacora de decisiones - roxymaster pcmaster

## formato
cada entrada: [fecha] - [descripcion breve]

## entradas

[2026-05-10] - implementacion base de pedidos con formulario, tabla y js.
[2026-05-11] - reestructuracion de pedidos en modulos core/ext (formulario, tabla, js).
[2026-05-12] - fix validacion url en api_pedidos.py (400 vs 500), heartbeat_cache con url por perfil.
[2026-12-05] - implementacion de agendamiento de pedidos por hora:
  - creado pcmaster/scripts/db_pedidos_ext.py con alter table para columnas hora_inicio_programada y hora_fin_programada
  - creado pcmaster/scripts/api_pedidos_agendamiento.py con endpoint POST /api/pedidos/crear_con_agenda
    - valida hora_inicio futura, hora_fin posterior, rechaza solo hora_fin
    - pedidos con agenda -> estado 'programado'
    - pedidos sin agenda -> flujo normal inmediato
  - actualizado pcmaster/publico/pedidos_formulario.html con campos programar inicio/fin
  - actualizado pcmaster/publico/pedidos_js.html para enviar hora_inicio/hora_fin al backend
  - actualizado pcmaster/scripts/pedidos_vigilante.py para transicionar programado->pendiente cuando llega la hora
  - actualizado pcmaster/scripts/api_pedidos.py endpoint mis_pedidos para incluir hora_inicio_programada y hora_fin_programada
  - tests: 5/5 pasaron (sin agenda, agenda completa, solo inicio, solo fin error, pasado error)