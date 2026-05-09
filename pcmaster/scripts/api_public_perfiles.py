# api_public_perfiles.py - endpoints de perfiles para dashboard publico
# roxymaster v8.3 - todo en minusculas, utf-8 sin bom, <= 400 lineas

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from api_auth import verificar_token_dependencia
from db import ejecutar_sql_unico, ejecutar_sql, ejecutar_insercion

router = APIRouter(prefix="/api", tags=["public_perfiles"])


# ---------------------------------------------------------------------------
# modelos
# ---------------------------------------------------------------------------
class CrearPerfilRequest(BaseModel):
    nombre: Optional[str] = None
    tipo: str = "local"
    api_key: Optional[str] = None


class ActualizarPerfilRequest(BaseModel):
    nombre: Optional[str] = None
    estado: Optional[str] = None


class IniciarPerfilRequest(BaseModel):
    url: Optional[str] = None
    streamer: Optional[str] = None


# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------
@router.get("/perfiles")
async def api_listar_perfiles(sesion: dict = Depends(verificar_token_dependencia)):
    """lista todos los perfiles del usuario autenticado, agrupados por computadora."""
    usuario_id = sesion["usuario_id"]

    # validar que el usuario existe
    usuario = ejecutar_sql_unico(
        "select id from usuarios where id = ?", (usuario_id,)
    )
    if not usuario:
        return {"exito": False, "mensaje": "usuario no encontrado"}

    # obtener todas las computadoras del usuario
    computadoras = ejecutar_sql(
        "select pcbot_id, hostname, ip_wan, ip_local, estado "
        "from computadoras where usuario_id = ?",
        (usuario_id,),
    )

    # agrupar perfiles por pcbot_id
    resultado = []
    for pc in computadoras:
        pcbot_id = pc["pcbot_id"]
        perfiles = ejecutar_sql(
            "select id, nombre_perfil, tipo, estado, ip_wan, "
            "horas_conexion, horas_en_uso, horas_hh, hash_id, workspace_id "
            "from perfiles where usuario_id = ? and pcbot_id = ? order by id",
            (usuario_id, pcbot_id),
        )
        total = len(perfiles)
        activos = sum(1 for p in perfiles if p["estado"] == "activo")
        inactivos = total - activos

        resultado.append({
            "pcbot_id": pcbot_id,
            "hostname": pc["hostname"] or pcbot_id,
            "ip_wan": pc["ip_wan"] or "",
            "ip_local": pc["ip_local"] or "",
            "estado_pc": pc["estado"] or "desconocido",
            "total_perfiles": total,
            "activos": activos,
            "inactivos": inactivos,
            "perfiles": [dict(p) for p in perfiles],
        })

    return {
        "exito": True,
        "computadoras": resultado,
        "total_global": sum(pc["total_perfiles"] for pc in resultado),
    }


