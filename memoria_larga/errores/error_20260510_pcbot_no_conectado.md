# error 2026-05-10: pcbot no conectado en sincronización de perfiles

## síntoma
El endpoint `/api/roxy/sync_profiles` retorna `500 Internal Server Error` con detalle `"pcbot no conectado"`. El usuario prueba1@roxymaster.local no puede sincronizar perfiles.

## causa raíz
El `pcbot_prueba1` no tiene una conexión WebSocket activa con el servidor. El orchestrator retorna inmediatamente `{'ok': False, 'error': 'pcbot no conectado'}` porque el diccionario `_conexiones_pcbots` no contiene el pcbot_id solicitado.

## logs colectados (2026-05-10 02:55 - 03:18)
- [DIAG-200] Sincronizando perfiles para pcbot=pcbot_prueba1
- [DIAG-100] Enviando comando a pcbot_prueba1
- [SYNC] Resultado del comando: {'ok': False, 'error': 'pcbot no conectado'}
- [DIAG-201] Resultado del comando: {'ok': False, 'error': 'pcbot no conectado'}

## logs ausentes (que confirmarían la falla)
- DIAG-001 (nueva conexion de pcbot): no aparece -> pcbot_prueba1 nunca se conectó
- DIAG-002 (handshake completo): no aparece
- DIAG-003 (mensaje recibido): no aparece
- DIAG-005/006/007 (respuesta_recargar_perfiles): no aparece
- DIAG-101/102/103/104: no aparecen porque enviar_comando_recargar_perfiles retorna antes de llegar a DIAG-101

## evidencia temporal
- 2026-05-10 02:53:11 -> última vez que pcbot_prueba1 se conectó (servidor anterior)
- 2026-05-10 02:55:01 -> primera prueba de sync (fracasa)
- 2026-05-10 03:17:54 -> se guardó api key para usuario 30
- 2026-05-10 03:17:55 -> múltiples intentos fallidos de sync
- 2026-05-10 03:20:43 -> PCWILMER desconectado
- 2026-05-10 03:22:58 -> PCWILMER conectado (pcbot_prueba1 nunca se reconectó)

## soluciones propuestas
1. **inmediata**: iniciar manualmente el bot pcbot_prueba1
2. **retry**: agregar reintento con espera de 5s en api_roxykey.py
3. **cola de comandos**: implementar cola persistente de comandos pendientes

## variables afectadas
- pcbot_id = pcbot_prueba1 (usuario_id=30)
- _conexiones_pcbots en orchestrator.py (vacío para pcbot_prueba1)