import http.server, os, json, socketserver
from detector import detectar_info, detectar_roxybrowser
class PortalHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/estado":
            info = detectar_info()
            info.update(detectar_roxybrowser())
            self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers()
            self.wfile.write(json.dumps(info).encode())
        else:
            self.send_response(404); self.end_headers()
def iniciar_portal(port=8087):
    with socketserver.TCPServer(("", port), PortalHandler) as httpd:
        httpd.serve_forever()
