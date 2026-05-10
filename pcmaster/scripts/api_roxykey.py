# api_roxykey.py - router para gestionar roxy api key del usuario. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from api_auth import verificar_token_dependencia
from db import ejecutar_sql, get_db_context
from orchestrator import _conexiones_ws

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
    """actualiza la roxy_api_key y roxy_workspace_id del usuario autenticado.
    asocia automaticamente el pcbot_id real desde la conexion websocket activa."""
    try:
        usuario_id = sesion["usuario_id"]

        # actualizar api key y workspace en usuarios
        ejecutar_sql(
            "update usuarios set roxy_api_key = ?, roxy_workspace_id = ? where id = ?",
            (req.roxy_api_key, req.roxy_workspace_id, usuario_id),
        )

        # obtener el pcbot_id real desde las conexiones websocket activas
        pcbot_id_real = None
        for pid in _conexiones_ws:
            pcbot_id_real = pid
            break  # tomar el primero (se asume que es el mismo equipo)

        if not pcbot_id_real:
            logger.warning(f"usuario {usuario_id} guardo api key pero no hay pcbot conectado")
            return {"exito": True, "mensaje": "roxy api key guardada, pero no hay pcbot conectado para asociar"}

        # guardar o reemplazar la computadora con el pcbot real
        with get_db_context() as conn:
            conn.execute(
                "insert into computadoras (pcbot_id, usuario_id, api_key_roxy, workspace_id, estado, ultima_conexion) "
                "values (?, ?, ?, ?, 'activa', datetime('now','localtime')) "
                "on conflict(pcbot_id) do update set "
                "api_key_roxy=excluded.api_key_roxy, workspace_id=excluded.workspace_id, "
                "estado='activa', ultima_conexion=excluded.ultima_conexion, usuario_id=excluded.usuario_id",
                (pcbot_id_real, usuario_id, req.roxy_api_key, req.roxy_workspace_id),
            )
            # actualizar el campo pcbot_id en usuarios
            conn.execute(
                "update usuarios set pcbot_id = ? where id = ?",
                (pcbot_id_real, usuario_id),
            )
            conn.commit()

        logger.info(f"api key guardada para usuario {usuario_id} con pcbot_id={pcbot_id_real}")
        return {"exito": True, "pcbot_id": pcbot_id_real, "mensaje": "api key guardada y pcbot asociado"}
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
    logger.info("[DIAG-200] Sincronizando perfiles para pcbot=%s", pcbot_id)
    logger.info(f"[SYNC] Enviando comando a {pcbot_id} con API key {api_key[:8]}...")
    from orchestrator import enviar_comando_recargar_perfiles
    resultado = await enviar_comando_recargar_perfiles(pcbot_id, api_key)
    logger.info(f"[SYNC] Resultado del comando: {resultado}")
    logger.info("[DIAG-201] Resultado del comando: %s", resultado)
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