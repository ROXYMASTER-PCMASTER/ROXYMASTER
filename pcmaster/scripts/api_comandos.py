# api_comandos.py - router fastapi para comandos y urls. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from api_auth import verificar_token_dependencia, verificar_admin_dependencia
from orchestrator import (
    comando_asignar,
    comando_comentarios_activar,
    comando_detener,
    comando_estado,
    comando_open_url,
    listar_comandos_pendientes,
)
from db import ejecutar_sql

router = APIRouter(prefix="/api", tags=["comandos"])


class AsignarRequest(BaseModel):
    pcbot_id: str
    cantidad: int
    url: str
    duracion_min: int = 60
    comentarios_activos: bool = False
    streamer: Optional[str] = ""


class ComentariosRequest(BaseModel):
    pcbot_id: str
    url: str


class DetenerRequest(BaseModel):
    pcbot_id: str
    url: str


class OpenUrlRequest(BaseModel):
    pcbot_id: str
    url: str
    perfil_ids: Optional[list] = None


# ---------------------------------------------------------------------------
# comando (endpoint generico)
# ---------------------------------------------------------------------------
@router.post("/comando")
async def api_comando(
    req: AsignarRequest = None,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """
    endpoint generico para comandos.
    el tipo se determina del body o query params.
    """
    # este endpoint delega en los especificos segun el tipo solicitado
    if not req:
        raise HTTPException(status_code=400, detail="cuerpo de comando requerido")

    resultado = await comando_asignar(
        pcbot_id=req.pcbot_id,
        cantidad=req.cantidad,
        url=req.url,
        duracion_min=req.duracion_min,
        comentarios_activos=req.comentarios_activos,
        streamer=req.streamer or "",
    )
    if not resultado.get("exito"):
        raise HTTPException(status_code=400, detail=resultado.get("error"))
    return resultado


# ---------------------------------------------------------------------------
# urls
# ---------------------------------------------------------------------------
@router.get("/urls")
async def api_urls(sesion: dict = Depends(verificar_token_dependencia)):
    """lista urls asignadas."""
    urls = ejecutar_sql(
        "select * from urls_asignadas order by fecha_asignacion desc"
    )
    return {"exito": True, "urls": urls}


@router.post("/urls/asignar")
async def api_asignar_url(
    req: AsignarRequest,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """asigna una url a perfiles de un pcbot."""
    resultado = await comando_asignar(
        pcbot_id=req.pcbot_id,
        cantidad=req.cantidad,
        url=req.url,
        duracion_min=req.duracion_min,
        comentarios_activos=req.comentarios_activos,
        streamer=req.streamer or "",
    )
    if not resultado.get("exito"):
        raise HTTPException(status_code=400, detail=resultado.get("error"))
    return resultado


@router.post("/urls/comentarios_activar")
async def api_comentarios_activar(
    req: ComentariosRequest,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """activa comentarios en una url asignada."""
    resultado = await comando_comentarios_activar(req.pcbot_id, req.url)
    if not resultado.get("exito"):
        raise HTTPException(status_code=400, detail=resultado.get("error"))
    return resultado


@router.post("/urls/detener")
async def api_detener_url(
    req: DetenerRequest,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """detiene la actividad de una url."""
    resultado = await comando_detener(req.pcbot_id, req.url)
    if not resultado.get("exito"):
        raise HTTPException(status_code=400, detail=resultado.get("error"))
    return resultado


@router.get("/comandos/pendientes")
async def api_comandos_pendientes(
    pcbot_id: Optional[str] = None,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """lista comandos pendientes."""
    comandos = listar_comandos_pendientes(pcbot_id)
    return {"exito": True, "comandos": comandos}


@router.get("/comando/estado/{pcbot_id}")
async def api_estado_pcbot(
    pcbot_id: str,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """solicita el estado de un pcbot."""
    resultado = await comando_estado(pcbot_id)
    return resultado