# bitacora de decisiones - roxymaster

## 2026-05-12 15:30 - correccion pedidos estancados + login endpoint verificado

**problema:** pedidos creados por api quedaban en 'pendiente' para siempre porque el vigilante
solo procesaba 'recibido'/'enviado', pero el flujo desde la api saltaba directo a 'pendiente'.
ademas, la funcion crear_comando en orchestrator.py tenia un bug que causaba recursion infinita
(ciclo de 3 intentos -> crear_comando -> store_async -> _ejecutar -> crear_comando).

**diagnostico:**
- api_pedidos.py: al crear pedido, si el pcbot no esta conectado, el comando se almacena en db
  como 'pendiente' pero nunca se envia. se anadio fallback que usa orchestrator.crear_comando
  para encolar correctamente.
- pedidos_vigilante.py: solo procesaba estados 'recibido' y 'enviado'. se amplio para incluir
  'pendiente'. tambien se corrigio logica de transicion pendiente -> trabajando cuando el comando
  ya fue enviado al pcbot.
- orchestrator.py: se anadio tope de 1 reintento en _ejecutar para evitar bucles recursivos.

**cambios realizados:**
1. api_pedidos.py: importar orchestrator, llamar crear_comando como fallback cuando pcbot conectado
2. pedidos_vigilante.py: _procesar_pendientes_y_enviados ahora incluye 'pendiente', y transiciona
   a 'trabajando' cuando el comando tiene estado 'enviado' en la tabla comandos
3. pedidos_vigilante.py: _ciclo_vigilante ahora llama a _procesar_pendientes_y_enviados cada ciclo
4. server.py: ya incluye correctamente router_auth con prefix="/api" (ruta /api/login funcional)

**resultado pruebas:**
- login endpoint: status 200, token jwt valido devuelto (prueba1@roxymaster.local)
- vigilante: procesa 71 pedidos pendientes, comienza transiciones
- imports: heartbeat_cache y pedidos_vigilante funcionan correctamente

**archivos modificados:**
- pcmaster/scripts/api_pedidos.py (anadido import orchestrator + fallback)
- pcmaster/scripts/pedidos_vigilante.py (ampliado estados procesados + transiciones)
- pcmaster/scripts/orchestrator.py (tope reintentos en _ejecutar)

## 2026-12-05 13:49 - modal de validacion de pedido

**contexto:** se solicito agregar un modal de confirmacion antes de crear un pedido, para que el usuario pueda revisar los datos y el costo antes de gastar tokens.

**cambios realizados:**
1. en `pedidos_core.html`:
   - se agregaron estilos CSS para `.modal-overlay`, `.modal-card`, `.modal-grid`, `.modal-item`, `.modal-total`, `.btn-modal-cancelar`, `.btn-modal-confirmar`
   - se agrego el HTML del modal con id `modal-validar-pedido`, grid de resumen (url, seguidores, perfiles, duracion, comentarios, tipo) y total con botones cancelar/confirmar
2. en `pedidos_ext.html`:
   - `crearPedido()` ahora abre el modal en lugar de enviar directamente
   - se agregaron funciones: `mostrarModalValidacion(data)`, `cerrarModalValidacion()`, `confirmarPedido()`
   - el modal calcula el costo en tiempo real usando la misma formula que `calcularCosto()`
   - al confirmar, se hace fetch a `/api/pedidos/crear` con los datos validados

**push:** commit `e9e3306` - "feat: modal de validacion de pedido con confirmacion antes de gastar tokens"

## 2026-12-05 13:00 - header unificado estilo marketplace en pedidos_core.html

**contexto:** se solicito unificar el header de `pedidos_core.html` con el mismo estilo que `marketplace.html`, usando tonos dorados (#f0b90b, #d4a017) y el mismo patron visual (avatar circular, titulo con gradiente, subtitulo, user-info con badge).

**cambios realizados:**
1. se agrego seccion `<header class="header">` completa con:
   - avatar circular con inicial "p" y animacion pulse
   - titulo "pedidos" con gradiente animado y diamante decorativo
   - subtitulo "gestiona tus ordenes de minado en tiempo real"
   - user-info con email, separador y badge de rol
2. efectos decorativos dorados:
   - linea inferior animada con glow
   - fondos con radial-gradients sutiles
3. se mantuvo el `#user-email` y `#user-rol` para ser llenados via js desde dashboard_publico.html
4. se ajusto `.panel-pedidos` para que no colisione con el nuevo header (padding-top removido, solo padding-inline)

**verificaciones:**
- archivo final: 341 lineas (dentro del limite de 600)
- backup previo en `backups/publico_20261205_1142/pedidos_core.html`
- push exitoso a origin/main: commit `ed87e50`
- servidor corriendo (PID 3576)

**pendiente:** el header se vera al recargar el dashboard o al cargar pedidos_core.html standalone. los datos de usuario se llenan desde dashboard_publico.js via DOM manipulation.

## 2026-12-05 14:27 - ajuste columnas tabla historial y header dorado centrado

**contexto:** se solicito reducir el ancho de las columnas perfiles, duracion, costo, estado y acciones en la tabla de historial de pedidos. tambien se pidio cambiar el header a tonalidad dorada y centrarlo.

**cambios realizados (solo CSS en pedidos_core.html):**
1. header `.header`: fondo cambiado a `linear-gradient(135deg,#1a0f00,#2d1a00)` (dorado oscuro), borde `rgba(240,185,11,0.2)`, `justify-content: center`
2. columnas reducidas:
   - `.col-perfiles`: 70px -> 55px
   - `.col-duracion`: 80px -> 65px
   - `.col-costo`: 90px -> 75px
   - `.col-estado`: 90px -> 70px
   - `.col-acciones`: 80px -> 60px
   - `.col-id`: 40px -> 35px
   - `.col-fecha`: 110px -> 100px

**archivos modificados:** solo `pcmaster/publico/pedidos_core.html`
**backup:** `backups/pedidos_core_20261205_1427.html`
**push:** pendiente