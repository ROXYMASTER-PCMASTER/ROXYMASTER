"""
PRUEBA DE ORQUESTACION --- 5 pruebas extremo a extremo
Envia comandos al WebSocket de PCMASTER (Tailscale: 100.111.179.65:5006)
"""
import asyncio
import json
import websockets
import time
from datetime import datetime

PCMASTER_WS = "ws://100.111.179.65:5006"
CLIENT_ID = "pcbot-prueba"
TIMEOUT_CMD = 15

resultados = []

def log(prueba_num, mensaje, ok=None):
    ts = datetime.now().strftime("%H:%M:%S")
    icono = "[OK]" if ok is True else ("[FAIL]" if ok is False else "[..]")
    linea = f"{icono} [{ts}] PRUEBA {prueba_num}: {mensaje}"
    print(linea)
    if ok is not None:
        resultados.append((prueba_num, ok, mensaje))

async def prueba_1_abrir_perfil():
    """PRUEBA 1: Abrir un perfil en una URL por tiempo determinado"""
    log(1, "Conectando a PCMASTER...")
    try:
        async with websockets.connect(PCMASTER_WS, ping_interval=None, close_timeout=5) as ws:
            await ws.send(json.dumps({
                "type": "identify",
                "client_id": CLIENT_ID,
                "role": "admin",
                "profiles": []
            }))

            cmd = {
                "type": "open_url",
                "data": {
                    "url": "https://kick.com/test-stream",
                    "profile": "perfil_prueba_1",
                    "duration": 30,
                    "comentarios_activo": True,
                    "nivel": "medio"
                }
            }
            await ws.send(json.dumps(cmd))
            log(1, "Comando enviado: abrir kick.com/test-stream en perfil_prueba_1 por 30s")

            try:
                resp = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT_CMD)
                data = json.loads(resp)
                log(1, f"Respuesta: {json.dumps(data, ensure_ascii=False)[:200]}", ok=True)
            except asyncio.TimeoutError:
                log(1, "Timeout esperando respuesta", ok=False)
    except Exception as e:
        log(1, f"Error: {type(e).__name__}: {e}", ok=False)

async def prueba_2_enviar_comentario():
    """PRUEBA 2: Enviar comentario manual a perfil abierto"""
    log(2, "Conectando a PCMASTER...")
    try:
        async with websockets.connect(PCMASTER_WS, ping_interval=None, close_timeout=5) as ws:
            await ws.send(json.dumps({
                "type": "identify",
                "client_id": CLIENT_ID,
                "role": "admin",
                "profiles": []
            }))

            cmd = {
                "type": "comment",
                "data": {
                    "text": "no seee papa que buen stream!!",
                    "profile": "perfil_prueba_1",
                    "url": "https://kick.com/test-stream"
                }
            }
            await ws.send(json.dumps(cmd))
            log(2, "Comando enviado: comentario a perfil_prueba_1")

            try:
                resp = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT_CMD)
                data = json.loads(resp)
                log(2, f"Respuesta: {json.dumps(data, ensure_ascii=False)[:200]}", ok=True)
            except asyncio.TimeoutError:
                log(2, "Timeout esperando respuesta", ok=False)
    except Exception as e:
        log(2, f"Error: {type(e).__name__}: {e}", ok=False)

async def prueba_3_dos_perfiles_simultaneos():
    """PRUEBA 3: Abrir 2 perfiles simultaneos a la misma URL"""
    log(3, "Conectando a PCMASTER...")
    try:
        async with websockets.connect(PCMASTER_WS, ping_interval=None, close_timeout=5) as ws:
            await ws.send(json.dumps({
                "type": "identify",
                "client_id": CLIENT_ID,
                "role": "admin",
                "profiles": []
            }))

            cmd1 = {
                "type": "open_url",
                "data": {
                    "url": "https://kick.com/stream-simultaneo",
                    "profile": "perfil_A",
                    "duration": 60,
                    "comentarios_activo": True,
                    "nivel": "alto"
                }
            }
            await ws.send(json.dumps(cmd1))
            log(3, "Comando 1 enviado: perfil_A a kick.com/stream-simultaneo")

            await asyncio.sleep(1)

            cmd2 = {
                "type": "open_url",
                "data": {
                    "url": "https://kick.com/stream-simultaneo",
                    "profile": "perfil_B",
                    "duration": 60,
                    "comentarios_activo": True,
                    "nivel": "alto"
                }
            }
            await ws.send(json.dumps(cmd2))
            log(3, "Comando 2 enviado: perfil_B a kick.com/stream-simultaneo")

            respuestas = []
            for i in range(2):
                try:
                    resp = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT_CMD)
                    respuestas.append(json.loads(resp))
                except asyncio.TimeoutError:
                    log(3, f"Timeout en respuesta {i+1}/2")

            if len(respuestas) == 2:
                log(3, f"2 perfiles despachados simultaneamente. Respuestas: {len(respuestas)}", ok=True)
            else:
                log(3, f"Solo {len(respuestas)}/2 respuestas recibidas", ok=False)
    except Exception as e:
        log(3, f"Error: {type(e).__name__}: {e}", ok=False)

