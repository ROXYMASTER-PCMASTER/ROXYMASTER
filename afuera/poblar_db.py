# poblar_db.py - inserta 20 cuentas reales con datos coherentes en roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

import hashlib
import secrets
import uuid
import random
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from db import ejecutar_sql, ejecutar_sql_unico, ejecutar_insercion, init_db

# ---------------------------------------------------------------------------
# configuracion
# ---------------------------------------------------------------------------
hash_iteraciones = 310000

# ---------------------------------------------------------------------------
# datos de 20 usuarios realistas
# ---------------------------------------------------------------------------
usuarios_data = [
    {"email": "carlos.mendoza@gmail.com", "username": "carlos_mendoza", "nombre": "carlos mendoza"},
    {"email": "maria.lopez@outlook.com", "username": "maria_lopez", "nombre": "maria lopez"},
    {"email": "jose.ramirez@yahoo.com", "username": "jose_ramirez", "nombre": "jose ramirez"},
    {"email": "ana.torres@hotmail.com", "username": "ana_torres", "nombre": "ana torres"},
    {"email": "luis.fernandez@gmail.com", "username": "luis_fernandez", "nombre": "luis fernandez"},
    {"email": "carmen.diaz@outlook.com", "username": "carmen_diaz", "nombre": "carmen diaz"},
    {"email": "pedro.martinez@yahoo.com", "username": "pedro_martinez", "nombre": "pedro martinez"},
    {"email": "sofia.garcia@gmail.com", "username": "sofia_garcia", "nombre": "sofia garcia"},
    {"email": "diego.rodriguez@hotmail.com", "username": "diego_rodriguez", "nombre": "diego rodriguez"},
    {"email": "valentina.morales@outlook.com", "username": "valentina_morales", "nombre": "valentina morales"},
    {"email": "andres.castillo@gmail.com", "username": "andres_castillo", "nombre": "andres castillo"},
    {"email": "laura.vega@yahoo.com", "username": "laura_vega", "nombre": "laura vega"},
    {"email": "ricardo.navarro@hotmail.com", "username": "ricardo_navarro", "nombre": "ricardo navarro"},
    {"email": "paola.rivas@gmail.com", "username": "paola_rivas", "nombre": "paola rivas"},
    {"email": "miguel.silva@outlook.com", "username": "miguel_silva", "nombre": "miguel silva"},
    {"email": "gabriela.herrera@yahoo.com", "username": "gabriela_herrera", "nombre": "gabriela herrera"},
    {"email": "jorge.medina@gmail.com", "username": "jorge_medina", "nombre": "jorge medina"},
    {"email": "diana.cruz@hotmail.com", "username": "diana_cruz", "nombre": "diana cruz"},
    {"email": "fernando.campos@outlook.com", "username": "fernando_campos", "nombre": "fernando campos"},
    {"email": "elena.vargas@gmail.com", "username": "elena_vargas", "nombre": "elena vargas"},
]

niveles_fiabilidad = ["bronce", "bronce", "plata", "plata", "plata", "plata", "oro", "oro", "oro", "oro", "oro", "platino", "platino", "platino", "diamante", "diamante", "diamante", "diamante", "diamante", "diamante"]

# ips wan realistas (peruanas)
ips_wan_pool = [
    "190.42.113.45", "190.42.114.78", "190.42.115.12", "200.106.23.67",
    "200.106.24.89", "200.106.25.34", "181.67.45.23", "181.67.46.78",
    "181.67.47.90", "190.43.12.56", "190.43.13.78", "190.43.14.90",
    "200.107.67.23", "200.107.68.45", "200.107.69.78", "181.68.23.12",
    "181.68.24.34", "181.68.25.56", "190.44.78.90", "190.44.79.23",
]

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def encriptar_password(password: str) -> str:
    """genera un hash pbkdf2-hmac-sha256 completo con formato pbkdf2:iteraciones:salt:hash."""
    salt = secrets.token_hex(24)
    hash_bytes = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"),
        hash_iteraciones, dklen=64,
    )
    return f"pbkdf2:{hash_iteraciones}:{salt}:{hash_bytes.hex()}"

def generar_codigo_referido() -> str:
    """genera codigo de referido unico de 8 caracteres."""
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(random.choices(chars, k=8))

def generar_token() -> str:
    """genera un token de sesion."""
    return uuid.uuid4().hex + secrets.token_hex(16)

