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


@router.post("/actualizar_roxy_key")
async def api_actualizar_roxy_key(
    req: RoxyKeyRequest,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """actualiza la roxy_api_key y roxy_workspace_id del usuario autenticado."""
    try:
        usuario_id = sesion["usuario_id"]
        ejecutar_sql(
            "update usuarios set roxy_api_key = ?, roxy_workspace_id = ? where id = ?",
            (req.roxy_api_key, req.roxy_workspace_id, usuario_id),
        )
        logger.info(f"roxy_api_key actualizada para usuario {usuario_id}")
        return {"exito": True, "mensaje": "roxy api key actualizada"}
    except Exception as e:
        logger.error(f"error al actualizar roxy_key: {e}")
        raise HTTPException(status_code=500, detail=f"error interno: {str(e)}")


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