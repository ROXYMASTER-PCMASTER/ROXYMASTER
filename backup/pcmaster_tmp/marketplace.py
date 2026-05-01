# ============================================================================
# ROXYMASTER v7.0 - MARKETPLACE P2P MODULE
# Ofertas de compra/venta de tokens KBT
# ============================================================================

import time
from typing import Optional

class MarketplaceP2P:
    """Gestiona el mercado P2P de tokens KBT."""

    def __init__(self):
        self.ofertas = {}      # oferta_id -> dict
        self._id_counter = 1

    def crear_oferta(self, vendedor: str, tokens: float, precio_soles: float) -> dict:
        """Crea una oferta de venta. Retorna {ok, oferta}."""
        if tokens <= 0 or precio_soles <= 0:
            return {"ok": False, "error": "Tokens y precio deben ser positivos"}
        if tokens < 0.01:
            return {"ok": False, "error": "Minimo 0.01 KBT por oferta"}

        oid = str(self._id_counter)
        self._id_counter += 1
        precio_token = round(precio_soles / tokens, 4)
        oferta = {
            "id": oid,
            "vendedor": vendedor,
            "tokens": round(tokens, 4),
            "precio_soles": round(precio_soles, 2),
            "precio_token": precio_token,
            "fecha": time.time(),
            "estado": "activa",
            "comprador": None
        }
        self.ofertas[oid] = oferta
        return {"ok": True, "oferta": oferta}

    def comprar_oferta(self, oid: str, comprador: str) -> dict:
        """Marca una oferta como vendida. Retorna {ok, oferta, error}."""
        oferta = self.ofertas.get(oid)
        if not oferta:
            return {"ok": False, "error": "Oferta no encontrada"}
        if oferta["estado"] != "activa":
            return {"ok": False, "error": f"Oferta ya esta {oferta['estado']}"}
        if oferta["vendedor"] == comprador:
            return {"ok": False, "error": "No puedes comprar tu propia oferta"}
        oferta["estado"] = "vendida"
        oferta["comprador"] = comprador
        return {"ok": True, "oferta": oferta}

    def cancelar_oferta(self, oid: str, solicitante: str) -> dict:
        """Cancela una oferta (solo el vendedor)."""
        oferta = self.ofertas.get(oid)
        if not oferta:
            return {"ok": False, "error": "Oferta no encontrada"}
        if oferta["vendedor"] != solicitante:
            return {"ok": False, "error": "Solo el vendedor puede cancelar"}
        if oferta["estado"] != "activa":
            return {"ok": False, "error": f"Oferta ya esta {oferta['estado']}"}
        oferta["estado"] = "cancelada"
        return {"ok": True, "oferta": oferta}

    def listar_activas(self) -> list:
        """Lista todas las ofertas activas."""
        return [o for o in self.ofertas.values() if o["estado"] == "activa"]

    def historial_usuario(self, email: str) -> list:
        """Historial de ofertas donde participo un usuario."""
        return [
            o for o in self.ofertas.values()
            if o["vendedor"] == email or o["comprador"] == email
        ]

    def get_oferta(self, oid: str) -> Optional[dict]:
        """Obtiene una oferta por ID."""
        return self.ofertas.get(oid)