@router.post("/perfiles/crear")
async def api_crear_perfil(
    req: CrearPerfilRequest,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """crea un nuevo perfil para el usuario."""
    usuario_id = sesion["usuario_id"]

    # si viene api_key usarla como nombre (compatibilidad con modal roxybrowser)
    nombre_perfil = (req.nombre or req.api_key or "").strip()
    if not nombre_perfil:
        return {"exito": False, "mensaje": "nombre o api_key es requerido"}

    id_nuevo = ejecutar_insercion(
        "insert into perfiles (usuario_id, nombre_perfil, tipo, estado) "
        "values (?, ?, ?, 'inactivo')",
        (usuario_id, nombre_perfil, req.tipo),
    )
    return {
        "exito": True,
        "id": id_nuevo,
        "mensaje": f"perfil '{nombre_perfil}' creado",
    }


@router.put("/perfiles/{perfil_id}")
async def api_actualizar_perfil(
    perfil_id: int,
    req: ActualizarPerfilRequest,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """actualiza nombre o estado de un perfil."""
    usuario_id = sesion["usuario_id"]

    perfil = ejecutar_sql_unico(
        "select id from perfiles where id = ? and usuario_id = ?",
        (perfil_id, usuario_id),
    )
    if not perfil:
        return {"exito": False, "mensaje": "perfil no encontrado"}

    campos = []
    params = []
    if req.nombre is not None:
        campos.append("nombre_perfil = ?")
        params.append(req.nombre.strip())
    if req.estado is not None:
        campos.append("estado = ?")
        params.append(req.estado)

    if campos:
        params.append(perfil_id)
        ejecutar_sql(
            f"update perfiles set {', '.join(campos)} where id = ?",
            tuple(params),
        )

    return {"exito": True, "mensaje": "perfil actualizado"}


@router.delete("/perfiles/{perfil_id}")
async def api_eliminar_perfil(
    perfil_id: int,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """elimina un perfil solo si esta inactivo."""
    usuario_id = sesion["usuario_id"]

    perfil = ejecutar_sql_unico(
        "select id, estado from perfiles where id = ? and usuario_id = ?",
        (perfil_id, usuario_id),
    )
    if not perfil:
        return {"exito": False, "mensaje": "perfil no encontrado"}
    if perfil["estado"] != "inactivo":
        return {"exito": False, "mensaje": "solo se puede eliminar perfiles inactivos"}

    ejecutar_sql(
        "delete from perfiles where id = ? and usuario_id = ?",
        (perfil_id, usuario_id),
    )
    return {"exito": True, "mensaje": "perfil eliminado"}


@router.post("/perfiles/{perfil_id}/eliminar")
async def api_eliminar_perfil_post(
    perfil_id: int,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """alias POST para eliminar perfil (compatibilidad frontend)."""
    return await api_eliminar_perfil(perfil_id, sesion)


@router.post("/perfiles/{perfil_id}/iniciar")
async def api_iniciar_perfil(
    perfil_id: int,
    req: IniciarPerfilRequest = None,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """envia orden a pcbot para iniciar el bot en ese perfil."""
    usuario_id = sesion["usuario_id"]

    if req is None:
        req = IniciarPerfilRequest()

    perfil = ejecutar_sql_unico(
        "select id, estado from perfiles where id = ? and usuario_id = ?",
        (perfil_id, usuario_id),
    )
    if not perfil:
        return {"exito": False, "mensaje": "perfil no encontrado"}
    if perfil["estado"] == "activo":
        return {"exito": False, "mensaje": "el perfil ya esta activo"}

    # obtener pcbot_id del usuario
    usuario = ejecutar_sql_unico(
        "select pcbot_id from usuarios where id = ?",
        (usuario_id,),
    )
    pcbot_id = usuario["pcbot_id"] if usuario else None

    if not pcbot_id:
        return {"exito": False, "mensaje": "no tienes un pcbot asociado"}

    # crear comando en cola
    import json as _json
    import uuid
    comando_id = str(uuid.uuid4())
    parametros = _json.dumps({
        "perfil_id": perfil_id,
        "url": req.url or "",
        "streamer": req.streamer or "",
    })

    ejecutar_insercion(
        "insert into comandos (comando_id, tipo, parametros, estado, pcbot_id) "
        "values (?, 'iniciar_perfil', ?, 'pendiente', ?)",
        (comando_id, parametros, pcbot_id),
    )

    return {
        "exito": True,
        "comando_id": comando_id,
        "mensaje": "orden de inicio enviada al pcbot",
    }


@router.post("/perfiles/{perfil_id}/detener")
async def api_detener_perfil(
    perfil_id: int,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """detiene el bot en ese perfil."""
    usuario_id = sesion["usuario_id"]

    perfil = ejecutar_sql_unico(
        "select id, estado from perfiles where id = ? and usuario_id = ?",
        (perfil_id, usuario_id),
    )
    if not perfil:
        return {"exito": False, "mensaje": "perfil no encontrado"}

    usuario = ejecutar_sql_unico(
        "select pcbot_id from usuarios where id = ?",
        (usuario_id,),
    )
    pcbot_id = usuario["pcbot_id"] if usuario else None

    if not pcbot_id:
        return {"exito": False, "mensaje": "no tienes un pcbot asociado"}

    import uuid
    comando_id = str(uuid.uuid4())

    ejecutar_insercion(
        "insert into comandos (comando_id, tipo, parametros, estado, pcbot_id) "
        "values (?, 'detener_perfil', ?, 'pendiente', ?)",
        (comando_id, f'{{"perfil_id": {perfil_id}}}', pcbot_id),
    )

    ejecutar_sql(
        "update perfiles set estado = 'inactivo' where id = ?",
        (perfil_id,),
    )

    return {
        "exito": True,
        "comando_id": comando_id,
        "mensaje": "orden de detencion enviada al pcbot",
    }