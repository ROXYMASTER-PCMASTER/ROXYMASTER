# ============================================================================
# auth.py - modulo de autenticacion roxymaster v8.3
# registro, login, tokens de sesion, wallets, bcrypt
# ============================================================================

import hashlib
import secrets
import sqlite3
import time
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple, Dict, List

# ---------------------------------------------------------------------------
# configuracion de base de datos
# ---------------------------------------------------------------------------
_base_dir = Path(__file__).parent.parent.absolute()
_data_dir = _base_dir / "data"
_db_path = _data_dir / "roxymaster.db"

# ===========================================================================
# helpers de hash (bcrypt simulado con hashlib salt + sha256 para
# compatibilidad sin dependencias externas; el salt se almacena junto al hash)
# ===========================================================================
def hash_password(password: str) -> str:
    """genera hash seguro con salt aleatorio usando sha256."""
    salt = secrets.token_hex(16)
    raw = (salt + password).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    return f"{salt}:{digest}"


def verificar_password(password: str, password_hash: str) -> bool:
    """verifica una contrasena contra su hash almacenado."""
    try:
        salt, digest = password_hash.split(":", 1)
    except (ValueError, AttributeError):
        return False
    raw = (salt + password).encode("utf-8")
    nuevo_digest = hashlib.sha256(raw).hexdigest()
    return secrets.compare_digest(nuevo_digest, digest)


# ===========================================================================
# generacion de wallet (direccion unica derivada del email)
# ===========================================================================
def generar_wallet(email: str) -> str:
    """genera una direccion de wallet interna unica derivada del email."""
    base = email.strip().lower().encode("utf-8")
    return "kbt_" + hashlib.sha256(base).hexdigest()[:16]


# ===========================================================================
# generacion de codigo de referido
# ===========================================================================
def generar_codigo_referido(email: str) -> str:
    """genera un codigo de referido unico de 8 caracteres."""
    base = email.strip().lower().encode("utf-8")
    return hashlib.sha256(base + b"ref").hexdigest()[:8]


