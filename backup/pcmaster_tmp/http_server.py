# ============================================================================
# ROXYMASTER v7.0 - HTTP SERVER MODULE
# API REST + Servicio de archivos estaticos (portales)
# ============================================================================

import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs


class APIHandler(BaseHTTPRequestHandler):
    """
    Manejador HTTP que expone la API REST y sirve los portales.
    Los objetos compartidos (orchestrator, auth, kbt, marketplace)
    se asignan como atributos de clase antes de iniciar el servidor.
    """

    # Atributos estaticos inyectados desde main.py
    orchestrator = None
    auth_manager = None
    kbt_engine = None
    marketplace = None
    admin_portal_path = ""
    portal_path = ""
    dashboard_path = ""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _send_json(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _send_html(self, path: str):
        if not os.path.isfile(path):
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        with open(path, "rb") as f:
            self.wfile.write(f.read())

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw)

    def _get_token(self) -> str:
        """Extrae token del header Authorization: Bearer <token>."""
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:]
        # Fallback: query param
        qs = parse_qs(urlparse(self.path).query)
        return qs.get("token", [""])[0]

    def _requiere_auth(self) -> dict:
        """Valida token y retorna sesion o None."""
        token = self._get_token()
        if not token:
            return None
        sesion = self.auth_manager.validar_token(token)
        if not sesion.get("valido"):
            return None
        return sesion

    def _log(self, msg: str):
        print(f"[HTTP] {self.command} {self.path} -> {msg}")

    # ------------------------------------------------------------------
    # CORS preflight
    # ------------------------------------------------------------------
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)

        # ---- Portal admin ----
        if path == "" or path == "/admin" or path == "/admin_portal":
            self._send_html(self.admin_portal_path)
            return

        # ---- Portal PCBOT ----
        if path == "/portal":
            self._send_html(self.portal_path)
            return

        # ---- Dashboard ----
        if path == "/dashboard":
            self._send_html(self.dashboard_path)
            return

        # ---- API: Dashboard ----
        if path == "/api/dashboard":
            data = self.orchestrator.get_dashboard()
            data["ofertas_p2p_activas"] = len(self.marketplace.listar_activas()) if self.marketplace else 0
            # Agregar stats KBT
            if self.kbt_engine:
                try:
                    data["kbt"] = self.kbt_engine.get_stats()
                except Exception:
                    data["kbt"] = {}
            self._send_json(data)
            return

        # ---- API: PCBOTs ----
        if path == "/api/pcbots":
            data = {}
            for pid, info in self.orchestrator.pcbots_info.items():
                data[pid] = {
                    "hostname": info.get("hostname", ""),
                    "usuario": info.get("usuario", ""),
                    "ip_local": info.get("ip_local", ""),
                    "estado": info.get("estado", "desconocido"),
                    "perfiles": len(info.get("perfiles", [])),
                    "activos": info.get("perfiles_activos", 0),
                    "inactivos": info.get("perfiles_inactivos", 0),
                    "colgados": info.get("perfiles_colgados", 0),
                    "last_heartbeat": info.get("last_heartbeat", 0)
                }
            self._send_json(data)
            return

        # ---- API: KBT Stats ----
        if path == "/api/kbt/stats":
            if not self.kbt_engine:
                self._send_json({"error": "KBT no disponible"}, 503)
                return
            self._send_json(self.kbt_engine.get_stats())
            return

        # ---- API: KBT Saldo ----
        if path == "/api/kbt/saldo":
            sesion = self._requiere_auth()
            if not sesion:
                self._send_json({"error": "No autorizado"}, 401)
                return
            if not self.kbt_engine:
                self._send_json({"error": "KBT no disponible"}, 503)
                return
            email = sesion["email"]
            saldo = self.kbt_engine.obtener_saldo_detallado(email)
            if not saldo:
                self._send_json({"error": "Granjero no encontrado"}, 404)
                return
            self._send_json(saldo)
            return

        # ---- API: Sesiones activas ----
        if path == "/api/kbt/sesiones":
            sesion = self._requiere_auth()
            if not sesion:
                self._send_json({"error": "No autorizado"}, 401)
                return
            if not self.kbt_engine:
                self._send_json({"error": "KBT no disponible"}, 503)
                return
            email = sesion["email"]
            sesiones_data = self.kbt_engine.obtener_sesiones_activas(email)
            self._send_json({"sesiones": sesiones_data})
            return

        # ---- API: P2P Ofertas ----
        if path == "/api/p2p/ofertas":
            if not self.marketplace:
                self._send_json({"error": "Marketplace no disponible"}, 503)
                return
            self._send_json({"ofertas": self.marketplace.listar_activas()})
            return

        # ---- API: P2P Historial ----
        if path == "/api/p2p/historial":
            sesion = self._requiere_auth()
            if not sesion:
                self._send_json({"error": "No autorizado"}, 401)
                return
            if not self.marketplace:
                self._send_json({"error": "Marketplace no disponible"}, 503)
                return
            email = sesion["email"]
            self._send_json({"historial": self.marketplace.historial_usuario(email)})
            return

        # ---- Ruta no encontrada ----
        self.send_error(404, "Not found")

    # ------------------------------------------------------------------
    # POST
    # ------------------------------------------------------------------
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        body = self._read_body()

        # ---- Login ----
        if path == "/api/login":
            email = body.get("email", "")
            password = body.get("password", "")
            pcbot_id = body.get("pcbot_id", "")
            if not email or not password:
                self._send_json({"ok": False, "error": "Email y password requeridos"}, 400)
                return
            result = self.auth_manager.login(email, password, pcbot_id)
            if result["ok"]:
                self._send_json(result)
            else:
                self._send_json(result, 401)
            return

        # ---- Registro ----
        if path == "/api/registro":
            email = body.get("email", "")
            password = body.get("password", "")
            pcbot_id = body.get("pcbot_id", "")
            if not email or not password:
                self._send_json({"ok": False, "error": "Email y password requeridos"}, 400)
                return
            result = self.auth_manager.registrar(email, password, pcbot_id)
            if result["ok"]:
                self._send_json(result)
            else:
                self._send_json(result, 400)
            return

        # ---- Cerrar sesion ----
        if path == "/api/logout":
            sesion = self._requiere_auth()
            if sesion:
                self.auth_manager.cerrar_sesion(self._get_token())
            self._send_json({"ok": True})
            return

        # ---- Asignar URL a perfiles ----
        if path == "/api/asignar":
            sesion = self._requiere_auth()
            if not sesion:
                self._send_json({"error": "No autorizado"}, 401)
                return
            pcbot_id = body.get("pcbot_id", "")
            url = body.get("url", "")
            n_perfiles = body.get("perfiles", 1)
            duracion = body.get("duracion", 62)
            if not pcbot_id or not url:
                self._send_json({"ok": False, "error": "pcbot_id y url requeridos"}, 400)
                return

            # Encolar para ejecucion asincrona
            import asyncio
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(
                self.orchestrator.asignar_url(pcbot_id, url, n_perfiles, duracion)
            )
            loop.close()

            self._send_json(result)
            self._log(f"Asignar: {pcbot_id} -> {url} x{n_perfiles}")
            return

        # ---- Detener perfiles ----
        if path == "/api/detener":
            sesion = self._requiere_auth()
            if not sesion:
                self._send_json({"error": "No autorizado"}, 401)
                return
            pcbot_id = body.get("pcbot_id", "")
            perfiles = body.get("perfiles", [])
            if not pcbot_id:
                self._send_json({"ok": False, "error": "pcbot_id requerido"}, 400)
                return

            import asyncio
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(
                self.orchestrator.detener_perfiles(pcbot_id, perfiles)
            )
            loop.close()

            self._send_json(result)
            return

        # ---- Activar comentarios ----
        if path == "/api/comentarios":
            sesion = self._requiere_auth()
            if not sesion:
                self._send_json({"error": "No autorizado"}, 401)
                return
            pcbot_id = body.get("pcbot_id", "")
            url = body.get("url", "")
            intervalo = body.get("intervalo", 120)
            if not pcbot_id or not url:
                self._send_json({"ok": False, "error": "pcbot_id y url requeridos"}, 400)
                return

            import asyncio
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(
                self.orchestrator.activar_comentarios(pcbot_id, url, intervalo)
            )
            loop.close()

            self._send_json(result)
            return

        # ---- P2P Crear oferta ----
        if path == "/api/p2p/crear":
            sesion = self._requiere_auth()
            if not sesion:
                self._send_json({"error": "No autorizado"}, 401)
                return
            if not self.marketplace:
                self._send_json({"error": "Marketplace no disponible"}, 503)
                return
            tokens = body.get("tokens", 0)
            precio = body.get("precio_soles", 0)
            email = sesion["email"]
            result = self.marketplace.crear_oferta(email, tokens, precio)
            if result["ok"]:
                self._send_json(result)
            else:
                self._send_json(result, 400)
            return

        # ---- P2P Comprar oferta ----
        if path == "/api/p2p/comprar":
            sesion = self._requiere_auth()
            if not sesion:
                self._send_json({"error": "No autorizado"}, 401)
                return
            if not self.marketplace:
                self._send_json({"error": "Marketplace no disponible"}, 503)
                return
            oferta_id = body.get("oferta_id", "")
            email = sesion["email"]
            result = self.marketplace.comprar_oferta(oferta_id, email)
            if result["ok"]:
                # Ejecutar transferencia KBT
                oferta = result["oferta"]
                if self.kbt_engine:
                    try:
                        self.kbt_engine.transferir(
                            email, oferta["vendedor"],
                            oferta["tokens"],
                            comision_pct=5
                        )
                    except Exception as e:
                        self._log(f"Error transfiriendo KBT: {e}")
                self._send_json(result)
            else:
                self._send_json(result, 400)
            return

        # ---- P2P Cancelar oferta ----
        if path == "/api/p2p/cancelar":
            sesion = self._requiere_auth()
            if not sesion:
                self._send_json({"error": "No autorizado"}, 401)
                return
            if not self.marketplace:
                self._send_json({"error": "Marketplace no disponible"}, 503)
                return
            oferta_id = body.get("oferta_id", "")
            email = sesion["email"]
            result = self.marketplace.cancelar_oferta(oferta_id, email)
            if result["ok"]:
                self._send_json(result)
            else:
                self._send_json(result, 400)
            return

        # ---- Ruta no encontrada ----
        self.send_error(404, "Not found")


def start_http_server(orchestrator, auth_manager, kbt_engine, marketplace,
                      admin_portal_path, portal_path, dashboard_path,
                      host="0.0.0.0", port=8086):
    """Inicia el servidor HTTP en un hilo separado."""
    # Inyectar dependencias
    APIHandler.orchestrator = orchestrator
    APIHandler.auth_manager = auth_manager
    APIHandler.kbt_engine = kbt_engine
    APIHandler.marketplace = marketplace
    APIHandler.admin_portal_path = admin_portal_path
    APIHandler.portal_path = portal_path
    APIHandler.dashboard_path = dashboard_path

    server = HTTPServer((host, port), APIHandler)
    print(f"[HTTP] Servidor HTTP iniciado en http://{host}:{port}")
    print(f"[HTTP] Admin Portal: http://{host}:{port}/admin")
    return server