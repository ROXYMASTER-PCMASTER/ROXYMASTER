"""
roxymaster v8.3 - roxybrowser api (pcbot)
navegacion via cdp websocket (page.navigate) en vez del endpoint roto.
metodos: abrir, cerrar, redirigir, comentar, obtener url, ejecutar js.
"""
import logging
import requests
import json
import asyncio
import os
import time

logger = logging.getLogger(__name__)

websockets_available = False
try:
    import websockets
    websockets_available = True
except ImportError:
    logger.warning("websockets no instalado, se usara solo metodo http")


def find_workspace_id() -> str:
    appdata_roxy = os.path.join(os.environ.get("APPDATA", ""), "RoxyBrowser", "browser-cache")
    if not os.path.isdir(appdata_roxy):
        return ""
    try:
        for item in os.listdir(appdata_roxy):
            item_path = os.path.join(appdata_roxy, item)
            if os.path.isdir(item_path) and len(item) >= 20:
                return item
    except Exception:
        pass
    return ""


class RoxyBrowserAPI:
    def __init__(self, api_url: str = "http://127.0.0.1:50000", workspace_id: str = "", api_key: str = ""):
        self.base = api_url.rstrip("/")
        self.timeout = 5
        self._workspace_id = workspace_id
        self._api_key = api_key
        # cache de http_port por profile_id para evitar re-abrir
        self._http_ports: dict[str, str] = {}

    def set_api_key(self, api_key: str):
        self._api_key = api_key
        logger.info("apikey de roxybrowser configurada")

    def set_workspace_id(self, workspace_id: str):
        self._workspace_id = workspace_id
        logger.info(f"workspace_id configurado: {workspace_id}")

    def get_api_key(self) -> str:
        return self._api_key

    def _headers(self) -> dict:
        return {"Token": self._api_key}

    def _request(self, method: str, path: str, body: dict = None) -> dict | None:
        """hace request a la api de roxybrowser y retorna json."""
        url = f"{self.base}{path}"
        headers = self._headers()
        if body:
            headers["Content-Type"] = "application/json"
        try:
            if method == "GET":
                resp = requests.get(url, headers=headers, timeout=self.timeout)
            else:
                resp = requests.post(url, headers=headers, json=body, timeout=self.timeout)
            if resp.status_code != 200:
                logger.warning(f"request {method} {path} -> status {resp.status_code}: {resp.text[:200]}")
                return None
            return resp.json()
        except requests.exceptions.ConnectionError as e:
            logger.error(f"error de conexion a {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"error en request {method} {path}: {e}")
            return None

    def _abrir_perfil(self, profile_id: str) -> dict | None:
        """abre perfil o devuelve datos si ya esta abierto."""
        ws_id = self.get_workspace_id()
        if not ws_id:
            logger.error("no se pudo obtener workspace_id")
            return None
        result = self._request("POST", "/browser/open", {"dirId": profile_id, "workspaceId": ws_id})
        if result and result.get("code") == 0:
            data = result.get("data", {})
            http_port = data.get("http", "")
            if http_port:
                self._http_ports[profile_id] = http_port
            return data
        return None

    def get_workspace_id(self) -> int | None:
        """obtiene el workspace id desde la api."""
        if self._workspace_id and str(self._workspace_id).isdigit():
            return int(self._workspace_id)
        result = self._request("GET", "/browser/workspace")
        if result and result.get("code") == 0:
            rows = result.get("data", {}).get("rows", [])
            if rows:
                ws_id = rows[0].get("id")
                if ws_id:
                    self._workspace_id = str(ws_id)
                    return ws_id
        return None

    def get_profiles(self, workspace_id: int = None) -> list:
        if workspace_id is None:
            ws_id = self.get_workspace_id()
            if not ws_id:
                return []
            workspace_id = ws_id
        result = self._request("GET", f"/browser/list?workspaceId={workspace_id}")
        if result and result.get("code") == 0:
            rows = result.get("data", {}).get("rows", [])
            return [
                {
                    "id": row.get("dirId", ""),
                    "dirId": row.get("dirId", ""),
                    "windowName": row.get("windowName", ""),
                    "nombre": row.get("windowName", ""),
                    "name": row.get("windowName", ""),
                    "hash_interno": row.get("dirId", ""),
                    "hash": row.get("dirId", ""),
                }
                for row in rows
            ]
        return []

    def get_profiles_detallados(self) -> list:
        perfiles = self.get_profiles()
        result = []
        for p in perfiles:
            result.append({
                "id": p.get("dirId", ""),
                "name": p.get("windowName", ""),
                "hash_interno": p.get("dirId", ""),
                "workspace": str(self.get_workspace_id() or ""),
                "status": "active" if p.get("dirId") else "unknown",
            })
        return result

    def get_workspaces(self, api_key: str = "") -> list:
        if api_key:
            self.set_api_key(api_key)
        ws_id = self.get_workspace_id()
        if ws_id:
            return [{"workspace_id": str(ws_id), "nombre": "default"}]
        return []

    def ping(self) -> bool:
        return self.get_workspace_id() is not None

    def get_version(self) -> str:
        result = self._request("GET", "/browser/workspace")
        if result and result.get("code") == 0:
            rows = result.get("data", {}).get("rows", [])
            if rows:
                return str(rows[0].get("version", "unknown"))
        return "unknown"

    def _obtener_page_ws(self, http_port: str) -> str | None:
        """obtiene el websocket url de la primera pagina del cdp."""
        try:
            resp = requests.get(f"http://{http_port}/json/list", timeout=3)
            if resp.status_code != 200:
                return None
            tabs = resp.json()
            for tab in tabs:
                if tab.get("type") == "page":
                    return tab.get("webSocketDebuggerUrl")
            # si no hay page, devuelve el primero
            if tabs:
                return tabs[0].get("webSocketDebuggerUrl")
        except Exception as e:
            logger.error(f"error obteniendo page ws de {http_port}: {e}")
        return None

    def navigate(self, profile_id: str, url: str) -> bool:
        """navega a url usando cdp websocket page.navigate.
        si websockets no esta disponible, usa put /json/new?url="""
        logger.info(f"[navigate] profile_id={profile_id}, url={url}")

        # 1. abrir perfil para obtener http_port
        data = self._abrir_perfil(profile_id)
        if not data:
            logger.error(f"[navigate] no se pudo abrir perfil {profile_id}")
            return False

        http_port = data.get("http", "") or self._http_ports.get(profile_id, "")
        if not http_port:
            logger.error(f"[navigate] no hay http_port para {profile_id}")
            return False

        logger.info(f"[navigate] perfil abierto, http_port={http_port}")

        # 2. navegar
        if not websockets_available:
            return self._navigate_via_put(http_port, url)

        try:
            # detectar si ya hay un loop corriendo
            loop = asyncio.get_running_loop()
            # ya estamos dentro de un loop -> usar un future con navigate_async
            future = asyncio.run_coroutine_threadsafe(
                self.navigate_async(profile_id, url), loop
            )
            return future.result(timeout=12)
        except RuntimeError:
            # no hay loop -> crear uno nuevo con metodo sync
            return self._navigate_via_ws_sync(http_port, url)

    def _navigate_via_put(self, http_port: str, url: str) -> bool:
        """abre nueva pestana con put /json/new?url="""
        try:
            resp = requests.put(f"http://{http_port}/json/new?{url}", timeout=5)
            ok = resp.status_code == 200
            if ok:
                logger.info(f"[navigate] put /json/new ok, url={url[:60]}")
            else:
                logger.warning(f"[navigate] put /json/new -> status={resp.status_code}")
            return ok
        except Exception as e:
            logger.error(f"[navigate] error en put /json/new: {e}")
            return False

    def _navigate_via_ws_sync(self, http_port: str, url: str) -> bool:
        """navega via ws en un loop nuevo (para contexto sin asyncio)."""
        page_ws = self._obtener_page_ws(http_port)
        if not page_ws:
            logger.warning(f"[navigate] no se encontro page ws, usando metodo put")
            return self._navigate_via_put(http_port, url)

        try:
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(
                    self._do_navigate_ws(page_ws, url)
                )
                return result
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"[navigate] error en ws sync yendo a {url[:60]}: {e}")
            return self._navigate_via_put(http_port, url)

    async def navigate_async(self, profile_id: str, url: str) -> bool:
        """version async de navigate (para usar desde contextos async)."""
        logger.info(f"[navigate_async] profile_id={profile_id[:20]}..., url={url[:60]}...")
        logger.info(f"[navigate_async] workspace_id={self._workspace_id}, api_key={'set' if self._api_key else 'not set'}")

        data = self._abrir_perfil(profile_id)
        if not data:
            logger.error(f"[navigate_async] no se pudo abrir perfil {profile_id[:20]}...")
            return False

        http_port = data.get("http", "") or self._http_ports.get(profile_id, "")
        logger.info(f"[navigate_async] data recibida: http={http_port}, ws={data.get('ws', 'no')[:30]}")
        if not http_port:
            logger.error(f"[navigate_async] no hay http_port para {profile_id[:20]}...")
            return False

        if not websockets_available:
            logger.info(f"[navigate_async] websockets no disponible, usando put")
            return self._navigate_via_put(http_port, url)

        page_ws = self._obtener_page_ws(http_port)
        logger.info(f"[navigate_async] page_ws obtenido: {page_ws[:40] if page_ws else 'none'}")
        if not page_ws:
            logger.warning(f"[navigate_async] no se encontro page ws, usando put")
            return self._navigate_via_put(http_port, url)

        try:
            resultado = await self._do_navigate_ws(page_ws, url)
            logger.info(f"[navigate_async] _do_navigate_ws result: {resultado}")
            return resultado
        except Exception as e:
            logger.error(f"[navigate_async] error en ws yendo a {url[:60]}: {e}")
            logger.info(f"[navigate_async] fallback a put /json/new")
            return self._navigate_via_put(http_port, url)

    async def _do_navigate_ws(self, page_ws: str, url: str) -> bool:
        """ejecuta page.navigate via websocket. debe llamarse desde un contexto async."""
        import websockets

        async with websockets.connect(page_ws, ping_interval=None, close_timeout=5) as ws:
            cmd = json.dumps({"id": 1, "method": "Page.navigate", "params": {"url": url}})
            await ws.send(cmd)
            resp = await asyncio.wait_for(ws.recv(), timeout=8)
            j = json.loads(resp)
            if "result" in j and "error" not in j:
                frame_id = j["result"].get("frameId", "")
                logger.info(f"[navigate] page.navigate ok, frame_id={frame_id[:20]} url={url[:60]}")
                return True
            else:
                error_msg = j.get("error", {}).get("message", str(j)[:100])
                logger.error(f"[navigate] page.navigate error: {error_msg}")
                return False

    def get_cdp_ws(self, profile_id: str) -> str:
        """obtiene el websocket url cdp de un perfil.
        retorna la url del page websocket o cadena vacia si no se puede."""
        http_port = self._http_ports.get(profile_id, "")
        if not http_port:
            data = self._abrir_perfil(profile_id)
            if data:
                http_port = data.get("http", "") or ""
        if http_port:
            page_ws = self._obtener_page_ws(http_port)
            if page_ws:
                return page_ws
        return ""

    def close_profile(self, profile_id: str) -> bool:
        """cierra un perfil en roxybrowser."""
        result = self._request("POST", f"/browser/close", {"dirId": profile_id})
        if result and result.get("code") == 0:
            self._http_ports.pop(profile_id, None)
            logger.info(f"[close_profile] perfil {profile_id[:16]}... cerrado")
            return True
        logger.warning(f"[close_profile] fallo al cerrar perfil {profile_id[:16]}...")
        return False

    def get_profile_page_url(self, profile_id: str) -> str:
        """obtiene la url actual del perfil via cdp /json/list."""
        http_port = self._http_ports.get(profile_id, "")
        if not http_port:
            data = self._abrir_perfil(profile_id)
            if data:
                http_port = data.get("http", "") or ""
        if http_port:
            try:
                resp = requests.get(f"http://{http_port}/json/list", timeout=3)
                if resp.status_code == 200:
                    tabs = resp.json()
                    for tab in tabs:
                        if tab.get("type") == "page" and tab.get("url", "").startswith("http"):
                            return tab.get("url", "")
            except Exception:
                pass
        return ""

    def abrir_perfil(self, profile_id: str) -> bool:
        """abre un perfil en roxybrowser (alias publico)."""
        data = self._abrir_perfil(profile_id)
        if data:
            logger.info(f"[abrir_perfil] perfil {profile_id[:16]}... abierto")
            return True
        logger.warning(f"[abrir_perfil] fallo al abrir perfil {profile_id[:16]}...")
        return False

    def redirigir_a(self, profile_id: str, url: str) -> bool:
        """redirige un perfil a una url sin cerrarlo (alias publico)."""
        return self.navigate(profile_id, url)

    def redirigir_todos(self, perfiles: list | dict, url: str) -> dict:
        """redirige multiples perfiles a la misma url.
        acepta lista de ids o dict {id: nombre}."""
        resultados = {}
        if isinstance(perfiles, dict):
            ids = list(perfiles.keys())
        else:
            ids = list(perfiles)
        for pid in ids:
            ok = self.navigate(pid, url)
            resultados[pid[:16]] = "ok" if ok else "fallo"
            time.sleep(0.3)  # pausa entre navegaciones
        logger.info(f"[redirigir_todos] {sum(1 for v in resultados.values() if v=='ok')}/{len(resultados)} ok")
        return resultados

    def estado_perfil(self, profile_id: str) -> dict:
        """obtiene estado completo de un perfil."""
        url_actual = self.get_profile_page_url(profile_id)
        http_port = self._http_ports.get(profile_id, "")
        esta_abierto = bool(http_port) or self._abrir_perfil(profile_id) is not None
        return {
            "id": profile_id[:16],
            "url_actual": url_actual,
            "abierto": esta_abierto,
            "http_port": http_port,
        }

    async def comentar_en_pagina(self, profile_id: str, texto: str, selector: str = "") -> bool:
        """escribe un comentario en la pagina actual via cdp.
        si no se especifica selector, intenta rutinas comunes.
        usa runtime.evaluate para inyectar texto."""
        http_port = self._http_ports.get(profile_id, "")
        if not http_port:
            data = self._abrir_perfil(profile_id)
            if data:
                http_port = data.get("http", "") or ""
        if not http_port:
            logger.error(f"[comentar] no hay http_port para {profile_id[:16]}...")
            return False

        page_ws = self._obtener_page_ws(http_port)
        if not page_ws:
            logger.error(f"[comentar] no se encontro page ws para {profile_id[:16]}...")
            return False

        import websockets
        try:
            async with websockets.connect(page_ws, ping_interval=None, close_timeout=5) as ws:
                # 1. obtener elemento de comentarios
                if not selector:
                    # selectores comunes en kick.com
                    selectores = [
                        "textarea[data-testid='chat-input']",
                        "textarea.chat-input",
                        "div[contenteditable='true']",
                        "input[type='text']",
                        "textarea",
                    ]
                    js_code = f"""
                    (() => {{
                        const selectores = {json.dumps(selectores)};
                        for (const sel of selectores) {{
                            const el = document.querySelector(sel);
                            if (el) return sel;
                        }}
                        return null;
                    }})()
                    """
                    cmd = json.dumps({"id": 2, "method": "Runtime.evaluate", "params": {"expression": js_code, "returnByValue": True}})
                    await ws.send(cmd)
                    resp = await asyncio.wait_for(ws.recv(), timeout=5)
                    j = json.loads(resp)
                    resultado = j.get("result", {}).get("result", {}).get("value", "")
                    if resultado:
                        selector = resultado
                    else:
                        logger.warning(f"[comentar] no se encontro campo de texto en {profile_id[:16]}...")
                        return False

                # 2. hacer focus y escribir
                js_focus = f"""
                (() => {{
                    const el = document.querySelector('{selector}');
                    if (!el) return false;
                    el.focus();
                    el.value = {json.dumps(texto)};
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return true;
                }})()
                """
                cmd = json.dumps({"id": 3, "method": "Runtime.evaluate", "params": {"expression": js_focus, "returnByValue": True}})
                await ws.send(cmd)
                resp = await asyncio.wait_for(ws.recv(), timeout=5)
                j = json.loads(resp)
                escrito = j.get("result", {}).get("result", {}).get("value", False)
                if escrito:
                    logger.info(f"[comentar] texto escrito en {profile_id[:16]}... via {selector}")
                    return True
                else:
                    logger.warning(f"[comentar] no se pudo escribir en {profile_id[:16]}...")
                    return False
        except Exception as e:
            logger.error(f"[comentar] error: {e}")
            return False

    async def ejecutar_js(self, profile_id: str, js_code: str) -> dict:
        """ejecuta javascript en el perfil via cdp y retorna resultado."""
        http_port = self._http_ports.get(profile_id, "")
        if not http_port:
            data = self._abrir_perfil(profile_id)
            if data:
                http_port = data.get("http", "") or ""
        if not http_port:
            logger.error(f"[ejecutar_js] no hay http_port para {profile_id[:16]}...")
            return {"ok": False, "error": "no http_port"}

        page_ws = self._obtener_page_ws(http_port)
        if not page_ws:
            return {"ok": False, "error": "no page ws"}

        import websockets
        try:
            async with websockets.connect(page_ws, ping_interval=None, close_timeout=5) as ws:
                cmd = json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": js_code, "returnByValue": True, "awaitPromise": True}})
                await ws.send(cmd)
                resp = await asyncio.wait_for(ws.recv(), timeout=10)
                j = json.loads(resp)
                if "result" in j and j.get("id") == 1:
                    resultado = j["result"].get("result", {}).get("value", None)
                    return {"ok": True, "resultado": resultado}
                else:
                    return {"ok": False, "error": j.get("error", {}).get("message", str(j)[:200])}
        except Exception as e:
            logger.error(f"[ejecutar_js] error: {e}")
            return {"ok": False, "error": str(e)}