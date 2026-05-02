"""
ROXYMASTER v8.0 - PCBOT MAIN
Punto de entrada del cliente PCBOT.
Inicia: Detección → WS Client → HTTP Portal → Profile Manager → State Tracker → Token Engine
"""

import logging
import os
import signal
import sys
import threading
import time
from pathlib import Path

from pcbot.scripts.config_loader import DATA_DIR, ensure_dirs
from pcbot.scripts.auto_detect import AutoDetect
from pcbot.scripts.api.roxybrowser_api import RoxyBrowserAPI
from pcbot.scripts.core.profile_manager import ProfileManager
from pcbot.scripts.core.state_tracker import StateTracker
from pcbot.scripts.core.token_engine import TokenEngine
from pcbot.scripts.api.ws_client import WSClient
from pcbot.scripts.http_portal import PortalServer

logger = logging.getLogger("PCBOT")

# ═══════════════════════════════════════════════════
# Configurar logging
# ═══════════════════════════════════════════════════
LOG_FILE = os.path.join(DATA_DIR, "pcbot.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

# ═══════════════════════════════════════════════════
# Config (desde config.json via config_loader)
# ═══════════════════════════════════════════════════
from pcbot.scripts.config_loader import PCMASTER_HOST, PCMASTER_WS_PORT, ROXYBROWSER_API_URL


def main():
    print()
    print("=" * 60)
    print("  🤖  ROXYMASTER v8.0 — PCBOT CLIENT")
    print("=" * 60)
    print()

    ensure_dirs()

    # ── 1. Auto-detección ──
    print("[1/6] Detectando entorno...")
    detector = AutoDetect()
    pc_info = detector.detectar()
    print(f"       Hostname: {pc_info['hostname']}")
    print(f"       IP Local: {pc_info['ip_local']}")
    print(f"       Tailscale: {pc_info['tailscale_ip']}")
    print(f"       Usuario:  {pc_info['username']}")
    print()

    # ── 2. RoxyBrowser API ──
    print("[2/6] Conectando a RoxyBrowser API...")
    roxy = RoxyBrowserAPI(base_url=ROXYBROWSER_API_URL)
    perfiles_api = roxy.listar_perfiles()

    if perfiles_api:
        print(f"       {len(perfiles_api)} perfiles detectados en RoxyBrowser:")
        for p in perfiles_api[:5]:
            print(f"         - {p.get('name', p.get('id', '?'))}")
    else:
        print("       ⚠️  0 perfiles detectados. Inicia perfiles en RoxyBrowser manualmente.")
    print()

    # ── 3. Componentes Core ──
    print("[3/6] Iniciando componentes core...")
    pm = ProfileManager()
    st = StateTracker()
    te = TokenEngine()

    # Sincronizar perfiles desde RoxyBrowser API
    pm.sync_from_api(perfiles_api, state_tracker=st)
    st.sync_from_profiles(pm.get_all())
    logger.info(f"ProfileManager: {len(pm.get_all())} perfiles registrados")
    logger.info(f"StateTracker: {st.resumen()}")
    logger.info(f"TokenEngine: {te.get_total()} KBT")
    print(f"       Perfiles: {len(pm.get_all())} | Estados: {st.resumen()}")
    print()

    # ── 4. WebSocket Client ──
    print(f"[4/6] Conectando a PCMASTER ({PCMASTER_HOST}:{PCMASTER_WS_PORT})...")
    ws = WSClient(
        server_host=PCMASTER_HOST,
        server_port=PCMASTER_WS_PORT,
        pc_info=pc_info,
        profile_manager=pm,
        state_tracker=st,
        token_engine=te,
        roxy_api=roxy,
    )
    ws_thread = threading.Thread(target=ws.connect, daemon=True)
    ws_thread.start()

    # Esperar handshake inicial
    time.sleep(2)
    if ws.connected:
        print(f"       ✅ Conectado a PCMASTER")
    else:
        print(f"       ⚠️  No se pudo conectar a PCMASTER (modo offline)")
    print()

    # ── 5. HTTP Portal ──
    print("[5/6] Iniciando Portal HTTP (puerto 8087)...")
    portal = PortalServer(
        profile_manager=pm,
        ws_client=ws,
        token_engine=te,
        state_tracker=st,
    )
    portal_thread = threading.Thread(target=portal.start, daemon=True)
    portal_thread.start()
    time.sleep(0.5)
    print()

    # ── 6. Auto-mantenimiento ──
    print("[6/6] Iniciando tareas de mantenimiento...")
    shutdown_flag = threading.Event()

    def recovery_loop():
        """Cada 30s verifica perfiles colgados e intenta recuperar."""
        while not shutdown_flag.is_set():
            time.sleep(30)
            try:
                hung = st.get_hung()
                if hung:
                    logger.info(f"Recuperando {len(hung)} perfiles colgados...")
                    for pid in hung:
                        st.set_state(pid, "inactive")
                        pm.redirect_to_portal(pid)
            except Exception as e:
                logger.debug(f"Recovery loop: {e}")

    recovery_thread = threading.Thread(target=recovery_loop, daemon=True)
    recovery_thread.start()

    # ── Señales de shutdown ──
    def shutdown(signum=None, frame=None):
        print("\n🛑 Apagando PCBOT...")
        shutdown_flag.set()
        ws.disconnect()
        portal.stop()
        logger.info("PCBOT apagado correctamente")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # ── Print resumen ──
    print()
    print("=" * 60)
    print("  ✅ PCBOT INICIADO")
    print("=" * 60)
    print(f"  🖥️  Hostname:     {pc_info['hostname']}")
    print(f"  📡 IP Local:      {pc_info['ip_local']}")
    print(f"  🔗 Tailscale:     {pc_info['tailscale_ip']}")
    print(f"  👤 Usuario:       {pc_info['username']}")
    print(f"  👥 Perfiles:      {len(pm.get_all())}")
    print(f"  📊 Estados:       {st.resumen()}")
    print(f"  🌐 Portal:        http://127.0.0.1:8087")
    print(f"  🔌 PCMASTER:      {'✅ Conectado' if ws.connected else '❌ Offline'}")
    print(f"  🪙 KBT Ganados:   {te.get_total()}")
    print("=" * 60)
    print()
    print("  Presiona Ctrl+C para salir")
    print()

    try:
        # Mantener vivo el hilo principal
        while not shutdown_flag.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()