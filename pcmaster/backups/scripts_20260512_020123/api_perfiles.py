from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import json

from api_auth import verificar_token_dependencia
from db import get_db
from orchestrator import enviar_comando_pcbot  # se creará después

router = APIRouter(prefix="/api/admin", tags=["admin_perfiles"])

class CrearPerfilRequest(BaseModel):
    api_key: str

class ActualizarDesdeRoxyRequest(BaseModel):
    usuario_id: int
    api_key_roxy: str
    workspace_id: str
    hash_id: str
    name_id: str
    total_perfiles: int
    perfiles: list  # lista de {nombre, estado, ...}

@router.post("/crear")
async def api_crear_perfil(req: CrearPerfilRequest, sesion: dict = Depends(verificar_token_dependencia)):
    usuario_id = sesion["usuario_id"]
    db = get_db()
    # Insertar registro temporal en tabla perfiles
    db.execute(
        "INSERT INTO perfiles (usuario_id, nombre_perfil, tipo, estado) VALUES (?, ?, ?, ?)",
        (usuario_id, req.api_key, "roxybrowser", "consultando")
    )
    perfil_id = db.lastrowid
    db.commit()

    # Enviar comando al pcbot del usuario
    comando = {
        "accion": "consultar_roxybrowser",
        "api_key": req.api_key,
        "perfil_id": perfil_id,
        "usuario_id": usuario_id
    }
    enviado = await enviar_comando_pcbot(usuario_id, comando)
    if not enviado:
        # Si no se pudo enviar, marcar como error en BD
        db.execute("UPDATE perfiles SET estado = 'error_conexion' WHERE id = ?", (perfil_id,))
        db.commit()
        raise HTTPException(status_code=503, detail="pcbot no disponible")

    return {"exito": True, "perfil_id": perfil_id, "mensaje": "consultando a roxybrowser..."}

@router.post("/actualizar_desde_roxy")
async def api_actualizar_desde_roxy(req: ActualizarDesdeRoxyRequest):
    db = get_db()
    # Actualizar el perfil con los datos recibidos
    db.execute(
        """UPDATE perfiles SET nombre_perfil = ?, workspace_id = ?, hash_id = ?, name_id = ?,
           total_perfiles_roxy = ?, estado = ? WHERE id = ?""",
        (req.name_id, req.workspace_id, req.hash_id, req.name_id, req.total_perfiles, "activo", req.perfil_id)
    )
    # Insertar cada perfil hijo (si se requiere)
    for p in req.perfiles:
        db.execute(
            "INSERT INTO perfiles_roxy (perfil_id, nombre, estado) VALUES (?, ?, ?)",
            (req.perfil_id, p.get("nombre", ""), p.get("estado", "desconocido"))
        )
    db.commit()
    return {"exito": True, "mensaje": "datos actualizados desde roxybrowser"}

@router.get("")
async def api_listar_perfiles(sesion: dict = Depends(verificar_token_dependencia)):
    db = get_db()
    usuario_id = sesion["usuario_id"]
    perfiles = db.execute(
        "SELECT id, nombre_perfil, tipo, estado, horas_conexion, ultimo_heartbeat, workspace_id, hash_id, name_id, total_perfiles_roxy FROM perfiles WHERE usuario_id = ?",
        (usuario_id,)
    ).fetchall()
    resultado = []
    for p in perfiles:
        resultado.append({
            "id": p["id"],
            "nombre_perfil": p["nombre_perfil"],
            "tipo": p["tipo"],
            "estado": p["estado"],
            "horas_conexion": p["horas_conexion"],
            "ultimo_heartbeat": p["ultimo_heartbeat"],
            "workspace_id": p["workspace_id"],
            "hash_id": p["hash_id"],
            "name_id": p["name_id"],
            "total_perfiles_roxy": p["total_perfiles_roxy"]
        })
    return {"exito": True, "perfiles": resultado}
