# api_admin_acciones.py - acciones administrativas, monitoreo y stats. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 500 lineas

import os
import shutil
from datetime import datetime
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from api_auth import verificar_admin_dependencia
from db import ejecutar_sql, ejecutar_sql_unico

router = APIRouter(prefix="/api/admin", tags=["admin_acciones"])

# ruta base del proyecto (relativa a este script)
RUTA_PROYECTO = Path(__file__).resolve().parent.parent.parent
RUTA_BACKUPS = RUTA_PROYECTO / "backups"


# ---------------------------------------------------------------------------
# 1. forzar ciclo de match (ambas rutas: /acciones/match y /acciones/forzar-match)
# ---------------------------------------------------------------------------
@router.post("/acciones/match")
@router.post("/acciones/forzar-match")
async def api_admin_forzar_match(
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """ejecuta un ciclo de match inmediato."""
    try:
        from procesador_cola import ejecutar_ciclo_match
        resultado = await ejecutar_ciclo_match()
        return {"exito": True, "mensaje": "ciclo de match ejecutado", "resultado": str(resultado)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"error al ejecutar match: {str(e)}")


# ---------------------------------------------------------------------------
# 2. limpiar asignaciones huerfanas
# ---------------------------------------------------------------------------
@router.post("/acciones/limpiar-huerfanas")
async def api_admin_limpiar_huerfanas(
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """marca como fallido asignaciones huerfanas."""
    marcadas = 0
    huerfanas = ejecutar_sql(
        "select a.id, a.pedido_id, a.pcbot_id from pedido_asignaciones a "
        "where a.estado in ('ejecutando', 'planificado') "
        "and (a.pedido_id not in (select id from pedidos where estado in ('activo', 'completado')) "
        "     or a.pcbot_id not in (select pcbot_id from pcbots_registrados where estado = 'conectado'))"
    )
    for h in huerfanas:
        ejecutar_sql(
            "update pedido_asignaciones set estado = 'fallido', fin = datetime('now','localtime') "
            "where id = ?",
            (h["id"],),
        )
        marcadas += 1

    return {"exito": True, "mensaje": f"{marcadas} asignaciones huerfanas limpiadas", "marcadas": marcadas}


# ---------------------------------------------------------------------------
# 3. backup manual de la base de datos
# ---------------------------------------------------------------------------
@router.post("/acciones/backup")
async def api_admin_backup_manual(
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """crea un backup manual de roxymaster.db en backups/ con timestamp."""
    db_path = RUTA_PROYECTO / "data" / "roxymaster.db"
    if not db_path.exists():
        raise HTTPException(status_code=404, detail="base de datos no encontrada en data/")

    RUTA_BACKUPS.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = RUTA_BACKUPS / f"roxymaster_{timestamp}.db"
    shutil.copy2(str(db_path), str(backup_path))

    return {"exito": True, "mensaje": "backup creado", "ruta": str(backup_path), "tamano_kb": round(backup_path.stat().st_size / 1024, 1)}


# ---------------------------------------------------------------------------
# 4. reiniciar procesador de cola
# ---------------------------------------------------------------------------
@router.post("/acciones/reiniciar-procesador")
async def api_admin_reiniciar_procesador(
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """reinicia el bucle del procesador de cola."""
    try:
        from procesador_cola import bucle_activo, detener_bucle
        if bucle_activo:
            await detener_bucle()
        import asyncio
        await asyncio.sleep(1)
        from procesador_cola import iniciar_bucle
        asyncio.create_task(iniciar_bucle())
        return {"exito": True, "mensaje": "procesador de cola reiniciado"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"error al reiniciar procesador: {str(e)}")


# ---------------------------------------------------------------------------
# 5. obtener logs del servidor
# ---------------------------------------------------------------------------
@router.get("/logs")
async def api_admin_obtener_logs(
    lineas: int = Query(100, ge=10, le=5000),
    filtro: Optional[str] = Query(None),
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """obtiene las ultimas N lineas de server_out.txt."""
    log_paths = [
        RUTA_PROYECTO / "server_out.txt",
        RUTA_PROYECTO / "server_err.txt",
    ]
    log_content = []
    for lp in log_paths:
        if lp.exists():
            try:
                with open(lp, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                log_content.extend([{"linea": l.rstrip("\n\r"), "origen": lp.name} for l in lines])
            except Exception:
                pass

    if filtro:
        filtro_upper = filtro.upper()
        log_content = [l for l in log_content if filtro_upper in l["linea"].upper()]

    # ultimas N
    log_content = log_content[-lineas:]

    return {"exito": True, "logs": log_content, "total": len(log_content), "filtro": filtro}


# ---------------------------------------------------------------------------
# 6. obtener solo lineas con ERROR o WARNING
# ---------------------------------------------------------------------------
@router.get("/logs/errores")
async def api_admin_logs_errores(
    lineas: int = Query(200, ge=10, le=5000),
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """obtiene solo las lineas con ERROR o WARNING de los logs."""
    log_paths = [
        RUTA_PROYECTO / "server_out.txt",
        RUTA_PROYECTO / "server_err.txt",
    ]
    errores = []
    for lp in log_paths:
        if lp.exists():
            try:
                with open(lp, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        l = line.rstrip("\n\r")
                        if "ERROR" in l or "WARNING" in l:
                            errores.append({"linea": l, "origen": lp.name})
            except Exception:
                pass

    errores = errores[-lineas:]

    return {"exito": True, "logs": errores, "total": len(errores)}


# ---------------------------------------------------------------------------
# 7. estadisticas avanzadas (kpis completos)
# ---------------------------------------------------------------------------
@router.get("/stats")
async def api_admin_stats(
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """kpis completos del sistema."""
    try:
        # total usuarios
        total_usuarios = ejecutar_sql_unico("select count(*) as c from usuarios")["c"] or 0
        activos = ejecutar_sql_unico("select count(*) as c from usuarios where activo = 1")["c"] or 0
        admins = ejecutar_sql_unico("select count(*) as c from usuarios where activo = 1 and rol = 'admin'")["c"] or 0
        usuarios = ejecutar_sql_unico("select count(*) as c from usuarios where activo = 1 and rol = 'usuario'")["c"] or 0

        # pedidos por estado
        pedidos_activos = ejecutar_sql_unico("select count(*) as c from pedidos where estado = 'activo'")["c"] or 0
        pedidos_completados = ejecutar_sql_unico("select count(*) as c from pedidos where estado = 'completado'")["c"] or 0
        pedidos_cancelados = ejecutar_sql_unico("select count(*) as c from pedidos where estado = 'cancelado'")["c"] or 0
        pedidos_fallidos = ejecutar_sql_unico("select count(*) as c from pedidos where estado in ('fallido','expirado')")["c"] or 0

        # perfiles
        total_perfiles = ejecutar_sql_unico("select count(*) as c from perfiles_roxy")["c"] or 0
        perfiles_activos = ejecutar_sql_unico("select count(*) as c from perfiles_roxy where activo = 1")["c"] or 0
        perfiles_caidos = ejecutar_sql_unico("select count(*) as c from perfiles_roxy where activo = 0 and estado = 'caido'")["c"] or 0
        perfiles_libres = ejecutar_sql_unico("select count(*) as c from perfiles_roxy where activo = 1 and estado = 'libre'")["c"] or 0

        # pcbots
        pcbots_conectados = ejecutar_sql_unico("select count(*) as c from pcbots_registrados where estado = 'conectado'")["c"] or 0
        pcbots_desconectados = ejecutar_sql_unico("select count(*) as c from pcbots_registrados where estado != 'conectado'")["c"] or 0

        # kbt
        kbt_circulando = ejecutar_sql_unico("select coalesce(sum(saldo), 0) as c from wallets where activa = 1")["c"] or 0

        # volumen 24h
        volumen_24h = ejecutar_sql_unico(
            "select coalesce(sum(costo_tokens), 0) as c from pedidos "
            "where fecha_creacion >= datetime('now','-1 day','localtime')"
        )["c"] or 0

        # sesiones activas
        sesiones_activas = ejecutar_sql_unico(
            "select count(*) as c from sesiones where expiracion > datetime('now','localtime')"
        )["c"] or 0

        # retiros pendientes
        retiros_pendientes = ejecutar_sql_unico(
            "select count(*) as c from retiros where estado = 'pendiente'"
        )["c"] or 0

        # comandos pendientes
        comandos_pendientes = ejecutar_sql_unico(
            "select count(*) as c from comandos where estado = 'pendiente'"
        )["c"] or 0

        return {
            "exito": True,
            "stats": {
                "usuarios": {
                    "total": total_usuarios,
                    "activos": activos,
                    "admins": admins,
                    "usuarios_comunes": usuarios,
                },
                "pedidos": {
                    "activos": pedidos_activos,
                    "completados": pedidos_completados,
                    "cancelados": pedidos_cancelados,
                    "fallidos": pedidos_fallidos,
                },
                "perfiles": {
                    "total": total_perfiles,
                    "activos": perfiles_activos,
                    "caidos": perfiles_caidos,
                    "libres": perfiles_libres,
                },
                "pcbots": {
                    "conectados": pcbots_conectados,
                    "desconectados": pcbots_desconectados,
                },
                "tokenomia": {
                    "kbt_circulando": float(kbt_circulando),
                    "volumen_24h": float(volumen_24h),
                },
                "sistema": {
                    "sesiones_activas": sesiones_activas,
                    "retiros_pendientes": retiros_pendientes,
                    "comandos_pendientes": comandos_pendientes,
                },
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"error al obtener stats: {str(e)}")
