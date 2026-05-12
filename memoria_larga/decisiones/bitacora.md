# bitacora de decisiones - roxymaster

## formato
cada entrada: YYYY-MM-DD HH:MM - descripcion de lo realizado

---

## 2026-05-12 11:25 - correccion: proteccion de marketplace.html y perfiles.html con redireccion al dashboard

**que se hizo**: se agrego script de redireccion iframe-check a marketplace.html y perfiles.html

**problema**: ambas paginas se podian abrir directamente sin autenticacion, mostrando contenido roto (ui no definido) porque no tenian el script de redireccion que verificaba si estaban dentro de un iframe del dashboard.

**solucion**: se copio exactamente el mismo patron usado en referidos.html, wallet.html y panel_dashboard.html:
- script iife que verifica `window.top === window.self`
- si es true (pagina abierta directamente), redirige a `dashboard_publico.html?tab=<nombre_panel>`
- marketplace.html redirige a `?tab=marketplace`
- perfiles.html redirige a `?tab=perfiles`
- se usa `window.location.replace` (no href) para evitar que el boton "atras" devuelva a la pagina desprotegida

**archivos modificados**:
- pcmaster/publico/marketplace.html (linea 6-12, +5 lineas)
- pcmaster/publico/perfiles.html (linea 6-12, +5 lineas)

**backup**: backups/publico_20260512_1124/

**archivos no tocados**: server.py, orchestrator.py, ws_manager.py, db.py, ni ningun archivo python.

## 2026-05-12 03:15 - diagnostico flujo crear pedido exitoso

**que se hizo**: se ejecuto diagnostico completo de creacion de pedido (api_pedidos.py endpoint /api/pedidos/crear)

**hallazgos**:
- login funciona con email "prueba1@roxymaster.local" password "12345678"
- endpoint /api/pedidos/crear recibe body con campos: url, seguidores, perfiles, horas (o minutos), nivel_comentarios, tipo_pedido (o tipo)
- el formato que FUNCIONA es el de api directa: horas (float), tipo_pedido (str)
- el formato frontend (minutos=int, tipo=str) FALLA con validacion "seguidores, perfiles y horas deben ser > 0"
- cuando el pedido se crea correctamente, api_pedidos.py llama a enviar_comando_al_pcbot(usuario_id, comando)
- enviar_comando_al_pcbot SI existe en ws_manager.py (linea 207) con firma (usuario_id: int, comando: dict) -> dict
- el pedido se crea con comando_enviado=true y estado=enviado

**problema detectado**: el PCBot NO esta conectado via WebSocket en este momento
- heartbeat_cache vacio (sin heartbeats recibidos)
- _conexiones_por_pcbot vacio
- los pedidos creados quedan en estado "enviado" y nunca pasan a "en_progreso"

**pendiente**: cuando el PCBot se conecte, verificar que:
1. el heartbeat llegue y se registre en heartbeat_cache
2. los pedidos en "enviado" se actualicen a "en_progreso"
3. el vigilante monitoree correctamente

## archivos revisados:
- pcmaster/scripts/ws_manager.py: tiene enviar_comando_al_pcbot (linea 207) y heartbeat_cache.py existe separado
- pcmaster/scripts/api_pedidos.py: endpoint crear pedido funciona, llama a ws_manager correctamente
- pcmaster/scripts/pedidos_vigilante.py: sintaxis valida, importa de ws_manager
- pcmaster/scripts/server.py: importa y lanza monitorear_pedidos() como tarea asincrona (linea 145)

## decisiones:
- NO modificar api_pedidos.py (funciona correctamente)
- NO modificar ws_manager.py (tiene la funcion correcta)
- pedidos_vigilante.py ya esta corregido y compila
- el problema actual es de conectividad (no hay PCBot), no de codigo