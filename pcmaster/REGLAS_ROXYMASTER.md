# REGLAS TÉCNICAS COMPLEMENTARIAS – ROXYMASTER v8.3

## Estructura del proyecto
- `pcmaster/`: servidor FastAPI + WebSocket.
- `pcbot/`: agente zombie (solo ejecuta, no decide).
- `pcmaster/scripts/`: lógica del servidor.
- `pcbot/scripts/`: lógica del agente.
- Backups y logs fuera de las carpetas principales (`_backups/`, `_bitacora/`).

## Archivos críticos del modelo centralizado (intocables sin autorización)

| Archivo | Rol |
|---------|-----|
| `pcmaster/scripts/procesador_cola.py` | Planificador central (match bajo demanda, prioridad de recuperación) |
| `pcmaster/scripts/procesador_cola_ext.py` | Auxiliares del planificador (`_obtener_perfiles_libres`, etc.) |
| `pcmaster/scripts/pedidos_vigilante.py` | Vigilante de pedidos activos (detecta caídas, registra bajas) |
| `pcmaster/scripts/heartbeat_cache.py` | Cache mínimo de heartbeats (guarda `"perfiles"`) |
| `pcmaster/scripts/orchestrator_ext.py` | Procesa heartbeat, ejecuta eventos, vigilante y match en orden |
| `pcmaster/scripts/db_pedidos_ext.py` | Migraciones (columnas nuevas, `contextos_streamer`) |
| `pcbot/scripts/orchestrator_local_ext.py` | Ejecutor en PCBot (observador, captura de chat, cierre) |

## Flujo de heartbeat (no modificar)
1. Heartbeat recibido → `heartbeat_cache` almacena `"perfiles"`.
2. `procesar_heartbeat_eventos` actualiza `perfiles_roxy`.
3. `_ciclo_vigilante()` inmediato → detecta bajas.
4. `asyncio.sleep(5)`.
5. `ejecutar_ciclo_match()` con prioridad urgente.

## Variables globales protegidas
- `MARGEN_PRIORIDAD = 5` (segundos, en `procesador_cola.py`)
- `_prioridad_recuperacion` (dict, pedidos con baja reciente)
- `_match_en_progreso` (flag anti-reentrada)
- `_cache` (dict en `heartbeat_cache.py`, clave `"perfiles"`)

## Colaboración entre máquinas
- PCBot envía heartbeat cada **30 s** con lista `"perfiles"`.
- PCBot **no** toma decisiones de asignación.
- Handshake bootstrap sin SHS.
- Carpeta compartida `pcbot_clon` mapeada como `Z:\` en PCBot.

## Estado actual del heartbeat
- Frecuencia: 30 segundos.
- Contenido: `pcbot_id`, `uptime`, `modo`, `"perfiles"` (con `profile_id`, `activo`, `url`, `state`).
- PCMaster **no** responde con API Keys.
- Tras reinicio del PCBot, PCMaster reactiva perfiles (`activo=1`) mediante el evento `reinicio`.

**Última actualización:** 2026-05-17