"""
roxymaster v8.3 - http portal server (pcbot)
servidor http asyncio en puerto 8087.
sirve # eliminado, api local de estado, dashboard y proxy a pcmaster.
todo en minusculas, utf-8 sin bom.
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger(__name__)

try:
    from aiohttp import web, ClientSession, ClientTimeout
except ImportError:
    web = None
    ClientSession = None
    ClientTimeout = None
    logger.error("aiohttp no instalado. pip install aiohttp")

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
PORTAL_HTML = BASE_DIR / "# eliminado"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class PortalServer:
    """servidor http local con api de estado y proxy a pcmaster."""

    def __init__(self, profile_manager=None, ws_client=None, token_engine=None, state_tracker=None):
        self.pm = profile_manager
        self.ws = ws_client
        self.te = token_engine
        self.st = state_tracker
        self._app = None
        self._runner = None
        self._site = None
        self._http_session = None
        self._port = 8087
        self._pcmaster_api = "http://100.111.179.65:8086/api"

    def _build_state(self) -> dict:
        """construye estado local para respuestas api."""
        pm_state = self.pm.get_all_states() if self.pm else {}
        st_status = self.st.get_all_status() if self.st else {}
        te_stats = self.te.get_stats() if self.te else {}
        ws_estado = self.ws.get_estado() if self.ws else {}
        uptime = int(time.time() - getattr(self, "_start", time.time()))
        return {
            "pcbot_id": os.environ.get("COMPUTERNAME", "pcbot"),
            "username": os.environ.get("USERNAME", "cyber"),
            "ip_local": getattr(self.pm, "ip_local", "127.0.0.1") if self.pm else "127.0.0.1",
            "modo": (self.ws.modo if self.ws else "pidiendo_ordenes"),
            "conectado": ws_estado.get("conectado", False),
            "uptime": f"{uptime // 3600}h {(uptime % 3600) // 60}m",
            "perfiles": {
                "counts": pm_state.get("counts", {}),
                "states": pm_state.get("states", {}),
                "timers": st_status,
            },
            "tokens": te_stats,
            "websocket": ws_estado,
        }

    async def _get_http_session(self):
        if self._http_session is None or self._http_session.closed:
            self._http_session = ClientSession(timeout=ClientTimeout(total=30))
        return self._http_session

    async def _proxy_to_pcmaster(self, request, endpoint_path):
        """proxy api request a pcmaster."""
        session = await self._get_http_session()
        url = f"{self._pcmaster_api}{endpoint_path}"
        headers = {}
        for h in ("Content-Type", "Authorization", "Cookie"):
            if h in request.headers:
                headers[h] = request.headers[h]
        try:
            body = await request.read()
            async with session.request(
                method=request.method, url=url, headers=headers,
                data=body if body else None, params=request.query,
            ) as resp:
                resp_body = await resp.read()
                return web.Response(
                    status=resp.status, body=resp_body,
                    content_type=resp.content_type or "application/json",
                )
        except asyncio.TimeoutError:
            return web.json_response({"error": "timeout"}, status=504)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=502)

    def _routes(self):
        if web is None:
            return []
        return [
            web.get("/", self._index),
            web.get("/# eliminado", self._index),
            web.get("/static/{filename:.*}", self._static),
            web.get("/api/estado", self._api_estado),
            web.get("/api/dashboard", self._api_dashboard),
            web.get("/api/profiles", self._api_profiles),
            web.post("/api/modo", self._api_modo),
            web.post("/api/recargar_perfiles", self._api_recargar),
            web.get("/api/tokens", self._api_tokens),
            web.route("*", "/api/{path:.*}", self._proxy),
        ]

    async def _index(self, request):
        if PORTAL_HTML.exists():
            return web.FileResponse(str(PORTAL_HTML))
        return web.Response(text="portal no encontrado", status=404)

    async def _static(self, request):
        filename = request.match_info.get("filename", "")
        filepath = (STATIC_DIR / filename).resolve()
        try:
            if not str(filepath).startswith(str(STATIC_DIR.resolve())):
                return web.Response(text="acceso denegado", status=403)
        except Exception:
            return web.Response(text="ruta invalida", status=400)
        if filepath.exists() and filepath.is_file():
            return web.FileResponse(str(filepath))
        return web.Response(text="archivo no encontrado", status=404)

    async def _api_estado(self, request):
        return web.json_response(self._build_state())

    async def _api_dashboard(self, request):
        """devuelve dashboard combinado (local + pcmaster)."""
        local = self._build_state()
        pcmaster_data = {}
        session = await self._get_http_session()
        hdrs = {}
        if "Authorization" in request.headers:
            hdrs["Authorization"] = request.headers["Authorization"]
        if "Cookie" in request.headers:
            hdrs["Cookie"] = request.headers["Cookie"]
        try:
            async with session.get(f"{self._pcmaster_api}/dashboard", timeout=10, headers=hdrs) as resp:
                if resp.status == 200:
                    pcmaster_data = await resp.json()
        except Exception:
            pass

        return web.json_response({
            "server_ok": bool(pcmaster_data),
            "balance": pcmaster_data.get("balance", local.get("tokens", {}).get("total_earned", 0)),
            "kbt_hoy": local.get("tokens", {}).get("total_earned", 0),
            "perfiles_activos": local.get("perfiles", {}).get("counts", {}).get("active", 0),
            "modo": local["modo"],
            "uptime": local["uptime"],
            "conectado": local["conectado"],
            "websocket": local.get("websocket", {}),
            "perfiles": local.get("perfiles", {}),
            "tokens": local.get("tokens", {}),
        })

    async def _api_profiles(self, request):
        """devuelve lista de perfiles con progreso."""
        profiles = []
        st_status = self.st.get_all_status() if self.st else {}
        counts = self.pm.get_all_states()["counts"] if self.pm else {}
        for pid, p in (self.pm.profiles.items() if self.pm else {}):
            timer_info = st_status.get(pid, {})
            profiles.append({
                "perfil_id": pid,
                "nombre": p.name or pid,
                "tipo": p.type,
                "estado": p.state.name.lower(),
                "url": p.current_url,
                "duracion_min": p.duracion_min,
                "progreso_pct": timer_info.get("progress_pct", 0),
                "elapsed_seconds": timer_info.get("elapsed_seconds", 0),
                "remaining_seconds": timer_info.get("remaining_seconds", 0),
            })
        return web.json_response({"profiles": profiles, "counts": counts})

    async def _api_modo(self, request):
        """cambia modo de operacion."""
        try:
            data = await request.json()
            modo = data.get("modo", "pidiendo_ordenes")
            if modo not in ("pidiendo_ordenes", "uso_personal"):
                return web.json_response({"error": "modo invalido"}, status=400)
            if self.ws:
                self.ws.cambiar_modo(modo)
            return web.json_response({"ok": True, "modo": modo})
        except Exception as e:
            return web.json_response({"error": str(e)}, status=400)

    async def _api_recargar(self, request):
        """recarga perfiles desde roxybrowser api."""
        if not self.pm:
            return web.json_response({"ok": False, "error": "no hay profile manager"})
        try:
            roxy = getattr(self.pm, "roxy", None)
            if roxy:
                perfiles = roxy.get_profiles()
                if perfiles:
                    self.pm.register_profiles(perfiles)
                    return web.json_response({"ok": True, "count": len(perfiles)})
            return web.json_response({"ok": False, "error": "no se pudieron recargar"})
        except Exception as e:
            return web.json_response({"ok": False, "error": str(e)})

    async def _api_tokens(self, request):
        """devuelve estadisticas de tokens."""
        if not self.te:
            return web.json_response({"kbt": 0, "history": []})
        return web.json_response({
            "kbt": self.te.get_balance(),
            "pending_sync": self.te.get_pending_sync(),
            "history": self.te.get_history(20),
        })

    async def _proxy(self, request):
        path = request.match_info.get("path", "")
        return await self._proxy_to_pcmaster(request, "/" + path)

    # ---------------------------------------------------------------
    # start / stop
    # ---------------------------------------------------------------
    def start(self, port: int = 8087):
        """inicia servidor http (bloqueante, pero compatible con async)."""
        if web is None:
            logger.error("aiohttp no disponible")
            return
        self._port = port
        self._start = time.time()
        self._app = web.Application()
        for route in self._routes():
            self._app.router.add_route(route.method, route.path, route.handler)
        self._runner = web.AppRunner(self._app)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._runner.setup())
        self._site = web.TCPSite(self._runner, "0.0.0.0", port)
        loop.run_until_complete(self._site.start())
        logger.info(f"portal http iniciado en http://0.0.0.0:{port}")

    async def start_async(self, port: int = 8087):
        """inicia servidor http (async, no bloqueante)."""
        if web is None:
            logger.error("aiohttp no disponible")
            return
        self._port = port
        self._start = time.time()
        self._app = web.Application()
        for route in self._routes():
            self._app.router.add_route(route.method, route.path, route.handler)
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "0.0.0.0", port)
        await self._site.start()
        logger.info(f"portal http async iniciado en http://0.0.0.0:{port}")

    async def stop_async(self):
        """detiene servidor http (async)."""
        if self._http_session and not self._http_session.closed:
            try:
                await self._http_session.close()
            except Exception:
                pass
        if self._runner:
            try:
                await self._runner.cleanup()
            except Exception:
                pass
        logger.info("portal http detenido")

    def stop(self):
        """detiene servidor http (sync wrapper)."""
        if self._http_session and not self._http_session.closed:
            try:
                asyncio.ensure_future(self._http_session.close())
            except Exception:
                pass
        if self._runner:
            try:
                asyncio.ensure_future(self._runner.cleanup())
            except Exception:
                pass
        logger.info("portal http detenido (sync)")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    portal = PortalServer()
    import asyncio
    asyncio.run(portal.start_async(8087))
    try:
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        portal.stop()
