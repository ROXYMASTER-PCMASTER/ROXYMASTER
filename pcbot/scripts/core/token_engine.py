"""
roxymaster v8.3 - token engine (pcbot)
contabilidad local de kbt ganados.
persiste en json, se sincroniza con pcmaster via ws.
todo en minusculas, utf-8 sin bom.
"""

import asyncio
import json
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKENS_PATH = os.path.join(BASE_DIR, "data", "kbt_local.json")


class TokenEngine:
    """contabilidad local de kbt ganados por ciclo de 62 minutos."""

    def __init__(self, sync_callback=None):
        self._tokens: dict[str, float] = {}
        self._history: list[dict] = []
        self._total_earned: float = 0.0
        self._pending_sync: float = 0.0
        self._sync_cb = sync_callback or (lambda t: None)
        self._load()

    def _load(self):
        """carga estado desde json."""
        try:
            if os.path.isfile(TOKENS_PATH):
                with open(TOKENS_PATH, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                self._tokens = data.get("tokens", {})
                self._history = data.get("history", [])
                self._total_earned = data.get("total_earned", 0.0)
                logger.info(
                    f"token_engine: cargado ({len(self._tokens)} perfiles, "
                    f"total {self._total_earned} kbt)"
                )
        except Exception as e:
            logger.warning(f"token_engine: error cargando kbt_local.json: {e}")

    def _save(self):
        """guarda estado a json."""
        try:
            os.makedirs(os.path.dirname(TOKENS_PATH), exist_ok=True)
            data = {
                "tokens": self._tokens,
                "history": self._history[-1000:],  # mantener ultimos 1000 eventos
                "total_earned": self._total_earned,
                "updated": time.time(),
            }
            with open(TOKENS_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"token_engine: error guardando kbt_local.json: {e}")

    def add_cycle_complete(self, profile_id: str, cantidad: float = 1.0):
        """acredita kbt a un perfil por ciclo completado de 62 min."""
        current = self._tokens.get(profile_id, 0.0)
        self._tokens[profile_id] = current + cantidad
        self._total_earned += cantidad
        self._pending_sync += cantidad

        event = {
            "profile_id": profile_id,
            "cantidad": cantidad,
            "timestamp": time.time(),
            "tipo": "cycle_complete",
        }
        self._history.append(event)
        self._save()

        logger.info(
            f"token_engine: +{cantidad} kbt para perfil {profile_id} "
            f"(total perfil: {self._tokens[profile_id]}, "
            f"total general: {self._total_earned})"
        )

    def deduct_referido(self, profile_id: str, porcentaje: float = 0.10) -> float:
        """descuenta porcentaje por comision de referido.
        devuelve monto descontado."""
        current = self._tokens.get(profile_id, 0.0)
        descuento = current * porcentaje
        self._tokens[profile_id] = current - descuento
        self._total_earned -= descuento

        event = {
            "profile_id": profile_id,
            "cantidad": -descuento,
            "timestamp": time.time(),
            "tipo": "referido_descuento",
        }
        self._history.append(event)
        self._save()

        logger.info(
            f"token_engine: -{descuento} kbt por referido en perfil {profile_id}"
        )
        return descuento

    def get_balance(self, profile_id: Optional[str] = None) -> float:
        """devuelve balance de un perfil o total de todos."""
        if profile_id:
            return self._tokens.get(profile_id, 0.0)
        return self._total_earned

    def get_all_balances(self) -> dict:
        """devuelve dict {profile_id: balance}."""
        return dict(self._tokens)

    def get_pending_sync(self) -> float:
        """devuelve kbt pendientes de sincronizar."""
        return self._pending_sync

    def clear_pending_sync(self, cantidad: Optional[float] = None):
        """limpia kbt pendientes de sincronizar."""
        if cantidad is not None:
            self._pending_sync = max(0.0, self._pending_sync - cantidad)
        else:
            self._pending_sync = 0.0

    def get_history(self, limit: int = 50) -> list:
        """devuelve historial reciente."""
        return self._history[-limit:]

    @property
    def kbt_generados(self) -> float:
        """alias de total_earned para compatibilidad con main.py."""
        return self._total_earned

    def generar_kbt(self, profile_id: str, cantidad: float = 1.0):
        """alias de add_cycle_complete para compatibilidad con main.py."""
        self.add_cycle_complete(profile_id, cantidad)

    def total(self) -> float:
        """alias de get_balance() para compatibilidad con main.py."""
        return self.get_balance()

    def get_stats(self) -> dict:
        """devuelve estadisticas resumidas."""
        return {
            "total_earned": self._total_earned,
            "pending_sync": self._pending_sync,
            "profiles_with_tokens": len(self._tokens),
            "total_events": len(self._history),
            "last_event": self._history[-1] if self._history else None,
        }

    async def sync_to_pcmaster(self, ws_client) -> bool:
        """envia kbt pendientes a pcmaster via ws."""
        if self._pending_sync <= 0:
            logger.debug("token_engine: nada que sincronizar")
            return True
        if not ws_client or not ws_client.connected:
            logger.warning("token_engine: ws no conectado, posponer sincronizacion")
            return False

        try:
            payload = {
                "type": "kbt_sync",
                "kbt": self._pending_sync,
                "balances": self._tokens,
            }
            await ws_client.send(json.dumps(payload))
            logger.info(f"token_engine: sincronizando {self._pending_sync} kbt")
            self.clear_pending_sync()
            return True
        except Exception as e:
            logger.error(f"token_engine: error sincronizando: {e}")
            return False

    async def periodic_sync(self, ws_client, interval: int = 60):
        """sincroniza periodicamente cada `interval` segundos."""
        try:
            while True:
                await asyncio.sleep(interval)
                await self.sync_to_pcmaster(ws_client)
        except asyncio.CancelledError:
            logger.info("token_engine: sincronizacion periodica cancelada")