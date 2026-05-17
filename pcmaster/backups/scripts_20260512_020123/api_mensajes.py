# api_mensajes.py - router fastapi para endpoints publicos de mensajes. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from api_auth import verificar_token_dependencia
from db import ejecutar_sql, ejecutar_sql_unico

router = APIRouter(prefix="/api/mensajes", tags=["mensajes_publicos"])


# modelos
class EnviarMensajeRequest(BaseModel):
    destino_email: str
    asunto: str = ""
    texto: str


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


@router.post("/enviar")
async def api_enviar_mensaje(
    req: EnviarMensajeRequest,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """envia un mensaje a otro usuario por su email."""
    origen_id = sesion["usuario_id"]

    if not req.texto or len(req.texto.strip()) == 0:
        raise HTTPException(status_code=400, detail="el texto del mensaje no puede estar vacio")

    # buscar destinatario por email
    destino = ejecutar_sql_unico(
        "select id from usuarios where email = ?",
        (req.destino_email.lower().strip(),),
    )
    if not destino:
        raise HTTPException(status_code=404, detail="destinatario no encontrado")

    if destino["id"] == origen_id:
        raise HTTPException(status_code=400, detail="no puedes enviarte un mensaje a ti mismo")

    from datetime import datetime
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    from db import ejecutar_insercion
    mensaje_id = ejecutar_insercion(
        "insert into mensajes (origen_id, destino_id, texto, asunto, leido, fecha) "
        "values (?, ?, ?, ?, 0, ?)",
        (origen_id, destino["id"], req.texto.strip(), req.asunto or "", ahora),
    )

    return {"exito": True, "mensaje_id": mensaje_id, "mensaje": "mensaje enviado correctamente"}


@router.get("/historial")
async def api_historial_mensajes(
    limite: int = 50,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """obtiene el historial de mensajes del usuario autenticado."""
    usuario_id = sesion["usuario_id"]

    if limite < 1 or limite > 200:
        limite = 50

    mensajes = ejecutar_sql(
        "select m.id, m.texto, m.asunto, m.fecha, m.leido, "
        "o.email as origen_email, d.email as destino_email "
        "from mensajes m "
        "join usuarios o on m.origen_id = o.id "
        "join usuarios d on m.destino_id = d.id "
        "where m.origen_id = ? or m.destino_id = ? "
        "order by m.fecha desc limit ?",
        (usuario_id, usuario_id, limite),
    )

    return {"exito": True, "mensajes": [dict(m) for m in mensajes]}


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