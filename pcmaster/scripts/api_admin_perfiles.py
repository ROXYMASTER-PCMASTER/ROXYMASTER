# api_admin_perfiles.py - gestion de perfiles para panel superadmin. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 500 lineas
# modulo dividido: _core (logica central) + _ext (handlers adicionales)

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from api_auth import verificar_admin_dependencia
from db import ejecutar_sql, ejecutar_sql_unico

router = APIRouter(prefix="/api/admin", tags=["admin_perfiles"])

# alias para compatibilidad frontend: /admin/perfiles -> /admin/perfiles_roxy
# ---------------------------------------------------------------------------
# 1. listar todos los perfiles con filtros
# ---------------------------------------------------------------------------
@router.get("/perfiles")
@router.get("/perfiles_roxy")
async def api_admin_listar_perfiles(
    pcbot_id: Optional[str] = Query(None),
    activo: Optional[int] = Query(None),
    estado_filtro: Optional[str] = Query(None),
    pagina: int = Query(1, ge=1),
    limite: int = Query(100, ge=1, le=500),
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """lista perfiles de perfiles_roxy con filtros opcionales."""
    condiciones = []
    params = []
    if pcbot_id:
        condiciones.append("p.pcbot_id = ?")
        params.append(pcbot_id)
    if activo is not None:
        condiciones.append("p.activo = ?")
        params.append(activo)
    if estado_filtro:
        condiciones.append("p.estado = ?")
        params.append(estado_filtro)

    where = "where " + " and ".join(condiciones) if condiciones else ""
    offset = (pagina - 1) * limite

    count_sql = f"select count(*) as total from perfiles_roxy p {where}"
    total = ejecutar_sql_unico(count_sql, tuple(params))["total"]

    data_sql = f"""
        select p.hash, p.pcbot_id, p.activo, p.estado, p.url_actual,
               p.liberacion_estimada, p.usuario_id, p.vip,
               p.ultimo_heartbeat, p.fecha_creacion,
               u.email as usuario_email
        from perfiles_roxy p
        left join usuarios u on p.usuario_id = u.id
        {where}
        order by p.fecha_creacion desc
        limit ? offset ?
    """
    params.extend([limite, offset])
    perfiles = ejecutar_sql(data_sql, tuple(params))

    return {
        "exito": True,
        "total": total,
        "pagina": pagina,
        "limite": limite,
        "perfiles": [{
            "hash": p["hash"],
            "pcbot_id": p["pcbot_id"] or "",
            "activo": p["activo"],
            "estado": p.get("estado", "desconocido"),
            "url_actual": p.get("url_actual", ""),
            "usuario_asignado": p.get("usuario_email") or str(p.get("usuario_id", "")) if p.get("usuario_id") else "",
            "usuario_id": p.get("usuario_id"),
            "vip": bool(p.get("vip", 0)),
            "ultimo_heartbeat": p.get("ultimo_heartbeat", ""),
            "fecha_creacion": p.get("fecha_creacion", ""),
            "liberacion_estimada": p.get("liberacion_estimada", ""),
        } for p in perfiles],
    }


# ---------------------------------------------------------------------------
# 2. activar/desactivar perfil (toggle activo)
# ---------------------------------------------------------------------------
@router.post("/perfiles/{perfil_hash}/toggle")
@router.post("/perfiles_roxy/{perfil_hash}/toggle")
async def api_admin_toggle_perfil(
    perfil_hash: str,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """cambia activo de un perfil entre 0 y 1."""
    perfil = ejecutar_sql_unico(
        "select hash, activo, estado from perfiles_roxy where hash = ?",
        (perfil_hash,),
    )
    if not perfil:
        raise HTTPException(status_code=404, detail="perfil no encontrado")

    nuevo_activo = 0 if perfil["activo"] else 1
    ejecutar_sql(
        "update perfiles_roxy set activo = ?, estado = case when ? = 0 then 'suspendido' else estado end where hash = ?",
        (nuevo_activo, nuevo_activo, perfil_hash),
    )
    return {
        "exito": True,
        "nuevo_estado": "activo" if nuevo_activo else "suspendido",
        "activo": nuevo_activo,
    }


# ---------------------------------------------------------------------------
# 3. eliminar perfil
# ---------------------------------------------------------------------------
@router.delete("/perfiles/{perfil_hash}")
@router.delete("/perfiles_roxy/{perfil_hash}")
async def api_admin_eliminar_perfil(
    perfil_hash: str,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """elimina un perfil de perfiles_roxy."""
    perfil = ejecutar_sql_unico("select hash from perfiles_roxy where hash = ?", (perfil_hash,))
    if not perfil:
        raise HTTPException(status_code=404, detail="perfil no encontrado")

    # verificar asignaciones activas
    activa = ejecutar_sql_unico(
        "select id from pedido_asignaciones where perfil_id = ? and estado = 'ejecutando'",
        (perfil_hash,),
    )
    if activa:
        raise HTTPException(status_code=400, detail="el perfil tiene una asignacion activa. cancela la asignacion primero.")

    ejecutar_sql("delete from pedido_asignaciones where perfil_id = ?", (perfil_hash,))
    ejecutar_sql("delete from perfiles_roxy where hash = ?", (perfil_hash,))
    return {"exito": True, "mensaje": "perfil eliminado"}


# ---------------------------------------------------------------------------
# 4. marcar perfil como caido
# ---------------------------------------------------------------------------
@router.post("/perfiles/{perfil_hash}/marcar-caido")
@router.post("/perfiles_roxy/{perfil_hash}/marcar-caido")
async def api_admin_marcar_perfil_caido(
    perfil_hash: str,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """marca un perfil como caido (activo=0, estado='caido')."""
    perfil = ejecutar_sql_unico("select hash from perfiles_roxy where hash = ?", (perfil_hash,))
    if not perfil:
        raise HTTPException(status_code=404, detail="perfil no encontrado")

    ejecutar_sql(
        "update perfiles_roxy set activo = 0, estado = 'caido' where hash = ?",
        (perfil_hash,),
    )
    return {"exito": True, "mensaje": "perfil marcado como caido"}