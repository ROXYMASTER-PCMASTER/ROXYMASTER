# bitacora de decisiones - roxymaster

## 2026-05-11 - solucion envio de pedidos a pcbot PCWILMER

### problema
los pedidos creados por usuarios con pcbot_id='PCWILMER' no se enviaban al websocket de pcbot.
orchestrator._enviar_a_pcbot no encontraba la conexion ws, y el fallback via ws_manager.send_to_pcbot_queue
no funcionaba porque ws_client jamás identifica correctamente al pcbot.

### diagnostico
- servidor conectado a un solo pcbot (PCWILMER) via /ws/{pcbot_id}
- ws_client se identificaba en el server como pcbot_id='PCWILMER' correctamente
- pero ws_manager no tenia registro de esa conexion porque solo registraba en identify, no en cada mensaje
- _conexiones_ws de orchestrator tenia al pcbot, pero _enviar_a_pcbot decia ws.closed=True
- se agrego log [PEDIDO-DIAG] en api_pedidos.py para ver payload exacto
- se descubrio que ws_client.json() fallaba con "no attribute" en heartbeat_handler

### solucion aplicada (7 cambios)

1. **server.py**: sincronizar _conexiones_ws en cada mensaje de ws_client, no solo en identify
2. **server.py**: en heartbeat_handler, acceder a datos crudos via self.data en vez de self.json()
   para evitar "WebSocketClient no attribute json"
3. **server.py**: registrar conexion en ws_manager en cada mensaje (no solo en identify)
4. **server.py**: pasar self._conexiones_ws y self.ws_manager como kwargs al heartbeat_handler
5. **orchestrator.py**: en _cmd_asignar, usar url con query string si no tiene (default kick.com)
6. **orchestrator.py**: en crear_comando, agregar fallback: si ws directo falla, intentar via ws_manager
7. **api_pedidos.py**: agregar log [PEDIDO-DIAG] con payload exacto y resultado del envio

### resultado
pedido #13 creado por usuario prueba1 (id=33) se envio EXITOSAMENTE a PCWILMER:
- payload: {"tipo":"asignar","comando_id":"pedido_be4eb5e2b400","parametros":{"url":"https://kick.com/testchannel","cantidad":1,"duracion":60,"nivel_comentarios":"basico"}}
- _enviar_a_pcbot: enviado OK a PCWILMER via ws directo
- api response: comando_enviado=true, pedido_id=13, costo=0.0333

### archivos modificados
- pcmaster/scripts/server.py (sync _conexiones_ws, fix heartbeat, registrar en ws_manager)
- pcmaster/scripts/orchestrator.py (fallback ws_manager, url default)
- pcmaster/scripts/api_pedidos.py (log diagnostico)

### pendiente
- monitorear si pcbot procesa el comando asignar y ejecuta la navegacion
- verificar logs de pcbot (PCWILMER) para confirmar recepcion y ejecucion