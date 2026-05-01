# ============================================================================
# roxymaster v7.0 - http server module
# api rest + servicio de archivos estaticos (portales)
# ============================================================================

import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs


class APIHandler(BaseHTTPRequestHandler):
    """
    manejador http que expone la api rest y sirve los portales.
    los objetos compartidos (orchestrator, auth, kbt, marketplace)
    se asignan como atributos de clase antes de iniciar el servidor.
    """

    # atributos estaticos inyectados desde main.py
    orchestrator = None
    auth_manager = None
    kbt_engine = None
    marketplace = None
    admin_portal_path = ""
    portal_path = ""
    dashboard_path = ""

    # ------------------------------------------------------------------
    # helpers
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
        """extrae token del header authorization: bearer <token>."""
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:]
        # fallback: query param
        qs = parse_qs(urlparse(self.path).query)
        return qs.get("token", [""])[0]

    def _requiere_auth(self) -> dict:
        """valida token y retorna sesion o none."""
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
    # cors preflight
    # ------------------------------------------------------------------
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    # ------------------------------------------------------------------
    # get
    # ------------------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query)

        # ---- portal admin ----
        if path == "" or path == "/admin" or path == "/admin_portal":
            self._send_html(self.admin_portal_path)
            return

        # ---- portal pcbot ----
        if path == "/portal":
            self._send_html(self.portal_path)
            return

        # ---- dashboard ----
        if path == "/dashboard":
            self._send_html(self.dashboard_path)
            return

        # ---- api: dashboard ----
        if path == "/api/dashboard":
            data = self.orchestrator.get_dashboard()
            data["ofertas_p2p_activas"] = len(self.marketplace.listar_activas()) if self.marketplace else 0
            # agregar stats kbt
            if self.kbt_engine:
                try:
                    data["kbt"] = self.kbt_engine.get_stats()
                except Exception:
                    data["kbt"] = {}
            self._send_json(data)
            return

        # ---- api: pcbots ----
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

        # ---- api: kbt stats ----
        if path == "/api/kbt/stats":
            if not self.kbt_engine:
                self._send_json({"error": "kbt no disponible"}, 503)
                return
            self._send_json(self.kbt_engine.get_stats())
            return

        # ---- api: kbt saldo ----
        if path == "/api/kbt/saldo":
            sesion = self._requiere_auth()
            if not sesion:
                self._send_json({"error": "no autorizado"}, 401)
                return
            if not self.kbt_engine:
                self._send_json({"error": "kbt no disponible"}, 503)
                return
            email = sesion["email"]
            saldo = self.kbt_engine.obtener_saldo_detallado(email)
            if not saldo:
                self._send_json({"error": "granjero no encontrado"}, 404)
                return
            self._send_json(saldo)
            return

        # ---- api: sesiones activas ----
        if path == "/api/kbt/sesiones":
            sesion = self._requiere_auth()
            if not sesion:
                self._send_json({"error": "no autorizado"}, 401)
                return
            if not self.kbt_engine:
                self._send_json({"error": "kbt no disponible"}, 503)
                return
            email = sesion["email"]
            sesiones_data = self.kbt_engine.obtener_sesiones_activas(email)
            self._send_json({"sesiones": sesiones_data})
            return

        # ---- api: p2p ofertas ----
        if path == "/api/p2p/ofertas":
            if not self.marketplace:
                self._send_json({"error": "marketplace no disponible"}, 503)
                return
            self._send_json({"ofertas": self.marketplace.listar_activas()})
            return

        # ---- api: p2p historial ----
        if path == "/api/p2p/historial":
            sesion = self._requiere_auth()
            if not sesion:
                self._send_json({"error": "no autorizado"}, 401)
                return
            if not self.marketplace:
                self._send_json({"error": "marketplace no disponible"}, 503)
                return
            email = sesion["email"]
            self._send_json({"historial": self.marketplace.historial_usuario(email)})
            return

        # ---- api: mi_estado ----
        if path == "/api/mi_estado":
            sesion = self._requiere_auth()
            if not sesion:
                self._send_json({"error": "no autorizado"}, 401)
                return
            email = sesion["email"]
            import sqlite3
            from config import DB_PATH
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            user = conn.execute(
                "select id, email, rol, wallet, codigo_referido, referido_por, created_at from usuarios where lower(email)=?",
                (email.lower(),)
            ).fetchone()
            if not user:
                conn.close()
                self._send_json({"error": "usuario no encontrado"}, 404)
                return
            wallet = conn.execute(
                "select saldo_tokens from wallets where usuario_id=?",
                (user["id"],)
            ).fetchone()
            saldo = wallet["saldo_tokens"] if wallet else 0
            conn.close()
            self._send_json({
                "ok": True,
                "id": user["id"],
                "email": user["email"],
                "rol": user["rol"],
                "wallet": user["wallet"],
                "codigo_referido": user["codigo_referido"],
                "referido_por": user["referido_por"],
                "saldo_tokens": saldo,
                "created_at": user["created_at"]
            })
            return

        # ---- ruta no encontrada ----
        self.send_error(404, "Not found")

    # ------------------------------------------------------------------
    # post
    # ------------------------------------------------------------------
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        body = self._read_body()

        # ---- login ----
        if path == "/api/login":
            email = body.get("email", "")
            password = body.get("password", "")
            pcbot_id = body.get("pcbot_id", "")
            if not email or not password:
                self._send_json({"ok": False, "error": "email y password requeridos"}, 400)
                return
            result = self.auth_manager.login(email, password, pcbot_id)
            if result["ok"]:
                self._send_json(result)
            else:
                self._send_json(result, 401)
            return

        # ---- registro (corregido: no envia pcbot_id extra) ----
        if path == "/api/registro" or path == "/api/register":
            email = body.get("email", "")
            password = body.get("password", "")
            referido_por = body.get("referido_por", body.get("pcbot_id", "pcmaster"))
            if not email or not password:
                self._send_json({"ok": False, "error": "email y password requeridos"}, 400)
                return
            resultado = self.auth_manager.registrar(email, password, referido_por)
            if resultado["ok"]:
                self._send_json(resultado)
            else:
                self._send_json(resultado, 400)
            return

        # ---- cerrar sesion ----
        if path == "/api/logout":
            sesion = self._requiere_auth()
            if sesion:
                self.auth_manager.cerrar_sesion(self._get_token())
            self._send_json({"ok": True})
            return

        # ---- comando de texto (orchestrator) ----
        if path == "/api/comando":
            sesion = self._requiere_auth()
            if not sesion:
                self._send_json({"error": "no autorizado"}, 401)
                return
            comando = body.get("comando", "")
            if not comando:
                self._send_json({"ok": False, "error": "comando requerido"}, 400)
                return
            # parser simple de comandos
            resultado = self._parse_comando(comando, sesion)
            self._send_json(resultado)
            self._log(f"comando: {comando} -> {resultado}")
            return

        # ---- asignar url a perfiles ----
        if path == "/api/asignar":
            sesion = self._requiere_auth()
            if not sesion:
                self._send_json({"error": "no autorizado"}, 401)
                return
            pcbot_id = body.get("pcbot_id", "")
            url = body.get("url", "")
            n_perfiles = body.get("perfiles", 1)
            duracion = body.get("duracion", 62)
            if not pcbot_id or not url:
                self._send_json({"ok": False, "error": "pcbot_id y url requeridos"}, 400)
                return

            # encolar para ejecucion asincrona
            import asyncio
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(
                self.orchestrator.asignar_url(pcbot_id, url, n_perfiles, duracion)
            )
            loop.close()

            self._send_json(result)
            self._log(f"asignar: {pcbot_id} -> {url} x{n_perfiles}")
            return

        # ---- detener perfiles ----
        if path == "/api/detener":
            sesion = self._requiere_auth()
            if not sesion:
                self._send_json({"error": "no autorizado"}, 401)
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

        # ---- activar comentarios ----
        if path == "/api/comentarios":
            sesion = self._requiere_auth()
            if not sesion:
                self._send_json({"error": "no autorizado"}, 401)
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

        # ---- p2p crear oferta ----
        if path == "/api/p2p/crear" or path == "/api/kbt/crear_oferta":
            sesion = self._requiere_auth()
            if not sesion:
                self._send_json({"error": "no autorizado"}, 401)
                return
            if not self.marketplace:
                self._send_json({"error": "marketplace no disponible"}, 503)
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

        # ---- p2p comprar oferta ----
        if path == "/api/p2p/comprar":
            sesion = self._requiere_auth()
            if not sesion:
                self._send_json({"error": "no autorizado"}, 401)
                return
            if not self.marketplace:
                self._send_json({"error": "marketplace no disponible"}, 503)
                return
            oferta_id = body.get("oferta_id", "")
            email = sesion["email"]
            result = self.marketplace.comprar_oferta(oferta_id, email)
            if result["ok"]:
                # ejecutar transferencia kbt
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

        # ---- p2p cancelar oferta ----
        if path == "/api/p2p/cancelar":
            sesion = self._requiere_auth()
            if not sesion:
                self._send_json({"error": "no autorizado"}, 401)
                return
            if not self.marketplace:
                self._send_json({"error": "marketplace no disponible"}, 503)
                return
            oferta_id = body.get("oferta_id", "")
            email = sesion["email"]
            result = self.marketplace.cancelar_oferta(oferta_id, email)
            if result["ok"]:
                self._send_json(result)
            else:
                self._send_json(result, 400)
            return

        # ---- ruta no encontrada ----
        self.send_error(404, "Not found")

    # ------------------------------------------------------------------
    # parser de comandos de texto
    # ------------------------------------------------------------------
    def _parse_comando(self, comando: str, sesion: dict) -> dict:
        """parsea comandos en texto natural y los ejecuta."""
        parts = comando.strip().split()
        if not parts:
            return {"ok": False, "error": "comando vacio"}

        accion = parts[0].lower()

        # asignar <cantidad> url <url> duracion <minutos>
        if accion == "asignar":
            try:
                cantidad = int(parts[1])
                url_idx = parts.index("url") if "url" in parts else -1
                dur_idx = parts.index("duracion") if "duracion" in parts else -1
                if url_idx == -1:
                    return {"ok": False, "error": "formato: asignar <cantidad> url <url> duracion <minutos>"}
                url = parts[url_idx + 1]
                duracion = int(parts[dur_idx + 1]) if dur_idx != -1 else 62

                import asyncio
                # obtener pcbot_id de la sesion
                pcbot_id = sesion.get("pcbot_id", "")
                if not pcbot_id:
                    pcbot_id = "pcbot_192.168.1.13"
                loop = asyncio.new_event_loop()
                result = loop.run_until_complete(
                    self.orchestrator.asignar_url(pcbot_id, url, cantidad, duracion)
                )
                loop.close()
                return result
            except Exception as e:
                return {"ok": False, "error": str(e)}

        # detener url <url>
        if accion == "detener":
            try:
                url_idx = parts.index("url") if "url" in parts else -1
                if url_idx == -1:
                    return {"ok": False, "error": "formato: detener url <url>"}
                url = parts[url_idx + 1]
                return {"ok": True, "accion": "detener", "url": url, "msg": "comando detener recibido - pendiente de implementacion completa"}
            except Exception as e:
                return {"ok": False, "error": str(e)}

        # comentarios_activar url <url> nivel <nivel>
        if accion == "comentarios_activar":
            try:
                url_idx = parts.index("url") if "url" in parts else -1
                nivel_idx = parts.index("nivel") if "nivel" in parts else -1
                if url_idx == -1:
                    return {"ok": False, "error": "formato: comentarios_activar url <url> nivel <nivel>"}
                url = parts[url_idx + 1]
                nivel = int(parts[nivel_idx + 1]) if nivel_idx != -1 else 1
                return {"ok": True, "accion": "comentarios_activar", "url": url, "nivel": nivel, "msg": "comando comentarios_activar recibido - pendiente de implementacion completa"}
            except Exception as e:
                return {"ok": False, "error": str(e)}

        return {"ok": False, "error": "accion desconocida", "comando": comando}


def start_http_server(orchestrator, auth_manager, kbt_engine, marketplace,
                      admin_portal_path, portal_path, dashboard_path,
                      host="0.0.0.0", port=8086):
    """inicia el servidor http en un hilo separado."""
    # inyectar dependencias
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