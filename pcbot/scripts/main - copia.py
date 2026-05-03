import sys, os
"""
roxymaster v8.3 - pcbot main
punto de entrada del cliente pcbot.
inicia: deteccion -> ws client -> http portal -> profile manager -> state tracker -> token engine
"""

import asyncio
import logging
import os
import signal
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_loader import (
    DATA_DIR, NOMBRE_PC, USUARIO_PC, IP_LOCAL, IP_TAILSCALE,
    PCMASTER_HOST, PCMASTER_WS_PORT, PCMASTER_HTTP_PORT,
    ROXYBROWSER_API_URL, PORTAL_PORT
)
from auto_detect import AutoDetect
from api.roxybrowser_api import RoxyBrowserAPI
from core.profile_manager import ProfileManager, ProfileState
from core.state_tracker import StateTracker
from core.token_engine import TokenEngine
from api.ws_client import WSClient
from http_portal import PortalServer

logger = logging.getLogger("pcbot")

# configurar logging
LOG_FILE = os.path.join(DATA_DIR, "pcbot.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

# asegurar directorios
os.makedirs(DATA_DIR, exist_ok=True)

# puerto del portal (si 8087 esta ocupado, usa 8088)
_actual_portal_port = PORTAL_PORT


def main():
    global _actual_portal_port

    print()
    print("=" * 60)
    print("  roxymaster v8.3 -- pcbot client")
    print("=" * 60)
    print()

    # paso 1: auto-deteccion + info de config_loader
    print("[1/6] detectando entorno...")
    detector = AutoDetect()
    detected = detector.detect_all()
    roxy_profiles_raw = detector.get_roxy_profiles()

    pc_info = {
        "hostname": NOMBRE_PC,
        "username": USUARIO_PC,
        "ip_local": IP_LOCAL,
        "tailscale_ip": IP_TAILSCALE,
        "browsers": list(detected.get("browsers", {}).keys()),
        "profile_apps": list(detected.get("profile_apps", {}).keys()),
        "profiles_count": len(roxy_profiles_raw),
    }

    print(f"       hostname: {pc_info['hostname']}")
    print(f"       ip local: {pc_info['ip_local']}")
    print(f"       tailscale: {pc_info['tailscale_ip']}")
    print(f"       usuario:  {pc_info['username']}")
    print(f"       navegadores: {', '.join(pc_info['browsers']) if pc_info['browsers'] else 'ninguno'}")
    print(f"       apps perfiles: {', '.join(pc_info['profile_apps']) if pc_info['profile_apps'] else 'ninguna'}")
    print()

    # paso 2: roxybrowser api
    print("[2/6] conectando a roxybrowser api...")
    roxy = RoxyBrowserAPI(base_url=ROXYBROWSER_API_URL)
    perfiles_api = roxy.get_profiles()

    if perfiles_api:
        print(f"       {len(perfiles_api)} perfiles detectados en roxybrowser:")
        for p in perfiles_api[:5]:
            print(f"         - {p.get('name', p.get('id', '?'))}")
    else:
        print("       advertencia: 0 perfiles detectados. inicia perfiles en roxybrowser manualmente.")
    print()

    # paso 3: componentes core
    print("[3/6] iniciando componentes core...")
    pm = ProfileManager(roxy)
    st = StateTracker()
    te = TokenEngine()

    # registrar perfiles
    pm.register_profiles(perfiles_api)
    for pid in pm.profiles:
        st.start_tracking(pid)

    # conectar callback de ciclo completado
    async def on_cycle(profile_id, kbt_amount):
        te.generar_kbt(profile_id, kbt_amount)

    st.set_on_cycle_complete(lambda pid, amt: asyncio.ensure_future(on_cycle(pid, amt)))

    logger.info(f"profilemanager: {len(pm.profiles)} perfiles registrados")
    logger.info(f"tokenengine: {te.total()} kbt")
    print(f"       perfiles: {len(pm.profiles)} | estados: {pm.get_all_states()['counts']}")
    print()

    # paso 4: websocket client (en su propio event loop asyncio en thread)
    print(f"[4/6] conectando a pcmaster ({PCMASTER_HOST}:{PCMASTER_WS_PORT})...")
    ws = WSClient(
        pcmaster_ip=PCMASTER_HOST,
        pcmaster_port=PCMASTER_WS_PORT,
        pcbot_id=NOMBRE_PC,
    )

    # configurar handshake
    ws.set_handshake({
        "pcbot_id": NOMBRE_PC,
        "hostname": NOMBRE_PC,
        "username": USUARIO_PC,
        "ip_local": IP_LOCAL,
        "ip_tailscale": IP_TAILSCALE,
        "profiles": len(pm.profiles),
        "version": "8.3",
        "kbt_generados": te.kbt_generados,
    })

    # handler de comandos desde pcmaster
    async def on_command(cmd):
        logger.info(f"comando recibido: {cmd}")
        cmd_type = cmd.get("tipo", "")
        if cmd_type == "asignar":
            url = cmd.get("url", "")
            cantidad = cmd.get("cantidad", 1)
            duracion = cmd.get("duracion", 60)
            pids = list(pm.profiles.keys())[:cantidad]
            await pm.execute_on_profiles(pids, url, duracion)
        elif cmd_type == "detener":
            url = cmd.get("url", "")
            for pid, p in pm.profiles.items():
                if p.current_url == url:
                    pm.redirect_to_portal(pid, f"http://127.0.0.1:{_actual_portal_port}")
        elif cmd_type == "comentarios_activar":
            logger.info(f"comentarios activados para: {cmd.get('url', '')}")
        elif cmd_type == "estado":
            pass  # se responde via heartbeat

    ws.set_command_handler(on_command)

    # ejecutar ws en event loop propio dentro de thread
    ws_loop = asyncio.new_event_loop()

    def ws_thread_runner():
        asyncio.set_event_loop(ws_loop)
        ws_loop.run_until_complete(ws.connect())

    ws_thread = threading.Thread(target=ws_thread_runner, daemon=True)
    ws_thread.start()

    # esperar handshake inicial
    time.sleep(2)
    print(f"       {'conectado a pcmaster' if ws.connected else 'no se pudo conectar a pcmaster (modo offline)'}")
    print()

    # paso 5: http portal
    print(f"[5/6] iniciando portal http (puerto {_actual_portal_port})...")

    # intentar puerto alternativo si 8087 esta ocupado
    def _start_portal(port):
        global _actual_portal_port
        try:
            portal = PortalServer(pm, ws, te, st)
            portal._actual_port = port
            return portal, port
        except OSError:
            return None, port

    portal = PortalServer(pm, ws, te, st)

    def portal_runner():
        global _actual_portal_port
        try:
            portal.start(_actual_portal_port)
        except OSError:
            # si falla, intentar 8088
            logger.warning(f"puerto {_actual_portal_port} ocupado, intentando 8088")
            _actual_portal_port = 8088
            portal.start(8088)

    portal_thread = threading.Thread(target=portal_runner, daemon=True)
    portal_thread.start()
    time.sleep(0.5)
    print()

    # paso 6: tareas de mantenimiento
    print("[6/6] iniciando tareas de mantenimiento...")
    shutdown_flag = threading.Event()

    def maintenance_loop():
        """cada 30s verifica ciclos completados y salud de perfiles."""
        while not shutdown_flag.is_set():
            time.sleep(30)
            try:
                # verificar ciclos completados
                asyncio.run_coroutine_threadsafe(st.check_cycles(), ws_loop)

                # verificar salud de perfiles
                health = pm.check_all_health()
                if health.get(ProfileState.HUNG, 0) > 0:
                    logger.info(f"perfiles colgados: {health[ProfileState.HUNG]}. recuperando...")
                    for pid, p in pm.profiles.items():
                        if p.state == ProfileState.HUNG:
                            p.state = ProfileState.INACTIVE
                            p.fail_count = 0
                            st.start_tracking(pid)

                # heartbeat al servidor si conectado
                if ws.connected and ws.ws:
                    status_data = {
                        "type": "heartbeat",
                        "pcbot_id": NOMBRE_PC,
                        "profiles": pm.get_all_states(),
                        "tokens": te.total(),
                        "uptime": _get_uptime(),
                        "timestamp": time.time(),
                    }
                    async def send_hb():
                        try:
                            import json
                            await ws.ws.send(json.dumps(status_data))
                        except Exception:
                            pass
                    asyncio.run_coroutine_threadsafe(send_hb(), ws_loop)

            except Exception as e:
                logger.debug(f"maintenance loop: {e}")

    maint_thread = threading.Thread(target=maintenance_loop, daemon=True)
    maint_thread.start()

    # seniales de shutdown
    def shutdown(signum=None, frame=None):
        print("\napagando pcbot...")
        shutdown_flag.set()
        ws.running = False
        portal.stop()
        logger.info("pcbot apagado correctamente")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # resumen
    print()
    print("=" * 60)
    print("  pcbot iniciado")
    print("=" * 60)
    print(f"  hostname:     {pc_info['hostname']}")
    print(f"  ip local:      {pc_info['ip_local']}")
    print(f"  tailscale:     {pc_info['tailscale_ip']}")
    print(f"  usuario:       {pc_info['username']}")
    print(f"  perfiles:      {len(pm.profiles)}")
    print(f"  estados:       {pm.get_all_states()['counts']}")
    print(f"  portal:        http://127.0.0.1:{_actual_portal_port}")
    print(f"  pcmaster:      {'conectado' if ws.connected else 'offline'}")
    print(f"  kbt ganados:   {te.total()}")
    print("=" * 60)
    print()
    print("  presiona ctrl+c para salir")
    print()

    try:
        while not shutdown_flag.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()


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


if __name__ == "__main__":
    main()
