# api_monitoreo.py - endpoints de monitoreo interno. roxymaster v8.3
# utf-8 sin bom, nombres en minusculas, <= 400 lineas

import json
import time
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from db import ejecutar_sql, ejecutar_sql_unico
from auth import verificar_token_dependency
from orchestrator import listar_pcbots_conectados, listar_comandos_pendientes
from jarvis_core import estado_jarvis

router = APIRouter(prefix="/api/monitoreo", tags=["monitoreo"])


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _ahora_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ts() -> int:
    return int(time.time())


# ---------------------------------------------------------------------------
# panel resumen
# ---------------------------------------------------------------------------
@router.get("/resumen")
async def resumen_monitoreo(usuario: dict = verificar_token_dependency):
    """devuelve un resumen del estado del sistema."""
    # contar pcbots
    pcbots = listar_pcbots_conectados()
    pcbots_conectados = len([p for p in pcbots if p.get("estado") == "conectado"])
    pcbots_inactivos = len([p for p in pcbots if p.get("estado") != "conectado"])

    # contar comandos en db
    comandos_pend = ejecutar_sql("select count(*) as cnt from comandos where estado = 'pendiente'")
    comandos_completados = ejecutar_sql("select count(*) as cnt from comandos where estado = 'completado'")

    # contar pedidos
    pedidos_pend = ejecutar_sql("select count(*) as cnt from pedidos where estado = 'pendiente'")
    pedidos_total = ejecutar_sql("select count(*) as cnt from pedidos")

    # estado jarvis
    j = estado_jarvis()

    return {
        "exito": True,
        "timestamp": _ahora_str(),
        "pcbots": {
            "total": len(pcbots),
            "conectados": pcbots_conectados,
            "inactivos": pcbots_inactivos,
            "lista": pcbots[:10],
        },
        "comandos": {
            "pendientes": comandos_pend[0]["cnt"] if comandos_pend else 0,
            "completados": comandos_completados[0]["cnt"] if comandos_completados else 0,
        },
        "pedidos": {
            "pendientes": pedidos_pend[0]["cnt"] if pedidos_pend else 0,
            "total": pedidos_total[0]["cnt"] if pedidos_total else 0,
        },
        "jarvis": {
            "activo": j.get("activo", False),
            "modo": j.get("modo", "desconocido"),
            "cola_pendiente": j.get("cola_pendiente", 0),
        },
    }


# ---------------------------------------------------------------------------
# logs del sistema
# ---------------------------------------------------------------------------
@router.get("/logs")
async def logs_sistema(
    limite: int = Query(50, ge=1, le=500),
    nivel: str = Query(None, regex="^(info|warn|error|debug)$"),
    usuario: dict = verificar_token_dependency,
):
    """devuelve los logs del sistema desde la tabla eventos."""
    condiciones = []
    params = []

    if nivel:
        condiciones.append("nivel = ?")
        params.append(nivel)

    where = "where " + " and ".join(condiciones) if condiciones else ""
    sql = f"select * from eventos {where} order by id desc limit ?"
    params.append(limite)

    filas = ejecutar_sql(sql, tuple(params))
    logs = []
    for f in filas:
        logs.append({
            "id": f["id"],
            "nivel": f.get("nivel", "info"),
            "mensaje": f.get("mensaje", ""),
            "origen": f.get("origen", ""),
            "timestamp": f.get("fecha_creacion", f.get("timestamp", "")),
        })
    return {"exito": True, "logs": logs, "total": len(logs)}


# ---------------------------------------------------------------------------
# metricas de rendimiento
# ---------------------------------------------------------------------------
@router.get("/metricas")
async def metricas_rendimiento(
    horas: int = Query(24, ge=1, le=168),
    usuario: dict = verificar_token_dependency,
):
    """metricas de rendimiento: kbt generados, comandos por hora, uptime."""
    # kbt total por hora (desde tabla kbt_transacciones)
    kbt_recientes = ejecutar_sql(
        """select strftime('%Y-%m-%d %H:00:00', fecha_creacion) as hora,
                  sum(cantidad) as total_kbt
           from kbt_transacciones
           where fecha_creacion >= datetime('now', ?)
           group by hora
           order by hora desc""",
        (f"-{horas} hours",),
    )

    # comandos por hora
    cmds_por_hora = ejecutar_sql(
        """select strftime('%Y-%m-%d %H:00:00', fecha_creacion) as hora,
                  count(*) as total_cmds,
                  sum(case when estado = 'completado' then 1 else 0 end) as completados
           from comandos
           where fecha_creacion >= datetime('now', ?)
           group by hora
           order by hora desc""",
        (f"-{horas} hours",),
    )

    return {
        "exito": True,
        "horas": horas,
        "kbt_por_hora": [dict(r) for r in kbt_recientes],
        "comandos_por_hora": [dict(r) for r in cmds_por_hora],
    }


# ---------------------------------------------------------------------------
# estado de componentes
# ---------------------------------------------------------------------------
@router.get("/componentes")
async def estado_componentes(usuario: dict = verificar_token_dependency):
    """verifica el estado de cada componente del sistema."""
    # db
    try:
        ejecutar_sql("select 1")
        db_ok = True
    except Exception:
        db_ok = False

    # jarvis
    j = estado_jarvis()

    # websocket
    from orchestrator import gestor_websockets
    ws_conectado = len(gestor_websockets) > 0

    return {
        "exito": True,
        "componentes": {
            "base_de_datos": {"ok": db_ok, "detalle": "conexion ok" if db_ok else "fallo en conexion"},
            "jarvis": {"ok": j.get("activo", False), "detalle": f"modo: {j.get('modo', 'n/a')}"},
            "websocket": {"ok": ws_conectado, "detalle": f"{len(gestor_websockets)} pcbots conectados" if ws_conectado else "sin pcbots"},
            "orquestrador": {"ok": True, "detalle": "operativo"},
        },
    }
