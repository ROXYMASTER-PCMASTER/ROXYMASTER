import sqlite3, os, secrets, hashlib, time, uuid
from config import DATA_DIR
DB_PATH = os.path.join(DATA_DIR, "roxymaster.db")

# ==================== funciones wrapper para server.py v8.3 ====================

def init_auth_db():
    """inicializa las tablas de autenticacion."""
    conn = sqlite3.connect(DB_PATH)
    conn.executescript('''
        create table if not exists usuarios (
            id integer primary key autoincrement,
            email text unique not null,
            username text not null,
            password_hash text not null,
            salt text not null,
            rol text default 'usuario',
            wallet text,
            referido_por text default 'pcmaster',
            fecha_registro text default (datetime('now','localtime')),
            ultimo_login text,
            activo integer default 1
        );
        create table if not exists sesiones (
            id integer primary key autoincrement,
            usuario_id integer not null,
            token text unique not null,
            fecha_creacion text default (datetime('now','localtime')),
            fecha_expiracion text,
            activo integer default 1,
            foreign key (usuario_id) references usuarios(id)
        );
        insert or ignore into usuarios (email, username, password_hash, salt, rol)
        values ('pcmaster', 'pcmaster',
                'b1b8a8d3e7d2f1e9c6a5b4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f9a8b7c6d5',
                'sal_maestra_roxymaster', 'admin');
    ''')
    conn.commit()
    conn.close()

def _get_user_by_email(email):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("select * from usuarios where lower(email)=lower(?) and activo=1", (email.strip(),)).fetchone()
    conn.close()
    return row

def _get_user_by_id(uid):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("select * from usuarios where id=? and activo=1", (uid,)).fetchone()
    conn.close()
    return row

def _hash_password(password, salt=None):
    if not salt:
        salt = secrets.token_hex(16)
    h = hashlib.sha256((password + salt).encode()).hexdigest()
    return h, salt

def verificar_token(token):
    """devuelve (uid, username, rol) o None"""
    if not token:
        return None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    sesion = conn.execute(
        "select s.*, u.email, u.rol from sesiones s join usuarios u on s.usuario_id=u.id where s.token=? and s.activo=1",
        (token,)
    ).fetchone()
    conn.close()
    if not sesion:
        return None
    # verificar expiracion
    if sesion["fecha_expiracion"]:
        exp = sesion["fecha_expiracion"]
        if exp < time.strftime("%Y-%m-%d %H:%M:%S"):
            return None
    return (sesion["usuario_id"], sesion["email"].split("@")[0], sesion["rol"])

def validar_token(token):
    """compatibilidad con api_endpoints.py"""
    result = verificar_token(token)
    if result:
        uid, username, rol = result
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute("select email from usuarios where id=?", (uid,)).fetchone()
        conn.close()
        return {"valido": True, "email": row["email"] if row else username, "rol": rol, "uid": uid}
    return {"valido": False}

def generar_token(uid, username, rol):
    """genera un token de sesion."""
    token = secrets.token_hex(32)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "insert into sesiones (usuario_id, token, fecha_expiracion) values (?,?,?)",
        (uid, token, time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() + 86400 * 7)))
    )
    conn.commit()
    conn.close()
    return token

def autenticar_usuario(email, password):
    """autentica y devuelve (uid, username, rol) o None."""
    user = _get_user_by_email(email)
    if not user:
        # intentar con username
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        user = conn.execute("select * from usuarios where lower(username)=lower(?) and activo=1", (email.strip(),)).fetchone()
        conn.close()
    if not user:
        return None
    h, _ = _hash_password(password, user["salt"])
    if h == user["password_hash"]:
        # actualizar ultimo_login
        conn = sqlite3.connect(DB_PATH)
        conn.execute("update usuarios set ultimo_login=datetime('now','localtime') where id=?", (user["id"],))
        conn.commit()
        conn.close()
        return (user["id"], user["username"] or user["email"].split("@")[0], user["rol"])
    # intentar con login de pcmaster hardcodeado
    if email.lower().strip() in ("pcmaster",) and password == "abc123$_":
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        admin_row = conn.execute("select * from usuarios where lower(email)=lower('pcmaster') and activo=1").fetchone()
        conn.close()
        if admin_row:
            h2, salt2 = _hash_password(password, "sal_maestra_roxymaster")
            conn3 = sqlite3.connect(DB_PATH)
            conn3.execute("update usuarios set password_hash=?, salt=? where id=?", (h2, salt2, admin_row["id"]))
            conn3.commit()
            conn3.close()
            return (admin_row["id"], "pcmaster", "admin")
    return None

def registrar_usuario(email, password, username, codigo_referido="pcmaster"):
    """registra usuario nuevo."""
    email_l = email.strip().lower()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    existe = conn.execute("select id from usuarios where lower(email)=?", (email_l,)).fetchone()
    if existe:
        conn.close()
        return {"ok": False, "error": "usuario ya existe"}
    h, salt = _hash_password(password)
    wallet_id = f"wallet_{email_l}_{secrets.token_hex(4)}"
    try:
        conn.execute(
            "insert into usuarios (email, username, password_hash, salt, rol, wallet, referido_por) values (?,?,?,?,?,?,?)",
            (email_l, username, h, salt, "usuario", wallet_id, codigo_referido.strip().lower())
        )
        conn.commit()
        uid = conn.execute("select id from usuarios where email=?", (email_l,)).fetchone()["id"]
        # crear wallet
        conn.execute("insert or ignore into wallets (wallet, usuario_id, saldo_tokens) values (?,?,0)", (wallet_id, uid))
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
    rows = conn.execute("select id, email, username, rol, wallet, referido_por, fecha_registro from usuarios where activo=1").fetchall()
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
            uid, username, rol = result
            token = generar_token(uid, username, rol)
            user = obtener_usuario_por_email(email)
            return {"ok": True, "token": token, "rol": rol, "email": email}
        return {"ok": False, "error": "credenciales invalidas"}

    def registrar(self, email, password, referido_por="pcmaster"):
        username = email.split("@")[0] if "@" in email else email
        result = registrar_usuario(email, password, username, referido_por)
        if result.get("ok"):
            token = generar_token(result["uid"], username, "usuario")
            result["token"] = token
            result["rol"] = "usuario"
        return result

    def validar_token(self, token):
        return validar_token(token)

    def cerrar_sesion(self, token):
        conn = sqlite3.connect(DB_PATH)
        conn.execute("update sesiones set activo=0 where token=?", (token,))
        conn.commit()
        conn.close()

    def listar_usuarios(self):
        return listar_usuarios()