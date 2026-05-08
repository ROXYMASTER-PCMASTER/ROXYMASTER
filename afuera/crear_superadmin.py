# crear_superadmin.py - crea el usuario superadmin admin@roxymaster.local

import hashlib
import secrets
import uuid
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from db import ejecutar_sql, ejecutar_sql_unico, ejecutar_insercion, init_db

hash_iteraciones = 310000

def encriptar_password(password: str) -> str:
    salt = secrets.token_hex(24)
    hash_bytes = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"),
        hash_iteraciones, dklen=64,
    )
    return f"pbkdf2:{hash_iteraciones}:{salt}:{hash_bytes.hex()}"

def generar_codigo_referido() -> str:
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    import random
    return "".join(random.choices(chars, k=8))

def generar_token() -> str:
    return uuid.uuid4().hex + secrets.token_hex(16)

def crear_superadmin():
    """crea el usuario superadmin con 1,500,000 tokens."""
    print("creando superadmin...")

    init_db()

    # verificar si ya existe
    existente = ejecutar_sql_unico("select id from usuarios where email = ?", ("admin@roxymaster.local",))
    if existente:
        print("  el superadmin ya existe, eliminando y recreando...")
        uid = existente["id"]
        ejecutar_sql("delete from transacciones where origen_id = ? or destino_id = ?", (uid, uid))
        ejecutar_sql("delete from ordenes_p2p where vendedor_id = ? or comprador_id = ?", (uid, uid))
        ejecutar_sql("delete from sesiones where usuario_id = ?", (uid,))
        ejecutar_sql("delete from referidos where referidor_id = ? or referido_id = ?", (uid, uid))
        ejecutar_sql("delete from perfiles where usuario_id = ?", (uid,))
        ejecutar_sql("delete from codigos_referido where usuario_id = ?", (uid,))
        ejecutar_sql("delete from wallets where usuario_id = ?", (uid,))
        ejecutar_sql("delete from usuarios where id = ?", (uid,))

    email = "admin@roxymaster.local"
    password = "12345678"
    password_hash = encriptar_password(password)
    username = "superadmin"
    wallet = "kbt_" + uuid.uuid4().hex[:24]
    codigo_ref = "roxyadmin"
    rol = "superadmin"
    nivel = "diamante"
    uptime_horas = 9999.9
    pcbot_id = "pcbot_superadmin"
    modo = "conectado"
    fecha_registro = "2026-01-01 00:00:00"
    ultimo_login = "2026-05-08 12:00:00"
    roxy_api_key = secrets.token_hex(32)
    roxy_workspace_id = "ws_" + uuid.uuid4().hex[:16]

    usuario_id = ejecutar_insercion(
        """insert into usuarios
           (email, password_hash, username, rol, wallet, codigo_referido,
            referido_por, referido_cambiado, nivel_fiabilidad, uptime_horas,
            pcbot_id, modo, ultimo_login, fecha_registro, roxy_api_key,
            roxy_workspace_id, activo)
           values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
        (email, password_hash, username, rol, wallet, codigo_ref,
         "pcmaster", 0, nivel, uptime_horas,
         pcbot_id, modo, ultimo_login, fecha_registro, roxy_api_key,
         roxy_workspace_id),
    )

    if not usuario_id:
        print("  error: no se pudo crear el superadmin")
        return

    # wallet con 1,500,000 tokens
    balance = 1500000.00
    minado_total = 750000.00
    recolectado_total = 450000.00
    comprado_total = 300000.00
    staking_total = 500000.00
    staking_desde = "2026-02-15"

    ejecutar_insercion(
        """insert into wallets
           (usuario_id, balance, minado_total, recolectado_total,
            comprado_total, retirado_total, staking_total, staking_desde)
           values (?, ?, ?, ?, ?, ?, ?, ?)""",
        (usuario_id, balance, minado_total, recolectado_total,
         comprado_total, 0.00, staking_total, staking_desde),
    )

    # codigo de referido
    ejecutar_insercion(
        "insert or ignore into codigos_referido (usuario_id, codigo) values (?, ?)",
        (usuario_id, codigo_ref),
    )

    # 5 perfiles
    perfiles_data = [
        ("perfil_admin_local", "local", "activo", "190.42.113.1"),
        ("perfil_admin_roxy", "roxy", "activo", "190.42.113.1"),
        ("perfil_admin_vip", "vip", "activo", "190.42.113.1"),
        ("perfil_admin_backup", "local", "inactivo", "190.42.113.1"),
        ("perfil_admin_monitoreo", "local", "activo", "190.42.113.1"),
    ]
    for nombre, tipo, estado, ip in perfiles_data:
        ejecutar_insercion(
            """insert into perfiles
               (usuario_id, nombre_perfil, tipo, estado, ip_wan,
                horas_conexion, horas_en_uso, horas_hh)
               values (?, ?, ?, ?, ?, ?, ?, ?)""",
            (usuario_id, nombre, tipo, estado, ip, 999.9, 850.0, 420.0),
        )

    # sesion activa con 1 año de expiracion
    token = generar_token()
    ejecutar_insercion(
        "insert into sesiones (token, usuario_id, email, rol, fecha_expiracion) values (?, ?, ?, ?, '2027-12-31 23:59:59')",
        (token, usuario_id, email, rol),
    )

    # actualizar reserva del sistema
    ejecutar_sql("update reserva set tokens = tokens + 1500000 where id = 1")

    print(f"  [ok] superadmin creado exitosamente")
    print(f"       email:    admin@roxymaster.local")
    print(f"       password: 12345678")
    print(f"       rol:      superadmin")
    print(f"       wallet:   {wallet[:20]}...")
    print(f"       balance:  {balance:,.2f} kbt")
    print(f"       perfiles: 5")
    print(f"       token:    {token[:20]}...")

if __name__ == "__main__":
    crear_superadmin()