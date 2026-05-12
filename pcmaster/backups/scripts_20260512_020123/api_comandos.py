# api_comandos.py - router fastapi para comandos y urls. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Any

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
# comando generico (estructura accion + params)
# ---------------------------------------------------------------------------
class ComandoGenericoRequest(BaseModel):
    accion: str
    params: dict = {}


@router.post("/comando")
async def api_comando(
    req: ComandoGenericoRequest,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """
    endpoint generico para comandos.
    accion: 'asignar_url', 'asignar_url_vip', 'detener', 'estado', etc.
    """
    accion = req.accion
    params = req.params
    usuario_id = sesion["usuario_id"]

    if accion == "asignar_url":
        # campos esperados en params: url, perfiles (cantidad), duracion, comentarios
        url = params.get("url", "")
        if not url:
            raise HTTPException(status_code=400, detail="url requerida en params")
        cantidad = int(params.get("perfiles", 1))
        duracion = int(params.get("duracion", 60))
        comentarios = bool(params.get("comentarios", False))

        # calcular costo kbt (ejemplo: 1 kbt por perfil por hora)
        costo_kbt = cantidad * max(1, duracion // 60)
        if costo_kbt < 1:
            costo_kbt = 1

        # delegar en comando_asignar
        resultado = await comando_asignar(
            pcbot_id="default",
            cantidad=cantidad,
            url=url,
            duracion_min=duracion,
            comentarios_activos=comentarios,
            streamer=params.get("streamer", ""),
        )
        if not resultado.get("exito"):
            raise HTTPException(status_code=400, detail=resultado.get("error", "error al asignar"))
        resultado["costo_kbt"] = costo_kbt
        return resultado

    elif accion == "asignar_url_vip":
        # igual que asignar_url pero con costo superior y prioridad
        url = params.get("url", "")
        if not url:
            raise HTTPException(status_code=400, detail="url requerida en params")
        cantidad = int(params.get("perfiles", 1))
        duracion = int(params.get("duracion", 60))

        # costo vip: 2x el normal
        costo_kbt_vip = cantidad * max(1, duracion // 60) * 2

        # delegar en comando_asignar
        resultado = await comando_asignar(
            pcbot_id="default_vip",
            cantidad=cantidad,
            url=url,
            duracion_min=duracion,
            comentarios_activos=bool(params.get("comentarios", False)),
            streamer=params.get("streamer", ""),
        )
        if not resultado.get("exito"):
            raise HTTPException(status_code=400, detail=resultado.get("error", "error al asignar vip"))
        resultado["costo_kbt_vip"] = costo_kbt_vip
        resultado["prioridad"] = "alta"
        return resultado

    elif accion == "detener":
        return await comando_detener(
            params.get("pcbot_id", ""),
            params.get("url", ""),
        )

    elif accion == "estado":
        return await comando_estado(params.get("pcbot_id", ""))

    else:
        raise HTTPException(status_code=400, detail=f"accion no reconocida: {accion}")


# ---------------------------------------------------------------------------
# urls (mantener compatibilidad con endpoints anteriores)
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