"""
ROXYMASTER v8.0 - AUTH MANAGER (PCMASTER)
Manejo de sesiones de usuario (login/logout).
Cada usuario se identifica con correo y contraseña.
Relaciona sesiones con PCBOTs.
"""

import hashlib
import json
import logging
import os
import time

from pcmaster.scripts.config_loader import DATA_DIR

logger = logging.getLogger(__name__)

USERS_FILE = os.path.join(DATA_DIR, "users.json")


class AuthManager:
    def __init__(self):
        self.sessions = {}
        self.users = {}
        self._load()

    def _load(self):
        if os.path.isfile(USERS_FILE):
            try:
                with open(USERS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.users = data.get("users", {})
            except Exception as e:
                logger.warning(f"No se pudo cargar users.json: {e}")

    def _save(self):
        try:
            with open(USERS_FILE, "w", encoding="utf-8") as f:
                json.dump({"users": self.users}, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"No se pudo guardar users.json: {e}")

    def _hash_pass(self, password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    def register(self, email: str, password: str) -> bool:
        if email in self.users:
            return False
        self.users[email] = {
            "email": email,
            "password_hash": self._hash_pass(password),
            "created_at": time.time(),
            "kbt_generados": 0,
            "kbt_comprados": 0,
        }
        self._save()
        logger.info(f"Usuario registrado: {email}")
        return True

    def login(self, email: str, password: str) -> str:
        user = self.users.get(email)
        if not user:
            return ""
        if user["password_hash"] != self._hash_pass(password):
            return ""

        import uuid
        session_id = str(uuid.uuid4())[:12]
        self.sessions[session_id] = {
            "email": email,
            "created_at": time.time(),
            "last_activity": time.time(),
            "pcbot_ids": []
        }
        logger.info(f"Login exitoso: {email} -> sesion {session_id}")
        return session_id

    def logout(self, session_id: str):
        if session_id in self.sessions:
            email = self.sessions[session_id]["email"]
            del self.sessions[session_id]
            logger.info(f"Logout: {email}")

    def get_session(self, session_id: str) -> dict:
        return self.sessions.get(session_id, {})

    def is_valid_session(self, session_id: str) -> bool:
        return session_id in self.sessions

    def link_pcbot(self, session_id: str, pcbot_id: str):
        if session_id in self.sessions:
            if pcbot_id not in self.sessions[session_id]["pcbot_ids"]:
                self.sessions[session_id]["pcbot_ids"].append(pcbot_id)
                self.sessions[session_id]["last_activity"] = time.time()

    def get_user_pcbots(self, email: str) -> list:
        linked = []
        for sid, sdata in self.sessions.items():
            if sdata.get("email") == email:
                linked.extend(sdata.get("pcbot_ids", []))
        return linked

    def add_kbt(self, email: str, generados: int = 0, comprados: int = 0):
        if email in self.users:
            self.users[email]["kbt_generados"] += generados
            self.users[email]["kbt_comprados"] += comprados
            self._save()

    def get_user_info(self, email: str) -> dict:
        return self.users.get(email, {})