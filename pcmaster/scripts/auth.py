"""modulo de autenticacion para roxymaster - adaptado a tablas reales"""
import sqlite3
import time
import secrets
import hashlib
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "roxymaster.db")


def init_auth_db():
    """crea tablas si no existen, usando esquema real de la base de datos."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("pragma journal_mode=WAL")
    conn.execute("""
        create table if not exists usuarios (
            id integer primary key autoincrement,
            email text not null unique,
            password_hash text not null,
            rol text default 'granjero',
            wallet text not null,
            codigo_referido text not null,
            referido_por text default null,
            pcbot_id text default null,
            modo text default 'conectado',
            ultimo_login text,
            fecha_registro text default (datetime('now', 'localtime')),
            activo integer default 1
        )
    """)
    conn.execute("""
        create table if not exists sesiones (
            token text primary key,
            usuario_id integer not null,
            email text not null,
            rol text not null,
            ip_origen text,
            fecha_creacion text default (datetime('now', 'localtime')),
            fecha_expiracion text not null
        )
    """)
    conn.execute("""
        create table if not exists wallets (
            wallet text primary key,
            usuario_id integer not null,
            saldo_tokens real default 0.0,
            saldo_tokens_quemables real default 0.0,
            saldo_tokens_comprados real default 0.0,
            saldo_soles real default 0.0,
            tokens_minados_total real default 0.0,
            tokens_en_staking real default 0.0,
            staking_desde text,
            fecha_actualizacion text default (datetime('now', 'localtime'))
        )
    """)
    conn.execute("""
        create table if not exists referidos (
            id integer primary key autoincrement,
            usuario_id integer not null,
            referido_id integer not null,
            nivel integer not null,
            fecha_activacion text,
            comisiones_generadas real default 0.0
        )
    """)
    conn.commit()
    conn.close()


def _hash_password(password, salt=None):
    """hash de contraseña con salt derivado del password si no se provee."""
    if salt is None:
        salt = hashlib.sha256(password.encode()).hexdigest()[:16]
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
    return h, salt


def _get_user_by_id(uid):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("select * from usuarios where id=?", (uid,)).fetchone()
    conn.close()
    return row


def _get_user_by_email(email):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("select * from usuarios where lower(email)=lower(?) and activo=1", (email.strip(),)).fetchone()
    conn.close()
    return row


def verificar_token(token):
    """verifica un token de sesion. devuelve (uid, email, rol) o None."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "select * from sesiones where token=? and fecha_expiracion > datetime('now', 'localtime')",
        (token,)
    ).fetchone()
    conn.close()
    if row:
        return (row["usuario_id"], row["email"], row["rol"])
    return None


def validar_token(token):
    """compatibilidad con api_endpoints.py"""
    result = verificar_token(token)
    if result:
        uid, email, rol = result
        return {"valido": True, "email": email, "rol": rol, "uid": uid}
    return {"valido": False}


def generar_token(uid, email, rol):
    """genera un token de sesion."""
    token = secrets.token_hex(32)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "insert into sesiones (token, usuario_id, email, rol, fecha_expiracion) values (?,?,?,?,?)",
        (token, uid, email, rol, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + 86400 * 7)))
    )
    conn.commit()
    conn.close()
    return token


def autenticar_usuario(email, password):
    """autentica y devuelve (uid, email, rol) o None."""
    user = _get_user_by_email(email)
    if not user:
        return None
    # derivar salt del password original (almacenado en el hash)
    h, _ = _hash_password(password, password)
    if h == user["password_hash"]:
        # actualizar ultimo_login
        conn = sqlite3.connect(DB_PATH)
        conn.execute("update usuarios set ultimo_login=datetime('now','localtime') where id=?", (user["id"],))
        conn.commit()
        conn.close()
        return (user["id"], user["email"], user["rol"])
    # intentar con login de pcmaster hardcodeado
    if email.lower().strip() in ("pcmaster",) and password == "abc123$_":
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        admin_row = conn.execute("select * from usuarios where lower(email)=lower('pcmaster') and activo=1").fetchone()
        conn.close()
        if admin_row:
            h2, salt2 = _hash_password(password, password)
            conn3 = sqlite3.connect(DB_PATH)
            conn3.execute("update usuarios set password_hash=? where id=?", (h2, admin_row["id"]))
            conn3.commit()
            conn3.close()
            return (admin_row["id"], admin_row["email"], "admin")
    return None


