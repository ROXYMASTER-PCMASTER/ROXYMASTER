# protocolo de eventos roxymaster

# objetivo:
# desacoplar componentes

# formato evento:

{
    "event": "nombre_evento",
    "source": "modulo_origen",
    "target": "modulo_destino",
    "timestamp": "utc",
    "payload": {}
}

# reglas:
# - json utf8
# - async
# - no bloqueo
# - idempotente
# - desacoplado

# ejemplos:

# profile_detected
# profile_updated
# ws_connected
# ws_disconnected
# heartbeat_received
# watchdog_alert
# reward_generated
# token_burned
# recovery_started
# recovery_finished
