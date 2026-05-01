"""
ROXYMASTER v8.0 - PCMASTER MAIN
Punto de entrada del servidor PCMASTER.
Inicia: WS Server + HTTP Admin + Tokenomics + Marketplace + Jarvis + Orchestrator
"""

import logging
import os
import signal
import sys
import threading

from pcmaster.scripts.config_loader import DATA_DIR, ensure_dirs
from pcmaster.scripts.auth_manager import AuthManager
from pcmaster.scripts.tokenomics import Tokenomics
from pcmaster.scripts.marketplace.engine import MarketplaceEngine
from pcmaster.scripts.jarvis import Jarvis
from pcmaster.scripts.orchestrator import Orchestrator
from pcmaster.scripts.ws_server import WSServer
from pcmaster.scripts.http_server import AdminServer

logger = logging.getLogger("PCMASTER")

# ═══════════════════════════════════════════════════
# Configurar logging
# ═══════════════════════════════════════════════════
LOG_FILE = os.path.join(DATA_DIR, "pcmaster.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

# ═══════════════════════════════════════════════════
# Componentes globales (compartidos entre hilos)
# ═══════════════════════════════════════════════════
ws_clients = {}          # dict compartido: {client_id: {...}}
shutdown_flag = threading.Event()


def main():
    print()
    print("=" * 60)
    print("  🏰  ROXYMASTER v8.0 — PCMASTER SERVER")
    print("=" * 60)
    print()

    ensure_dirs()

    # ── 1. Auth Manager ──
    print("[1/7] Iniciando Auth Manager...")
    auth = AuthManager()
    logger.info("Auth Manager iniciado")

    # ── 2. Tokenomics ──
    print("[2/7] Iniciando Tokenomics (150K KBT genesis)...")
    tkm = Tokenomics()
    logger.info(f"Tokenomics: {tkm.total_supply()} KBT total supply")

    # ── 3. Marketplace ──
    print("[3/7] Iniciando Marketplace...")
    marketplace = MarketplaceEngine(tkm)
    logger.info(f"Marketplace: {len(marketplace.get_prices())} paquetes")

    # ── 4. Jarvis IA ──
    print("[4/7] Iniciando Jarvis IA...")
    jarvis = Jarvis()
    logger.info(f"Jarvis: modelo={jarvis.modelo}, ollama={'ON' if jarvis.ollama_activo else 'OFF'}")

    # ── 5. Orchestrator ──
    print("[5/7] Iniciando Orchestrator...")
    orchestrator = Orchestrator(ws_clients=ws_clients, jarvis=jarvis)
    logger.info("Orchestrator iniciado")

    # ── 6. WebSocket Server ──
    print("[6/7] Iniciando WebSocket Server (puerto 5006)...")
    ws_server = WSServer(
        host="0.0.0.0",
        port=5006,
        ws_clients=ws_clients,
        auth_manager=auth,
        orchestrator=orchestrator,
    )
    ws_thread = threading.Thread(target=ws_server.start, daemon=True)
    ws_thread.start()
    logger.info("WebSocket Server iniciado en :5006")

    # ── 7. HTTP Admin Server ──
    print("[7/7] Iniciando HTTP Admin Server (puerto 8086)...")
    admin_server = AdminServer(
        auth_manager=auth,
        ws_clients=ws_clients,
        orchestrator=orchestrator,
        tokenomics=tkm,
        marketplace=marketplace,
        jarvis=jarvis,
    )
    # Admin corre en el hilo principal

    # ── Señales de shutdown ──
    def shutdown(signum=None, frame=None):
        print("\n🛑 Apagando PCMASTER...")
        shutdown_flag.set()
        ws_server.stop()
        admin_server.stop()
        logger.info("PCMASTER apagado correctamente")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # ── Print resumen ──
    print()
    print("=" * 60)
    print("  ✅ PCMASTER INICIADO")
    print("=" * 60)
    print(f"  🔌 WebSocket:   ws://0.0.0.0:5006")
    print(f"  🌐 HTTP Admin:  http://127.0.0.1:8086")
    print(f"  🔑 Admin:       PCMASTER@roxy / Abc123$_")
    print(f"  💰 KBT Supply:  {tkm.total_supply():,.0f} KBT")
    print(f"  🧠 Jarvis:      {jarvis.modelo}")
    print("=" * 60)
    print()
    print("  Esperando conexiones de PCBOTs...")
    print()

    try:
        admin_server.start()
    except KeyboardInterrupt:
        shutdown()
    except Exception as e:
        logger.error(f"Error fatal: {e}")
        shutdown()


if __name__ == "__main__":
    main()