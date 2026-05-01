import time
class Marketplace:
    def __init__(self, tokenomics):
        self.kbt = tokenomics
        self.ofertas = {}
        self._id = 1

    def crear_oferta(self, vendedor, tokens, precio_soles):
        if tokens <= 0: return {"ok": False, "error": "tokens deben ser positivos"}
        if self.kbt.get_saldo(vendedor) < tokens: return {"ok": False, "error": "saldo insuficiente"}
        oid = str(self._id); self._id += 1
        self.ofertas[oid] = {"id": oid, "vendedor": vendedor, "tokens": tokens, "precio_soles": precio_soles, "precio_unitario": round(precio_soles/tokens, 4) if tokens else 0, "estado": "activa", "comprador": None, "fecha": time.time()}
        return {"ok": True, "oferta": self.ofertas[oid]}

    def comprar_oferta(self, oid, comprador):
        of = self.ofertas.get(oid)
        if not of: return {"ok": False, "error": "oferta no encontrada"}
        if of["estado"] != "activa": return {"ok": False, "error": "oferta no disponible"}
        if of["vendedor"] == comprador: return {"ok": False, "error": "no puedes comprar tu propia oferta"}
        comision = of["tokens"] * self.kbt.params["comision_marketplace"]
        self.kbt.transferir(of["vendedor"], comprador, of["tokens"])
        rese = self.kbt.conn.execute("update reserva set tokens = tokens + ? where id=1", (comision,))
        self.kbt.conn.commit()
        of["estado"] = "vendida"; of["comprador"] = comprador
        return {"ok": True, "comision": comision}

    def cancelar_oferta(self, oid, solicitante):
        of = self.ofertas.get(oid)
        if not of: return {"ok": False, "error": "oferta no encontrada"}
        if of["vendedor"] != solicitante: return {"ok": False, "error": "solo el vendedor puede cancelar"}
        if of["estado"] != "activa": return {"ok": False, "error": "oferta no activa"}
        of["estado"] = "cancelada"
        return {"ok": True}

    def listar_activas(self):
        return [o for o in self.ofertas.values() if o["estado"] == "activa"]