# ---------------------------------------------------------------------------
# insercion principal
# ---------------------------------------------------------------------------
def poblar():
    """inserta 20 usuarios con todos los campos llenos."""
    print("poblando base de datos con 20 cuentas reales...")
    print("")

    # asegurar que existan tablas
    init_db()

    # obtener usuarios existentes
    usuarios_existentes = ejecutar_sql("select email from usuarios")
    emails_existentes = {u["email"] for u in usuarios_existentes}

    insertados = 0
    codigos_usados_lista = []
    ids_nuevos = []

    for i, u in enumerate(usuarios_data):
        email = u["email"]
        if email in emails_existentes:
            print(f"  [skip] {email} ya existe")
            continue

        username = u["username"]
        password = "Roxy2024!"
        password_hash = encriptar_password(password)

        wallet = "kbt_" + uuid.uuid4().hex[:24]

        # codigo unico
        codigo_ref = generar_codigo_referido()
        while codigo_ref in codigos_usados_lista:
            codigo_ref = generar_codigo_referido()
        codigos_usados_lista.append(codigo_ref)

        # distribuir roles
        if i == 0:
            rol = "admin"
        elif i < 4:
            rol = "moderador"
        else:
            rol = "usuario"

        # algunos referidos por otros usuarios (no pcmaster)
        if i < 6:
            referido_por = "pcmaster"
            referido_cambiado = 0
        elif i < 12:
            # referido por alguien de los primeros 6
            ref_idx = i % 6
            if ref_idx < len(codigos_usados_lista):
                referido_por = codigos_usados_lista[ref_idx]
            else:
                referido_por = "pcmaster"
            referido_cambiado = 1
        else:
            ref_idx = (i - 3) % 7
            if ref_idx < len(codigos_usados_lista):
                referido_por = codigos_usados_lista[ref_idx]
            else:
                referido_por = "pcmaster"
            referido_cambiado = 1

        nivel = niveles_fiabilidad[i]
        uptime_horas = round(random.uniform(10, 850), 1)
        pcbot_id = f"pcbot_{uuid.uuid4().hex[:12]}" if random.random() > 0.2 else None
        modo = random.choice(["conectado", "conectado", "conectado", "desconectado", "ocupado"])

        # fecha de registro escalonada (mas viejos los primeros)
        dias_atras = random.randint(1, 180)
        fecha_registro = f"2026-{random.randint(1,5):02d}-{random.randint(1,28):02d} {random.randint(8,20):02d}:{random.randint(0,59):02d}:{random.randint(0,59):02d}"

        # ultimo login (mas reciente)
        ultimo_login = f"2026-{random.randint(5,5):02d}-{random.randint(1,28):02d} {random.randint(6,23):02d}:{random.randint(0,59):02d}:{random.randint(0,59):02d}"

        # roxy api key y workspace (algunos tienen)
        roxy_api_key = secrets.token_hex(32) if random.random() > 0.3 else ""
        roxy_workspace_id = "ws_" + uuid.uuid4().hex[:16] if random.random() > 0.4 else ""

        # insertar usuario
        usuario_id = ejecutar_insercion(
            """insert into usuarios
               (email, password_hash, username, rol, wallet, codigo_referido,
                referido_por, referido_cambiado, nivel_fiabilidad, uptime_horas,
                pcbot_id, modo, ultimo_login, fecha_registro, roxy_api_key,
                roxy_workspace_id, activo)
               values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (email, password_hash, username, rol, wallet, codigo_ref,
             referido_por, referido_cambiado, nivel, uptime_horas,
             pcbot_id, modo, ultimo_login, fecha_registro, roxy_api_key,
             roxy_workspace_id),
        )

        if not usuario_id:
            print(f"  [error] no se pudo insertar {email}")
            continue

        ids_nuevos.append(usuario_id)

        # crear wallet
        stages = ["minado", "recolectado", "comprado"]
        pesos_stage = [0.5, 0.3, 0.2]
        total_balance = round(random.uniform(50, 5000), 2)
        minado_total = round(total_balance * 0.5 * random.uniform(0.7, 1.3), 2)
        recolectado_total = round(total_balance * 0.3 * random.uniform(0.7, 1.3), 2)
        comprado_total = round(total_balance * 0.2 * random.uniform(0.7, 1.3), 2)
        retirado_total = round(random.uniform(0, total_balance * 0.4), 2)
        staking_total = round(random.uniform(0, total_balance * 0.3), 2)

        if staking_total > 0:
            staking_desde = f"2026-{random.randint(1,4):02d}-{random.randint(1,28):02d}"
        else:
            staking_desde = None

        ejecutar_insercion(
            """insert into wallets
               (usuario_id, balance, minado_total, recolectado_total,
                comprado_total, retirado_total, staking_total, staking_desde)
               values (?, ?, ?, ?, ?, ?, ?, ?)""",
            (usuario_id, total_balance, minado_total, recolectado_total,
             comprado_total, retirado_total, staking_total, staking_desde),
        )

        # crear codigo de referido
        ejecutar_insercion(
            "insert or ignore into codigos_referido (usuario_id, codigo) values (?, ?)",
            (usuario_id, codigo_ref),
        )

        # crear perfiles (1-3 por usuario)
        num_perfiles = random.randint(1, 3)
        tipos_perfil = ["local", "local", "local", "local", "roxy", "vip"]
        estados_perfil = ["activo", "activo", "inactivo", "inactivo", "ocupado"]

        for p in range(num_perfiles):
            np = random.choice(tipos_perfil)
            est = random.choice(estados_perfil)
            ip_wan = random.choice(ips_wan_pool)
            horas_conexion = round(random.uniform(5, 400), 1)
            horas_en_uso = round(horas_conexion * random.uniform(0.3, 0.9), 1)
            horas_hh = round(horas_en_uso * random.uniform(0.1, 0.4), 1)

            nombre_perfil = f"perfil_{username}_{p+1}"

            ejecutar_insercion(
                """insert into perfiles
                   (usuario_id, nombre_perfil, tipo, estado, ip_wan,
                    horas_conexion, horas_en_uso, horas_hh)
                   values (?, ?, ?, ?, ?, ?, ?, ?)""",
                (usuario_id, nombre_perfil, np, est, ip_wan,
                 horas_conexion, horas_en_uso, horas_hh),
            )

        # crear sesion de token (algunos tienen sesion activa, otros no)
        if random.random() > 0.3:
            token = generar_token()
            expiracion = f"2026-{random.randint(5,6):02d}-{random.randint(1,28):02d} {random.randint(0,23):02d}:{random.randint(0,59):02d}:{random.randint(0,59):02d}"
            ejecutar_insercion(
                "insert into sesiones (token, usuario_id, email, rol, fecha_expiracion) values (?, ?, ?, ?, ?)",
                (token, usuario_id, email, rol, expiracion),
            )

        print(f"  [ok] {email:<35} rol={rol:<10} nivel={nivel:<8} balance={total_balance:>8.2f} kbt  perfiles={num_perfiles}")
        insertados += 1

    # -----------------------------------------------------------------------
    # establecer relaciones de referidos entre los nuevos usuarios
    # -----------------------------------------------------------------------
    if len(ids_nuevos) >= 5:
        print("")
        print("estableciendo relaciones de referidos...")
        for i, uid in enumerate(ids_nuevos[1:], 1):
            # referir a alguien con id menor
            referidor_id = ids_nuevos[(i - 1) % len(ids_nuevos)]
            if referidor_id == uid:
                referidor_id = ids_nuevos[i % len(ids_nuevos)]
            if referidor_id == uid:
                continue
            nivel_ref = min(i, 3)
            comisiones = round(random.uniform(0.5, 25.0), 2)
            fecha_act = f"2026-{random.randint(1,5):02d}-{random.randint(1,28):02d} {random.randint(8,20):02d}:{random.randint(0,59):02d}:{random.randint(0,59):02d}"
            try:
                ejecutar_insercion(
                    """insert or ignore into referidos
                       (referidor_id, referido_id, nivel, comisiones_generadas, fecha_activacion)
                       values (?, ?, ?, ?, ?)""",
                    (referidor_id, uid, nivel_ref, comisiones, fecha_act),
                )
            except Exception as e:
                pass  # no importa si falla algun referido

    # -----------------------------------------------------------------------
    # crear algunas ordenes p2p y transacciones
    # -----------------------------------------------------------------------
    if len(ids_nuevos) >= 4:
        print("")
        print("creando ordenes p2p y transacciones...")
        for i in range(4):
            if i * 2 + 1 >= len(ids_nuevos):
                break
            vendedor_id = ids_nuevos[i * 2]
            comprador_id = ids_nuevos[i * 2 + 1]
            cantidad = round(random.uniform(10, 200), 2)
            precio = round(random.uniform(0.8, 2.5), 2)
            estados_orden = ["completada", "completada", "completada", "abierta", "escrow"]
            ejecutar_insercion(
                """insert into ordenes_p2p
                   (vendedor_id, comprador_id, cantidad_kbt, precio_pen, tipo, estado)
                   values (?, ?, ?, ?, 'venta', ?)""",
                (vendedor_id, comprador_id, cantidad, precio, random.choice(estados_orden)),
            )

        # algunas transacciones entre usuarios
        for i in range(len(ids_nuevos) - 1):
            monto = round(random.uniform(1, 50), 2)
            ejecutar_insercion(
                """insert into transacciones
                   (origen_id, destino_id, tipo, monto, concepto)
                   values (?, ?, 'transferencia', ?, 'pago por servicios')""",
                (ids_nuevos[i], ids_nuevos[i + 1], monto),
            )

    print("")
    print(f"total usuarios insertados: {insertados}")
    print("poblacion completada exitosamente.")


if __name__ == "__main__":
    poblar()