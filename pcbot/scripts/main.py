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
    ROXYBROWSER_API_URL, ROXY_WORKSPACE_ID
)
from cargador_secretos import obtener_ip_pcmaster, obtener_puerto_ws, obtener_secreto_shs
from deteccion_perfiles import DeteccionPerfiles
from api.roxybrowser_api import RoxyBrowserAPI
from core.profile_manager import ProfileManager, ProfileState
from core.state_tracker import StateTracker
from core.token_engine import TokenEngine
from api.ws_client import WSClient
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


async def consultar_roxybrowser(api_key: str) -> list:
    """consulta roxybrowser con la api_key dada y devuelve lista de perfiles."""
    url = "http://127.0.0.1:50000/api/browsers"
    headers = {"x-api-key": api_key}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    browsers = data if isinstance(data, list) else data.get("browsers", [])
                    return [{"roxy_profile_id": str(b.get("id","")), "nombre": b.get("name",""), "workspace": b.get("workspace",""), "estado": "activo"} for b in browsers]
                else:
                    logger.error(f"RoxyBrowser HTTP {resp.status}")
                    return []
    except Exception as e:
        logger.error(f"Error RoxyBrowser: {e}")
        return []

async def async_main():
    """corazon del pcbot, todo async."""
    global _modo_actual

    print("=" * 60)
    print("  roxymaster v8.3 -- pcbot client (agente puro)")
    print("=" * 60)

    # ---------------------------------------------------------------
    # paso 1: deteccion completa del entorno con deteccionperfiles
    # ---------------------------------------------------------------
    print("[1/6] detectando entorno completo...")
    detector = DeteccionPerfiles()
    env_info = await detector.detectar_todo()

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
    # paso 2: roxybrowser api (sincrono pero liviano)
    # ---------------------------------------------------------------
    print("[2/6] conectando a roxybrowser api...")
    roxy = RoxyBrowserAPI(ROXYBROWSER_API_URL, ROXY_WORKSPACE_ID)
    perfiles_api = roxy.get_profiles()

    if perfiles_api:
        print(f"       {len(perfiles_api)} perfiles detectados en roxybrowser:")
        for p in perfiles_api[:5]:
            print(f"         - {p.get('name', p.get('id', '?'))}")
    else:
        print("       advertencia: 0 perfiles detectados via api.")
        print("       intentando usar perfiles de deteccion local...")
        # usar perfiles de deteccion local como fallback
        perfiles_api = roxy_profiles

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
    # paso 4: websocket client
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

    ws.set_handshake({
        "pcbot_id": NOMBRE_PC,
        "hostname": NOMBRE_PC,
        "username": USUARIO_PC,
        "ip_local": IP_LOCAL,
        "ip_tailscale": IP_TAILSCALE,
        "ip_wan": pc_info["ip_wan"],
        "workspace_id": env_info.get("workspace_id", ROXY_WORKSPACE_ID),
        "perfiles_roxy": [
            {
                "id": p.get("id", ""),
                "name": p.get("name", p.get("id", "")),
                "status": p.get("state", p.get("status", "unknown")),
                "hash": p.get("hash_interno", p.get("hash", "")),
            }
            for p in roxy_profiles[:20]
        ],
        "perfiles_vip": perfiles_vip,
        "navegadores": pc_info["browsers"],
        "browser_debug": [
            {
                "name": name,
                "user_data_dir": info.get("user_data_dir", ""),
                "debug_port": info.get("debug_port", 0),
                "session_exists": info.get("session_exists", False),
            }
            for name, info in browsers.items()
            if isinstance(info, dict)
        ],
        "modo": _modo_actual,
        "version": "8.3",
        "kbt_generados": te.kbt_generados,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })

    # delegar todos los comandos al orchestrator
    async def on_command(cmd):
        global _modo_actual
        logger.info(f"comando recibido: {cmd.get('tipo', '?')}")
        result = await orchestrator.process_command(cmd)
        # si el comando cambia el modo, sincronizar
        if cmd.get("tipo") == "cambiar_modo" and result.get("ok"):
            nuevo_modo = cmd.get("modo", cmd.get("data", {}).get("modo", ""))
            if nuevo_modo:
                _modo_actual = nuevo_modo
                ws.cambiar_modo(nuevo_modo)
        return result

    ws.set_command_handler(on_command)

    # pasar referencia ws al orchestrator para estado de heartbeat
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
    print(f"  hostname:     {pc_info['hostname']}")
    print(f"  ip local:      {pc_info['ip_local']}")
    print(f"  tailscale:     {pc_info['tailscale_ip']}")
    print(f"  ip wan:        {pc_info['ip_wan']}")
    print(f"  usuario:       {pc_info['username']}")
    print(f"  perfiles:      {pc_info['roxy_profiles_count']} roxy + {pc_info['vip_count']} vip")
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
