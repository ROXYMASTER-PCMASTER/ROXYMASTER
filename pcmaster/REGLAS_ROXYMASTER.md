# REGLAS DE ORO DEL PROYECTO ROXYMASTER v8.3

## 1. Nomenclatura y estilo
- Todo en minúsculas: variables, funciones, rutas, comentarios. Solo mayúsculas en siglas técnicas (API, KBT, JSON, HTML, CSS, HTTP, WS, HMAC, SHA256, JWT, URL, ID, IP, PC).
- Ningún archivo supera las 400 líneas. Si crece, se divide en dos módulos con sufijo `_core` y `_ext`.
- Se usa `async/await` siempre. No threading para lógica core. Solo `asyncio.create_task` para tareas concurrentes.
- Prohibido usar emojis en código, comentarios, logs, respuestas API, nombres de archivo.
- Codificación UTF-8 sin BOM.
- Contraseñas hasheadas con pbkdf2-hmac-sha256 (100000 iteraciones). Tokens de sesión con expiración de 7 días.
- Logs sin datos sensibles. Rutas dinámicas con variables de entorno, nunca hardcodeadas.

## 2. Estructura del proyecto
- `pcmaster/`: servidor FastAPI + WebSocket.
- `pcbot/`: agente zombie (detección de perfiles, heartbeat, cliente WS).
- `pcmaster/scripts/publico/`: portal público (login, registro, dashboard).
- `pcmaster/scripts/`: lógica del servidor.
- `pcbot/scripts/`: lógica del agente.
- Backups y logs se guardan **fuera** de las carpetas principales (`_backups/`, `_bitacora/`, `archived_tools/`, etc.).

## 3. Colaboración entre máquinas
- PCMaster (servidor) y PCBot (agente) se comunican vía WebSocket a través de Tailscale.
- La carpeta compartida `pcbot_clon` mapeada como `Z:\` en PCBot se usa para intercambiar reportes y correcciones.
- No se usa SHS ni secretos compartidos en archivos; toda la comunicación es por la carpeta compartida o WebSocket.

## 4. Anti-bucles y anti-errores
- Si una estrategia falla 2 veces seguidas, se cambia de enfoque y se documenta.
- Si un error se repite 3 veces, se escribe `error_repetido.md` en el escritorio con diagnóstico y 3 caminos alternativos.
- Si el servidor o script no arranca tras 2 correcciones, se escribe `errores_pendientes.txt` en el escritorio con traceback.
- Si un bucle supera 4 ciclos sin progreso, se rompe y se pide instrucciones explícitas.
- Cada 5 ciclos de espera, se escribe `esperando [recurso]` para mostrar que no está congelado.
- Si se encuentra un archivo corrupto o ilegible, se renombra añadiendo `.corrupto` al final y se genera uno nuevo en blanco.

## 5. Seguridad
- No se almacenan secretos en el código. Se usan variables de entorno o archivos de configuración no versionados.
- Los endpoints de heartbeat y registro de perfiles requieren autenticación por token.
- Las API Keys de RoxyBrowser se almacenan encriptadas y se envían al agente solo a través de WebSocket autenticado.

## 6. Watchdog y Heartbeat (estado actual)
- PCBot envía heartbeat cada 60s con hostname, IPs, workspace_id y lista de perfiles.
- PCMaster responde con API Keys pendientes.
- Al recibir una nueva API Key, PCBot consulta la API local de RoxyBrowser (http://127.0.0.1:50000) y registra los perfiles en el servidor.

**Última actualización:** 2026-05-08
