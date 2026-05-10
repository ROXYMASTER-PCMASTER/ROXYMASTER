# api_roxykey.py - router para gestionar roxy api key del usuario. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api_auth import verificar_token_dependencia
from db import ejecutar_sql

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["roxykey"])


class RoxyKeyRequest(BaseModel):
    roxy_api_key: str = ""
    roxy_workspace_id: str = ""


@router.post("/roxy/api_key")
async def api_roxy_guardar_api_key(
    req: RoxyKeyRequest,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """guarda la api key de roxybrowser (alias REST-friendly para actualizar_roxy_key)."""
    return await api_actualizar_roxy_key(req, sesion)


@router.post("/actualizar_roxy_key")
async def api_actualizar_roxy_key(
    req: RoxyKeyRequest,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """actualiza la roxy_api_key y roxy_workspace_id del usuario autenticado."""
    try:
        usuario_id = sesion["usuario_id"]
        pcbot_id = sesion.get("pcbot_id", "")
        ejecutar_sql(
            "update usuarios set roxy_api_key = ?, roxy_workspace_id = ? where id = ?",
            (req.roxy_api_key, req.roxy_workspace_id, usuario_id),
        )
        # actualizar tambien en tabla computadoras
        if pcbot_id:
            ejecutar_sql(
                "insert into computadoras (pcbot_id, usuario_id, api_key_roxy, workspace_id, estado, ultima_conexion) "
                "values (?, ?, ?, ?, 'activa', datetime('now','localtime')) "
                "on conflict(pcbot_id) do update set "
                "api_key_roxy=excluded.api_key_roxy, workspace_id=excluded.workspace_id, "
                "estado='activa', ultima_conexion=excluded.ultima_conexion, usuario_id=excluded.usuario_id",
                (pcbot_id, usuario_id, req.roxy_api_key, req.roxy_workspace_id),
            )
        logger.info(f"roxy_api_key actualizada para usuario {usuario_id}, pcbot_id={pcbot_id}")
        return {"exito": True, "mensaje": "roxy api key actualizada"}
    except Exception as e:
        logger.error(f"error al actualizar roxy_key: {e}")
        raise HTTPException(status_code=500, detail=f"error interno: {str(e)}")


@router.get("/roxy/profiles")
async def obtener_perfiles_roxy_endpoint(
    request: Request,
    usuario=Depends(verificar_token_dependencia),
):
    """devuelve los perfiles roxy sincronizados del usuario."""
    from db import obtener_perfiles_roxy
    perfiles = obtener_perfiles_roxy(usuario["usuario_id"])
    return {"perfiles": perfiles}


@router.post("/roxy/sync_profiles")
async def sincronizar_perfiles(
    request: Request,
    usuario=Depends(verificar_token_dependencia),
):
    """fuerza sincronizacion de perfiles con el pcbot y guarda resultado."""
    pcbot_id = usuario.get("pcbot_id")
    if not pcbot_id:
        raise HTTPException(400, "no hay pcbot asociado a este usuario")
    # obtener api key desde computadoras
    from db import get_db, guardar_perfil_roxy
    with get_db() as conn:
        row = conn.execute(
            "select api_key_roxy from computadoras where pcbot_id = ?",
            (pcbot_id,),
        ).fetchone()
        if not row or not row[0]:
            raise HTTPException(400, "no hay api key de roxybrowser guardada para esta computadora")
        api_key = row[0]
    # enviar comando al pcbot usando orchestrator
    from orchestrator import enviar_comando_recargar_perfiles
    resultado = await enviar_comando_recargar_perfiles(pcbot_id, api_key)
    if not resultado.get("ok"):
        raise HTTPException(500, resultado.get("error", "error al sincronizar con el pcbot"))
    # guardar perfiles recibidos
    workspace_id = resultado.get("workspace_id")
    for perfil in resultado.get("perfiles", []):
        guardar_perfil_roxy(
            usuario["usuario_id"],
            pcbot_id,
            perfil["nombre"],
            perfil["hash"],
            workspace_id,
        )
    return {"ok": True, "perfiles_guardados": len(resultado.get("perfiles", []))}


@router.get("/roxy_key")
async def api_obtener_roxy_key(sesion: dict = Depends(verificar_token_dependencia)):
    """obtiene la roxy_api_key y roxy_workspace_id del usuario autenticado."""
    try:
        usuario_id = sesion["usuario_id"]
        from db import ejecutar_sql_unico
        usuario = ejecutar_sql_unico(
            "select roxy_api_key, roxy_workspace_id from usuarios where id = ?",
            (usuario_id,),
        )
        if not usuario:
            raise HTTPException(status_code=404, detail="usuario no encontrado")
        return {
            "exito": True,
            "roxy_api_key": usuario.get("roxy_api_key", ""),
            "roxy_workspace_id": usuario.get("roxy_workspace_id", ""),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"error al obtener roxy_key: {e}")
        raise HTTPException(status_code=500, detail=f"error interno: {str(e)}")