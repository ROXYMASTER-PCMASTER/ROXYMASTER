# api_heartbeat.py - roxymaster v8.3
# endpoint para recibir heartbeat de pcbot y devolver api keys pendientes.

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from api_auth import verificar_token_dependencia
from db import get_db

router = APIRouter(prefix="/api", tags=["heartbeat"])


class PerfilHeartbeat(BaseModel):
    nombre: str
    estado: str = "activo"
    horas_conexion: float = 0.0
    ultimo_heartbeat: Optional[str] = None


class HeartbeatRequest(BaseModel):
    hostname: str
    usuario: str
    ip_local: Optional[str] = ""
    ip_tailscale: Optional[str] = ""
    ip_wan: Optional[str] = ""
    workspace_id: str
    perfiles_roxy: List[PerfilHeartbeat] = []
    navegadores: List[str] = []
    perfiles_vip: List[str] = []
    modo: str = "pidiendo_ordenes"
    version_agente: str = "8.3"


def _mapear_perfil_heartbeat(pf: PerfilHeartbeat, computadora_id: int) -> dict:
    """mapea un perfil del heartbeat a fila de tabla perfiles."""
    return {
        "computadora_id": computadora_id,
        "nombre_perfil": pf.nombre,
        "tipo": "roxy",
        "estado": pf.estado,
        "horas_conexion": pf.horas_conexion,
        "horas_en_uso": 0.0,
        "horas_hh": 0.0,
        "ip_wan": "",
        "ultimo_heartbeat": pf.ultimo_heartbeat or datetime.now().isoformat(),
    }


@router.post("/heartbeat")
async def recibir_heartbeat(
    req: HeartbeatRequest,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """recibe heartbeat del pcbot y devuelve api keys pendientes."""
    db = get_db()
    usuario_id = sesion["usuario_id"]

    # 1. buscar o crear la computadora por workspace_id
    computadora = db.execute(
        "SELECT id FROM computadoras WHERE workspace_id = ? AND usuario_id = ?",
        (req.workspace_id, usuario_id),
    ).fetchone()

    if not computadora:
        db.execute(
            "INSERT INTO computadoras "
            "(usuario_id, hostname, ip_local, ip_tailscale, ip_wan, workspace_id, ultimo_heartbeat) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                usuario_id,
                req.hostname,
                req.ip_local,
                req.ip_tailscale,
                req.ip_wan,
                req.workspace_id,
                datetime.now().isoformat(),
            ),
        )
        db.commit()
        computadora_id = db.execute(
            "SELECT id FROM computadoras WHERE workspace_id = ?",
            (req.workspace_id,),
        ).fetchone()["id"]
    else:
        computadora_id = computadora["id"]
        db.execute(
            "UPDATE computadoras SET ultimo_heartbeat = ?, ip_local = ?, ip_tailscale = ?, ip_wan = ? WHERE id = ?",
            (datetime.now().isoformat(), req.ip_local, req.ip_tailscale, req.ip_wan, computadora_id),
        )
        db.commit()

    # 2. actualizar perfiles asociados a esta computadora
    for pf in req.perfiles_roxy:
        existente = db.execute(
            "SELECT id FROM perfiles WHERE computadora_id = ? AND nombre_perfil = ?",
            (computadora_id, pf.nombre),
        ).fetchone()
        if existente:
            db.execute(
                "UPDATE perfiles SET estado = ?, horas_conexion = ?, ultimo_heartbeat = ? WHERE id = ?",
                (pf.estado, pf.horas_conexion, pf.ultimo_heartbeat or datetime.now().isoformat(), existente["id"]),
            )
        else:
            db.execute(
                "INSERT INTO perfiles "
                "(usuario_id, computadora_id, nombre_perfil, tipo, estado, horas_conexion, ultimo_heartbeat) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    usuario_id,
                    computadora_id,
                    pf.nombre,
                    "roxy",
                    pf.estado,
                    pf.horas_conexion,
                    pf.ultimo_heartbeat or datetime.now().isoformat(),
                ),
            )
    db.commit()

    # 3. buscar api keys pendientes (activas, no enviadas)
    api_keys_pendientes = []
    keys = db.execute(
        "SELECT api_key FROM api_keys_roxy "
        "WHERE usuario_id = ? AND activa = 1 "
        "AND activa = 1",
        (usuario_id, computadora_id),
    ).fetchall()
    for k in keys:
        api_keys_pendientes.append(k["api_key"])

    # 4. responder con las api keys pendientes
    return {
        "exito": True,
        "api_keys_pendientes": api_keys_pendientes,
        "comandos_pendientes": [],
    }


