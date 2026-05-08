# shs.py - protocolo de firma y verificacion hmac para websockets seguros
# identico en pcmaster y pcbot. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom

import hmac
import hashlib
import json
import time
from typing import Optional

from config_loader import obtener_setting

# ---------------------------------------------------------------------------
# secreto compartido (mismo en ambos extremos)
# ---------------------------------------------------------------------------
secreto_sistema = obtener_setting("secreto_sistema", "1EEEBDDF6E7FC3EC6B6F14A92D3ED39743E8E2C357425FB9CDA2E860201712F1")
secreto_bytes = secreto_sistema.encode("utf-8")

# ventana de tolerancia para timestamp (segundos)
tolerancia_timestamp = 60


def set_secreto(nuevo_secreto: str):
    """actualiza el secreto compartido usado para firmar y verificar.
    usado por ws_client cuando recibe identify_ok de pcmaster.
    """
    global secreto_bytes
    if nuevo_secreto:
        secreto_bytes = nuevo_secreto.encode("utf-8")


def firmar_payload(payload: dict, secreto_override: str = "") -> dict:
    """
    firma un payload agregando timestamp y signature hmac.
    devuelve el diccionario con los campos 'timestamp' y 'signature' agregados.
    si se pasa secreto_override, usa ese en lugar del global.
    """
    _secreto = secreto_override.encode("utf-8") if secreto_override else secreto_bytes
    ts = str(int(time.time()))
    mensaje = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    # construir mensaje para hmac: timestamp + ":" + json_payload
    msg_bytes = f"{ts}:{mensaje}".encode("utf-8")
    firma = hmac.new(_secreto, msg_bytes, hashlib.sha256).hexdigest()

    payload_firmado = dict(payload)
    payload_firmado["timestamp"] = ts
    payload_firmado["signature"] = firma
    return payload_firmado


