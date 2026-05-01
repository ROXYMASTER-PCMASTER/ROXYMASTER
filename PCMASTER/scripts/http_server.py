"""
ROXYMASTER v8.0 - HTTP SERVER (PCMASTER)
Servidor HTTP que sirve el portal admin y API REST completa.
Puerto por defecto: 8086
"""

import json
import logging
import socket
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from pcmaster.scripts.config_loader import DATA_DIR

logger = logging.getLogger(__name__)

PORTAL_PORT = 8086
PCMASTER_DIR = Path(__file__).parent.parent
PORTAL_FILE = PCMASTER_DIR / "portal.html"
if not PORTAL_FILE.is_file():
    PORTAL_FILE = Path(DATA_DIR) / "portal.html"


class AdminHandler(SimpleHTTPRequestHandler):
    """
    Handler HTTP para el portal admin de PCMASTER.
    Sirve portal.html + API REST con todas las funciones admin.
    """

    instances = {}

    def __init__(self, *args, auth_manager=None, ws_clients=None,
                 orchestrator=None, tokenomics=None, marketplace=None,
                 jarvis=None, **kwargs):
        self.auth = auth_manager
        self.ws_clients = ws_clients or {}
        self.orchestrator = orchestrator
        self.tokenomics = tokenomics
        self.marketplace = marketplace
        self.jarvis = jarvis
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        logger.debug(f"HTTP {self.client_address[0]}: {format % args}")

    def do_OPTIONS(self):
        self._cors()
        self.send_response(200)
        self.end_headers()

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")

    def _json(self, status: int, data: dict):
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except Exception:
            return {}

    def _is_admin(self, body: dict) -> bool:
        sid = body.get("session_id", "")
        if not sid or not self.auth:
            return False
        return self.auth.get_role(sid) == "admin"

    # ═══════════════════════════════════════════════
    # GET
    # ═══════════════════════════════════════════════
    def do_GET(self):
        path = self.path.split("?")[0]

        # ── Portal HTML ──
        if path in ("/", "/portal", "/portal.html", "/index.html"):
            try:
                content = PORTAL_FILE.read_text(encoding="utf-8")
                self.send_response(200)
                self._cors()
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(content.encode())
            except FileNotFoundError:
                self._json(404, {"error": "portal.html no encontrado"})
            return

        # ── Dashboard ──
        if path == "/api/dashboard":
            profiles_info = []
            pcbot_count = 0
            total_profiles = 0
            active = inactive = hung = 0
            urls = set()

            for cid, cdata in self.ws_clients.items():
                pcbot_count += 1
                perf = cdata.get("profiles", [])
                total_profiles += len(perf)
                for p in perf:
                    s = p.get("state", "inactive")
                    active += 1 if s == "active" else 0
                    inactive += 1 if s == "inactive" else 0
                    hung += 1 if s == "hung" else 0
                    if p.get("current_url"):
                        urls.add(p["current_url"])
            return self._json(200, {
                "server_ok": True,
                "pcbots_connected": pcbot_count,
                "profiles_total": total_profiles,
                "profiles_active": active,
                "profiles_inactive": inactive,
                "profiles_hung": hung,
                "urls_viewing": len(urls),
                "kbt_circulante": self.tokenomics.circulante() if self.tokenomics else 150_000,
                "active_sessions": self.auth.count_sessions() if self.auth else 0,
                "last_heartbeat": datetime.now().strftime("%H:%M:%S"),
            })

        # ── PCBOTs ──
        if path == "/api/pcbots":
            clients = {}
            for cid, cdata in self.ws_clients.items():
                clients[cid] = {
                    "info": cdata.get("info", {}),
                    "heartbeats": cdata.get("heartbeats", 0),
                    "last_heartbeat_ago": cdata.get("last_hb_ago", 0),
                    "profiles": cdata.get("profiles", []),
                }
            return self._json(200, {"clients": clients})

        # ── Tokenomics ──
        if path == "/api/tokenomics":
            if self.tokenomics:
                st = self.tokenomics.get_status()
                st["rewards"] = self.tokenomics.get_rewards_table()
                return self._json(200, st)
            return self._json(200, {"total": 150_000, "supply": {}})

        # ── Marketplace ──
        if path == "/api/marketplace":
            if self.marketplace:
                return self._json(200, {
                    "prices": self.marketplace.get_prices(),
                    "ventas": self.marketplace.get_sales_history(),
                    "total_sales_usd": self.marketplace.get_total_sales_usd(),
                })
            return self._json(200, {"prices": {}})

        # ── Jarvis ──
        if path == "/api/jarvis":
            if self.jarvis:
                return self._json(200, self.jarvis.get_status())
            return self._json(200, {"modelo": "N/A", "ollama_activo": False})

        self._json(404, {"error": "Not found"})

    # ═══════════════════════════════════════════════
    # POST
    # ═══════════════════════════════════════════════
    def do_POST(self):
        path = self.path.split("?")[0]
        body = self._body()

        # ── Login ──
        if path == "/api/login":
            email = body.get("email", "").strip().lower()
            password = body.get("password", "")
            if not email or not password:
                return self._json(401, {"error": "Credenciales requeridas"})

            if self.auth:
                result = self.auth.login(email, password)
            else:
                # Sin auth: admin por defecto si es PCMASTER
                result = {
                    "session_id": "admin_" + email.replace("@", "_"),
                    "role": "admin" if password == "Abc123$_" else "user",
                    "pc_info": {"hostname": socket.gethostname()}
                }
            return self._json(200, result)

        # ── Logout ──
        if path == "/api/logout":
            if self.auth:
                self.auth.logout(body.get("session_id", ""))
            return self._json(200, {"ok": True})

        # ── Comando (Orquestar) ──
        if path == "/api/command":
            if not self._is_admin(body):
                return self._json(403, {"error": "Acceso denegado"})

            action = body.get("action", "")
            pcbot_id = body.get("pcbot_id", "")
            profile_ids = body.get("profile_ids", [])
            url = body.get("url", "")
            duracion = body.get("duracion_min", 62)
            comentar = body.get("comentar", False)

            if not action or not pcbot_id:
                return self._json(400, {"error": "action y pcbot_id requeridos"})

            if self.orchestrator:
                result = self.orchestrator.send_command(
                    pcbot_id=pcbot_id,
                    action=action,
                    profile_ids=profile_ids,
                    url=url,
                    duracion_min=duracion,
                    comentar=comentar,
                )
                return self._json(200, result)

            return self._json(500, {"error": "Orquestador no disponible"})

        # ── Marketplace Buy ──
        if path == "/api/marketplace/buy":
            if not self._is_admin(body):
                return self._json(403, {"error": "Acceso denegado"})

            email = body.get("email", "")
            package = body.get("package", "")
            if not email or not package:
                return self._json(400, {"error": "email y package requeridos"})

            if self.marketplace:
                result = self.marketplace.buy(email, package)
                return self._json(200, result)

            return self._json(500, {"error": "Marketplace no disponible"})

        # ── Jarvis Test ──
        if path == "/api/jarvis/test":
            if not self._is_admin(body):
                return self._json(403, {"error": "Acceso denegado"})

            ctx = body.get("contexto", {})
            if self.jarvis:
                comentario = self.jarvis.generar_comentario(ctx)
                return self._json(200, {"comentario": comentario})

            return self._json(500, {"error": "Jarvis no disponible"})

        self._json(404, {"error": "Not found"})