# ===========================================================================
# inicializacion de tablas
# ===========================================================================
def init_auth_db():
    """crea las tablas necesarias para autenticacion y wallets."""
    os.makedirs(str(_data_dir), exist_ok=True)
    conn = sqlite3.connect(str(_db_path))
    cursor = conn.cursor()

    # tabla usuarios
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            rol TEXT DEFAULT 'granjero',
            wallet TEXT UNIQUE NOT NULL,
            codigo_referido TEXT UNIQUE NOT NULL,
            referido_por TEXT DEFAULT NULL,
            pcbot_id TEXT DEFAULT NULL,
            modo TEXT DEFAULT 'conectado',
            ultimo_login TEXT,
            fecha_registro TEXT DEFAULT (datetime('now', 'localtime')),
            activo INTEGER DEFAULT 1
        )
    """)

    # tabla sesiones
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sesiones (
            token TEXT PRIMARY KEY,
            usuario_id INTEGER NOT NULL,
            email TEXT NOT NULL,
            rol TEXT NOT NULL,
            ip_origen TEXT,
            fecha_creacion TEXT DEFAULT (datetime('now', 'localtime')),
            fecha_expiracion TEXT NOT NULL,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )
    """)

    # tabla wallets (balance independiente)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS wallets (
            wallet TEXT PRIMARY KEY,
            usuario_id INTEGER UNIQUE NOT NULL,
            saldo_tokens REAL DEFAULT 0.0,
            saldo_tokens_quemables REAL DEFAULT 0.0,
            saldo_tokens_comprados REAL DEFAULT 0.0,
            saldo_soles REAL DEFAULT 0.0,
            tokens_minados_total REAL DEFAULT 0.0,
            tokens_en_staking REAL DEFAULT 0.0,
            staking_desde TEXT,
            fecha_actualizacion TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )
    """)

    # tabla referidos (arbol)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS referidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            referido_id INTEGER NOT NULL,
            nivel INTEGER NOT NULL CHECK (nivel IN (1, 2, 3)),
            fecha_activacion TEXT,
            comisiones_generadas REAL DEFAULT 0.0,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id),
            FOREIGN KEY (referido_id) REFERENCES usuarios(id),
            UNIQUE (usuario_id, referido_id, nivel)
        )
    """)

    # tabla pcbot_registrados (registro de maquinas conectadas)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pcbot_registrados (
            pcbot_id TEXT PRIMARY KEY,
            usuario_id INTEGER,
            nombre_pc TEXT NOT NULL,
            usuario TEXT NOT NULL,
            ip_local TEXT,
            ip_tailscale TEXT,
            ip_wan TEXT,
            token_sesion TEXT,
            estado TEXT DEFAULT 'conectado',
            navegadores TEXT,
            perfiles TEXT,
            logo TEXT,
            ultima_conexion TEXT DEFAULT (datetime('now', 'localtime')),
            primera_conexion TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        )
    """)

    # crear admin por defecto si no existe
    cursor.execute("SELECT id FROM usuarios WHERE email = 'pcmaster'")
    if not cursor.fetchone():
        admin_pass = hash_password("abc123$_")
        admin_wallet = generar_wallet("pcmaster")
        admin_ref = generar_codigo_referido("pcmaster")
        cursor.execute(
            "INSERT INTO usuarios (email, password_hash, rol, wallet, codigo_referido) "
            "VALUES (?, ?, 'admin', ?, ?)",
            ("pcmaster", admin_pass, admin_wallet, admin_ref)
        )
        uid = cursor.lastrowid
        cursor.execute(
            "INSERT INTO wallets (wallet, usuario_id, saldo_tokens) VALUES (?, ?, 1000000.0)",
            (admin_wallet, uid)
        )
        cursor.execute(
            "INSERT INTO referidos (usuario_id, referido_id, nivel) VALUES (?, ?, 1)",
            (uid, uid)
        )

    conn.commit()
    conn.close()


# ===========================================================================
# operaciones de autenticacion
# ===========================================================================
def registrar_usuario(email: str, password: str, pcbot_id: str = None,
                      codigo_referido: str = None, username: str = None) -> dict:
    """registra un nuevo usuario y crea su wallet.
    retorna {ok, token, mensaje, uid, wallet, codigo_referido, error}."""
    email = email.strip().lower()
    
    # username opcional: si no se pasa se usa la parte local del email
    if username is None:
        username = email.split('@')[0] if '@' in email else email

    if len(password) < 4:
        return {"ok": False, "error": "contrasena muy corta (minimo 4 caracteres)"}

    conn = sqlite3.connect(str(_db_path))
    cursor = conn.cursor()

    # verificar email unico
    cursor.execute("SELECT id FROM usuarios WHERE email = ?", (email,))
    if cursor.fetchone():
        conn.close()
        return {"ok": False, "error": "el email ya esta registrado"}

    # verificar codigo de referido
    referido_por = None
    referido_uid = None
    if codigo_referido and codigo_referido.strip():
        cursor.execute(
            "SELECT id FROM usuarios WHERE codigo_referido = ?",
            (codigo_referido.strip().lower(),)
        )
        ref_row = cursor.fetchone()
        if ref_row:
            referido_por = codigo_referido.strip().lower()
            referido_uid = ref_row[0]

    # crear usuario
    pass_hash = hash_password(password)
    wallet = generar_wallet(email)
    cod_ref = generar_codigo_referido(email)

    cursor.execute(
        "INSERT INTO usuarios (email, password_hash, rol, wallet, codigo_referido, "
        "referido_por, pcbot_id) VALUES (?, ?, 'granjero', ?, ?, ?, ?)",
        (email, pass_hash, wallet, cod_ref, referido_por, pcbot_id or "")
    )
    uid = cursor.lastrowid

    # crear wallet
    cursor.execute(
        "INSERT INTO wallets (wallet, usuario_id) VALUES (?, ?)",
        (wallet, uid)
    )

    # procesar arbol de referidos (3 niveles)
    if referido_uid:
        _construir_arbol_referidos(cursor, referido_uid, uid)

    # crear sesion automatica
    token = _crear_sesion_db(cursor, uid, email, "granjero", "127.0.0.1")
    cursor.execute(
        "UPDATE usuarios SET ultimo_login = datetime('now', 'localtime') WHERE id = ?",
        (uid,)
    )

    conn.commit()
    conn.close()

    return {
        "ok": True,
        "token": token,
        "mensaje": "cuenta creada exitosamente",
        "uid": uid,
        "usuario": email,
        "rol": "granjero",
        "wallet": wallet,
        "codigo_referido": cod_ref
    }


def login_usuario(email: str, password: str, pcbot_id: str = None,
                   ip_origen: str = "127.0.0.1") -> dict:
    """inicia sesion. retorna {ok, token, usuario, rol, wallet, uid, error}."""
    email = email.strip().lower()

    conn = sqlite3.connect(str(_db_path))
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, password_hash, rol, wallet, codigo_referido, activo "
        "FROM usuarios WHERE email = ?",
        (email,)
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"ok": False, "error": "usuario no encontrado"}

    uid, pass_hash, rol, wallet, cod_ref, activo = row

    if not activo:
        conn.close()
        return {"ok": False, "error": "cuenta desactivada"}

    if not verificar_password(password, pass_hash):
        conn.close()
        return {"ok": False, "error": "contrasena incorrecta"}

    # actualizar pcbot_id
    if pcbot_id:
        cursor.execute("UPDATE usuarios SET pcbot_id = ? WHERE id = ?", (pcbot_id, uid))

    # crear sesion
    token = _crear_sesion_db(cursor, uid, email, rol, ip_origen)
    cursor.execute(
        "UPDATE usuarios SET ultimo_login = datetime('now', 'localtime') WHERE id = ?",
        (uid,)
    )

    conn.commit()
    conn.close()

    return {
        "ok": True,
        "token": token,
        "uid": uid,
        "usuario": email,
        "rol": rol,
        "wallet": wallet,
        "codigo_referido": cod_ref
    }


# ===========================================================================
# funciones de compatibilidad con server.py
# estos wrappers adaptan las firmas reales a lo que server.py importa
# ===========================================================================

def generar_token(uid: int, username: str, rol: str) -> str:
    """genera un token de sesion dado uid, username y rol.
    firma esperada por server.py: generar_token(uid, username, rol) -> token.
    """
    conn = sqlite3.connect(str(_db_path))
    cursor = conn.cursor()
    email = f"{username}@{uid}.local"
    cursor.execute("SELECT email FROM usuarios WHERE id = ?", (uid,))
    row = cursor.fetchone()
    if row:
        email = row[0]
    token = _crear_sesion_db(cursor, uid, email, rol, "127.0.0.1")
    conn.commit()
    conn.close()
    return token


def verificar_token(token: str) -> Optional[Tuple[int, str, str]]:
    """verifica un token de sesion y retorna (uid, username, rol) o None.
    firma esperada por server.py: verificar_token(token) -> (uid, username, rol) | None.
    """
    if not token:
        return None
    conn = sqlite3.connect(str(_db_path))
    cursor = conn.cursor()
    cursor.execute(
        "SELECT s.usuario_id, s.email, s.rol, s.fecha_expiracion "
        "FROM sesiones s WHERE s.token = ?",
        (token,)
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    uid, email, rol, exp_str = row
    conn.close()

    try:
        exp_dt = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None

    if datetime.now() > exp_dt:
        _limpiar_sesion(token)
        return None

    # username desde email
    username = email.split('@')[0] if '@' in email else email
    return (uid, username, rol)


def autenticar_usuario(email: str, password: str) -> Optional[Tuple[int, str, str]]:
    """autentica usuario y retorna (uid, username, rol) o None.
    firma esperada por server.py: autenticar_usuario(email, password) -> (uid, username, rol) | None.
    """
    email = email.strip().lower()
    conn = sqlite3.connect(str(_db_path))
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, password_hash, rol, activo FROM usuarios WHERE email = ?",
        (email,)
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    uid, pass_hash, rol, activo = row
    conn.close()

    if not activo:
        return None
    if not verificar_password(password, pass_hash):
        return None

    username = email.split('@')[0] if '@' in email else email
    return (uid, username, rol)


def validar_token(token: str) -> dict:
    """valida un token de sesion. retorna {valido, usuario_id, email, rol, error}.
    usado por funciones internas que esperan dict, no tuple."""
    if not token:
        return {"valido": False, "error": "token vacio"}

    conn = sqlite3.connect(str(_db_path))
    cursor = conn.cursor()
    cursor.execute(
        "SELECT s.usuario_id, s.email, s.rol, s.fecha_expiracion "
        "FROM sesiones s WHERE s.token = ?",
        (token,)
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"valido": False, "error": "token invalido"}

    uid, email, rol, exp_str = row
    conn.close()

    try:
        exp_dt = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return {"valido": False, "error": "token con fecha invalida"}

    if datetime.now() > exp_dt:
        _limpiar_sesion(token)
        return {"valido": False, "error": "token expirado"}

    return {
        "valido": True,
        "usuario_id": uid,
        "email": email,
        "rol": rol
    }


# ---------------------------------------------------------------------------
# operaciones auxiliares
# ---------------------------------------------------------------------------

def cerrar_sesion(token: str):
    """elimina una sesion por token."""
    _limpiar_sesion(token)


def cambiar_password(email: str, password_actual: str, password_nuevo: str) -> dict:
    """cambia la contrasena de un usuario."""
    email = email.strip().lower()
    conn = sqlite3.connect(str(_db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT id, password_hash FROM usuarios WHERE email = ?", (email,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"ok": False, "error": "usuario no encontrado"}
    uid, old_hash = row
    if not verificar_password(password_actual, old_hash):
        conn.close()
        return {"ok": False, "error": "contrasena actual incorrecta"}
    new_hash = hash_password(password_nuevo)
    cursor.execute("UPDATE usuarios SET password_hash = ? WHERE id = ?", (new_hash, uid))
    conn.commit()
    conn.close()
    return {"ok": True, "mensaje": "contrasena actualizada"}


def obtener_info_usuario(email: str = None, usuario_id: int = None) -> Optional[Dict]:
    """obtiene informacion completa de un usuario, incluyendo saldo de wallet."""
    conn = sqlite3.connect(str(_db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if email:
        email = email.strip().lower()
        cursor.execute(
            "SELECT u.*, w.saldo_tokens, w.saldo_tokens_quemables, "
            "w.saldo_tokens_comprados, w.saldo_soles, w.tokens_minados_total, "
            "w.tokens_en_staking FROM usuarios u "
            "JOIN wallets w ON u.id = w.usuario_id "
            "WHERE u.email = ?", (email,)
        )
    elif usuario_id:
        cursor.execute(
            "SELECT u.*, w.saldo_tokens, w.saldo_tokens_quemables, "
            "w.saldo_tokens_comprados, w.saldo_soles, w.tokens_minados_total, "
            "w.tokens_en_staking FROM usuarios u "
            "JOIN wallets w ON u.id = w.usuario_id "
            "WHERE u.id = ?", (usuario_id,)
        )
    else:
        conn.close()
        return None

    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def obtener_usuario_por_id(usuario_id: int) -> Optional[Dict]:
    """obtiene usuario por id (alias para server.py)."""
    return obtener_info_usuario(usuario_id=usuario_id)


def obtener_usuario_por_email(email: str) -> Optional[Dict]:
    """obtiene usuario por email (alias para server.py)."""
    return obtener_info_usuario(email=email)


def listar_usuarios(rol: str = None, activo: int = None,
                    limite: int = 100, offset: int = 0) -> List[Dict]:
    """lista usuarios con filtros opcionales."""
    conn = sqlite3.connect(str(_db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
        SELECT u.id, u.email, u.rol, u.wallet, u.codigo_referido,
               u.pcbot_id, u.modo, u.ultimo_login, u.fecha_registro, u.activo,
               w.saldo_tokens, w.saldo_tokens_quemables, w.saldo_tokens_comprados,
               w.saldo_soles, w.tokens_minados_total, w.tokens_en_staking
        FROM usuarios u
        JOIN wallets w ON u.id = w.usuario_id
        WHERE 1=1
    """
    params = []

    if rol:
        query += " AND u.rol = ?"
        params.append(rol)
    if activo is not None:
        query += " AND u.activo = ?"
        params.append(activo)

    query += " ORDER BY u.id DESC LIMIT ? OFFSET ?"
    params.extend([limite, offset])

    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def cambiar_rol(admin_token: str, email: str, nuevo_rol: str) -> dict:
    """cambia el rol de un usuario. solo admins pueden ejecutarlo.
    retorna {ok, mensaje, error}."""
    email = email.strip().lower()

    # validar que el admin_token sea de un admin
    sesion = validar_token(admin_token)
    if not sesion.get("valido"):
        return {"ok": False, "error": "token de admin invalido o expirado"}
    if sesion.get("rol") != "admin":
        return {"ok": False, "error": "solo administradores pueden cambiar roles"}

    if nuevo_rol not in ("granjero", "streamer", "admin"):
        return {"ok": False, "error": f"rol '{nuevo_rol}' no valido"}

    conn = sqlite3.connect(str(_db_path))
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET rol = ? WHERE email = ?", (nuevo_rol, email))
    if cursor.rowcount == 0:
        conn.close()
        return {"ok": False, "error": "usuario no encontrado"}
    conn.commit()
    conn.close()
    return {"ok": True, "mensaje": f"rol de {email} cambiado a {nuevo_rol}"}


