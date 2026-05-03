# error repetido: reconexion infinita a pcmaster (ws://100.111.179.65:5006)

## accion intentada
conectar pcbot a pcmaster via websocket (ws_client.py) con handshake + heartbeats periodicos.

## comando ejecutado
python main.py (pcbot/scripts/), que inicia ws_client.py conectando a ws://100.111.179.65:5006

## mensaje de error
el log muestra ciclos ininterrumpidos de:
```
conectando a pcmaster: ws://100.111.179.65:5006
conectado a pcmaster (intento #N)
handshake enviado a pcmaster (modo: pidiendo_ordenes)
```
... ~27-30s despues:
```
conectando a pcmaster: ws://100.111.179.65:5006 (intento #N+1)
```
nunca se ve un heartbeat exitoso ni respuesta "registro_ok" ni "heartbeat_ack".

## razon probable del fallo
- el servidor de produccion (100.111.179.65:5006) cierra conexiones websocket que no reciben mensajes en ~30s.
- el cliente logra handshake, pero nunca envia el primer heartbeat porque:
  1. `_safe_send_heartbeat()` falla silenciosamente (el error log esta en DEBUG, no INFO).
  2. tras 6 heartbeats fallidos (60s con intervalo de 10s), `_hb_fail_count` alcanza 6 y fuerza reconexion.
  3. el servidor cierra la conexion (~30s) antes de que el cliente detecte los 6 fallos.
  4. el `async with websockets.connect(...)` captura `ConnectionClosed` y reconecta.
- causa raiz: posiblemente `_safe_send_heartbeat()` retorna False porque `self.ws` se vuelve None tras el handshake (el receiver loop termina abruptamente cuando el servidor cierra), o porque `self.ws.send()` lanza excepcion no capturada que el try/except no maneja correctamente.

## tres caminos alternativos propuestos

### camino a: modo simulacion (offline-first)
- permitir que pcbot funcione completamente offline usando estado local.
- ws_client.py entra en modo "offline" donde no fuerza reconexion activa.
- intenta reconectar cada 60s en lugar de inmediatamente.
- usa un ping manual (ws.send + ws.recv con timeout de 5s) para detectar si la conexion sigue viva antes de enviar heartbeat.

### camino b: websocket por polling http
- reemplazar la conexion websocket con polling http a la api rest de pcmaster.
- cada 10s, http_get a `http://100.111.179.65:8086/api/pcbot/heartbeat` con los mismos datos.
- el servidor responde con comandos pendientes.
- mas simple, mas tolerante a fallos de red, evita el manejo complejo de ws.

### camino c: conexion ws con ping manual y heartbeat en sender loop principal
- en lugar de `async with websockets.connect(...)`, usar `await websockets.connect(...)` sin context manager.
- en el sender loop, antes de enviar heartbeat, hacer un `await self.ws.ping()` para verificar que el socket esta vivo.
- eliminar `_sender_loop` y `_receiver_loop` como tasks separados; usar un solo loop que alterna send/recv con `asyncio.wait_for`.
- reconnect timeout progresivo: 5, 10, 20, 30s (max 60s).