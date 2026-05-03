"""
roxymaster v8.3 - pcbot main (refactorizado)
punto de entrada del cliente pcbot.
integra deteccion_perfiles, ws_client, http_portal y modos de operacion.
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
    ROXYBROWSER_API_URL, PORTAL_PORT
)
from cargador_secretos import obtener_ip_pcmaster, obtener_puerto_ws, obtener_secreto_shs
from deteccion_perfiles import DeteccionPerfiles
from api.roxybrowser_api import RoxyBrowserAPI
from core.profile_manager import ProfileManager, ProfileState
from core.state_tracker import StateTracker
from core.token_engine import TokenEngine
from api.ws_client import WSClient
from http_portal import PortalServer

logger = logging.getLogger("pcbot")

LOG_FILE = os.path.join(DATA_DIR, "pcbot.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

os.makedirs(DATA_DIR, exist_ok=True)

_actual_portal_port = PORTAL_PORT
_modo_actual = "pidiendo_ordenes"


def main():
    global _actual_portal_port, _modo_actual

    print("=" * 60)
    print("  roxymaster v8.3 -- pcbot client (refactorizado)")
    print("=" * 60)

    # ---------------------------------------------------------------
    # paso 1: deteccion completa del entorno con DeteccionPerfiles
    # ---------------------------------------------------------------
    print("[1/7] detectando entorno completo...")
    detector = DeteccionPerfiles()
    env_info = detector.detectar_todo()

    system_info = env_info.get("system", {})
    browsers = env_info.get("browsers", {})
    roxy_clasificados = env_info.get("roxy_clasificados", {})
    perfiles_vip = env_info.get("vip_profiles", [])
    roxy_profiles = env_info.get("roxy_profiles", [])

    pc_info = {
        "hostname": NOMBRE_PC,
        "username": USUARIO_PC,
        "ip_local": IP_LOCAL,
        "tailscale_ip": IP_TAILSCALE,
        "ip_wan": env_info.get("ip_wan", "0.0.0.0"),
        "browsers": list(browsers.keys()),
        "roxy_profiles_count": len(roxy_profiles),
        "roxy_listos": len(roxy_clasificados.get("listo", [])),
        "vip_count": len(perfiles_vip),
    }

    print(f"       hostname: {pc_info['hostname']}")
    print(f"       ip local: {pc_info['ip_local']}")
    print(f"       tailscale: {pc_info['tailscale_ip']}")
    print(f"       ip wan: {pc_info['ip_wan']}")
    print(f"       usuario:  {pc_info['username']}")
    print(f"       navegadores: {', '.join(pc_info['browsers']) if pc_info['browsers'] else 'ninguno'}")
    print(f"       perfiles roxy: {pc_info['roxy_profiles_count']} ({pc_info['roxy_listos']} listos)")
    print(f"       perfiles vip: {pc_info['vip_count']}")
    print()

    # ---------------------------------------------------------------
    # paso 2: roxybrowser api
    # ---------------------------------------------------------------
    print("[2/7] conectando a roxybrowser api...")
    roxy = RoxyBrowserAPI(base_url=ROXYBROWSER_API_URL)
    perfiles_api = roxy.get_profiles()

    if perfiles_api:
        print(f"       {len(perfiles_api)} perfiles detectados en roxybrowser:")
        for p in perfiles_api[:5]:
            print(f"         - {p.get('name', p.get('id', '?'))}")
    else:
        print("       advertencia: 0 perfiles detectados. inicia perfiles en roxybrowser manualmente.")
    print()

    # ---------------------------------------------------------------
    # paso 3: componentes core (pm, st, te)
    # ---------------------------------------------------------------
    print("[3/7] iniciando componentes core...")
    pm = ProfileManager(roxy)
    st = StateTracker()
    te = TokenEngine()

    pm.register_profiles(perfiles_api)
    for pid in pm.profiles:
        if pm.profiles[pid].name:
            st.start_tracking(pid)

    async def on_cycle(profile_id, kbt_amount):
        te.generar_kbt(profile_id, kbt_amount)

    st.set_on_cycle_complete(lambda pid, amt: asyncio.ensure_future(on_cycle(pid, amt)))

    logger.info(f"profilemanager: {len(pm.profiles)} perfiles registrados")
    logger.info(f"tokenengine: {te.total()} kbt")
    print(f"       perfiles: {len(pm.profiles)} | estados: {pm.get_all_states()['counts']}")
    print()

    # ---------------------------------------------------------------
    # paso 4: websocket client (con handshake completo + deteccion)
    # ---------------------------------------------------------------
    pcmaster_ip = obtener_ip_pcmaster()
    ws_puerto = obtener_puerto_ws()
    secreto = obtener_secreto_shs()
    print(f"[4/7] conectando a pcmaster via tailscale ({pcmaster_ip}:{ws_puerto})...")

    secreto = obtener_secreto_shs()
    ws = WSClient(
        pcmaster_ip=pcmaster_ip,
        pcmaster_port=ws_puerto,
        pcbot_id=NOMBRE_PC,
    )
    ws.configurar_secreto(secreto)

    # configurar handshake completo
    ws.set_handshake({
        "pcbot_id": NOMBRE_PC,
        "hostname": NOMBRE_PC,
        "username": USUARIO_PC,
        "ip_local": IP_LOCAL,
        "ip_tailscale": IP_TAILSCALE,
        "ip_wan": pc_info["ip_wan"],
        "perfiles_roxy": roxy_profiles[:20],
        "perfiles_vip": perfiles_vip,
        "navegadores": pc_info["browsers"],
        "modo": _modo_actual,
        "version": "8.3",
        "kbt_generados": te.kbt_generados,
    })

    # configurar referencias cruzadas para heartbeats
    ws.token_engine_ref = te
    ws.perfiles_roxy = roxy_profiles
    ws.perfiles_vip = perfiles_vip

    # comando handler
    async def on_command(cmd):
        global _modo_actual
        logger.info(f"comando recibido: {cmd}")
        cmd_type = cmd.get("tipo", "")

        if cmd_type == "cambiar_modo":
            nuevo = cmd.get("modo", "").strip()
            if nuevo in ("pidiendo_ordenes", "uso_personal"):
                _modo_actual = nuevo
                ws.cambiar_modo(nuevo)
                logger.info(f"modo cambiado a {nuevo} por pcmaster")

        elif cmd_type == "asignar":
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
            pass

    ws.set_command_handler(on_command)

    # hilo para conectar websocket (bloquea con reconexion)
    ws_loop = asyncio.new_event_loop()

    def ws_thread_runner():
        asyncio.set_event_loop(ws_loop)
        ws_loop.run_until_complete(ws.connect())

    ws_thread = threading.Thread(target=ws_thread_runner, daemon=True)
    ws_thread.start()
    time.sleep(2)

    print(f"       {'conectado a pcmaster' if ws.connected else 'modo offline'}")
    print()

    # ---------------------------------------------------------------
    # paso 5: http portal (con endpoint /api/modo)
    # ---------------------------------------------------------------
    print(f"[5/7] iniciando portal http (puerto {_actual_portal_port})...")
    portal = PortalServer(pm, ws, te, st)

    def portal_runner():
        global _actual_portal_port
        try:
            portal.start(_actual_portal_port)
        except OSError:
            logger.warning(f"puerto {_actual_portal_port} ocupado, intentando 8088")
            _actual_portal_port = 8088
            portal.start(8088)

    portal_thread = threading.Thread(target=portal_runner, daemon=True)
    portal_thread.start()
    time.sleep(0.5)
    print()

    # ---------------------------------------------------------------
    # paso 6: tareas de mantenimiento (ligero, heartbeats via ws)
    # ---------------------------------------------------------------
    print("[6/7] iniciando tareas de mantenimiento...")
    shutdown_flag = threading.Event()

    def maintenance_loop():
        while not shutdown_flag.is_set():
            time.sleep(30)
            try:
                # verificar ciclos de state tracker
                asyncio.run_coroutine_threadsafe(st.check_cycles(), ws_loop)

                # recuperar perfiles colgados
                health = pm.check_all_health()
                for pid, p in pm.profiles.items():
                    if p.state == ProfileState.HUNG:
                        logger.info(f"recuperando perfil colgado: {p.name or pid}")
                        p.state = ProfileState.INACTIVE
                        p.fail_count = 0
                        st.start_tracking(pid)

            except Exception as e:
                logger.debug(f"maintenance loop: {e}")

    maint_thread = threading.Thread(target=maintenance_loop, daemon=True)
    maint_thread.start()

    # ---------------------------------------------------------------
    # paso 7: shutdown handler
    # ---------------------------------------------------------------
    def shutdown(signum=None, frame=None):
        print("\napagando pcbot...")
        shutdown_flag.set()
        ws.running = False
        portal.stop()
        logger.info("pcbot apagado correctamente")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print()
    print("=" * 60)
    print("  pcbot iniciado (refactorizado v8.3)")
    print("=" * 60)
    print(f"  hostname:     {pc_info['hostname']}")
    print(f"  ip local:      {pc_info['ip_local']}")
    print(f"  tailscale:     {pc_info['tailscale_ip']}")
    print(f"  ip wan:        {pc_info['ip_wan']}")
    print(f"  usuario:       {pc_info['username']}")
    print(f"  perfiles:      {pc_info['roxy_profiles_count']} roxy + {pc_info['vip_count']} vip")
    print(f"  modo:          {_modo_actual}")
    print(f"  portal:        http://127.0.0.1:{_actual_portal_port}")
    print(f"  pcmaster:      {'conectado a ' + pcmaster_ip if ws.connected else 'offline'}")
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


if __name__ == "__main__":
    main()