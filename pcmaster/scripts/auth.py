# auth.py - autenticacion pbkdf2, registro, login, verificacion de token y roles
# roxymaster v8.3. todos los nombres en minusculas, utf-8 sin bom

import hashlib
import secrets
import uuid
import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from db import ejecutar_sql, ejecutar_sql_unico, ejecutar_insercion
from variables_globales import init_variables_db

bearer_scheme = HTTPBearer(auto_error=False)

# configuracion de hashing
hash_iteraciones = 310000
hash_longitud_salt = 24
hash_longitud_hash = 64

# expiracion de token de sesion (24 horas)
expiracion_sesion_horas = 24

# regex para validar email (basico, sin mayusculas)
email_regex = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$")


def encriptar_password(password: str, salt: str = None) -> tuple:
    """
    hashea una contraseña con pbkdf2-hmac-sha256.
    devuelve (hash_hex, salt_hex). si no se proporciona salt, genera uno nuevo.
    """
    if salt is None:
        salt = secrets.token_hex(hash_longitud_salt)
    if isinstance(salt, str):
        salt_bytes = salt.encode("utf-8")
    else:
        salt_bytes = salt
    hash_bytes = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_bytes,
        hash_iteraciones,
        dklen=hash_longitud_hash,
    )
    return hash_bytes.hex(), salt if isinstance(salt, str) else salt_bytes.hex()


def verificar_password(password: str, salt: str, hash_almacenado: str) -> bool:
    """verifica una contraseña contra el hash almacenado con comparacion en tiempo constante."""
    hash_calculado, _ = encriptar_password(password, salt)
    return secrets.compare_digest(hash_calculado, hash_almacenado)


def generar_token() -> str:
    """genera un token de sesion aleatorio (uuid4 + hex)."""
    return uuid.uuid4().hex + secrets.token_hex(16)


def generar_codigo_referido() -> str:
    """genera un codigo de referido unico de 8 caracteres alfanumericos en minusculas."""
    import random
    import string
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def validar_email(email: str) -> bool:
    """valida el formato basico de un email (solo minusculas)."""
    if not email or not isinstance(email, str):
        return False
    return bool(email_regex.match(email.lower().strip()))


def registrar_usuario(
    email: str,
    password: str,
    username: str = None,
    codigo_referido_externo: str = None,
    pcbot_id: str = None,
) -> dict:
    """
    registra un nuevo usuario en el sistema.
    devuelve un dict con exito/error y el token de sesion si fue exitoso.
    """
    email = email.lower().strip() if email else ""

    # validaciones
    if not validar_email(email):
        return {"exito": False, "error": "email invalido"}
    if not password or len(password) < 6:
        return {"exito": False, "error": "la contraseña debe tener al menos 6 caracteres"}

    # verificar si el email ya existe
    existente = ejecutar_sql_unico("select id from usuarios where email = ?", (email,))
    if existente:
        return {"exito": False, "error": "el email ya esta registrado"}

    # hashear contraseña
    hash_pw, salt = encriptar_password(password)
    password_hash = f"pbkdf2:{hash_iteraciones}:{salt}:{hash_pw}"

    # generar wallet y codigo de referido
    wallet = "kbt_" + uuid.uuid4().hex[:24]
    codigo_ref = generar_codigo_referido()

    # determinar referidor
    referido_por = "pcmaster"
    if codigo_referido_externo:
        ref_existente = ejecutar_sql_unico(
            "select id from usuarios where codigo_referido = ?", (codigo_referido_externo,)
        )
        if ref_existente:
            referido_por = codigo_referido_externo

    # insertar usuario
    usuario_id = ejecutar_insercion(
        """insert into usuarios (email, password_hash, username, rol, wallet, codigo_referido, referido_por, pcbot_id)
           values (?, ?, ?, 'usuario', ?, ?, ?, ?)""",
        (email, password_hash, username or email.split("@")[0], wallet, codigo_ref, referido_por, pcbot_id),
    )

    if not usuario_id:
        return {"exito": False, "error": "error al crear el usuario"}

    # crear wallet
    ejecutar_insercion(
        "insert into wallets (usuario_id) values (?)", (usuario_id,)
    )

    # crear codigo de referido
    ejecutar_insercion(
        "insert or ignore into codigos_referido (usuario_id, codigo) values (?, ?)",
        (usuario_id, codigo_ref),
    )

    # generar token de sesion
    token = generar_token()
    fecha_expiracion = (datetime.now() + timedelta(hours=expiracion_sesion_horas)).strftime("%Y-%m-%d %H:%M:%S")
    ejecutar_insercion(
        "insert into sesiones (token, usuario_id, email, rol, fecha_expiracion) values (?, ?, ?, 'usuario', ?)",
        (token, usuario_id, email, fecha_expiracion),
    )

    # inicializar variables globales si es el primer usuario
    init_variables_db()

    return {
        "exito": True,
        "token": token,
        "usuario_id": usuario_id,
        "email": email,
        "rol": "usuario",
        "wallet": wallet,
        "codigo_referido": codigo_ref,
    }


