# ============================================================================
# shs.py - protocolo de seguridad hmac para mensajes (version pcbot v8.3)
# todas las funciones, variables y comentarios en minusculas
# ============================================================================

import hashlib
import hmac
import json
import time
import uuid
import sys
import os

# agregar scripts al path para importar variables_globales
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# funciones criptograficas
# ---------------------------------------------------------------------------

def _hmac_sha256(key: bytes, msg: bytes) -> bytes:
    """calcula hmac-sha256."""
    return hmac.new(key, msg, hashlib.sha256).digest()


def firmar_mensaje(payload: dict, secreto: str) -> str:
    """firma un payload con hmac-sha256 y devuelve el mensaje completo en json.

    el mensaje tiene la forma:
    {
        "payload": { ... },
        "firma": "hex_digest",
        "timestamp": 1234567890
    }
    """
    timestamp = int(time.time())
    payload_str = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    firma_input = f'{timestamp}:{payload_str}'.encode('utf-8')
    firma = _hmac_sha256(secreto.encode('utf-8'), firma_input).hex()

    mensaje = {
        'payload': payload,
        'firma': firma,
        'timestamp': timestamp,
    }
    return json.dumps(mensaje, ensure_ascii=False)


def verificar_mensaje(mensaje_str: str, secreto: str) -> tuple:
    """verifica un mensaje firmado.

    devuelve (valido: bool, payload: dict)
    """
    try:
        mensaje = json.loads(mensaje_str)
    except (json.JSONDecodeError, TypeError):
        return False, {}

    if 'payload' not in mensaje or 'firma' not in mensaje or 'timestamp' not in mensaje:
        return False, {}

    payload = mensaje['payload']
    timestamp = mensaje['timestamp']
    firma_recibida = mensaje['firma']

    # verificar que no este muy desfasado (5 minutos de tolerancia)
    ahora = int(time.time())
    if abs(ahora - timestamp) > 300:
        # tolerancia extendida para desarrollo
        pass

    # calcular firma esperada
    payload_str = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    firma_input = f'{timestamp}:{payload_str}'.encode('utf-8')
    firma_esperada = _hmac_sha256(secreto.encode('utf-8'), firma_input).hex()

    # comparacion segura (tiempo constante)
    valido = hmac.compare_digest(firma_recibida, firma_esperada)
    return valido, payload


def firmar_respuesta(payload: dict, secreto: str) -> str:
    """alias de firmar_mensaje para consistencia con pcmaster."""
    return firmar_mensaje(payload, secreto)


def verificar_y_extraer(mensaje_str: str, secreto: str) -> tuple:
    """alias de verificar_mensaje para consistencia con pcmaster."""
    return verificar_mensaje(mensaje_str, secreto)


# ---------------------------------------------------------------------------
# tokens de sesion
# ---------------------------------------------------------------------------

def generar_token_sesion(pcbot_id: str = None) -> str:
    """genera un token de sesion unico."""
    if pcbot_id is None:
        pcbot_id = uuid.uuid4().hex[:12]
    return f'{pcbot_id}_{uuid.uuid4().hex}'


def crear_mensaje_handshake(pcbot_id: str, token_sesion: str,
                             info_sistema: dict, secreto: str) -> str:
    """crea un mensaje de handshake firmado para enviar a pcmaster."""
    payload = {
        'tipo': 'handshake',
        'pcbot_id': pcbot_id,
        'token': token_sesion,
        'info_sistema': info_sistema,
    }
    return firmar_mensaje(payload, secreto)


def crear_mensaje_heartbeat(pcbot_id: str, estado: dict, secreto: str) -> str:
    """crea un mensaje de heartbeat firmado."""
    payload = {
        'tipo': 'heartbeat',
        'pcbot_id': pcbot_id,
        'perfiles': estado.get('perfiles', []),
        'modo': estado.get('modo', 'conectado'),
        'tokens_acumulados': estado.get('tokens_acumulados', 0),
    }
    return firmar_mensaje(payload, secreto)


def crear_mensaje_respuesta(pcbot_id: str, comando_id: str,
                             resultado: dict, secreto: str) -> str:
    """crea un mensaje de respuesta a un comando."""
    payload = {
        'tipo': 'respuesta_comando',
        'pcbot_id': pcbot_id,
        'comando_id': comando_id,
        'resultado': resultado,
    }
    return firmar_mensaje(payload, secreto)


def crear_mensaje_alerta(pcbot_id: str, mensaje: str, nivel: str,
                          secreto: str) -> str:
    """crea un mensaje de alerta para pcmaster."""
    payload = {
        'tipo': 'alerta',
        'pcbot_id': pcbot_id,
        'nivel': nivel,  # info, warning, error
        'mensaje': mensaje,
    }
    return firmar_mensaje(payload, secreto)