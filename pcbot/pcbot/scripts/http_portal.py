"""
roxymaster v8.3 - http portal (pcbot)
servidor http local que sirve el portal.html y api para el pcbot.
puerto por defecto: 8087
incluye endpoint /api/modo para cambiar entre uso_personal y pidiendo_ordenes.
"""

import json
import logging
import os
import socket
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from config_loader import DATA_DIR

logger = logging.getLogger(__name__)

PORTAL_PORT = 8087
PCBOT_DIR = Path(__file__).parent.parent
PORTAL_FILE = PCBOT_DIR / "portal.html"
if not PORTAL_FILE.is_file():
    PORTAL_FILE = Path(DATA_DIR) / "portal.html"

MODO_DEFAULT = "pidiendo_ordenes"


class PortalHandler(SimpleHTTPRequestHandler):
    """
    handler http para el portal del pcbot.
    sirve portal.html + api rest local.
    los componentes (pm, ws, te, st) se inyectan via atributos de clase.
    """

    # atributos de clase inyectados por PortalServer
    profile_manager = None
    ws_client = None
    token_engine = None
    state_tracker = None

    def log_message(self, format, *args):
        logger.debug(f"http {self.client_address[0]}: {format % args}")

    def do_OPTIONS(self):
        self._cors_headers()
        self.send_response(200)
        self.end_headers()

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")

    def _json_reply(self, status: int, data: dict):
        self.send_response(status)
        self._cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def _get_modo(self) -> str:
        """obtiene el modo actual desde ws_client."""
        if self.ws_client:
            return getattr(self.ws_client, "modo", MODO_DEFAULT)
        return MODO_DEFAULT

    def _set_modo(self, nuevo_modo: str):
        """cambia el modo en ws_client."""
        if self.ws_client and hasattr(self.ws_client, "cambiar_modo"):
            self.ws_client.cambiar_modo(nuevo_modo)

    def do_GET(self):
        path = self.path.split("?")[0]

        # -- servir portal.html --
        if path in ("/", "/portal", "/portal.html", "/index.html"):
            try:
                content = PORTAL_FILE.read_text(encoding="utf-8")
                self.send_response(200)
                self._cors_headers()
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(content.encode())
            except FileNotFoundError:
                self._json_reply(404, {"error": "portal.html no encontrado"})
            return

        pm = self.profile_manager
        te = self.token_engine
        st = self.state_tracker
        ws = self.ws_client

        # -- api: dashboard local --
        if path == "/api/dashboard":
            all_states = pm.get_all_states() if pm else {"counts": {"total": 0, "active": 0, "inactive": 0, "hung": 0}}
            counts = all_states.get("counts", {})
            server_ok = ws and ws.connected
            return self._json_reply(200, {
                "server_ok": server_ok,
                "pcbots_connected": 1 if server_ok else 0,
                "profiles_total": counts.get("total", 0),
                "profiles_active": counts.get("active", 0),
                "profiles_inactive": counts.get("inactive", 0),
                "profiles_hung": counts.get("hung", 0),
                "urls_viewing": counts.get("active", 0),
                "last_heartbeat": ws.last_heartbeat if ws else 0,
                "mis_kbt": te.total() if te else 0,
                "mi_uptime": self._get_uptime(),
                "modo": self._get_modo(),
            })

        # -- api: profiles --
        if path == "/api/profiles":
            all_states = pm.get_all_states() if pm else {"active": [], "inactive": [], "hung": [], "counts": {}}
            return self._json_reply(200, {
                "profiles": all_states.get("active", []) + all_states.get("inactive", []) + all_states.get("hung", []),
                "counts": all_states.get("counts", {}),
            })

        # -- api: tokens --
        if path == "/api/tokens":
            return self._json_reply(200, {
                "total": te.total() if te else 0,
                "generados": te.kbt_generados if te else 0,
                "comprados": te.kbt_comprados if te else 0,
                "historial_reciente": te.historial[-10:] if te else [],
            })

        # -- api: config del pcmaster (para portal.html) --
        if path == "/api/pcmaster_config":
            from config_loader import PCMASTER_HOST, PCMASTER_HTTP_PORT, PCMASTER_WS_PORT
            return self._json_reply(200, {
                "pcmaster_api": f"http://{PCMASTER_HOST}:{PCMASTER_HTTP_PORT}/api",
                "pcmaster_ws": f"ws://{PCMASTER_HOST}:{PCMASTER_WS_PORT}",
            })

        # -- api: estado (tracker) --
        if path == "/api/estado":
            progress = st.get_all_progress() if st else {}
            return self._json_reply(200, {
                "tracker": progress,
                "profiles_count": len(pm.profiles) if pm else 0,
                "ws_connected": ws.connected if ws else False,
                "modo": self._get_modo(),
            })

        # -- api: modo (GET) --
        if path == "/api/modo":
            return self._json_reply(200, {
                "modo": self._get_modo(),
            })

        # -- 404 --
        self._json_reply(404, {"error": "Not found", "path": path})

    def do_POST(self):
        path = self.path.split("?")[0]
        body = self._read_body()

        # -- login (solo retorna info local, no autentica contra pcmaster) --
        if path == "/api/login":
            email = body.get("email", "").strip()
            password = body.get("password", "")
            if email and password:
                return self._json_reply(200, {
                    "session_id": email.replace("@", "_").replace(".", "_")[:12],
                    "role": "user",
                    "pc_info": {
                        "hostname": socket.gethostname(),
                        "ip": self._local_ip(),
                    }
                })
            return self._json_reply(401, {"error": "Credenciales requeridas"})

        # -- logout --
        if path == "/api/logout":
            return self._json_reply(200, {"ok": True})

        # -- recargar perfiles desde roxybrowser --
        if path == "/api/recargar_perfiles":
            if self.profile_manager and self.profile_manager.api:
                profiles = self.profile_manager.api.get_profiles()
                self.profile_manager.register_profiles(profiles)
                return self._json_reply(200, {"ok": True, "count": len(profiles)})
            return self._json_reply(500, {"error": "profile_manager o su api no disponible"})

        # -- cambiar modo (POST) --
        if path == "/api/modo":
            nuevo_modo = body.get("modo", "").strip()
            if nuevo_modo in ("pidiendo_ordenes", "uso_personal"):
                self._set_modo(nuevo_modo)
                return self._json_reply(200, {"ok": True, "modo": nuevo_modo})
            return self._json_reply(400, {"error": "modo invalido. usar: pidiendo_ordenes o uso_personal"})

        self._json_reply(404, {"error": "Not found"})

    @staticmethod
    def _local_ip():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    @staticmethod
    def _get_uptime():
        try:
            import psutil
            boot = psutil.boot_time()
            uptime = time.time() - boot
            h = int(uptime // 3600)
            m = int((uptime % 3600) // 60)
            return f"{h}h {m}m"
        except Exception:
            return "N/A"


class PortalServer:
    """
    servidor http del portal pcbot.
    inyecta componentes via atributos de clase en PortalHandler.
    """

    def __init__(self, profile_manager=None, ws_client=None,
                 token_engine=None, state_tracker=None):
        self.profile_manager = profile_manager
        self.ws_client = ws_client
        self.token_engine = token_engine
        self.state_tracker = state_tracker
        self.server = None

    def _inject_components(self):
        """inyecta componentes como atributos de clase en PortalHandler."""
        PortalHandler.profile_manager = self.profile_manager
        PortalHandler.ws_client = self.ws_client
        PortalHandler.token_engine = self.token_engine
        PortalHandler.state_tracker = self.state_tracker

    def start(self, port: int = None):
        port = port or PORTAL_PORT
        self._inject_components()
        self.server = HTTPServer(
            ("0.0.0.0", port),
            PortalHandler
        )
        logger.info(f"portal pcbot iniciado en http://{self._local_ip()}:{port}")
        print(f"\n  portal pcbot -> http://127.0.0.1:{port}\n")
        self.server.serve_forever()

    def stop(self):
        if self.server:
            self.server.shutdown()
        logger.info("portal pcbot detenido")

    @staticmethod
    def _local_ip():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"