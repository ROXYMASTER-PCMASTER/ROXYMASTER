"""
roxymaster v8.3 - pcbot main (agente puro)
punto de entrada del cliente pcbot.
integracion: deteccion_perfiles, ws_client, componentes core.
sin portal, sin interfaz grafica, solo agente en segundo plano.
todo en minusculas, utf-8 sin bom.
"""

import asyncio
import logging
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_loader import (
    DATA_DIR, NOMBRE_PC, USUARIO_PC, IP_LOCAL, IP_TAILSCALE,
    ROXYBROWSER_API_URL,
)
from cargador_secretos import obtener_ip_pcmaster, obtener_puerto_ws, obtener_secreto_shs
from deteccion_perfiles import DeteccionPerfiles
from api.roxybrowser_api import RoxyBrowserAPI, find_workspace_id
from core.profile_manager import ProfileManager, ProfileState
from core.state_tracker import StateTracker
from core.token_engine import TokenEngine
from ws_client import WSClient
import aiohttp
from orchestrator_local import OrchestratorLocal

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

_modo_actual = "pidiendo_ordenes"


async def async_main():
    """corazon del pcbot, todo async."""
    global _modo_actual

    print("=" * 60)
    print("  roxymaster v8.3 -- pcbot client (agente puro)")
    print("=" * 60)

    # ---------------------------------------------------------------
    # paso 1: deteccion minima del entorno (solo sistema)
    # ---------------------------------------------------------------
    print("[1/6] detectando entorno...")
    detector = DeteccionPerfiles()
    env_info = await detector.detectar_todo()

    system_info = env_info.get("system", {})
    ip_wan = env_info.get("ip_wan", "0.0.0.0")
    sistema_operativo = system_info.get("os", "windows")

    print(f"       hostname: {NOMBRE_PC}")
    print(f"       ip local: {IP_LOCAL}")
    print(f"       tailscale: {IP_TAILSCALE}")
    print(f"       ip wan: {ip_wan}")
    print()

    # ---------------------------------------------------------------
    # paso 2: roxybrowser api - obtiene workspace id real via api rest
    # ---------------------------------------------------------------
    print("[2/6] conectando a roxybrowser api...")
    # solo usar find_workspace_id si es un numero (workspace id real)
    workspace_id_hint = find_workspace_id()
    if workspace_id_hint and workspace_id_hint.isdigit():
        workspace_id = workspace_id_hint
    else:
        workspace_id = ""

    roxy = RoxyBrowserAPI(ROXYBROWSER_API_URL, workspace_id)
    # forzar obtencion del workspace_id real via api rest
    ws_id_real = roxy.get_workspace_id()
    if ws_id_real:
        print(f"       workspace id obtenido via api: {ws_id_real}")
    else:
        print("       advertencia: no se pudo obtener workspace id de roxybrowser api")
    perfiles_api = roxy.get_profiles()

    if perfiles_api:
        print(f"       {len(perfiles_api)} perfiles detectados en roxybrowser:")
        for p in perfiles_api[:5]:
            print(f"         - {p.get('name', p.get('id', '?'))}")
    else:
        print("       advertencia: 0 perfiles detectados via api.")

    print()

    # ---------------------------------------------------------------
    # paso 3: componentes core (pm, st, te, orchestrator)
    # ---------------------------------------------------------------
    print("[3/6] iniciando componentes core...")
    pm = ProfileManager(roxy)
    st = StateTracker()
    te = TokenEngine()
    orchestrator = OrchestratorLocal(pm, roxy)

    pm.register_profiles(perfiles_api)
    for pid in pm.profiles:
        if pm.profiles[pid].name:
            st.start_tracking(pid)

    async def on_cycle(profile_id):
        te.generar_kbt(profile_id, 1.0)
        # redirigir a portal publico al completar ciclo de 62 min
        p = pm.get_profile(profile_id)
        if p and p.state == ProfileState.ACTIVE:
            logger.info(f"ciclo completado para {profile_id}, redirigiendo a portal")
            await pm.redirect_to_portal(profile_id, "https://www.wafabot.com")

    def cycle_callback(pid):
        async def wrapper():
            await on_cycle(pid)
        asyncio.create_task(wrapper())

    st.set_on_cycle_complete(cycle_callback)

    logger.info(f"profilemanager: {len(pm.profiles)} perfiles registrados")
    logger.info(f"tokenengine: {te.total()} kbt")
    print(f"       perfiles: {len(pm.profiles)} | estados: {pm.get_all_states()['counts']}")
    print()

    # ---------------------------------------------------------------
    # paso 4: websocket client - handshake minimo (solo identificacion)
    # ---------------------------------------------------------------
    pcmaster_ip = obtener_ip_pcmaster()
    ws_puerto = obtener_puerto_ws()
    print(f"[4/6] conectando a pcmaster via tailscale ({pcmaster_ip}:{ws_puerto})...")

    secreto = obtener_secreto_shs()
    if not secreto:
        logger.error("no hay secreto shs configurado. el agente no podra autenticarse con pcmaster.")
        print("       error: secreto shs no encontrado en data/secrets/cliente.json")
        print("       el administrador debe proporcionar el secreto compartido.")
        print("       continuando en modo offline...")
    else:
        logger.info("secreto shs cargado correctamente")

    ws = WSClient(
        pcmaster_ip=pcmaster_ip,
        pcmaster_port=ws_puerto,
        pcbot_id=NOMBRE_PC,
    )

    # handshake minimo: solo datos de identificacion de la pc
    ws.set_handshake({
        "pcbot_id": NOMBRE_PC,
        "hostname": NOMBRE_PC,
        "ip_local": IP_LOCAL,
        "ip_tailscale": IP_TAILSCALE,
        "ip_wan": ip_wan,
        "sistema_operativo": sistema_operativo,
        "version_agente": "8.3",
        "modo": _modo_actual,
    })

    # delegar todos los comandos al orchestrator
    async def on_command(cmd):
        global _modo_actual
        logger.info(f"comando recibido: {cmd.get('tipo', '?')}")
        cmd_type = cmd.get("tipo", cmd.get("type", ""))
        cmd_id = cmd.get("comando_id", cmd.get("id", str(time.time())))
        params = cmd.get("parametros", cmd.get("data", {}))
        result = await orchestrator.process_command_async(cmd_type, cmd_id, params)
        # si el comando cambia el modo, sincronizar
        if cmd.get("tipo") == "cambiar_modo" and result.get("ok"):
            nuevo_modo = cmd.get("modo", cmd.get("data", {}).get("modo", ""))
            if nuevo_modo:
                _modo_actual = nuevo_modo
                ws.cambiar_modo(nuevo_modo)
        return result

    ws.set_command_handler(on_command)

    # pasar profile manager al ws para incluir datos de perfiles en heartbeat
    ws.set_profile_manager(pm)

    # pasar orchestrator al ws para incluir datos de pedidos en heartbeat
    ws.set_orchestrator(orchestrator)

    # pasar referencia ws al orchestrator para estado de heartbeat y enviar respuestas
    orchestrator.ws_client = ws

    # iniciar ws en background
    ws_task = asyncio.create_task(ws.connect())
    for _ in range(5):
        await asyncio.sleep(1)
        if ws.connected:
            break

    print(f"       {'conectado a pcmaster' if ws.connected else 'modo offline'}")
    print()

    # ---------------------------------------------------------------
    # paso 5: tareas de mantenimiento
    # ---------------------------------------------------------------
    print("[5/6] iniciando tareas de mantenimiento...")

    async def maintenance_loop():
        while True:
            await asyncio.sleep(30)
            try:
                # verificar ciclos de state tracker
                await st.check_cycles()

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

    maint_task = asyncio.create_task(maintenance_loop())

    # ---------------------------------------------------------------
    # informacion final
    # ---------------------------------------------------------------
    print()
    print("=" * 60)
    print("  pcbot iniciado (agente puro v8.3)")
    print("=" * 60)
    print(f"  hostname:     {NOMBRE_PC}")
    print(f"  ip local:      {IP_LOCAL}")
    print(f"  tailscale:     {IP_TAILSCALE}")
    print(f"  ip wan:        {ip_wan}")
    print(f"  usuario:       {USUARIO_PC}")
    print(f"  perfiles:      {len(perfiles_api)} roxy")
    print(f"  modo:          {_modo_actual}")
    print(f"  pcmaster:      {'conectado a ' + pcmaster_ip if ws.connected else 'offline'}")
    print(f"  kbt ganados:   {te.total()}")
    print("=" * 60)
    print()
    print("  presiona ctrl+c para salir")
    print()

    # esperar hasta que se cancele
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass

    # shutdown
    print("\napagando pcbot...")
    ws.running = False
    maint_task.cancel()
    logger.info("pcbot apagado correctamente")


def main():
    """punto de entrada sincrono."""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"error fatal en pcbot: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()