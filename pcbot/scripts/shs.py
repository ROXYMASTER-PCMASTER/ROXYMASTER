"""
roxymaster v8.3 - protocolo de seguridad hmac.
implementacion propia usando solo biblioteca estandar.
"""
import hashlib
import hmac as hmac_lib
import json
import time
import uuid

_SECRETO = ""

# ---------------------------------------------------------------------------
# funciones de firma hmac-sha256
# ---------------------------------------------------------------------------

def set_secreto(secreto: str):
    """configura el secreto compartido."""
    global _SECRETO
    _SECRETO = secreto


def _calcular_firma(payload: dict, secreto: str) -> str:
    """calcula hmac-sha256 del payload ordenado."""
    msg = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    h = hmac_lib.new(
        secreto.encode("utf-8"),
        msg.encode("utf-8"),
        hashlib.sha256,
    )
    return h.hexdigest()


def firmar_mensaje(payload: dict, secreto: str = None) -> str:
    """firma un payload con hmac-sha256 y devuelve json string."""
    s = secreto or _SECRETO
    firma = _calcular_firma(payload, s)
    ts = int(time.time())
    firmado = {
        "firma": firma,
        "ts": ts,
        "payload": payload,
    }
    return json.dumps(firmado, ensure_ascii=False)


def verificar_mensaje(mensaje_str: str, secreto: str = None) -> tuple:
    """verifica un mensaje firmado. devuelve (valido: bool, payload: dict)."""
    s = secreto or _SECRETO
    if not s:
        return False, {}
    try:
        mensaje = json.loads(mensaje_str)
    except (json.JSONDecodeError, TypeError):
        return False, {}
    firma = mensaje.get("firma", "")
    payload = mensaje.get("payload", {})
    if not firma or not payload:
        return False, {}
    firma_esperada = _calcular_firma(payload, s)
    # comparacion constante en tiempo para evitar timing attack
    if not hmac_lib.compare_digest(firma, firma_esperada):
        return False, {}
    return True, payload


def firmar_respuesta(payload: dict, secreto: str = None) -> str:
    """alias de firmar_mensaje para compatibilidad."""
    return firmar_mensaje(payload, secreto)


def verificar_y_extraer(mensaje_str: str, secreto: str = None) -> tuple:
    """alias de verificar_mensaje para compatibilidad."""
    return verificar_mensaje(mensaje_str, secreto)


def generar_token_sesion(pcbot_id: str = None) -> str:
    """genera un token de sesion unico."""
    if pcbot_id is None:
        pcbot_id = uuid.uuid4().hex[:12]
    return f"{pcbot_id}_{uuid.uuid4().hex}"


# si se ejecuta directamente, prueba basica
if __name__ == "__main__":
    set_secreto("test_secret")
    msg = firmar_mensaje({"comando": "ping"})
    print(f"mensaje firmado: {msg[:60]}...")
    val, payload = verificar_mensaje(msg)
    print(f"verificacion: {'ok' if val else 'fallo'}")
    print(f"payload: {payload}")