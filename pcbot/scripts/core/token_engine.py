"""
ROXYMASTER v8.0 - TOKEN ENGINE (PCBOT)
Manejo local de KBT (Kick Token) ganados.
Cada 62 min de sesion ininterrumpida = 1 KBT.
Los KBT generados se reportan a PCMASTER para su registro central.
"""

import json
import logging
import os

from config_loader import DATA_DIR

logger = logging.getLogger(__name__)

TOKENS_FILE = os.path.join(DATA_DIR, "tokens.json")


class TokenEngine:
    def __init__(self):
        self.kbt_generados = 0
        self.kbt_comprados = 0
        self.historial = []
        self._load()

    def _load(self):
        if os.path.isfile(TOKENS_FILE):
            try:
                with open(TOKENS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.kbt_generados = data.get("generados", 0)
                    self.kbt_comprados = data.get("comprados", 0)
                    self.historial = data.get("historial", [])
            except Exception as e:
                logger.warning(f"No se pudo cargar tokens.json: {e}")

    def _save(self):
        try:
            with open(TOKENS_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "generados": self.kbt_generados,
                    "comprados": self.kbt_comprados,
                    "total": self.kbt_generados + self.kbt_comprados,
                    "historial": self.historial[-100:]
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"No se pudo guardar tokens.json: {e}")

    def generar_kbt(self, profile_id: str, cantidad: int = 1):
        import datetime
        self.kbt_generados += cantidad
        self.historial.append({
            "tipo": "generado",
            "profile_id": profile_id,
            "cantidad": cantidad,
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z"
        })
        self._save()
        logger.info(f"KBT Generado: {cantidad} (perfil {profile_id}). Total: {self.total()}")

    def comprar_kbt(self, cantidad: int, monto_usd: float):
        import datetime
        self.kbt_comprados += cantidad
        self.historial.append({
            "tipo": "comprado",
            "cantidad": cantidad,
            "monto_usd": monto_usd,
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z"
        })
        self._save()
        logger.info(f"KBT Comprado: {cantidad} por ${monto_usd}. Total: {self.total()}")

    def total(self) -> int:
        return self.kbt_generados + self.kbt_comprados

    def get_status(self) -> dict:
        return {
            "generados": self.kbt_generados,
            "comprados": self.kbt_comprados,
            "total": self.total(),
            "historial_reciente": self.historial[-10:]
        }