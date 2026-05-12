# bitacora - solucion navegacion roxybrowser via cdp websocket

## fecha
2026-10-05

## problema
los perfiles de roxybrowser no navegaban cuando pcbot enviaba el comando `asignar` desde pcmaster.

### sintomas
1. orchestrator_local._cmd_asignar retornaba `"ok": false, "error": "fallo al navegar"`
2. profile_manager.navigate_to llamaba a roxy.navigate() (sync) pero desde un contexto async
3. error oculto: `cannot run event loop while another loop is running` (deadlock asyncio)
4. el endpoint http `/api/browser/{id}/navigate` de roxybrowser devolvia error 404/403

### causa raiz
1. **deadlock asyncio**: profile_manager.navigate_to era async pero llamaba a roxy.navigate() que creaba su propio event loop. al estar dentro del loop de asyncio, python bloqueaba porque no permite loops anidados.
2. **endpoint rest roto**: el endpoint `POST /api/browser/{profile_id}/navigate` no funcionaba consistentemente. la api de roxybrowser tiene endpoints inestables para navegacion.
3. **ws_manager no involucrado**: el problema no era de websocket con pcmaster, sino de ejecucion local de la navegacion.

## solucion implementada

### 1. roxybrowser_api.py - nuevos metodos
se implemento navegacion via **cdp websocket** (chrome devtools protocol) en vez del endpoint rest:

- `navigate_async()` - version async que usa cdp page.navigate via websocket
- `navigate()` - version sync con deteccion automatica de loop asyncio
- `_do_navigate_ws()` - ejecuta el comando `Page.navigate` via websocket
- `_navigate_via_put()` - fallback usando `PUT /json/new?url` del cdp http
- fallback automatico: si ws falla, usa put http; si put falla, retorna false

### 2. profile_manager.py - correccion async
- `navigate_to()` cambiado de `roxy.navigate()` (sync) a `await roxy.navigate_async()` (async)
- esto elimina el deadlock de loops anidados

### 3. orchestrator_local.py - parseo nivel_comentarios
- `_parse_nivel_comentarios()` convierte string a entero: basico=0, normal=1, vip=2
- `_cmd_asignar()` ya usaba este metodo correctamente

## nuevos metodos agregados a roxybrowser_api.py

| metodo | descripcion |
|--------|-------------|
| `abrir_perfil(profile_id)` | abre un perfil en roxybrowser (bool) |
| `close_profile(profile_id)` | cierra un perfil (bool) |
| `navigate(profile_id, url)` | navega a url (sync, detecta loop) |
| `navigate_async(profile_id, url)` | navega a url (async) |
| `redirigir_a(profile_id, url)` | alias de navigate |
| `redirigir_todos(perfiles, url)` | navega multiples perfiles a misma url |
| `get_profile_page_url(profile_id)` | obtiene url actual del perfil |
| `estado_perfil(profile_id)` | estado completo (url, abierto, puerto) |
| `comentar_en_pagina(profile_id, texto)` | escribe texto en campo de comentarios |
| `ejecutar_js(profile_id, codigo)` | ejecuta javascript en el perfil |

## flujo de navegacion actual

```
pcmaster -> ws -> pcbot -> orchestrator._cmd_asignar
  -> profile_manager.navigate_to (async)
    -> roxy.navigate_async (abre perfil, obtiene http_port)
      -> obtiene page websocket via /json/list
        -> send page.navigate via ws
          -> si falla -> fallback put /json/new?url
```

## pruebas realizadas

1. navegacion cdp ws a kick.com/test -> 4 perfiles, todos ok
2. fallback put cuando ws falla -> funciona
3. redireccion a wafabot.com -> 4 perfiles, todos ok
4. cierre de perfiles -> 2 perfiles, ambos ok
5. nivel_comentarios normal/basico/vip -> conversion correcta
6. duracion_min y current_url -> se actualizan en perfil

## archivos modificados

| archivo | cambios |
|---------|---------|
| `scripts/api/roxybrowser_api.py` | + navegacion cdp ws, +comentar, +ejecutar_js, +estado, +redirigir_todos |
| `scripts/core/profile_manager.py` | navigate_to usa await roxy.navigate_async() en vez de roxy.navigate() |

## observaciones

- la api de roxybrowser en puerto 50000 solo sirve para abrir/cerrar perfiles
- la navegacion real debe hacerse via cdp websocket directamente al puerto http del perfil
- cada perfil al abrirse expone un puerto http (ej: 52193) que sirve json de depuracion
- el websocket se obtiene de `http://{http_port}/json/list` -> `webSocketDebuggerUrl`
- el comando `Page.navigate` se envia como `{"id":1,"method":"Page.navigate","params":{"url":"..."}}`
- la respuesta contiene un `frameId` que confirma la navegacion