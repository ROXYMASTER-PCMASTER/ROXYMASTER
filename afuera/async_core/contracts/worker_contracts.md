# contratos async

# cada worker debe:

# - recibir eventos
# - procesar async
# - responder timeout
# - emitir resultado
# - registrar errores
# - no bloquear loop

# prohibido:
# - time.sleep
# - sqlite bloqueante
# - requests sync
# - loops infinitos sin control
