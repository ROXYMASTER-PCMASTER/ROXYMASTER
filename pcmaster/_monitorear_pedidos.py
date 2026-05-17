# _monitorear_pedidos.py - monitorea pedidos entrantes y su envio a pcbot
# corre en loop mostrando en tiempo real los pedidos que llegan y se procesan
# ejecutar con: python _monitorear_pedidos.py

import sqlite3
import os
import time
import json

def get_db():
    base = os.path.dirname(__file__)
    ruta = os.path.join(base, "data", "roxymaster.db")
    if not os.path.exists(ruta):
        ruta = os.path.join(base, "scripts", "data", "roxymaster.db")
    return ruta

db_path = get_db()
print(f"db: {db_path}")
print("monitoreando pedidos y comandos... (ctrl+c para salir)")
print()

ultimo_pedido_id = 0
ultimo_comando_id = 0
ultimo_log_lineas = 0

while True:
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # pedidos nuevos
        c.execute("select id, usuario_id, url, cantidad, estado from pedidos order by id desc limit 5")
        pedidos = c.fetchall()
        for p in pedidos:
            if p["id"] > ultimo_pedido_id:
                print(f"[PEDIDO] id={p['id']} usuario={p['usuario_id']} url={p['url']} cant={p['cantidad']} estado={p['estado']}")
        
        if pedidos:
            ultimo_pedido_id = max(p["id"] for p in pedidos)

        # comandos recientes
        c.execute("select id, comando_id, tipo, estado, pcbot_id, creado_en from comandos order by id desc limit 10")
        comandos = c.fetchall()
        for cmd in comandos:
            if cmd["id"] > ultimo_comando_id:
                print(f"[COMANDO] id={cmd['id']} tipo={cmd['tipo']} estado={cmd['estado']} pcbot={cmd['pcbot_id']} creado={cmd['creado_en']}")
        
        if comandos:
            ultimo_comando_id = max(cmd["id"] for cmd in comandos)

        conn.close()

        # ultimas lineas del server log
        log_path = os.path.join(base, "server_out.txt") if os.path.exists(os.path.join(os.path.dirname(__file__), "server_out.txt")) else os.path.join(os.path.dirname(__file__), "scripts", "server_out.txt")
        if os.path.exists(log_path):
            with open(log_path, "r") as f:
                lineas = f.readlines()
            if len(lineas) > ultimo_log_lineas:
                for i in range(ultimo_log_lineas, len(lineas)):
                    linea = lineas[i].strip()
                    if any(x in linea for x in ["[HB]", "[PEDIDOS-DIAG]", "[ORCH-DIAG]", "[WSM-DIAG]", "[DIAG-SYNC]", "[SERVER-DIAG]", "_enviar_pendientes", "crear_comando", "asignar"]):
                        print(f"[LOG] {linea}")
                ultimo_log_lineas = len(lineas)

    except Exception as e:
        print(f"[ERROR] {e}")

    time.sleep(5)