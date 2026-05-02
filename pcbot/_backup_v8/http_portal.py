"""
ROXYMASTER v8.0 - HTTP PORTAL (PCBOT)
Servidor HTTP local que sirve el portal.html y API para el PCBOT.
Puerto por defecto: 8087
"""

import json
import logging
import os
import socket
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from pcbot.scripts.config_loader import DATA_DIR

logger = logging.getLogger(__name__)

PORTAL_PORT = 8087
PCBOT_DIR = Path(__file__).parent.parent
PORTAL_FILE = PCBOT_DIR / "portal.html"
if not PORTAL_FILE.is_file():
    PORTAL_FILE = Path(DATA_DIR) / "portal.html"


class PortalHandler(SimpleHTTPRequestHandler):
    """
    Handler HTTP para el portal del PCBOT.
    Sirve portal.html + API REST local.
    """

    def __init__(self, *args, profile_manager=None, ws_client=None,
                 token_engine=None, state_tracker=None, **kwargs):
        self.profile_manager = profile_manager
        self.ws_client = ws_client
        self.token_engine = token_engine
        self.state_tracker = state_tracker
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        logger.debug(f"HTTP {self.client_address[0]}: {format % args}")

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

    def do_GET(self):
        path = self.path.split("?")[0]

        # ── Servir portal.html ──
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

        # ── API: Dashboard local ──
        if path == "/api/dashboard":
            profiles = self.profile_manager.get_all() if self.profile_manager else []
            counts = {
                "active": sum(1 for p in profiles if p.get("state") == "active"),
                "inactive": sum(1 for p in profiles if p.get("state") == "inactive"),
                "hung": sum(1 for p in profiles if p.get("state") == "hung"),
            }
            server_ok = self.ws_client and self.ws_client.connected
            return self._json_reply(200, {
                "server_ok": server_ok,
                "pcbots_connected": 1 if server_ok else 0,
                "profiles_total": len(profiles),
                "profiles_active": counts["active"],
                "profiles_inactive": counts["inactive"],
                "profiles_hung": counts["hung"],
                "urls_viewing": counts["active"],
                "last_heartbeat": self.ws_client.last_heartbeat_time if self.ws_client else "N/A",
                "mis_kbt": self.token_engine.get_total() if self.token_engine else 0,
                "mi_uptime": self._get_uptime(),
            })

        # ── API: Profiles ──
        if path == "/api/profiles":
            profiles = self.profile_manager.get_all() if self.profile_manager else []
            return self._json_reply(200, {
                "profiles": profiles,
                "solo_mode": self.state_tracker.solo_mode if self.state_tracker else False,
                "counts": {
                    "active": sum(1 for p in profiles if p.get("state") == "active"),
                    "inactive": sum(1 for p in profiles if p.get("state") == "inactive"),
                    "hung": sum(1 for p in profiles if p.get("state") == "hung"),
                }
            })

        # ── API: Tokens ──
        if path == "/api/tokens":
            te = self.token_engine
            return self._json_reply(200, {
                "total": te.get_total() if te else 0,
                "generados": te.generados if te else 0,
                "comprados": 0,
                "historial_reciente": te.historial[-10:] if te else [],
            })

        # ── 404 ──
        self._json_reply(404, {"error": "Not found", "path": path})

    def do_POST(self):
        path = self.path.split("?")[0]
        body = self._read_body()

        # ── Login ──
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

        # ── Logout ──
        if path == "/api/logout":
            return self._json_reply(200, {"ok": True})

        # ── Toggle Solo Mode ──
        if path == "/api/toggle_solo":
            if self.state_tracker:
                new_mode = self.state_tracker.toggle_solo()
                return self._json_reply(200, {"solo_mode": new_mode})
            return self._json_reply(500, {"error": "state_tracker no disponible"})

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
        import time
        import psutil
        try:
            boot = psutil.boot_time()
            uptime = time.time() - boot
            h = int(uptime // 3600)
            m = int((uptime % 3600) // 60)
            return f"{h}h {m}m"
        except Exception:
            return "N/A"


class PortalServer:
    """
    Servidor HTTP del portal PCBOT.
    """

    def __init__(self, profile_manager=None, ws_client=None,
                 token_engine=None, state_tracker=None):
        self.profile_manager = profile_manager
        self.ws_client = ws_client
        self.token_engine = token_engine
        self.state_tracker = state_tracker
        self.server = None

    def _handler_factory(self, *args, **kwargs):
        return PortalHandler(
            *args,
            profile_manager=self.profile_manager,
            ws_client=self.ws_client,
            token_engine=self.token_engine,
            state_tracker=self.state_tracker,
            **kwargs
        )

    def start(self, port: int = None):
        port = port or PORTAL_PORT
        self.server = HTTPServer(
            ("0.0.0.0", port),
            self._handler_factory
        )
        logger.info(f"Portal PCBOT iniciado en http://{self._local_ip()}:{port}")
        print(f"\n  🌐 Portal PCBOT → http://127.0.0.1:{port}\n")
        self.server.serve_forever()

    def stop(self):
        if self.server:
            self.server.shutdown()
        logger.info("Portal PCBOT detenido")

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