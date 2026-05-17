# _diag_crear_pedido.py - script temporal de diagnostico
# prueba el flujo completo de crear pedido y muestra cada paso
# no modifica endpoints ni archivos del sistema

import asyncio
import json
import sys
import os
import httpx
from datetime import datetime

# --- configuracion ---
BASE_URL = "http://localhost:8086"
LOGIN_URL = f"{BASE_URL}/api/login"
CREAR_PEDIDO_URL = f"{BASE_URL}/api/pedidos/crear"

async def diagnostico():
    print("=" * 60)
    print(f"DIAGNOSTICO CREAR PEDIDO - {datetime.now().isoformat()}")
    print("=" * 60)

    # paso 1: login
    print("\n[1] HACIENDO LOGIN...")
    async with httpx.AsyncClient() as client:
        login_body = {
            "email": "prueba1@roxymaster.local",
            "password": "12345678"
        }
        print(f"  body: {json.dumps(login_body, ensure_ascii=False)}")
        try:
            r = await client.post(LOGIN_URL, json=login_body, timeout=10)
            print(f"  status: {r.status_code}")
            print(f"  respuesta: {r.text[:500]}")
            data = r.json()
        except Exception as e:
            print(f"  ERROR CONEXION: {e}")
            return

    if not data.get("exito"):
        print("  FALLO: login no exitoso")
        return

    token = data.get("token") or data.get("access_token")
    print(f"  token obtenido: {token[:40]}...")

    # paso 2: ver wallet
    print("\n[2] VERIFICANDO WALLET...")
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.get(f"{BASE_URL}/api/wallet", headers=headers, timeout=10)
        print(f"  status: {r.status_code}")
        print(f"  wallet: {r.text[:500]}")

    # paso 3: ver pcbots conectados
    print("\n[3] PCBOTS CONECTADOS...")
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}/api/ws/estado", timeout=10)
        print(f"  status: {r.status_code}")
        print(f"  ws_estado: {r.text[:500]}")

    # paso 4: calcular costo primero
    print("\n[4] CALCULANDO COSTO...")
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {token}"}
        calcular_body = {
            "seguidores": 100,
            "perfiles": 2,
            "horas": 0.167,  # 10 minutos
            "nivel_comentarios": "basico",
            "tipo_pedido": "vistas"
        }
        print(f"  body: {json.dumps(calcular_body, ensure_ascii=False)}")
        r = await client.post(f"{BASE_URL}/api/pedidos/calcular_costo", json=calcular_body, headers=headers, timeout=10)
        print(f"  status: {r.status_code}")
        print(f"  respuesta: {r.text[:500]}")

    # paso 5: crear pedido CON CAMPOS DEL FRONTEND
    print("\n[5] CREANDO PEDIDO (con campos del frontend: minutos, tipo)...")
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {token}"}
        pedido_body_frontend = {
            "url": "https://kick.com/diagtest",
            "seguidores": 100,
            "perfiles": 2,
            "minutos": 10,      # campo del frontend
            "nivel_comentarios": "basico",
            "tipo": "vistas"     # campo del frontend
        }
        print(f"  body frontend: {json.dumps(pedido_body_frontend, ensure_ascii=False)}")
        r = await client.post(CREAR_PEDIDO_URL, json=pedido_body_frontend, headers=headers, timeout=15)
        print(f"  status: {r.status_code}")
        print(f"  respuesta: {r.text[:1000]}")

    # paso 6: crear pedido CON CAMPOS DE API DIRECTA
    print("\n[6] CREANDO PEDIDO (con campos de api directa: horas, tipo_pedido)...")
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {token}"}
        pedido_body_api = {
            "url": "https://kick.com/diagtest2",
            "seguidores": 100,
            "perfiles": 1,
            "horas": 0.167,      # campo de api directa
            "nivel_comentarios": "basico",
            "tipo_pedido": "vistas"  # campo de api directa
        }
        print(f"  body api: {json.dumps(pedido_body_api, ensure_ascii=False)}")
        r = await client.post(CREAR_PEDIDO_URL, json=pedido_body_api, headers=headers, timeout=15)
        print(f"  status: {r.status_code}")
        print(f"  respuesta: {r.text[:1000]}")

    # paso 7: ver pedidos creados
    print("\n[7] LISTANDO MIS PEDIDOS...")
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {token}"}
        r = await client.get(f"{BASE_URL}/api/pedidos/mis_pedidos", headers=headers, timeout=10)
        print(f"  status: {r.status_code}")
        data = r.json()
        pedidos = data.get("pedidos", [])
        print(f"  total pedidos: {len(pedidos)}")
        if pedidos:
            for p in pedidos[:3]:
                print(f"    id={p.get('id')} estado={p.get('estado')} url={p.get('url')[:30]}")

    print("\n" + "=" * 60)
    print("DIAGNOSTICO COMPLETADO")
    print("REVISA LOS LOGS DEL SERVIDOR PARA VER [PEDIDO-LOG] paso X/6")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(diagnostico())