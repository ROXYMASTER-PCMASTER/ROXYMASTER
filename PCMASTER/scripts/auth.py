import hashlib, secrets, time, sqlite3, os
from config import DATA_DIR
DB_PATH = os.path.join(DATA_DIR, "roxymaster.db")
try:
    import bcrypt
    BCRYPT = True
except ImportError:
    BCRYPT = False

def hash_password(password):
    if BCRYPT:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    return hashlib.sha256(f"roxymaster_salt_{password}".encode()).hexdigest()

def verify_password(password, hash_val):
    if BCRYPT:
        try:
            return bcrypt.checkpw(password.encode(), hash_val.encode())
        except: pass
    return hash_val == hashlib.sha256(f"roxymaster_salt_{password}".encode()).hexdigest()

class AuthManager:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.sesiones = {}
        self._init_db()

    def _init_db(self):
        self.conn.executescript('''
            create table if not exists auth_users (
                email text primary key,
                password_hash text not null,
                rol text default 'granjero',
                pcbot_id text,
                saldo_tokens real default 0,
                referido_por text,
                codigo_referido text,
                fecha_registro text default (datetime('now')),
                referido_cambiado integer default 0
            );
            create table if not exists auth_tokens (
                token text primary key,
                email text not null,
                expires text not null
            );
        ''')
        self.conn.commit()
        if not self.conn.execute("select 1 from auth_users where email='pcmaster'").fetchone():
            self.conn.execute("insert into auth_users (email,password_hash,rol,referido_por,codigo_referido) values (?,?,?,?,?)",
                              ("pcmaster", hash_password("abc123$_"), "admin", "pcmaster", "pcmaster"))
            self.conn.commit()

    def registrar(self, email, password, referido_por="pcmaster"):
        email = email.lower()
        referido_por = referido_por.lower()
        if self.conn.execute("select 1 from auth_users where email=?", (email,)).fetchone():
            return {"ok": False, "error": "usuario ya existe"}
        if len(password) < 4:
            return {"ok": False, "error": "contraseña muy corta"}
        hash_val = hash_password(password)
        self.conn.execute("insert into auth_users (email,password_hash,rol,referido_por) values (?,?,?,?)",
                          (email, hash_val, "granjero", referido_por))
        self.conn.commit()
        token = self._crear_sesion(email, "granjero")
        return {"ok": True, "token": token, "rol": "granjero", "email": email}

    def login(self, email, password):
        email = email.lower()
        row = self.conn.execute("select * from auth_users where email=?", (email,)).fetchone()
        if not row: return {"ok": False, "error": "usuario no encontrado"}
        if not verify_password(password, row["password_hash"]):
            return {"ok": False, "error": "contraseña incorrecta"}
        token = self._crear_sesion(email, row["rol"])
        return {"ok": True, "token": token, "rol": row["rol"], "email": email}

    def validar_token(self, token):
        sesion = self.sesiones.get(token)
        if not sesion: return {"valido": False, "error": "token invalido"}
        if time.time() - sesion["creado"] > 86400:
            del self.sesiones[token]
            return {"valido": False, "error": "token expirado"}
        return {"valido": True, "email": sesion["email"], "rol": sesion["rol"]}

    def cerrar_sesion(self, token):
        self.sesiones.pop(token, None)

    def listar_usuarios(self):
        rows = self.conn.execute("select email, rol, saldo_tokens, referido_por, fecha_registro from auth_users where rol != 'admin'").fetchall()
        return [{"email": r["email"], "rol": r["rol"], "saldo_tokens": r["saldo_tokens"], "referido_por": r["referido_por"], "fecha_registro": r["fecha_registro"]} for r in rows]

    def _crear_sesion(self, email, rol):
        token = secrets.token_hex(32)
        self.sesiones[token] = {"email": email, "rol": rol, "creado": time.time()}
        return token

    @property
    def usuarios(self):
        return {r["email"]: dict(r) for r in self.conn.execute("select * from auth_users").fetchall()}
