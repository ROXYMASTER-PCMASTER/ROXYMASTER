import os, json
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(BASE_DIR, "config.json"), "r", encoding="utf-8-sig") as f:
    _cfg = json.load(f)
IP_LOCAL = _cfg["server"]["ip_servidor"]
IP_TAILSCALE = _cfg["server"]["ip_tailscale"]
WS_PORT = _cfg["server"]["ws_port"]
HTTP_PORT = _cfg["server"]["puerto_http"]
JARVIS_MODELO = _cfg.get("ollama", {}).get("modelo", "llama3.2")
OLLAMA_API_URL = _cfg.get("ollama", {}).get("api_url", "http://localhost:11434")
VERSION = _cfg.get("version", "8.0")
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