async def prueba_4_heartbeat():
    """PRUEBA 4: Verificar heartbeat (ping/pong)"""
    log(4, "Conectando a PCMASTER...")
    try:
        async with websockets.connect(PCMASTER_WS, ping_interval=5, ping_timeout=10, close_timeout=5) as ws:
            await ws.send(json.dumps({
                "type": "identify",
                "client_id": CLIENT_ID,
                "role": "admin",
                "profiles": []
            }))

            exitos = 0
            for i in range(5):
                try:
                    await ws.send(json.dumps({"type": "heartbeat"}))
                    resp = await asyncio.wait_for(ws.recv(), timeout=5)
                    data = json.loads(resp)
                    if data.get("type") == "heartbeat_ack":
                        exitos += 1
                        log(4, f"Heartbeat {i+1}/5: ACK recibido")
                except asyncio.TimeoutError:
                    log(4, f"Heartbeat {i+1}/5: TIMEOUT")
                except Exception as e:
                    log(4, f"Heartbeat {i+1}/5: Error: {type(e).__name__}")

                await asyncio.sleep(3)

            if exitos >= 4:
                log(4, f"Heartbeat: {exitos}/5 exitosos --- latencia estable", ok=True)
            elif exitos >= 1:
                log(4, f"Heartbeat: solo {exitos}/5 exitosos --- inestable", ok=False)
            else:
                log(4, "Heartbeat: 0/5 --- sin respuesta", ok=False)
    except Exception as e:
        log(4, f"Error: {type(e).__name__}: {e}", ok=False)

async def prueba_5_status_final():
    """PRUEBA 5: Obtener status global del servidor"""
    log(5, "Conectando a PCMASTER...")
    try:
        async with websockets.connect(PCMASTER_WS, ping_interval=None, close_timeout=5) as ws:
            await ws.send(json.dumps({
                "type": "identify",
                "client_id": CLIENT_ID,
                "role": "admin",
                "profiles": []
            }))

            await ws.send(json.dumps({"type": "get_status"}))
            log(5, "Comando get_status enviado")

            try:
                resp = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT_CMD)
                data = json.loads(resp)
                log(5, f"Status recibido: {json.dumps(data, ensure_ascii=False)[:300]}", ok=True)
            except asyncio.TimeoutError:
                log(5, "Timeout esperando status", ok=False)
    except Exception as e:
        log(5, f"Error: {type(e).__name__}: {e}", ok=False)

async def main():
    print("=" * 60)
    print("ROXYMASTER v6.1 --- PRUEBAS DE ORQUESTACION")
    print(f"PCMASTER: {PCMASTER_WS}")
    print(f"Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    pruebas = [
        ("1. Abrir perfil por tiempo", prueba_1_abrir_perfil),
        ("2. Enviar comentario", prueba_2_enviar_comentario),
        ("3. Dos perfiles simultaneos", prueba_3_dos_perfiles_simultaneos),
        ("4. Heartbeat", prueba_4_heartbeat),
        ("5. Status final", prueba_5_status_final),
    ]

    for nombre, funcion in pruebas:
        print(f"\n{'---' * 17}")
        print(f">>> {nombre}")
        print(f"{'---' * 17}")
        await funcion()
        await asyncio.sleep(2)

    print("\n" + "=" * 60)
    print("RESULTADOS FINALES")
    print("=" * 60)
    pasadas = sum(1 for _, ok, _ in resultados if ok)
    total = len(resultados)
    for num, ok, msg in resultados:
        icono = "[PASS]" if ok else "[FAIL]"
        print(f"  {icono} Prueba {num}: {msg[:80]}")

    print(f"\n>> {pasadas}/{total} pruebas pasadas")
    if pasadas == total:
        print("SISTEMA OPERATIVO --- Todas las pruebas pasaron")
    else:
        print(f"ATENCION: {total - pasadas} prueba(s) fallaron --- revisar logs")

    # Guardar en archivo
    with open("resultados_prueba.txt", "w", encoding="utf-8") as f:
        f.write(f"ROXYMASTER v6.1 --- Resultados de pruebas\n")
        f.write(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"{'=' * 60}\n")
        for num, ok, msg in resultados:
            f.write(f"  {'PASS' if ok else 'FAIL'} Prueba {num}: {msg}\n")
        f.write(f"\n{pasadas}/{total} pasadas\n")

if __name__ == "__main__":
    asyncio.run(main())