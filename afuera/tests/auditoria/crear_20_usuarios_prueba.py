"""
script: crear 20 usuarios de prueba con datos completos en todas las tablas
uso: python crear_20_usuarios_prueba.py
nota: todos los emails llevan prefijo test_ para facil rastreo y limpieza
      eliminar con: python -c "from crear_20_usuarios_prueba import limpiar_todo; limpiar_todo()"
"""
import sqlite3
import hashlib
import os
import uuid
from datetime import datetime, timedelta

DB_PATH = r"pcmaster\data\roxymaster.db"

# contrasena fija para todos los test (hash pbkdf2-sha256 100k iteraciones)
TEST_PASS = "Test0r!2024"

def hash_password(password):
    """misma logica que server.py: pbkdf2-hmac-sha256 100000 iteraciones"""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)
    return salt.hex() + ':' + dk.hex()

def generar_token():
    return uuid.uuid4().hex + uuid.uuid4().hex[:16]

def crear_usuarios_prueba():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # --- datos base de 20 usuarios "reales" ---
    usuarios_data = [
        # (email, username, wallet, nivel_fiabilidad, referido_por, modo, uptime_horas, pcbot_id)
        ("test_alex_01@test.com", "alexgamer", "0xAb5801a7D398351b8bE11C439e05C5B3259aeC9B", "platino", "pcmaster", "pidiendo", 1200, "pcbot-001"),
        ("test_maria_02@test.com", "maria_kick", "0x28C6c06298d514Db089934071355E5743bf33603", "oro", "pcmaster", "conectado", 850, "pcbot-002"),
        ("test_carlos_03@test.com", "carlos_stream", "0x9F8F72aA9304c8B593d555F12eF6589cC3D579f2", "oro", "test_alex_01@test.com", "pidiendo", 720, "pcbot-003"),
        ("test_laura_04@test.com", "laura_twitch", "0xE6C7E0D1a8Cb3f1b5Dc9E8f2a6B4d0C3e7F1a2B3", "plata", "test_alex_01@test.com", "conectado", 540, "pcbot-004"),
        ("test_pedro_05@test.com", "pedro_perfil", "0xD2B9c8f1a3E7d0C5b6F4e8A2d1C9b3F7e0D5a8E", "plata", "test_maria_02@test.com", "conectado", 380, "pcbot-005"),
        ("test_ana_06@test.com", "ana_views", "0xF4c3B2a1D9e8F7d6C5b4A3e2D1f0E9c8B7a6F5d4", "bronce", "test_maria_02@test.com", "conectado", 200, "pcbot-006"),
        ("test_jorge_07@test.com", "jorge_farm", "0xB8a7F6c5D4e3B2a1F0d9E8c7D6b5A4f3C2e1D0b9", "plata", "pcmaster", "pidiendo", 620, "pcbot-007"),
        ("test_sofia_08@test.com", "sofia_miner", "0xC3d4E5f6A7b8C9d0E1f2A3b4C5d6E7f8A9b0C1d2", "oro", "test_jorge_07@test.com", "conectado", 910, "pcbot-008"),
        ("test_diego_09@test.com", "diego_bot", "0xF2e1D0c9B8a7F6e5D4c3B2a1F0e9D8c7B6a5F4e3", "bronce", "pcmaster", "conectado", 150, "pcbot-009"),
        ("test_carmen_10@test.com", "carmen_kick", "0xA9b8C7d6E5f4G3h2I1j0K9l8M7n6O5p4Q3r2S1t0", "plata", "test_sofia_08@test.com", "pidiendo", 450, "pcbot-010"),
        ("test_pablo_11@test.com", "pablo_twitch", "0xB0c1D2e3F4g5H6i7J8k9L0m1N2o3P4q5R6s7T8u9", "oro", "test_alex_01@test.com", "conectado", 760, "pcbot-011"),
        ("test_luis_12@test.com", "luis_stream", "0xC1d2E3f4G5h6I7j8K9l0M1n2O3p4Q5r6S7t8U9v0", "bronce", "pcmaster", "conectado", 90, "pcbot-012"),
        ("test_elena_13@test.com", "elena_vip", "0xD2e3F4g5H6i7J8k9L0m1N2o3P4q5R6s7T8u9V0w1", "platino", "test_pablo_11@test.com", "pidiendo", 1100, "pcbot-013"),
        ("test_roberto_14@test.com", "roberto_farm", "0xE3f4G5h6I7j8K9l0M1n2O3p4Q5r6S7t8U9v0W1x2", "plata", "test_elena_13@test.com", "conectado", 510, "pcbot-014"),
        ("test_veronica_15@test.com", "veronica_miner", "0xF4g5H6i7J8k9L0m1N2o3P4q5R6s7T8u9V0w1X2y3", "oro", "pcmaster", "conectado", 880, "pcbot-015"),
        ("test_andres_16@test.com", "andres_kick", "0xA5b6C7d8E9f0G1h2I3j4K5l6M7n8O9p0Q1r2S3t4", "bronce", "test_veronica_15@test.com", "conectado", 180, "pcbot-016"),
        ("test_valeria_17@test.com", "valeria_twitch", "0xB6c7D8e9F0g1H2i3J4k5L6m7N8o9P0q1R2s3T4u5", "plata", "test_maria_02@test.com", "pidiendo", 490, "pcbot-017"),
        ("test_fernando_18@test.com", "fernando_stream", "0xC7d8E9f0G1h2I3j4K5l6M7n8O9p0Q1r2S3t4U5v6", "oro", "test_valeria_17@test.com", "conectado", 830, "pcbot-018"),
        ("test_patricia_19@test.com", "patricia_vip", "0xD8e9F0g1H2i3J4k5L6m7N8o9P0q1R2s3T4u5V6w7", "platino", "pcmaster", "pidiendo", 1350, "pcbot-019"),
        ("test_gustavo_20@test.com", "gustavo_farm", "0xE9f0G1h2I3j4K5l6M7n8O9p0Q1r2S3t4U5v6W7x8", "plata", "test_patricia_19@test.com", "conectado", 560, "pcbot-020"),
    ]

    password_hash = hash_password(TEST_PASS)
    ahora = datetime.now()

    wallets_balance = [2500.0, 1800.0, 920.0, 650.0, 410.0, 180.0, 780.0, 1500.0, 120.0, 530.0,
                1340.0, 60.0, 3200.0, 590.0, 2100.0, 200.0, 480.0, 1100.0, 4100.0, 670.0]
    wallets_minado = [4200.0, 3100.0, 1800.0, 1100.0, 700.0, 280.0, 1300.0, 2600.0, 190.0, 890.0,
               2200.0, 100.0, 5600.0, 980.0, 3600.0, 320.0, 810.0, 1900.0, 7200.0, 1150.0]

    usuarios_ids = []
    for i, row in enumerate(usuarios_data):
        email, username, wallet, nivel, referido, modo, uptime, pcbot_id = row
        # fecha registro escalonada: cada uno 3 dias antes
        fecha_reg = (ahora - timedelta(days=(20 - i) * 3)).strftime("%Y-%m-%d %H:%M:%S")
        ultimo_login = (ahora - timedelta(hours=i * 2)).strftime("%Y-%m-%d %H:%M:%S")
        codigo_ref = "TEST" + str(i+1).zfill(2) + uuid.uuid4().hex[:4].upper()
        c.execute("""
            INSERT INTO usuarios (email, password_hash, username, rol, wallet, codigo_referido,
                referido_por, referido_cambiado, nivel_fiabilidad, uptime_horas, pcbot_id,
                modo, ultimo_login, fecha_registro, activo, roxy_api_key, roxy_workspace_id)
            VALUES (?, ?, ?, 'usuario', ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        """, (email, password_hash, username, wallet, codigo_ref,
              referido, nivel, uptime, pcbot_id, modo, ultimo_login, fecha_reg,
              "roxy_key_" + str(i+1).zfill(2) + "_" + uuid.uuid4().hex[:12],
              "ws_" + str(i+1).zfill(2) + "_" + uuid.uuid4().hex[:8]))
        usuarios_ids.append(c.lastrowid)
        print("  [OK] usuario " + str(i+1) + ": " + email + " (id=" + str(c.lastrowid) + ", ref=" + codigo_ref + ")")

    # --- wallets (1 por usuario) ---
    for i, uid in enumerate(usuarios_ids):
        bal = wallets_balance[i]
        minado = wallets_minado[i]
        recolectado = round(minado * 0.7, 2)
        comprado = bal if i < 10 else 0
        retirado = round(bal * 0.2, 2) if i > 0 else 0
        staking = round(bal * 0.3, 2) if i % 3 == 0 else 0
        if staking > 0:
            staking_desde = (ahora - timedelta(days=30 + i * 5)).strftime("%Y-%m-%d")
        else:
            staking_desde = None
        actualizado = (ahora - timedelta(hours=i)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            INSERT INTO wallets (usuario_id, balance, minado_total, recolectado_total,
                comprado_total, retirado_total, staking_total, staking_desde, actualizado)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (uid, bal, minado, recolectado, comprado, retirado, staking, staking_desde, actualizado))
        print("  [OK] wallet " + str(i+1) + ": usuario " + str(uid) + " balance=" + str(bal))

    # --- codigos_referido ---
    for i, uid in enumerate(usuarios_ids):
        codigo = "TEST" + str(i+1).zfill(2) + uuid.uuid4().hex[:4].upper()
        c.execute("INSERT INTO codigos_referido (usuario_id, codigo, activo) VALUES (?, ?, 1)",
                  (uid, codigo))

    # --- perfiles (2 por usuario = 40 perfiles) ---
    tipos_perfil = ["kick", "twitch", "youtube", "local"]
    estados_perfil = ["activo", "inactivo", "suspendido"]
    letras = ["a", "b"]
    for i, uid in enumerate(usuarios_ids):
        for j in range(2):
            tipo = tipos_perfil[(i + j) % 4]
            estado = estados_perfil[i % 3]
            nombre = "perfil_" + str(i+1) + "_" + letras[j]
            horas_conn = round((i + 1) * 12.5 + j * 8, 1)
            horas_uso = round(horas_conn * 0.65, 1)
            horas_hh = round(horas_uso * 0.15, 1)
            ip = "181." + str(64 + (i % 50)) + "." + str(1 + (j * 50)) + "." + str(i + 10)
            ultimo_hb = (ahora - timedelta(minutes=5 + i * 3)).strftime("%Y-%m-%d %H:%M:%S")
            c.execute("""
                INSERT INTO perfiles (usuario_id, nombre_perfil, tipo, estado, ip_wan,
                    horas_conexion, horas_en_uso, horas_hh, ultimo_heartbeat)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (uid, nombre, tipo, estado, ip, horas_conn, horas_uso, horas_hh, ultimo_hb))
    print("  [OK] 40 perfiles creados (2 por usuario)")

    # --- sesiones (token por usuario activo) ---
    for i in range(15):
        uid = usuarios_ids[i]
        token = generar_token()
        email = usuarios_data[i][0]
        expiracion = (ahora + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        creacion = (ahora - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            INSERT INTO sesiones (token, usuario_id, email, rol, fecha_creacion, fecha_expiracion)
            VALUES (?, ?, ?, 'usuario', ?, ?)
        """, (token, uid, email, creacion, expiracion))
    print("  [OK] 15 sesiones activas creadas")

    # --- ordenes_p2p (15 ordenes) ---
    for i in range(15):
        vendedor_id = usuarios_ids[i]
        cantidad = round(50 + i * 15.5, 2)
        precio = round(0.85 + i * 0.03, 4)
        tipo = "venta" if i < 10 else "compra"
        estado = "abierta" if i < 12 else "completada"
        fecha_creacion = (ahora - timedelta(days=i * 2)).strftime("%Y-%m-%d %H:%M:%S")
        fecha_completada = None
        comprador_id = None
        if estado == "completada":
            fecha_completada = (ahora - timedelta(days=i * 2 - 1)).strftime("%Y-%m-%d %H:%M:%S")
            comprador_id = usuarios_ids[(i + 5) % 20]
        c.execute("""
            INSERT INTO ordenes_p2p (vendedor_id, comprador_id, cantidad_kbt, precio_pen, tipo, estado,
                fecha_creacion, fecha_completada)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (vendedor_id, comprador_id, cantidad, precio, tipo, estado, fecha_creacion, fecha_completada))
    print("  [OK] 15 ordenes p2p creadas")

    # --- transacciones (20) ---
    tipos_tx = ["minado", "recoleccion", "compra", "venta", "referido", "bonus", "staking"]
    conceptos = [
        "minado de perfiles 24h", "recoleccion automatica semanal",
        "compra de kbt en mercado", "venta de kbt a usuario",
        "comision de referido nivel 1", "bonus happy hour",
        "recompensa staking mensual"
    ]
    for i in range(20):
        origen = usuarios_ids[i % 20]
        destino = usuarios_ids[(i + 7) % 20]
        tipo = tipos_tx[i % 7]
        monto = round(5 + i * 3.25, 2)
        concepto = conceptos[i % 7]
        fecha = (ahora - timedelta(days=i * 1.5, hours=i)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            INSERT INTO transacciones (origen_id, destino_id, tipo, monto, concepto, fecha)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (origen, destino, tipo, monto, concepto, fecha))
    print("  [OK] 20 transacciones creadas")

    # --- referidos (arbol) ---
    # (referido_id_index, referidor_id_index, nivel)
    referidos_data = [
        (3, 1, 1),   # carlos referido por alex (n1)
        (4, 1, 1),   # laura referida por alex (n1)
        (6, 2, 1),   # ana referida por maria (n1)
        (8, 7, 1),   # sofia referida por jorge (n1)
        (10, 8, 2),  # carmen referida por sofia (n2)
        (11, 1, 1),  # pablo referido por alex (n1)
        (13, 11, 1), # elena referida por pablo (n1)
        (14, 13, 2), # roberto referido por elena (n2)
        (16, 15, 1), # andres referido por veronica (n1)
        (18, 17, 1), # fernando referido por valeria (n1)
        (20, 19, 1), # gustavo referido por patricia (n1)
    ]
    for refdo_idx, refdor_idx, nivel in referidos_data:
        refdo_id = usuarios_ids[refdo_idx - 1]
        refdor_id = usuarios_ids[refdor_idx - 1]
        comisiones = round(10 + nivel * 5 + refdo_idx * 0.5, 2)
        fecha_act = (ahora - timedelta(days=30 + refdo_idx * 2)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            INSERT INTO referidos (referidor_id, referido_id, nivel, comisiones_generadas, fecha_activacion)
            VALUES (?, ?, ?, ?, ?)
        """, (refdor_id, refdo_id, nivel, comisiones, fecha_act))
    print("  [OK] 11 referidos creados")

    # --- mensajes (25) ---
    mensajes_txt = [
        "hola, como va el minado hoy?",
        "recibi el pago de las comisiones, gracias!",
        "necesito mas perfiles para la proxima hora feliz",
        "el marketplace tiene buenos precios esta semana",
        "puedes revisar mi solicitud de retiro?",
        "como configuro un nuevo perfil de kick?",
        "el bot dejo de funcionar, que hago?",
        "las ganancias de hoy fueron excelentes!",
        "cuando es la proxima actualizacion?",
        "tienes referidos nuevos en tu arbol?",
        "mi wallet no actualiza el balance",
        "felicidades por el nivel platino!",
        "puedo aumentar mi limite de ordenes?",
        "el soporte tecnico responde rapido",
        "como funciona el staking de kbt?",
        "los perfiles de twitch rinden mejor",
        "necesito ayuda con la instalacion del agente",
        "el multiplicador de happy hour esta activo",
        "recibi un bono por registro, gracias!",
        "como veo mi historial de transacciones?",
        "el panel admin muestra datos incorrectos",
        "se puede minar en multiples pcs?",
        "la ip tailscale cambio, como actualizo?",
        "los retiros demoran cuanto tiempo?",
        "excelente servicio, recomendare a mas gente"
    ]
    for i, texto in enumerate(mensajes_txt[:25]):
        origen_id = usuarios_ids[i % 20]
        destino_id = usuarios_ids[(i + 3) % 20]
        leido = 1 if i % 4 == 0 else 0
        fecha = (ahora - timedelta(days=i, hours=i * 3)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            INSERT INTO mensajes (origen_id, destino_id, texto, leido, fecha, asunto)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (origen_id, destino_id, texto, leido, fecha, "asunto mensaje " + str(i+1)))
    print("  [OK] 25 mensajes creados")

    # --- urls_asignadas (10) ---
    urls = [
        ("https://kick.com/testchannel1", "testchannel1", 3, 120, 2),
        ("https://twitch.tv/testchannel2", "testchannel2", 5, 240, 4),
        ("https://youtube.com/@testchannel3", "testchannel3", 2, 60, 1),
        ("https://kick.com/testchannel4", "testchannel4", 4, 180, 3),
        ("https://twitch.tv/testchannel5", "testchannel5", 6, 300, 5),
        ("https://kick.com/testchannel6", "testchannel6", 2, 90, 1),
        ("https://youtube.com/@testchannel7", "testchannel7", 3, 150, 2),
        ("https://twitch.tv/testchannel8", "testchannel8", 4, 200, 3),
        ("https://kick.com/testchannel9", "testchannel9", 5, 240, 4),
        ("https://twitch.tv/testchannel10", "testchannel10", 3, 120, 2),
    ]
    for i, (url, streamer, perfiles, duracion, comentarios) in enumerate(urls):
        estado = "activa" if i < 7 else "completada"
        fecha_asig = (ahora - timedelta(days=int(15 - i * 1.5))).strftime("%Y-%m-%d %H:%M:%S")
        if estado == "completada":
            fecha_fin = (ahora - timedelta(days=int(5 - i * 1.5))).strftime("%Y-%m-%d %H:%M:%S")
        else:
            fecha_fin = None
        pcbot_id = "pcbot-" + str(i+1).zfill(3) if i < 5 else None
        c.execute("""
            INSERT INTO urls_asignadas (url, streamer, perfiles_asignados, duracion_min,
                comentarios_activos, estado, fecha_asignacion, fecha_fin, pcbot_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (url, streamer, perfiles, duracion, comentarios, estado, fecha_asig, fecha_fin, pcbot_id))
    print("  [OK] 10 urls asignadas creadas")

    # --- sesiones_activas (8) ---
    for i in range(8):
        perfil_id = "perfil_sesion_" + str(i+1)
        url = "https://kick.com/live_channel_" + str(i+1)
        streamer = "streamer_" + str(i+1)
        estado = "activo" if i < 5 else "pausado"
        inicio = (ahora - timedelta(hours=2 + i)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("""
            INSERT INTO sesiones_activas (perfil_id, url, streamer, estado, inicio)
            VALUES (?, ?, ?, ?, ?)
        """, (perfil_id, url, streamer, estado, inicio))
    print("  [OK] 8 sesiones activas creadas")

    # --- comandos (12) ---
    for i in range(12):
        comando_id = "cmd_" + uuid.uuid4().hex[:8]
        if i % 3 == 0:
            tipo = "iniciar"
        elif i % 3 == 1:
            tipo = "detener"
        else:
            tipo = "actualizar"
        estado = "ejecutado" if i < 8 else "pendiente"
        parametros = '{"perfiles": ' + str(i+1) + ', "duracion": ' + str(60 + i * 30) + '}'
        fecha_creacion = (ahora - timedelta(days=i)).strftime("%Y-%m-%d %H:%M:%S")
        if estado == "ejecutado":
            fecha_ejecucion = (ahora - timedelta(days=i, hours=-2)).strftime("%Y-%m-%d %H:%M:%S")
            resultado = "ok"
        else:
            fecha_ejecucion = None
            resultado = None
        pcbot_id = "pcbot-" + str((i % 10) + 1).zfill(3)
        c.execute("""
            INSERT INTO comandos (comando_id, tipo, parametros, estado, fecha_creacion,
                fecha_ejecucion, resultado, streamer, pcbot_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (comando_id, tipo, parametros, estado, fecha_creacion, fecha_ejecucion, resultado,
              "streamer_" + str(i+1), pcbot_id))
    print("  [OK] 12 comandos creados")

    # --- retiros (8) ---
    estados_retiro = ["pendiente", "aprobado", "completado", "rechazado"]
    for i in range(8):
        uid = usuarios_ids[i]
        cantidad_kbt = round(50 + i * 25, 2)
        cantidad_pen = round(cantidad_kbt * 0.92, 2)
        comision = round(cantidad_kbt * 0.08, 2)
        estado = estados_retiro[i % 4]
        fecha_sol = (ahora - timedelta(days=10 - i)).strftime("%Y-%m-%d %H:%M:%S")
        if estado != "pendiente":
            fecha_proc = (ahora - timedelta(days=9 - i)).strftime("%Y-%m-%d %H:%M:%S")
        else:
            fecha_proc = None
        c.execute("""
            INSERT INTO retiros (usuario_id, cantidad_kbt, cantidad_pen, comision, estado,
                fecha_solicitud, fecha_procesado)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (uid, cantidad_kbt, cantidad_pen, comision, estado, fecha_sol, fecha_proc))
    print("  [OK] 8 retiros creados")

    conn.commit()
    conn.close()
    print("\n=== TOTAL: 20 usuarios creados con datos completos ===")
    print("contrasena de todos los test: " + TEST_PASS)
    print('para eliminar: python -c "from crear_20_usuarios_prueba import limpiar_todo; limpiar_todo()"')
    return usuarios_ids


def limpiar_todo():
    """elimina todos los usuarios test_ y sus datos asociados"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM usuarios WHERE email LIKE 'test_%'")
    ids = [r[0] for r in c.fetchall()]
    if not ids:
        print("no hay usuarios test_ para limpiar")
        conn.close()
        return
    ids_str = ",".join(str(i) for i in ids)
    tables = ["codigos_referido", "wallets", "sesiones", "perfiles", "ordenes_p2p",
              "transacciones", "referidos", "mensajes", "retiros"]
    for t in tables:
        if t == "ordenes_p2p":
            c.execute("DELETE FROM " + t + " WHERE vendedor_id IN (" + ids_str + ") OR comprador_id IN (" + ids_str + ")")
        elif t == "mensajes":
            c.execute("DELETE FROM " + t + " WHERE origen_id IN (" + ids_str + ") OR destino_id IN (" + ids_str + ")")
        elif t == "referidos":
            c.execute("DELETE FROM " + t + " WHERE referidor_id IN (" + ids_str + ") OR referido_id IN (" + ids_str + ")")
        elif t == "transacciones":
            c.execute("DELETE FROM " + t + " WHERE origen_id IN (" + ids_str + ") OR destino_id IN (" + ids_str + ")")
        else:
            c.execute("DELETE FROM " + t + " WHERE usuario_id IN (" + ids_str + ")")
    c.execute("DELETE FROM usuarios WHERE id IN (" + ids_str + ")")
    conn.commit()
    conn.close()
    print("limpiados " + str(len(ids)) + " usuarios test_ y todos sus datos asociados")


if __name__ == "__main__":
    print("creando 20 usuarios de prueba con datos completos...\n")
    crear_usuarios_prueba()