def iniciar_sesion(email: str, password: str) -> dict:
    """inicia sesion y devuelve token de sesion si las credenciales son correctas.
    acepta email o username como identificador."""
    credencial = (email or "").lower().strip()
    if not credencial:
        return {"exito": False, "error": "credenciales invalidas"}

    # buscar por email primero, luego por username
    usuario = ejecutar_sql_unico(
        "select id, email, password_hash, rol, activo, codigo_referido, "
        "referido_por, referido_cambiado, nivel_fiabilidad, pcbot_id from usuarios where email = ?",
        (credencial,),
    )
    if not usuario:
        usuario = ejecutar_sql_unico(
            "select id, email, password_hash, rol, activo, codigo_referido, "
            "referido_por, referido_cambiado, nivel_fiabilidad, pcbot_id from usuarios where username = ?",
            (credencial,),
        )

    if not usuario:
        return {"exito": False, "error": "credenciales incorrectas"}

    if not usuario["activo"]:
        return {"exito": False, "error": "cuenta desactivada"}

    # parsear hash almacenado: pbkdf2:iteraciones:salt:hash
    password_hash = usuario["password_hash"]
    try:
        _, iters, salt, stored_hash = password_hash.split(":")
    except ValueError:
        return {"exito": False, "error": "formato de hash invalido"}

    if not verificar_password(password, salt, stored_hash):
        return {"exito": False, "error": "credenciales incorrectas"}

    # generar token de sesion
    token = generar_token()
    fecha_expiracion = (datetime.now() + timedelta(hours=expiracion_sesion_horas)).strftime("%Y-%m-%d %H:%M:%S")
    ejecutar_insercion(
        "insert into sesiones (token, usuario_id, email, rol, fecha_expiracion) values (?, ?, ?, ?, ?)",
        (token, usuario["id"], usuario["email"], usuario["rol"], fecha_expiracion),
    )

    # actualizar ultimo_login
    ejecutar_sql(
        "update usuarios set ultimo_login = datetime('now','localtime') where id = ?",
        (usuario["id"],),
    )

    return {
        "exito": True,
        "token": token,
        "usuario_id": usuario["id"],
        "email": usuario["email"],
        "rol": usuario["rol"],
        "codigo_referido": usuario.get("codigo_referido", ""),
        "referido_por": usuario.get("referido_por", ""),
        "referido_cambiado": usuario.get("referido_cambiado", 0),
        "nivel_fiabilidad": usuario.get("nivel_fiabilidad", "bronce"),
        "pcbot_id": usuario.get("pcbot_id", ""),
    }


