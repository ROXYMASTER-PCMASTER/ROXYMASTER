# api_mensajes.py - router fastapi para endpoints publicos de mensajes. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

from fastapi import APIRouter, Depends, HTTPException
from api_auth import verificar_token_dependencia
from db import ejecutar_sql, ejecutar_sql_unico

router = APIRouter(prefix="/api/mensajes", tags=["mensajes_publicos"])


@router.get("/no_leidos")
async def api_mensajes_no_leidos(sesion: dict = Depends(verificar_token_dependencia)):
    """devuelve el conteo y el ultimo mensaje no leido del usuario autenticado."""
    usuario_id = sesion["usuario_id"]
    count_row = ejecutar_sql_unico(
        "select count(*) as total from mensajes where destino_id = ? and leido = 0",
        (usuario_id,),
    )
    total = count_row["total"] if count_row else 0
    ultimo = None
    if total > 0:
        row = ejecutar_sql_unico(
            "select m.id, m.texto, m.fecha, o.email as origen_email "
            "from mensajes m join usuarios o on m.origen_id = o.id "
            "where m.destino_id = ? and m.leido = 0 "
            "order by m.fecha desc limit 1",
            (usuario_id,),
        )
        if row:
            ultimo = dict(row)
    return {"exito": True, "count": total, "ultimo_mensaje": ultimo}


@router.post("/{mensaje_id}/leido")
async def api_marcar_leido(
    mensaje_id: int,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """marca un mensaje como leido por el destinatario."""
    usuario_id = sesion["usuario_id"]
    mensaje = ejecutar_sql_unico(
        "select * from mensajes where id = ? and destino_id = ?",
        (mensaje_id, usuario_id),
    )
    if not mensaje:
        raise HTTPException(status_code=404, detail="mensaje no encontrado")
    ejecutar_sql(
        "update mensajes set leido = 1 where id = ?",
        (mensaje_id,),
    )
    return {"exito": True, "mensaje": "marcado como leido"}