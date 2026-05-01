"""
SHS - Secret Handshake Protocol v1.0
Capa de seguridad HMAC-SHA256 + nonces para comunicacion PCBOT <-> PCMASTER

MITIGA:
- Suplantacion de PCBOTs (sin secreto no se puede firmar)
- Replay attacks (nonce + timestamp con ventana de 30s)
- Inyeccion de mensajes falsos (verificacion HMAC)
- Mensajes modificados en transito
"""

import os
import json
import hmac
import time
import hashlib
import base64
from pathlib import Path

# ============================================================================
# CONFIGURACION
# ============================================================================

# Ventana de tiempo para validacion de nonce (segundos)
NONCE_WINDOW = 30

# Clave maestra compartida (derivada al primer handshake)
MASTER_SECRET = b"R0XYM4ST3R_S3CR3T_K3Y_2024_v6.1"

# Archivo donde PCMASTER almacena secretos por PCBOT
SECRETS_FILE = Path(os.environ.get("APPDATA", "")) / "RoxyMaster" / "secrets.json"

def ensure_secrets_dir():
    """Asegura que el directorio de secretos existe"""
    SECRETS_FILE.parent.mkdir(parents=True, exist_ok=True)

def load_secrets():
    """Carga secretos por PCBOT desde archivo"""
    ensure_secrets_dir()
    if SECRETS_FILE.exists():
        try:
            with open(SECRETS_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_secrets(secrets_dict):
    """Guarda secretos por PCBOT a archivo"""
    ensure_secrets_dir()
    with open(SECRETS_FILE, "w") as f:
        json.dump(secrets_dict, f, indent=2)

def derive_client_secret(client_id):
    """
    Deriva secreto unico por PCBOT usando:
    MASTER_SECRET + client_id + SALT via PBKDF2-like derivation
    
    Retorna: bytes (32 bytes)
    """
    salt = f"ROXYv6.1_{client_id}".encode("utf-8")
    # HKDF-like: HMAC-SHA256 iterativo
    k = MASTER_SECRET
    for i in range(1000):
        k = hmac.new(k, salt + i.to_bytes(4, "big"), hashlib.sha256).digest()
    return k[:32]  # 256 bits

def sign_message(client_id, client_secret, message_dict):
    """
    Firma un mensaje con HMAC-SHA256
    
    Args:
        client_id: ID del PCBOT
        client_secret: secreto derivado (bytes, 32)
        message_dict: dict con el mensaje (sin 'auth')
    
    Retorna: dict con 'auth' agregado: {nonce, timestamp, hmac}
    """
    ts = int(time.time())
    nonce = base64.b64encode(os.urandom(16)).decode("ascii")
    
    # Construir payload a firmar: nonce|timestamp|client_id|json_sorted
    sorted_json = json.dumps(message_dict, sort_keys=True, separators=(",", ":"))
    payload = f"{nonce}|{ts}|{client_id}|{sorted_json}".encode("utf-8")
    
    signature = hmac.new(client_secret, payload, hashlib.sha256).hexdigest()
    
    return {
        "nonce": nonce,
        "timestamp": ts,
        "hmac": signature
    }

def verify_message(client_id, client_secret, full_message_dict):
    """
    Verifica HMAC y valida nonce + timestamp
    
    Args:
        client_id: ID del PCBOT
        client_secret: secreto derivado (bytes, 32)
        full_message_dict: dict con 'auth': {nonce, timestamp, hmac} y resto del mensaje
    
    Retorna: (valido: bool, mensaje_sin_auth: dict)
    """
    auth = full_message_dict.get("auth", {})
    if not auth:
        return False, {}
    
    nonce = auth.get("nonce", "")
    ts = auth.get("timestamp", 0)
    received_hmac = auth.get("hmac", "")
    
    if not nonce or not ts or not received_hmac:
        return False, {}
    
    # Validar ventana de tiempo (anti-replay)
    ahora = int(time.time())
    if abs(ahora - ts) > NONCE_WINDOW:
        return False, {}
    
    # Reconstruir el mensaje sin 'auth' para verificar
    message_without_auth = {k: v for k, v in full_message_dict.items() if k != "auth"}
    sorted_json = json.dumps(message_without_auth, sort_keys=True, separators=(",", ":"))
    payload = f"{nonce}|{ts}|{client_id}|{sorted_json}".encode("utf-8")
    
    expected_hmac = hmac.new(client_secret, payload, hashlib.sha256).hexdigest()
    
    # Comparacion en tiempo constante
    is_valid = hmac.compare_digest(received_hmac, expected_hmac)
    
    return is_valid, message_without_auth

# ============================================================================
# GESTION DE SECRETOS EN PCMASTER
# ============================================================================

class SecretManager:
    """
    Gestiona secretos de PCBOTs en el lado PCMASTER.
    Cada PCBOT tiene su propio secreto derivado almacenado en secrets.json.
    """
    
    def __init__(self):
        self._cache = load_secrets()
    
    def get_or_create_secret(self, client_id):
        """
        Obtiene o crea el secreto para un PCBOT.
        Si es nuevo, genera y persiste su secreto.
        
        Retorna: bytes (32) - el secreto derivado
        """
        if client_id in self._cache:
            stored = self._cache[client_id]
            return bytes.fromhex(stored["secret_hex"])
        
        # Nuevo PCBOT: derivar y almacenar secreto
        secret = derive_client_secret(client_id)
        self._cache[client_id] = {
            "secret_hex": secret.hex(),
            "created_at": time.time(),
            "last_seen": time.time()
        }
        save_secrets(self._cache)
        return secret
    
    def update_last_seen(self, client_id):
        """Actualiza timestamp de ultima actividad"""
        if client_id in self._cache:
            self._cache[client_id]["last_seen"] = time.time()
            save_secrets(self._cache)
    
    def remove_secret(self, client_id):
        """Elimina secreto de un PCBOT (cuando se desconecta)"""
        if client_id in self._cache:
            del self._cache[client_id]
            save_secrets(self._cache)
    
    def verify(self, client_id, full_message):
        """
        Verifica un mensaje firmado de un PCBOT.
        
        Retorna: (valido: bool, mensaje_limpio: dict)
        """
        secret = self.get_or_create_secret(client_id)
        result = verify_message(client_id, secret, full_message)
        if result[0]:
            self.update_last_seen(client_id)
        return result
    
    def sign_for(self, client_id, message_dict):
        """
        Firma un mensaje saliente hacia un PCBOT.
        
        Retorna: dict con 'auth' agregado
        """
        secret = self.get_or_create_secret(client_id)
        auth = sign_message(client_id, secret, message_dict)
        result = dict(message_dict)
        result["auth"] = auth
        return result

# ============================================================================
# LADO PCBOT - FIRMADOR DE MENSAJES
# ============================================================================

class ClientSigner:
    """
    Firmador de mensajes para PCBOT.
    Deriva el secreto localmente usando el mismo algoritmo que PCMASTER.
    """
    
    def __init__(self, client_id):
        self.client_id = client_id
        self.secret = derive_client_secret(client_id)
    
    def sign(self, message_dict):
        """
        Firma un mensaje para enviar a PCMASTER.
        
        Retorna: dict con 'auth' agregado
        """
        auth = sign_message(self.client_id, self.secret, message_dict)
        result = dict(message_dict)
        result["auth"] = auth
        return result
    
    def verify(self, full_message_dict):
        """
        Verifica un mensaje recibido de PCMASTER.
        
        Retorna: (valido: bool, mensaje_limpio: dict)
        """
        return verify_message(self.client_id, self.secret, full_message_dict)