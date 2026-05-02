# ============================================================================
# shs.py - protocolo de seguridad hmac para mensajes roxymaster v8.3
# garantiza integridad y autenticidad de los mensajes websocket
# ============================================================================

import hmac
import hashlib
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
import sqlite3

# ---------------------------------------------------------------------------
# configuracion
# ---------------------------------------------------------------------------
_base_dir = Path(__file__).parent.parent.absolute()
_data_dir = _base_dir / 'data'
_db_path = _data_dir / 'roxymaster.db'

# clave secreta compartida (en produccion se genera por sesion)
_secreto_compartido = "roxymaster_kbt_v83_secreto_interno_2026"


def set_secreto(secreto: str):
    """establece la clave secreta compartida."""
    global _secreto_compartido
    _secreto_compartido = secreto


def get_secreto() -> str:
    """obtiene la clave secreta actual."""
    return _secreto_compartido


# ---------------------------------------------------------------------------
# funciones hmac
# ---------------------------------------------------------------------------

def firmar_mensaje(mensaje: dict, secreto: Optional[str] = None) -> dict:
    """firma un mensaje anadiendo un hmac."""
    key = (secreto or _secreto_compartido).encode('utf-8')
    payload = json.dumps(mensaje, sort_keys=True, ensure_ascii=False)
    firma = hmac.new(key, payload.encode('utf-8'), hashlib.sha256).hexdigest()
    return {
        'payload': mensaje,
        'hmac': firma,
        'timestamp': int(time.time()),
    }


def verificar_mensaje(mensaje_firmado: dict,
                       secreto: Optional[str] = None,
                       tolerancia_segundos: int = 300) -> Tuple[bool, Optional[dict]]:
    """verifica la firma hmac de un mensaje.
    devuelve (valido, payload) o (False, None) si la firma no coincide."""
    if 'payload' not in mensaje_firmado or 'hmac' not in mensaje_firmado:
        return False, None

    # verificar timestamp (anti-replay)
    ts = mensaje_firmado.get('timestamp', 0)
    ahora = int(time.time())
    if abs(ahora - ts) > tolerancia_segundos:
        return False, None

    key = (secreto or _secreto_compartido).encode('utf-8')
    payload = mensaje_firmado['payload']
    payload_str = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    firma_esperada = hmac.new(key, payload_str.encode('utf-8'),
                               hashlib.sha256).hexdigest()

    if hmac.compare_digest(mensaje_firmado['hmac'], firma_esperada):
        return True, payload
    return False, None


def firmar_respuesta(payload: dict, secreto: Optional[str] = None) -> str:
    """firma y serializa una respuesta como json string."""
    firmado = firmar_mensaje(payload, secreto)
    return json.dumps(firmado, ensure_ascii=False)


def verificar_y_extraer(mensaje_json: str,
                         secreto: Optional[str] = None) -> Tuple[bool, Optional[dict]]:
    """parsea un json, verifica firma y extrae el payload."""
    try:
        firmado = json.loads(mensaje_json)
    except (json.JSONDecodeError, TypeError):
        return False, None
    return verificar_mensaje(firmado, secreto)


# ---------------------------------------------------------------------------
# gestion de sesiones seguras con pcbot
# ---------------------------------------------------------------------------

