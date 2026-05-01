# ============================================================================
# ROXYMASTER v7.0 - MAIN ENTRY POINT (PCMASTER)
# Inicializa todos los modulos y arranca los servidores HTTP + WebSocket
# ============================================================================

import asyncio
import threading
import sys
import os
import signal

# Agregar scripts/ al path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import *
from auth import AuthManager
from orchestrator import Orchestrator
from marketplace import MarketplaceP2P
from ws_server import WSServer
from http_server import start_http_server

# Tokenomics (opcional)
try:
    from tokenomics import Tokenomics
    KBT_AVAILABLE = True
except ImportError:
    KBT_AVAILABLE = False
    print("[!] Tokenomics no disponible - KBT desactivado")

# SHS (opcional)
try:
    from shs import SecretManager
    SHS_AVAILABLE = True
except ImportError:
    SHS_AVAILABLE = False
    print("[!] SHS no disponible")


# ============================================================================
# INICIALIZACION
# ============================================================================
print("=" * 60)
print(f"  ROXYMASTER v{VERSION} - PCMASTER SERVER")
print(f"  IP Local: {IP_SERVIDOR}  |  IP Tailscale: {IP_TAILSCALE}")
print(f"  WS Port: {WS_PORT}  |  HTTP Port: {HTTP_PORT}")
print("=" * 60)

# Inicializar modulos
auth_manager = AuthManager()
orchestrator = Orchestrator()
marketplace = MarketplaceP2P()

# KBT Engine
if KBT_AVAILABLE:
    kbt_engine = Tokenomics()
    print(f"[KBT] Motor Tokenomics inicializado - {kbt_engine.get_stats().get('total_granjeros', 0)} granjeros")
else:
    kbt_engine = None

# SHS
if SHS_AVAILABLE:
    secret_manager = SecretManager()
    print(f"[SHS] SecretManager inicializado")
else:
    secret_manager = None

# ============================================================================
# SERVIDOR HTTP (en hilo separado)
# ============================================================================
print("[*] Iniciando servidor HTTP...")
httpd = start_http_server(
    orchestrator=orchestrator,
    auth_manager=auth_manager,
    kbt_engine=kbt_engine,
    marketplace=marketplace,
    admin_portal_path=ADMIN_PORTAL_PATH,
    portal_path=PORTAL_PATH,
    dashboard_path=DASHBOARD_PATH,
    host="0.0.0.0",
    port=HTTP_PORT
)

# Hilo HTTP
http_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
http_thread.start()

# ============================================================================
# SERVIDOR WEBSOCKET (asyncio)
# ============================================================================
print("[*] Iniciando servidor WebSocket...")
ws_server = WSServer(orchestrator, auth_manager, kbt_engine)


async def main_async():
    await ws_server.start(host="0.0.0.0", port=WS_PORT)
    # Mantener vivo
    while True:
        await asyncio.sleep(3600)


def run_ws():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main_async())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()


ws_thread = threading.Thread(target=run_ws, daemon=True)
ws_thread.start()

# ============================================================================
# MODO INTERACTIVO
# ============================================================================
print()
print("[*] PCMASTER LISTO")
print(f"[*] Admin Portal: http://{IP_SERVIDOR}:{HTTP_PORT}/admin")
print(f"[*] Dashboard API: http://{IP_SERVIDOR}:{HTTP_PORT}/api/dashboard")
print(f"[*] WebSocket: ws://{IP_SERVIDOR}:{WS_PORT}")
print()
print("Presiona Ctrl+C para detener...")

while True:
    try:
        cmd = input("PCMASTER> ").strip().lower()
        if cmd == "exit" or cmd == "salir":
            break
        elif cmd == "status" or cmd == "estado":
            d = orchestrator.get_dashboard()
            print(f"  PCBOTs: {d['pcbots_conectados']}/{d['pcbots_total']}")
            print(f"  Perfiles: {d['perfiles_total']} (activos:{d['perfiles_activos']} inactivos:{d['perfiles_inactivos']} colgados:{d['perfiles_colgados']})")
        elif cmd == "pcbots":
            for pid, info in orchestrator.pcbots_info.items():
                print(f"  {pid}: {info.get('estado','?')} | {info.get('hostname','?')} | perfiles:{len(info.get('perfiles',[]))}")
        elif cmd == "kbt":
            if kbt_engine:
                s = kbt_engine.get_stats()
                print(f"  Granjeros: {s['total_granjeros']} | Tokens circ: {s['tokens_en_circulacion']} | Perfiles: {s['total_perfiles']}")
            else:
                print("  KBT no disponible")
        elif cmd == "p2p":
            activas = marketplace.listar_activas()
            print(f"  Ofertas activas: {len(activas)}")
            for o in activas:
                print(f"    #{o['id']}: {o['tokens']}KBT @ {o['precio_soles']}SOL ({o['precio_token']}SOL/KBT) - {o['vendedor']}")
        elif cmd == "help" or cmd == "ayuda":
            print("  status  - Dashboard resumido")
            print("  pcbots  - Lista de PCBOTs")
            print("  kbt     - Estadisticas KBT")
            print("  p2p     - Ofertas del marketplace")
            print("  exit    - Salir")
        else:
            print(f"  Comando desconocido: {cmd} (usa 'help')")
    except KeyboardInterrupt:
        break
    except EOFError:
        # Modo no-interactivo (ejecutado desde .bat o terminal sin stdin)
        # Simplemente dormir y mantener vivos los servidores
        import time as _time
        _time.sleep(10)

print("\n[*] Deteniendo PCMASTER...")
httpd.shutdown()
print("[*] PCMASTER detenido.")