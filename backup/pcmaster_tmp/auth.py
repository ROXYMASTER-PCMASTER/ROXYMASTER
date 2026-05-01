# ============================================================================
# ROXYMASTER v7.0 - AUTH MODULE
# Gestion de sesiones y usuarios (sin validacion de email)
# ============================================================================

import hashlib
import secrets
import time

class AuthManager:
    """Maneja usuarios y sesiones del sistema."""

    def __init__(self):
        self.sesiones = {}   # token -> {"email": str, "rol": str, "creado": float, "pcbot_id": str}
        self.usuarios = {}   # email -> {"password_hash": str, "rol": str, "pcbot_id": str}

        # Admin por defecto
        admin_email = "PCMASTER"
        admin_hash = hashlib.sha256("Abc123$_".encode()).hexdigest()
        self.usuarios[admin_email] = {
            "password_hash": admin_hash,
            "rol": "admin",
            "pcbot_id": "PCMASTER_SERVER"
        }

    def registrar(self, email: str, password: str, pcbot_id: str = None) -> dict:
        """Registra un nuevo usuario. Retorna {ok, token, error}."""
        email = email.strip().upper()
        if email in self.usuarios:
            return {"ok": False, "error": "Usuario ya existe"}
        if len(password) < 4:
            return {"ok": False, "error": "Contrasena muy corta (min 4)"}

        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        self.usuarios[email] = {
            "password_hash": pw_hash,
            "rol": "granjero",
            "pcbot_id": pcbot_id or ""
        }

        # Crear sesion automatica
        token = self._crear_sesion(email, "granjero", pcbot_id)
        return {"ok": True, "token": token, "rol": "granjero"}

    def login(self, email: str, password: str, pcbot_id: str = None) -> dict:
        """Inicia sesion. Retorna {ok, token, rol, error}."""
        email = email.strip().upper()
        user = self.usuarios.get(email)
        if not user:
            return {"ok": False, "error": "Usuario no encontrado"}

        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        if pw_hash != user["password_hash"]:
            return {"ok": False, "error": "Contrasena incorrecta"}

        # Actualizar pcbot_id si viene
        if pcbot_id:
            user["pcbot_id"] = pcbot_id

        token = self._crear_sesion(email, user["rol"], user.get("pcbot_id", ""))
        return {"ok": True, "token": token, "rol": user["rol"]}

    def validar_token(self, token: str) -> dict:
        """Valida un token de sesion. Retorna {valido, email, rol, pcbot_id}."""
        sesion = self.sesiones.get(token)
        if not sesion:
            return {"valido": False, "error": "Token invalido"}
        # Sesiones expiran a las 24h
        if time.time() - sesion["creado"] > 86400:
            del self.sesiones[token]
            return {"valido": False, "error": "Token expirado"}
        return {
            "valido": True,
            "email": sesion["email"],
            "rol": sesion["rol"],
            "pcbot_id": sesion.get("pcbot_id", "")
        }

    def cerrar_sesion(self, token: str):
        """Elimina una sesion."""
        self.sesiones.pop(token, None)

    def _crear_sesion(self, email: str, rol: str, pcbot_id: str = None) -> str:
        token = secrets.token_hex(32)
        self.sesiones[token] = {
            "email": email,
            "rol": rol,
            "creado": time.time(),
            "pcbot_id": pcbot_id or ""
        }
        return token