def verificar_token(token: str) -> dict:
    """
    verifica un token de sesion.
    devuelve dict con datos del usuario si es valido, o None si expiro/no existe.
    """
    if not token:
        return None

    sesion = ejecutar_sql_unico(
        "select s.usuario_id, s.email, s.rol, s.fecha_expiracion, u.activo "
        "from sesiones s join usuarios u on s.usuario_id = u.id "
        "where s.token = ?",
        (token,),
    )

    if not sesion:
        return None

    if not sesion["activo"]:
        # eliminar sesion si el usuario esta inactivo
        ejecutar_sql("delete from sesiones where token = ?", (token,))
        return None

    # verificar expiracion
    try:
        fecha_exp = datetime.strptime(sesion["fecha_expiracion"], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None

    if datetime.now() > fecha_exp:
        ejecutar_sql("delete from sesiones where token = ?", (token,))
        return None

    # obtener pcbot_id del usuario si existe
    usuario_info = ejecutar_sql_unico(
        "select pcbot_id from usuarios where id = ?",
        (sesion["usuario_id"],),
    )
    pcbot_id = usuario_info["pcbot_id"] if usuario_info else ""

    return {
        "usuario_id": sesion["usuario_id"],
        "email": sesion["email"],
        "rol": sesion["rol"],
        "token": token,
        "pcbot_id": pcbot_id,
    }


def cerrar_sesion(token: str):
    """elimina una sesion de la base de datos."""
    if token:
        ejecutar_sql("delete from sesiones where token = ?", (token,))


def obtener_rol(token: str) -> str:
    """obtiene el rol del usuario asociado a un token. devuelve 'anonimo' si no es valido."""
    sesion = verificar_token(token)
    return sesion["rol"] if sesion else "anonimo"


def es_admin(token: str) -> bool:
    """verifica si el token pertenece a un administrador."""
    return obtener_rol(token) == "admin"


def listar_usuarios() -> list:
    """lista todos los usuarios para el panel de administracion (sin datos sensibles)."""
    usuarios = ejecutar_sql(
        "select id, email, username, rol, nivel_fiabilidad, uptime_horas, pcbot_id, "
        "modo, ultimo_login, fecha_registro, activo, codigo_referido, referido_por "
        "from usuarios order by id"
    )
    return usuarios


def actualizar_rol_usuario(usuario_id: int, nuevo_rol: str) -> bool:
    """actualiza el rol de un usuario (admin, usuario, etc.)."""
    roles_validos = ("usuario", "admin", "moderador")
    if nuevo_rol not in roles_validos:
        return False
    filas = ejecutar_sql(
        "update usuarios set rol = ? where id = ?", (nuevo_rol, usuario_id)
    )
    return len(filas) > 0 if hasattr(filas, "__len__") else True


def cambiar_password(usuario_id: int, password_actual: str, password_nueva: str) -> dict:
    """cambia la contraseña de un usuario verificando la actual."""
    if not password_nueva or len(password_nueva) < 6:
        return {"exito": False, "error": "la nueva contraseña debe tener al menos 6 caracteres"}

    usuario = ejecutar_sql_unico(
        "select password_hash from usuarios where id = ?", (usuario_id,)
    )
    if not usuario:
        return {"exito": False, "error": "usuario no encontrado"}

    try:
        _, iters, salt, stored_hash = usuario["password_hash"].split(":")
    except ValueError:
        return {"exito": False, "error": "formato de hash invalido"}

    if not verificar_password(password_actual, salt, stored_hash):
        return {"exito": False, "error": "contraseña actual incorrecta"}

    nuevo_hash, nuevo_salt = encriptar_password(password_nueva)
    nuevo_password_hash = f"pbkdf2:{hash_iteraciones}:{nuevo_salt}:{nuevo_hash}"
    ejecutar_sql(
        "update usuarios set password_hash = ? where id = ?", (nuevo_password_hash, usuario_id)
    )

    return {"exito": True, "mensaje": "contraseña actualizada correctamente"}

def verificar_token_dependency():
    return verificar_token


# ---------------------------------------------------------------------------
# dependencias fastapi para endpoints protegidos
# ---------------------------------------------------------------------------
def verificar_token_opcional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Optional[dict]:
    """verifica token desde header authorization bearer o query param 'token'.
    devuelve dict con sesion o None si no hay token valido."""
    token = None
    if credentials:
        token = credentials.credentials
    if not token:
        token = request.query_params.get("token")
    if not token:
        token = request.headers.get("x-auth-token")
    if not token:
        return None
    try:
        return verificar_token(token)
    except Exception:
        return None


def verificar_admin_dependencia(
    sesion: dict = Depends(verificar_token_opcional),
) -> dict:
    """verifica que la sesion pertenezca a un administrador.
    lanza http 401 si no hay sesion, 403 si no es admin."""
    if not sesion:
        raise HTTPException(status_code=401, detail="token no proporcionado o invalido")
    if sesion.get("rol") != "admin":
        raise HTTPException(status_code=403, detail="acceso solo para administradores")
    return sesion


async def obtener_usuario_desde_request(request: Request = None) -> Optional[dict]:
    """obtiene el usuario autenticado desde un request.
    revisa headers, query params o cookies.
    devuelve dict con sesion o None si no autenticado."""
    if request is None:
        return None
    return verificar_token_opcional(request)