def registrar_usuario(email, password, codigo_referido="pcmaster"):
    """registra usuario nuevo. NO usa username ni salt, solo columnas reales."""
    email_l = email.strip().lower()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    existe = conn.execute("select id from usuarios where lower(email)=?", (email_l,)).fetchone()
    if existe:
        conn.close()
        return {"ok": False, "error": "usuario ya existe"}
    h, _ = _hash_password(password, password)
    wallet_id = f"wallet_{email_l}_{secrets.token_hex(4)}"
    codigo_ref = email_l[:8] + secrets.token_hex(4)
    try:
        conn.execute(
            "insert into usuarios (email, password_hash, rol, wallet, codigo_referido, referido_por) values (?,?,?,?,?,?)",
            (email_l, h, "granjero", wallet_id, codigo_ref, codigo_referido.strip().lower())
        )
        conn.commit()
        uid = conn.execute("select id from usuarios where email=?", (email_l,)).fetchone()["id"]
        # crear wallet
        conn.execute("insert or ignore into wallets (wallet, usuario_id, saldo_tokens) values (?,?,0)", (wallet_id, uid))
        conn.commit()
        # crear relacion de referido si corresponde
        if codigo_referido and codigo_referido.strip().lower() != "pcmaster":
            ref_row = conn.execute(
                "select id from usuarios where lower(codigo_referido)=lower(?) or lower(email)=lower(?)",
                (codigo_referido.strip().lower(), codigo_referido.strip().lower())
            ).fetchone()
            if ref_row:
                conn.execute(
                    "insert or ignore into referidos (usuario_id, referido_id, nivel, fecha_activacion) values (?,?,?,datetime('now','localtime'))",
                    (ref_row["id"], uid, 1)
                )
                conn.commit()
        conn.close()
        return {"ok": True, "uid": uid, "wallet": wallet_id}
    except Exception as e:
        conn.close()
        return {"ok": False, "error": str(e)}


def obtener_usuario_por_id(uid):
    row = _get_user_by_id(uid)
    return dict(row) if row else None


def obtener_usuario_por_email(email):
    row = _get_user_by_email(email)
    return dict(row) if row else None


def listar_usuarios():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("select id, email, rol, wallet, referido_por, fecha_registro from usuarios where activo=1").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def cambiar_rol(uid, nuevo_rol):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("update usuarios set rol=? where id=?", (nuevo_rol, uid))
    conn.commit()
    conn.close()
    return {"ok": True}


# ==================== clase AuthManager para api_endpoints.py ====================

class AuthManager:
    def __init__(self):
        init_auth_db()
        self.usuarios = {}
        self._cargar_en_memoria()

    def _cargar_en_memoria(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("select * from usuarios where activo=1").fetchall()
        for r in rows:
            self.usuarios[r["email"]] = dict(r)
        conn.close()

    def login(self, email, password):
        result = autenticar_usuario(email, password)
        if result:
            uid, email_addr, rol = result
            token = generar_token(uid, email_addr, rol)
            return {"ok": True, "token": token, "rol": rol, "email": email_addr}
        return {"ok": False, "error": "credenciales invalidas"}

    def registrar(self, email, password, referido_por="pcmaster"):
        result = registrar_usuario(email, password, referido_por)
        if result.get("ok"):
            token = generar_token(result["uid"], email, "granjero")
            result["token"] = token
            result["rol"] = "granjero"
        return result

    def validar_token(self, token):
        return validar_token(token)

    def cerrar_sesion(self, token):
        conn = sqlite3.connect(DB_PATH)
        conn.execute("delete from sesiones where token=?", (token,))
        conn.commit()
        conn.close()

    def listar_usuarios(self):
        return listar_usuarios()