def verificar_payload(payload: dict, secreto_override: str = "") -> bool:
    """
    verifica la firma hmac de un payload recibido.
    comprueba que el timestamp no este expirado y que la firma coincida.
    si se pasa secreto_override, usa ese en lugar del global.
    devuelve True si es valido, False en caso contrario.
    """
    try:
        ts_recibido = payload.get("timestamp", "")
        firma_recibida = payload.get("signature", "")
        _secreto = secreto_override.encode("utf-8") if secreto_override else secreto_bytes

        # verificar que el timestamp existe y esta dentro de tolerancia
        if not ts_recibido or not firma_recibida:
            return False
        ahora = int(time.time())
        if abs(ahora - int(ts_recibido)) > tolerancia_timestamp:
            return False

        # reconstruir payload sin los campos de firma
        payload_sin_firma = {k: v for k, v in payload.items() if k not in ("timestamp", "signature")}
        mensaje = json.dumps(payload_sin_firma, sort_keys=True, separators=(",", ":"))
        msg_bytes = f"{ts_recibido}:{mensaje}".encode("utf-8")

        firma_calculada = hmac.new(_secreto, msg_bytes, hashlib.sha256).hexdigest()

        return hmac.compare_digest(firma_calculada, firma_recibida)
    except (KeyError, ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# formato encapsulado compatible con orchestrator.py
# pcmaster espera: {"payload": "json_string", "firma": "hex", "timestamp": "..."}
# ---------------------------------------------------------------------------
def firmar_mensaje_encapsulado(payload: dict, secreto_override: str = "") -> str:
    """
    firma un payload y lo devuelve como json en formato encapsulado
    compatible con orchestrator.py de pcmaster.

    formato salida:
      {"payload": '{"tipo":"identify",...}', "firma": "hex...", "timestamp": "..."}

    el servidor (orchestrator.py) usara verificar_firma(payload_str, firma, secreto).
    """
    _secreto = secreto_override if secreto_override else secreto_sistema
    ts = str(int(time.time()))
    payload_json = json.dumps(payload, ensure_ascii=False)
    msg_bytes = payload_json.encode("utf-8")
    firma = hmac.new(_secreto.encode("utf-8"), msg_bytes, hashlib.sha256).hexdigest()
    mensaje = {
        "payload": payload_json,
        "firma": firma,
        "timestamp": ts,
    }
    return json.dumps(mensaje, separators=(",", ":"))


def firmar_mensaje_simple(payload: dict) -> str:
    """
    envia un payload sin firma en formato encapsulado minimo.
    usado para el handshake inicial cuando no tenemos secreto (bootstrap).
    el servidor detecta solicitar_secreto:true y lo acepta sin firma.

    formato salida:
      {"payload": '{"tipo":"identify","solicitar_secreto":true,...}', "firma": "", "timestamp": "..."}
    """
    ts = str(int(time.time()))
    payload_json = json.dumps(payload, ensure_ascii=False)
    mensaje = {
        "payload": payload_json,
        "firma": "",
        "timestamp": ts,
    }
    return json.dumps(mensaje, separators=(",", ":"))


def verificar_mensaje_encapsulado(mensaje_str: str, secreto_override: str = "") -> Optional[dict]:
    """
    verifica un mensaje recibido en formato encapsulado compatible con orchestrator.

    formato esperado:
      {"payload": '{"tipo":"identify_ok",...}', "firma": "hex...", "timestamp": "..."}

    si la verificacion es exitosa, devuelve el dict del payload interno.
    si falla, devuelve None.
    """
    try:
        mensaje = json.loads(mensaje_str)
    except (json.JSONDecodeError, TypeError):
        return None

    payload_str = mensaje.get("payload", "")
    firma_recibida = mensaje.get("firma", "")
    if not payload_str:
        return None

    # si no hay firma (mensaje bootstrap), devolver payload sin verificar
    if not firma_recibida:
        try:
            return json.loads(payload_str)
        except (json.JSONDecodeError, TypeError):
            return None

    # verificar firma
    _secreto = secreto_override if secreto_override else secreto_sistema
    esperada = hmac.new(
        _secreto.encode("utf-8"),
        payload_str.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if hmac.compare_digest(esperada, firma_recibida):
        try:
            return json.loads(payload_str)
        except (json.JSONDecodeError, TypeError):
            return None
    return None


# ---------------------------------------------------------------------------
# funciones legacy (formato auto-firmado timestamp+signature)
# ---------------------------------------------------------------------------
def firmar_mensaje_ws(mensaje: dict) -> str:
    """firma un mensaje para websocket y devuelve el json como string."""
    payload_firmado = firmar_payload(mensaje)
    return json.dumps(payload_firmado, separators=(",", ":"))


def verificar_mensaje_ws(mensaje_str: str) -> Optional[dict]:
    """verifica un mensaje ws recibido como string.
    devuelve el payload sin firma si es valido, o None si falla."""
    try:
        payload = json.loads(mensaje_str)
    except (json.JSONDecodeError, TypeError):
        return None
    if verificar_payload(payload):
        return {k: v for k, v in payload.items() if k not in ("timestamp", "signature")}
    return None


def generar_nonce(longitud: int = 16) -> str:
    """genera un nonce aleatorio hexadecimal para handshakes ws."""
    import secrets
    return secrets.token_hex(longitud)


def generar_secreto_pcbot() -> str:
    """genera un secreto unico de 32 bytes hex para un pcbot, usando uuid4 + token aleatorio."""
    import secrets as _s
    import uuid as _u
    return f"shs_{_u.uuid4().hex[:16]}_{_s.token_hex(24)}"


def handshake_firmar(nonce: str, pcbot_id: str) -> str:
    """firma un handshake ws: hmac(secreto, nonce + ':' + pcbot_id)."""
    msg = f"{nonce}:{pcbot_id}".encode("utf-8")
    return hmac.new(secreto_bytes, msg, hashlib.sha256).hexdigest()


def handshake_verificar(nonce: str, pcbot_id: str, firma: str) -> bool:
    """verifica un handshake ws firmado."""
    esperada = handshake_firmar(nonce, pcbot_id)
    return hmac.compare_digest(esperada, firma)


# ---------------------------------------------------------------------------
# wrappers de compatibilidad para orchestrator (firmas legacy)
# ---------------------------------------------------------------------------
def firmar(payload_json: str, secreto: str = "") -> str:
    """firma un payload json en string con hmac usando el secreto del sistema."""
    _secreto = secreto if secreto else secreto_sistema
    msg_bytes = f"{payload_json}".encode("utf-8")
    return hmac.new(_secreto.encode("utf-8"), msg_bytes, hashlib.sha256).hexdigest()


def verificar_firma(payload_json: str, firma_recibida: str, secreto: str = "") -> bool:
    """verifica la firma hmac de un payload json en string."""
    _secreto = secreto if secreto else secreto_sistema
    esperada = hmac.new(
        _secreto.encode("utf-8"),
        payload_json.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(esperada, firma_recibida)


if __name__ == "__main__":
    # test rapidos de compatibilidad
    prueba = {"tipo": "identify", "pcbot_id": "test_pc"}
    firmado = firmar_payload(prueba)
    assert verificar_payload(firmado), "verificacion debe pasar"
    # test encapsulado
    enc = firmar_mensaje_encapsulado(prueba)
    resultado = verificar_mensaje_encapsulado(enc)
    assert resultado is not None, "encapsulado debe verificar"
    assert resultado.get("tipo") == "identify", "payload debe coincidir"
    # test encapsulado sin firma
    simple = firmar_mensaje_simple(prueba)
    resultado2 = verificar_mensaje_encapsulado(simple)
    assert resultado2 is not None, "simple debe verificar sin firma"
    print("shs tests pasados")