def obtener_referidos(usuario_id: int) -> List[Dict]:
    """obtiene el arbol de referidos de 3 niveles para un usuario."""
    conn = sqlite3.connect(str(_db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT r.nivel, u.email as referido_email, u.wallet as referido_wallet,
               r.comisiones_generadas, r.fecha_activacion,
               w.saldo_tokens as tokens_referido
        FROM referidos r
        JOIN usuarios u ON r.referido_id = u.id
        LEFT JOIN wallets w ON u.id = w.usuario_id
        WHERE r.usuario_id = ?
        ORDER BY r.nivel, r.fecha_activacion
    """, (usuario_id,))

    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def actualizar_pcbot_id(email: str, pcbot_id: str):
    """actualiza el pcbot_id asociado a un usuario."""
    email = email.strip().lower()
    conn = sqlite3.connect(str(_db_path))
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET pcbot_id = ? WHERE email = ?", (pcbot_id, email))
    conn.commit()
    conn.close()


def generar_token_recuperacion(email: str) -> dict:
    """genera un token de recuperacion de contrasena temporal."""
    email = email.strip().lower()
    conn = sqlite3.connect(str(_db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM usuarios WHERE email = ?", (email,))
    if not cursor.fetchone():
        conn.close()
        return {"ok": False, "error": "usuario no encontrado"}
    token = secrets.token_hex(16)
    cursor.execute(
        "INSERT OR REPLACE INTO sesiones (token, usuario_id, email, rol, "
        "fecha_expiracion) SELECT ?, id, email, rol, datetime('now', '+1 hour') "
        "FROM usuarios WHERE email = ?",
        (token, email)
    )
    conn.commit()
    conn.close()
    return {"ok": True, "token": token, "mensaje": "token de recuperacion generado"}


# ===========================================================================
# funciones internas
# ===========================================================================
def _crear_sesion_db(cursor, usuario_id: int, email: str, rol: str,
                     ip_origen: str = "127.0.0.1") -> str:
    """crea una sesion en la base de datos y retorna el token."""
    token = secrets.token_hex(32)
    exp = (datetime.now() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO sesiones (token, usuario_id, email, rol, ip_origen, "
        "fecha_expiracion) VALUES (?, ?, ?, ?, ?, ?)",
        (token, usuario_id, email, rol, ip_origen, exp)
    )
    return token


def _limpiar_sesion(token: str):
    """elimina una sesion y limpia sesiones expiradas."""
    try:
        conn = sqlite3.connect(str(_db_path))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM sesiones WHERE token = ?", (token,))
        cursor.execute(
            "DELETE FROM sesiones WHERE fecha_expiracion < datetime('now', 'localtime')"
        )
        conn.commit()
        conn.close()
    except sqlite3.Error:
        pass


def _construir_arbol_referidos(cursor, referido_uid: int, nuevo_uid: int):
    """construye el arbol de referidos de 3 niveles hacia arriba."""
    # nivel 1: el que refirio directamente
    cursor.execute(
        "INSERT OR IGNORE INTO referidos (usuario_id, referido_id, nivel) "
        "VALUES (?, ?, 1)",
        (referido_uid, nuevo_uid)
    )

    # nivel 2: el padre del que refirio
    cursor.execute(
        "SELECT usuario_id FROM referidos WHERE referido_id = ? AND nivel = 1",
        (referido_uid,)
    )
    nivel2 = cursor.fetchone()
    if nivel2:
        cursor.execute(
            "INSERT OR IGNORE INTO referidos (usuario_id, referido_id, nivel) "
            "VALUES (?, ?, 2)",
            (nivel2[0], nuevo_uid)
        )

        # nivel 3: el abuelo
        cursor.execute(
            "SELECT usuario_id FROM referidos WHERE referido_id = ? AND nivel = 1",
            (nivel2[0],)
        )
        nivel3 = cursor.fetchone()
        if nivel3:
            cursor.execute(
                "INSERT OR IGNORE INTO referidos (usuario_id, referido_id, nivel) "
                "VALUES (?, ?, 3)",
                (nivel3[0], nuevo_uid)
            )


# ===========================================================================
# inicializacion al importar
# ===========================================================================
init_auth_db()