class AdminServer:
    """
    Servidor HTTP admin de PCMASTER.
    """

    def __init__(self, auth_manager=None, ws_clients: dict = None,
                 orchestrator=None, tokenomics=None, marketplace=None,
                 jarvis=None):
        self.auth = auth_manager
        self.ws_clients = ws_clients or {}
        self.orchestrator = orchestrator
        self.tokenomics = tokenomics
        self.marketplace = marketplace
        self.jarvis = jarvis
        self.server = None

    def _handler_factory(self, *args, **kwargs):
        return AdminHandler(
            *args,
            auth_manager=self.auth,
            ws_clients=self.ws_clients,
            orchestrator=self.orchestrator,
            tokenomics=self.tokenomics,
            marketplace=self.marketplace,
            jarvis=self.jarvis,
            **kwargs
        )

    def start(self, port: int = None):
        port = port or PORTAL_PORT
        self.server = HTTPServer(
            ("0.0.0.0", port),
            self._handler_factory
        )
        logger.info(f"Portal PCMASTER iniciado en http://{self._local_ip()}:{port}")
        print(f"\n  🏰 Portal PCMASTER → http://0.0.0.0:{port}")
        print(f"  🌐 Local:          http://127.0.0.1:{port}")
        print(f"  🔑 Admin login:    PCMASTER@roxy / Abc123$_")
        print()
        self.server.serve_forever()

    def stop(self):
        if self.server:
            self.server.shutdown()
        logger.info("Portal PCMASTER detenido")

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