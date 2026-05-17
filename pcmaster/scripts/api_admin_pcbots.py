# api_admin_pcbots.py - gestion de pcbots para panel superadmin. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 500 lineas

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional

from api_auth import verificar_admin_dependencia
from db import ejecutar_sql, ejecutar_sql_unico

router = APIRouter(prefix="/api/admin", tags=["admin_pcbots"])


# ---------------------------------------------------------------------------
# 1. listar pcbots registrados (formato compatible con frontend)
# ---------------------------------------------------------------------------
@router.get("/pcbots")
async def api_admin_listar_pcbots(
    pagina: int = Query(1, ge=1),
    limite: int = Query(50, ge=1, le=200),
    estado_filtro: Optional[str] = Query(None),
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """lista todos los pcbots registrados con su estado."""
    condiciones = []
    params = []
    if estado_filtro:
        if estado_filtro == "conectado":
            condiciones.append("p.estado = 'conectado'")
        elif estado_filtro == "desconectado":
            condiciones.append("p.estado = 'desconectado'")
        else:
            condiciones.append("p.estado = ?")
            params.append(estado_filtro)

    where = "where " + " and ".join(condiciones) if condiciones else ""
    offset = (pagina - 1) * limite

    total = ejecutar_sql_unico(
        f"select count(*) as total from pcbots_registrados p {where}", tuple(params)
    )["total"]

    data_sql = f"""
        select p.id, p.pcbot_id, p.hostname, p.usuario, p.ip_local,
               p.ip_tailscale, p.ip_wan, p.workspace_id, p.estado,
               p.modo, p.version_agente, p.ultimo_heartbeat,
               p.ultima_conexion, p.kbt_acumulados, p.perfiles_activos,
               p.uptime_segundos
        from pcbots_registrados p
        {where}
        order by p.ultimo_heartbeat desc
        limit ? offset ?
    """
    params.extend([limite, offset])
    pcbots_raw = ejecutar_sql(data_sql, tuple(params))

    # normalizar para frontend (compatibilidad con panel admin)
    pcbots = []
    for p in pcbots_raw:
        conectado = p.get("estado") == "conectado"
        uptime_s = p.get("uptime_segundos", 0) or 0
        uptime_str = f"{uptime_s // 3600}h {(uptime_s % 3600) // 60}m" if uptime_s > 0 else "-"
        pcbots.append({
            "id": p.get("pcbot_id") or str(p["id"]),
            "pcbot_id": p.get("pcbot_id") or str(p["id"]),
            "email": p.get("usuario") or "",
            "conectado": conectado,
            "estado": p.get("estado", "desconocido"),
            "usuario_id": p.get("usuario") or p.get("hostname") or "-",
            "ip": p.get("ip_local") or p.get("ip_tailscale") or "-",
            "version": p.get("version_agente") or "-",
            "ultimo_heartbeat": p.get("ultimo_heartbeat") or "-",
            "perfiles": p.get("perfiles_activos", 0) or 0,
            "perfiles_activos": p.get("perfiles_activos", 0) or 0,
            "hostname": p.get("hostname") or "",
            "modo": p.get("modo", "desconocido"),
            "uptime": uptime_str,
            "uptime_segundos": uptime_s,
        })

    return {
        "exito": True,
        "total": total,
        "pagina": pagina,
        "limite": limite,
        "pcbots": pcbots,
    }


# ---------------------------------------------------------------------------
# 2. ver detalle de un pcbot
# ---------------------------------------------------------------------------
@router.get("/pcbots/{pcbot_id}")
async def api_admin_ver_pcbot(
    pcbot_id: str,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """devuelve el detalle completo de un pcbot."""
    pcbot = ejecutar_sql_unico(
        "select * from pcbots_registrados where pcbot_id = ?",
        (pcbot_id,),
    )
    if not pcbot:
        raise HTTPException(status_code=404, detail="pcbot no encontrado")

    # obtener heartbeats recientes
    heartbeats = ejecutar_sql(
        "select * from heartbeat_cache where pcbot_id = ? order by timestamp desc limit 20",
        (pcbot_id,),
    )
    pcbot["heartbeats_recientes"] = heartbeats

    # obtener perfiles de este pcbot
    perfiles = ejecutar_sql(
        "select nombre, hash, activo, ultimo_heartbeat from perfiles_roxy where pcbot_id = ?",
        (pcbot_id,),
    )
    pcbot["perfiles"] = perfiles

    return {"exito": True, "dato": pcbot}


# ---------------------------------------------------------------------------
# 3. desconectar pcbot forzosamente
# ---------------------------------------------------------------------------
@router.post("/pcbots/{pcbot_id}/desconectar")
async def api_admin_desconectar_pcbot(
    pcbot_id: str,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """marca un pcbot como desconectado y libera sus recursos."""
    pcbot = ejecutar_sql_unico(
        "select id from pcbots_registrados where pcbot_id = ?",
        (pcbot_id,),
    )
    if not pcbot:
        # intentar por id numerico
        try:
            pid = int(pcbot_id)
            pcbot = ejecutar_sql_unico(
                "select id from pcbots_registrados where id = ?",
                (pid,),
            )
        except ValueError:
            pass
    if not pcbot:
        raise HTTPException(status_code=404, detail="pcbot no encontrado")

    ejecutar_sql(
        "update pcbots_registrados set estado = 'desconectado', modo = 'desconocido' where id = ?",
        (pcbot["id"],),
    )

    # desactivar perfiles asociados a este pcbot
    ejecutar_sql(
        "update perfiles_roxy set activo = 0 where pcbot_id in "
        "(select pcbot_id from pcbots_registrados where id = ?)",
        (pcbot["id"],),
    )

    return {"exito": True, "mensaje": f"pcbot {pcbot_id} desconectado forzosamente"}


# ---------------------------------------------------------------------------
# 4. ver heartbeats recientes de un pcbot
# ---------------------------------------------------------------------------
@router.get("/pcbots/{pcbot_id}/heartbeats")
async def api_admin_heartbeats_pcbot(
    pcbot_id: str,
    limite: int = Query(50, ge=1, le=200),
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """devuelve los ultimos heartbeats de un pcbot."""
    heartbeats = ejecutar_sql(
        "select * from heartbeat_cache where pcbot_id = ? "
        "order by timestamp desc limit ?",
        (pcbot_id, limite),
    )
    return {"exito": True, "datos": heartbeats}