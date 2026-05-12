# bitacora de decisiones - roxymaster

## formato
`fecha - decision: descripcion. razon: motivo. impacto: efecto.`

---

2026-05-06 - decision: separar tokenomics en _core y _ext. razon: tokenomics_core.py superaba 400 lineas. impacto: modulo partido, tasks.py actualizado.

2026-05-07 - decision: cambiar import en orchestrator de from ws_manager import ... a from pcmaster.scripts.ws_manager import .... razon: error de modulo no encontrado. impacto: imports explicitos con ruta completa.

2026-05-10 - decision: corregir referencia a usuario_id en lugar de pedido_id al insertar asignaciones. razon: _test_vigilante_imports.py fallaba. impacto: se cambio a f"where pedido_id = ?".

2026-05-10 - decision: eliminar import de obtener_pcbot_de_usuario en pedidos_vigilante.py. razon: funcion no existe en ws_manager, causaba import error. impacto: import simplificado.

2026-05-10 - decision: mapear pcbot_id con usuario_id para enviar comandos. razon: ws_manager.enviar_comando_al_pcbot requiere usuario_id. impacto: se creo _obtener_usuario_por_pcbot() que consulta usuarios por pcbot_id.

2026-05-10 - decision: implementar modulo vigilante de pedidos. archivos: pedidos_vigilante.py (logica principal), db_pedidos_vigilante.py (tabla pedido_asignaciones). impacto: server.py modificado con 2 lineas (import + tarea). sin cambios en archivos grandes existentes (orchestrator, db, api_pedidos, ws_manager).

2026-05-11 - decision: fix busqueda heartbeat perfiles - se accede a ws_manager._conexiones_por_pcbot directamente. razon: no habia getter publico para heartbeat almacenado. impacto: import directo del dict interno con try/except.

2026-05-11 - decision: servidor rearrancado con exito, vigilante activo (confirmado en logs: "vigilante de pedidos iniciado, intervalo=30s"). estado: sistema sano.

2026-05-11 - decision: cambiar columna `fecha_inicio` por `fecha_creacion` en consulta sql del vigilante. razon: la tabla pedidos no tiene columna `fecha_inicio`, tiene `fecha_creacion`. impacto: consulta corregida para usar fecha_creacion como referencia para calcular tiempo restante.

2026-05-11 - decision: corregir import en server.py para que no falle al iniciar. razon: import directo de monitorear_pedidos desde pedidos_vigilante en lugar de desde tasks. impacto: se agregaron los imports correctos y se quitaron los anteriores erroneos.

2026-05-11 - decision: cambiar estrategia de arranque - usar python directo en lugar de Start-Process con rutas relativas. razon: Start-Process con pipenv fallaba silenciosamente. impacto: servidor arranca correctamente con `python pcmaster/scripts/server.py`.