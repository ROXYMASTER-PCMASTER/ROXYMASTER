# api_admin_pedidos.py - gestion de pedidos para panel superadmin. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional

from api_auth import verificar_admin_dependencia
from db import ejecutar_sql, ejecutar_sql_unico

router = APIRouter(prefix="/api/admin", tags=["admin_pedidos"])


# ---------------------------------------------------------------------------
# 1. listar todos los pedidos
# ---------------------------------------------------------------------------
@router.get("/pedidos")
async def api_admin_listar_pedidos(
    pagina: int = Query(1, ge=1),
    limite: int = Query(50, ge=1, le=200),
    estado_filtro: Optional[str] = Query(None),
    tipo_filtro: Optional[str] = Query(None),
    usuario_id: Optional[int] = Query(None),
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """lista todos los pedidos del sistema con filtros."""
    condiciones = []
    params = []
    if estado_filtro:
        condiciones.append("p.estado = ?")
        params.append(estado_filtro)
    if tipo_filtro:
        condiciones.append("p.tipo_pedido = ?")
        params.append(tipo_filtro)
    if usuario_id:
        condiciones.append("p.usuario_id = ?")
        params.append(usuario_id)

    where = "where " + " and ".join(condiciones) if condiciones else ""
    offset = (pagina - 1) * limite

    total = ejecutar_sql_unico(
        f"select count(*) as total from pedidos p {where}", tuple(params)
    )["total"]

    data_sql = f"""
        select p.id, p.usuario_id, u.email as usuario_email, u.username as usuario_username,
               p.url, p.estado, p.tipo_pedido, p.cantidad_perfiles,
               p.duracion_horas, p.costo_tokens, p.fecha_creacion,
               p.nivel_comentarios, p.comando_id
        from pedidos p
        left join usuarios u on u.id = p.usuario_id
        {where}
        order by p.fecha_creacion desc
        limit ? offset ?
    """
    params.extend([limite, offset])
    pedidos = ejecutar_sql(data_sql, tuple(params))

    return {
        "exito": True,
        "total": total,
        "pagina": pagina,
        "limite": limite,
        "pedidos": pedidos,
    }


# ---------------------------------------------------------------------------
# 2. ver detalle de un pedido
# ---------------------------------------------------------------------------
@router.get("/pedidos/{pedido_id}")
async def api_admin_ver_pedido(
    pedido_id: int,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """devuelve el detalle completo de un pedido."""
    pedido = ejecutar_sql_unico(
        "select p.*, u.email as usuario_email, u.username as usuario_username "
        "from pedidos p left join usuarios u on u.id = p.usuario_id "
        "where p.id = ?",
        (pedido_id,),
    )
    if not pedido:
        raise HTTPException(status_code=404, detail="pedido no encontrado")

    # obtener asignaciones asociadas si existen
    asignaciones = ejecutar_sql(
        "select a.id, a.perfil_hash, a.pcbot_id, a.url as asignacion_url, "
        "a.duracion_seg, a.inicio, a.fin, a.estado as estado_asignacion, "
        "a.comando_id, a.liberacion_estimada "
        "from asignaciones a where a.pedido_id = ?",
        (pedido_id,),
    )
    pedido["asignaciones"] = asignaciones
    return {"exito": True, "dato": pedido}


# ---------------------------------------------------------------------------
# 3. cancelar pedido
# ---------------------------------------------------------------------------
@router.post("/pedidos/{pedido_id}/cancelar")
async def api_admin_cancelar_pedido(
    pedido_id: int,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """cancela un pedido manualmente."""
    pedido = ejecutar_sql_unico(
        "select id, estado from pedidos where id = ?",
        (pedido_id,),
    )
    if not pedido:
        raise HTTPException(status_code=404, detail="pedido no encontrado")

    if pedido["estado"] in ("cancelado", "completado"):
        raise HTTPException(status_code=400, detail="el pedido ya esta cancelado o completado")

    ejecutar_sql(
        "update pedidos set estado = 'cancelado' where id = ?",
        (pedido_id,),
    )

    # liberar asignaciones activas de este pedido
    ejecutar_sql(
        "update asignaciones set estado = 'cancelada' where pedido_id = ? and estado = 'activa'",
        (pedido_id,),
    )

    return {"exito": True, "mensaje": "pedido cancelado exitosamente"}


# ---------------------------------------------------------------------------
# 4. reabrir pedido
# ---------------------------------------------------------------------------
@router.post("/pedidos/{pedido_id}/reabrir")
async def api_admin_reabrir_pedido(
    pedido_id: int,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """reabre un pedido cancelado."""
    pedido = ejecutar_sql_unico(
        "select id, estado from pedidos where id = ?",
        (pedido_id,),
    )
    if not pedido:
        raise HTTPException(status_code=404, detail="pedido no encontrado")

    if pedido["estado"] not in ("cancelado", "fallido"):
        raise HTTPException(status_code=400, detail="el pedido no esta cancelado ni fallido")

    ejecutar_sql(
        "update pedidos set estado = 'pendiente' where id = ?",
        (pedido_id,),
    )
    return {"exito": True, "mensaje": "pedido reabierto exitosamente"}


# ---------------------------------------------------------------------------
# 5. forzar reasignacion manual
# ---------------------------------------------------------------------------
@router.post("/pedidos/{pedido_id}/reasignar")
async def api_admin_reasignar_pedido(
    pedido_id: int,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """fuerza la reasignacion de un pedido (lo marca como pendiente para el proximo ciclo)."""
    pedido = ejecutar_sql_unico(
        "select id, estado from pedidos where id = ?",
        (pedido_id,),
    )
    if not pedido:
        raise HTTPException(status_code=404, detail="pedido no encontrado")

    ejecutar_sql(
        "update pedidos set estado = 'pendiente' where id = ?",
        (pedido_id,),
    )
    # eliminar asignaciones activas previas para que se regeneren
    ejecutar_sql(
        "delete from asignaciones where pedido_id = ?",
        (pedido_id,),
    )
    return {"exito": True, "mensaje": "reasignacion forzada. el pedido sera procesado en el proximo ciclo"}