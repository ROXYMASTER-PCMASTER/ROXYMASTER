# ============================================================================
# ROXYMASTER v7.0 - ORCHESTRATOR MODULE
# Envia comandos a PCBOTs y gestiona el estado de la red
# ============================================================================

import json
import time
import threading

class Orchestrator:
    """Orquesta comandos hacia los PCBOTs conectados."""

    def __init__(self):
        self.pcbots = {}           # pcbot_id -> websocket
        self.pcbots_info = {}      # pcbot_id -> {perfiles, estado, last_heartbeat, ...}
        self.perfiles_map = {}     # perfil_id -> pcbot_id
        self.grupos = {}           # grupo_id -> {nombre, perfiles: []}
        self.pool_comentarios = {} # url -> [comentario1, comentario2, ...]
        self.start_time = time.time()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Registro de PCBOTs
    # ------------------------------------------------------------------
    def registrar_pcbot(self, pcbot_id: str, websocket, info: dict):
        """Registra un PCBOT conectado."""
        with self._lock:
            self.pcbots[pcbot_id] = websocket
            self.pcbots_info[pcbot_id] = {
                "ip_local": info.get("ip_local", ""),
                "ip_tailscale": info.get("ip_tailscale", ""),
                "hostname": info.get("hostname", ""),
                "usuario": info.get("usuario", ""),
                "perfiles": info.get("perfiles", []),
                "estado": "conectado",
                "last_heartbeat": time.time(),
                "conectado_desde": time.time()
            }
            # Mapear perfiles
            for p in info.get("perfiles", []):
                pid = p.get("id", p.get("nombre", ""))
                if pid:
                    self.perfiles_map[pid] = pcbot_id

    def remover_pcbot(self, pcbot_id: str):
        """Elimina un PCBOT desconectado."""
        with self._lock:
            self.pcbots.pop(pcbot_id, None)
            if pcbot_id in self.pcbots_info:
                self.pcbots_info[pcbot_id]["estado"] = "desconectado"
            # Limpiar mapeo de perfiles
            to_remove = [pid for pid, bid in self.perfiles_map.items() if bid == pcbot_id]
            for pid in to_remove:
                del self.perfiles_map[pid]

    def heartbeat(self, pcbot_id: str, estados: dict):
        """Actualiza heartbeat y estados de perfiles."""
        with self._lock:
            if pcbot_id in self.pcbots_info:
                self.pcbots_info[pcbot_id]["last_heartbeat"] = time.time()
                self.pcbots_info[pcbot_id]["estado"] = "conectado"
                self.pcbots_info[pcbot_id]["perfiles_activos"] = estados.get("activos", 0)
                self.pcbots_info[pcbot_id]["perfiles_inactivos"] = estados.get("inactivos", 0)
                self.pcbots_info[pcbot_id]["perfiles_colgados"] = estados.get("colgados", 0)

    # ------------------------------------------------------------------
    # Comandos a PCBOTs
    # ------------------------------------------------------------------
    async def enviar_comando(self, pcbot_id: str, comando: dict) -> dict:
        """Envia un comando a un PCBOT especifico."""
        ws = self.pcbots.get(pcbot_id)
        if not ws:
            return {"ok": False, "error": f"PCBOT {pcbot_id} no conectado"}
        try:
            await ws.send(json.dumps(comando))
            return {"ok": True, "mensaje": "Comando enviado"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def asignar_url(self, pcbot_id: str, url: str, n_perfiles: int, duracion: int = 62):
        """Ordena a un PCBOT abrir URL en N perfiles."""
        return await self.enviar_comando(pcbot_id, {
            "tipo": "asignar",
            "url": url,
            "perfiles": n_perfiles,
            "duracion": duracion
        })

    async def detener_perfiles(self, pcbot_id: str, perfiles: list = None):
        """Ordena detener perfiles especificos o todos."""
        return await self.enviar_comando(pcbot_id, {
            "tipo": "detener",
            "perfiles": perfiles or []
        })

    async def activar_comentarios(self, pcbot_id: str, url: str, intervalo: int = 120):
        """Activa comentarios automaticos en una URL."""
        return await self.enviar_comando(pcbot_id, {
            "tipo": "comentarios",
            "url": url,
            "intervalo": intervalo
        })

    # ------------------------------------------------------------------
    # Grupos de perfiles
    # ------------------------------------------------------------------
    def crear_grupo(self, grupo_id: str, nombre: str):
        with self._lock:
            self.grupos[grupo_id] = {"nombre": nombre, "perfiles": []}
        return {"ok": True, "grupo": self.grupos[grupo_id]}

    def asignar_a_grupo(self, grupo_id: str, perfiles: list):
        with self._lock:
            if grupo_id not in self.grupos:
                return {"ok": False, "error": "Grupo no existe"}
            self.grupos[grupo_id]["perfiles"].extend(perfiles)
        return {"ok": True}

    # ------------------------------------------------------------------
    # Pool de comentarios
    # ------------------------------------------------------------------
    def agregar_comentario(self, url: str, comentario: str):
        with self._lock:
            if url not in self.pool_comentarios:
                self.pool_comentarios[url] = []
            self.pool_comentarios[url].append(comentario)

    def obtener_comentarios(self, url: str) -> list:
        return self.pool_comentarios.get(url, [])

    # ------------------------------------------------------------------
    # Dashboard info
    # ------------------------------------------------------------------
    def get_dashboard(self) -> dict:
        """Retorna datos completos del dashboard."""
        with self._lock:
            pcbots_conectados = sum(1 for i in self.pcbots_info.values() if i["estado"] == "conectado")
            total_perfiles = sum(len(i.get("perfiles", [])) for i in self.pcbots_info.values())
            activos = sum(i.get("perfiles_activos", 0) for i in self.pcbots_info.values())
            inactivos = sum(i.get("perfiles_inactivos", 0) for i in self.pcbots_info.values())
            colgados = sum(i.get("perfiles_colgados", 0) for i in self.pcbots_info.values())

            return {
                "uptime": round(time.time() - self.start_time),
                "pcbots_conectados": pcbots_conectados,
                "pcbots_total": len(self.pcbots_info),
                "perfiles_total": total_perfiles,
                "perfiles_activos": activos,
                "perfiles_inactivos": inactivos,
                "perfiles_colgados": colgados,
                "grupos": len(self.grupos),
                "ofertas_p2p_activas": 0,  # Se inyecta desde afuera
                "pcbots": {
                    pid: {
                        "hostname": i.get("hostname", ""),
                        "usuario": i.get("usuario", ""),
                        "ip_local": i.get("ip_local", ""),
                        "estado": i["estado"],
                        "perfiles": len(i.get("perfiles", [])),
                        "activos": i.get("perfiles_activos", 0),
                        "inactivos": i.get("perfiles_inactivos", 0),
                        "colgados": i.get("perfiles_colgados", 0),
                        "last_heartbeat": i.get("last_heartbeat", 0)
                    }
                    for pid, i in self.pcbots_info.items()
                }
            }