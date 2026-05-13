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
[2026-12-05 19:57] - gran refactor: procesador de cola fifo + vigilante simplificado + server integrado
  - decision: separar responsabilidades en 3 modulos: procesador_cola (cola), vigilante (monitoreo), server (orquestador)
  - creado pcmaster/scripts/procesador_cola.py (359 lineas):
    - procesar_cola_pedidos(): bucle cada 10s, toma pedidos pendientes/programados con hora cumplida, asigna perfiles
    - _asignar_perfil(): construye comando asignar con formato exacto que espera el PCBot (duracion en segundos, hora_inicio/fin si aplica)
    - _obtener_perfiles_libres(): cruza perfiles_roxy con heartbeat (perfiles activos) para encontrar disponibles
    - soporta agendamiento: pedidos con hora_inicio_programada futura quedan en programado
    - reintento: si no hay perfiles libres, deja en pendiente para siguiente ciclo
  - simplificado pcmaster/scripts/pedidos_vigilante.py (de 544 a 260 lineas):
    - eliminada toda la logica de cola y transicion programado->pendiente (ahora en procesador_cola)
    - eliminada la subida de pedidos a PCBot (ahora en procesador_cola)
    - conservada: deteccion de perfiles caidos por heartbeat (url ausente), reemplazo con perfil libre, finalizacion de pedidos expirados
    - verifica url del perfil contra url del pedido (campo url en heartbeat de cada perfil)
    - solo monitorea pedidos en_progreso, ignora programado/pendiente/completado
  - integrado en pcmaster/scripts/server.py:
    - import de procesador_cola.al final del bloque de imports
    - asyncio.create_task(procesar_cola_pedidos()) en lifespan junto a monitorear_pedidos()
  - backup automatico creado en backups/pcmaster_20261205_1954/
  - tests de import: procesador_cola.py importa sin errores (imports: asyncio, logging, time, json, uuid, datetime, database, ws_manager, heartbeat_cache)
  - tests de import: pedidos_vigilante.py importa sin errores (imports: asyncio, json, logging, datetime, database, ws_manager, heartbeat_cache, db_pedidos_ext)
  - push exitoso a remoto (commit afcc977)