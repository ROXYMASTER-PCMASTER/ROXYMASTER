# api_dashboard_ext.py - endpoints de referidos, modo toggle y cambio de referidor.
# roxymaster v8.3 - todo en minusculas, utf-8 sin bom, <= 400 lineas

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api_auth import verificar_token_dependencia
from db import ejecutar_sql_unico, ejecutar_sql

router = APIRouter(prefix="/api", tags=["dashboard_ext"])


@router.get("/mis_referidos")
async def api_mis_referidos(sesion: dict = Depends(verificar_token_dependencia)):
    """lista los referidos del usuario autenticado."""
    usuario_id = sesion["usuario_id"]

    # obtener codigo de referido del usuario
    usuario = ejecutar_sql_unico(
        "select codigo_referido, referido_por, referido_cambiado from usuarios where id = ?",
        (usuario_id,),
    )

    codigo = usuario["codigo_referido"] if usuario and usuario["codigo_referido"] else ""
    referido_por = usuario["referido_por"] if usuario and usuario["referido_por"] else "pcmaster"
    referido_cambiado = usuario["referido_cambiado"] if usuario else 0

    # obtener lista de referidos directos
    referidos_directos = ejecutar_sql(
        "select u.email, r.nivel, r.comisiones_generadas "
        "from usuarios u "
        "join referidos r on u.id = r.referido_id "
        "where r.referidor_id = ?",
        (usuario_id,),
    )

    # arbol: nivel 1 y 2
    arbol = []
    for rd in referidos_directos:
        arbol.append({
            "email": rd["email"],
            "nivel": rd["nivel"],
            "comisiones": rd["comisiones_generadas"],
        })
        # nivel 2: referidos de mis referidos
        sub = ejecutar_sql(
            "select u.email, r.nivel, r.comisiones_generadas "
            "from usuarios u "
            "join referidos r on u.id = r.referido_id "
            "join usuarios ref on ref.id = r.referidor_id "
            "where ref.email = ?",
            (rd["email"],),
        )
        for s in sub:
            arbol.append({
                "email": s["email"],
                "nivel": 2,
                "comisiones": s["comisiones_generadas"],
            })

    # conteo de referidos
    ref_totales = len(referidos_directos)
    ref_activos = ejecutar_sql_unico(
        "select count(*) as total from referidos r "
        "join usuarios u on u.id = r.referido_id "
        "where r.referidor_id = ? and u.activo = 1",
        (usuario_id,),
    )

    return {
        "exito": True,
        "codigo_referido": codigo,
        "referido_por": referido_por,
        "referido_cambiado": referido_cambiado,
        "referidos_directos": [dict(r) for r in referidos_directos],
        "referidos_totales": ref_totales,
        "referidos_activos": ref_activos["total"] if ref_activos else 0,
        "arbol": arbol,
    }


# modelos
class CambiarReferidorRequest(BaseModel):
    nuevo_codigo: str


@router.post("/cambiar_referidor")
async def api_cambiar_referidor(
    req: CambiarReferidorRequest,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """cambia el referidor del usuario (solo una vez)."""
    usuario_id = sesion["usuario_id"]

    usuario = ejecutar_sql_unico(
        "select referido_cambiado from usuarios where id = ?",
        (usuario_id,),
    )
    if not usuario:
        return {"exito": False, "mensaje": "usuario no encontrado"}
    if usuario["referido_cambiado"]:
        return {"exito": False, "mensaje": "ya cambiaste tu referidor anteriormente"}

    referidor = ejecutar_sql_unico(
        "select id from usuarios where codigo_referido = ?",
        (req.nuevo_codigo,),
    )
    if not referidor:
        return {"exito": False, "mensaje": "codigo de referido no valido"}

    ejecutar_sql(
        "update usuarios set referido_por = ?, referido_cambiado = 1 where id = ?",
        (req.nuevo_codigo, usuario_id),
    )
    return {"exito": True, "mensaje": "referidor actualizado correctamente"}


# ---- modo toggle ----
class ModoToggleRequest(BaseModel):
    modo: str = ""


@router.post("/modo/toggle")
async def api_modo_toggle(
    req: ModoToggleRequest,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """cambia el modo del usuario entre 'pidiendo_ordenes' y 'uso_personal'."""
    usuario_id = sesion["usuario_id"]

    usuario = ejecutar_sql_unico(
        "select id, modo from usuarios where id = ?",
        (usuario_id,),
    )
    if not usuario:
        return {"exito": False, "mensaje": "usuario no encontrado"}

    modo_actual = str(usuario["modo"]) if usuario["modo"] else "conectado"

    if req.modo and req.modo in ("pidiendo_ordenes", "uso_personal"):
        nuevo_modo = req.modo
    else:
        nuevo_modo = "uso_personal" if modo_actual == "pidiendo_ordenes" else "pidiendo_ordenes"

    ejecutar_sql(
        "update usuarios set modo = ? where id = ?",
        (nuevo_modo, usuario_id),
    )

    return {
        "exito": True,
        "modo_anterior": modo_actual,
        "modo_nuevo": nuevo_modo,
        "mensaje": f"modo cambiado a {nuevo_modo}",
    }