def generar_token_sesion(pcbot_id: str) -> str:
    """genera un token de sesion unico para un pcbot."""
    semilla = f"{pcbot_id}_{time.time()}_{id(pcbot_id)}"
    token = hmac.new(
        _secreto_compartido.encode('utf-8'),
        semilla.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()[:32]
    return token


def validar_token_sesion(pcbot_id: str, token: str) -> bool:
    """valida que un token de sesion sea correcto."""
    conn = sqlite3.connect(str(_db_path))
    c = conn.cursor()
    c.execute(
        'select token_sesion from pcbot_registrados '
        'where pcbot_id = ?',
        (pcbot_id,))
    row = c.fetchone()
    conn.close()
    if row and row[0]:
        return hmac.compare_digest(row[0], token)
    return False


def registrar_token_sesion(pcbot_id: str, token: str):
    """almacena el token de sesion en la base de datos."""
    conn = sqlite3.connect(str(_db_path))
    c = conn.cursor()
    c.execute(
        'update pcbot_registrados set token_sesion = ? '
        'where pcbot_id = ?',
        (token, pcbot_id))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# autenticacion de mensajes pcbot <-> pcmaster
# ---------------------------------------------------------------------------

def crear_handshake(pcbot_id: str, token: str,
                     info_sistema: dict) -> str:
    """crea el mensaje de handshake firmado para la conexion inicial."""
    mensaje = {
        'tipo': 'handshake',
        'pcbot_id': pcbot_id,
        'token': token,
        'info_sistema': info_sistema,
    }
    return firmar_respuesta(mensaje)


def crear_heartbeat(pcbot_id: str, token: str,
                     estado_perfiles: list) -> str:
    """crea el mensaje de heartbeat firmado."""
    mensaje = {
        'tipo': 'heartbeat',
        'pcbot_id': pcbot_id,
        'token': token,
        'perfiles': estado_perfiles,
        'timestamp': int(time.time()),
    }
    return firmar_respuesta(mensaje)


def crear_comando_respuesta(comando_id: str, resultado: dict) -> str:
    """crea una respuesta firmada a un comando."""
    mensaje = {
        'tipo': 'respuesta_comando',
        'comando_id': comando_id,
        'resultado': resultado,
        'timestamp': int(time.time()),
    }
    return firmar_respuesta(mensaje)


def crear_comando_pcmaster(comando_id: str, accion: str,
                             datos: dict) -> str:
    """crea un comando firmado desde pcmaster hacia pcbot."""
    mensaje = {
        'tipo': 'comando',
        'comando_id': comando_id,
        'accion': accion,
        'datos': datos,
        'timestamp': int(time.time()),
    }
    return firmar_respuesta(mensaje)


# ---------------------------------------------------------------------------
# utilidades de seguridad
# ---------------------------------------------------------------------------

def hash_contenido(contenido: str) -> str:
    """genera un hash sha256 de un contenido."""
    return hashlib.sha256(contenido.encode('utf-8')).hexdigest()


def comparar_hashes(h1: str, h2: str) -> bool:
    """compara dos hashes de forma segura (timing-attack safe)."""
    return hmac.compare_digest(h1, h2)


def generar_nonce(longitud: int = 16) -> str:
    """genera un nonce aleatorio."""
    import secrets
    return secrets.token_hex(longitud)


def encriptar_mensaje_simple(mensaje: str, clave: Optional[str] = None) -> str:
    """encriptacion simple xor con clave para ofuscacion adicional.
    no es criptograficamente segura, es una capa extra."""
    key = (clave or _secreto_compartido)
    key_bytes = key.encode('utf-8')
    msg_bytes = mensaje.encode('utf-8')
    result = bytearray()
    for i, b in enumerate(msg_bytes):
        result.append(b ^ key_bytes[i % len(key_bytes)])
    return result.hex()


def desencriptar_mensaje_simple(cifrado_hex: str,
                                 clave: Optional[str] = None) -> str:
    """desencripta un mensaje ofuscado con xor."""
    key = (clave or _secreto_compartido)
    key_bytes = key.encode('utf-8')
    try:
        cifrado = bytes.fromhex(cifrado_hex)
    except ValueError:
        return ''
    result = bytearray()
    for i, b in enumerate(cifrado):
        result.append(b ^ key_bytes[i % len(key_bytes)])
    return result.decode('utf-8', errors='replace')


# ---------------------------------------------------------------------------
# registro de eventos de seguridad
# ---------------------------------------------------------------------------

def init_seguridad_db():
    """crea la tabla de eventos de seguridad."""
    conn = sqlite3.connect(str(_db_path))
    c = conn.cursor()
    c.execute('''
        create table if not exists eventos_seguridad (
            id integer primary key autoincrement,
            tipo text not null,
            pcbot_id text,
            detalle text,
            ip_origen text,
            fecha text default (datetime('now', 'localtime'))
        )
    ''')
    conn.commit()
    conn.close()


def registrar_evento_seguridad(tipo: str, pcbot_id: Optional[str] = None,
                                detalle: str = '',
                                ip_origen: Optional[str] = None):
    """registra un evento de seguridad."""
    conn = sqlite3.connect(str(_db_path))
    c = conn.cursor()
    c.execute(
        'insert into eventos_seguridad (tipo, pcbot_id, detalle, ip_origen) '
        'values (?, ?, ?, ?)',
        (tipo, pcbot_id, detalle, ip_origen))
    conn.commit()
    conn.close()


def obtener_eventos_seguridad(limite: int = 100) -> list:
    """obtiene los ultimos eventos de seguridad."""
    conn = sqlite3.connect(str(_db_path))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        'select * from eventos_seguridad '
        'order by fecha desc limit ?',
        (limite,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# inicializacion
# ---------------------------------------------------------------------------

init_seguridad_db()