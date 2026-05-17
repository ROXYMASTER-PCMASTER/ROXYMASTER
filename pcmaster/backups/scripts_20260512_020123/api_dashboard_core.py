# api_dashboard_core.py - endpoints principales del dashboard: resumen, estado, perfiles, pcs.
# roxymaster v8.3 - todo en minusculas, utf-8 sin bom, <= 400 lineas

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api_auth import verificar_token_dependencia
from db import ejecutar_sql_unico, ejecutar_sql
from tokenomics import obtener_balance as consultar_balance
from orchestrator import listar_pcbots_conectados, listar_comandos_pendientes
from variables_globales import obtener_variables

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
async def api_dashboard(sesion: dict = Depends(verificar_token_dependencia)):
    """dashboard principal con resumen del sistema y kpis del usuario."""
    usuario_id = sesion["usuario_id"]

    # datos del usuario (sin password_hash)
    usuario = ejecutar_sql_unico(
        "select id, email, username, rol, nivel_fiabilidad, uptime_horas, pcbot_id, modo, "
        "codigo_referido, referido_por, fecha_registro from usuarios where id = ?",
        (usuario_id,),
    )
    if not usuario:
        return {"exito": False, "mensaje": "usuario no encontrado"}

    # balance real desde wallets con coalesce
    row_wallet = ejecutar_sql_unico(
        "select coalesce(balance, 0) as balance, coalesce(minado_total, 0) as minado_total, "
        "coalesce(comprado_total, 0) as comprado_total from wallets where usuario_id = ?",
        (usuario_id,),
    )
    balance = float(row_wallet["balance"]) if row_wallet else 0.0
    minado_total = float(row_wallet["minado_total"]) if row_wallet else 0.0

    # precio token desde variables_globales
    vars_sistema = obtener_variables()
    p_token = float(vars_sistema.get("p_token", 1.0))
    saldo_pen = round(balance * p_token, 2)

    # contar perfiles activos
    perfiles_activos = 0
    perfiles_totales = 0
    row_perfiles = ejecutar_sql_unico(
        "select count(*) as total from perfiles where usuario_id = ? and estado = 'activo'",
        (usuario_id,),
    )
    if row_perfiles:
        perfiles_activos = row_perfiles["total"]

    row_perfiles_totales = ejecutar_sql_unico(
        "select count(*) as total from perfiles where usuario_id = ?",
        (usuario_id,),
    )
    if row_perfiles_totales:
        perfiles_totales = row_perfiles_totales["total"]

    # kbt minados hoy
    kbt_hoy = 0.0
    row_kbt = ejecutar_sql_unico(
        "select coalesce(sum(monto), 0) as total from transacciones "
        "where (origen_id = ? or destino_id = ?) and tipo = 'minado' and date(fecha) = date('now')",
        (usuario_id, usuario_id),
    )
    if row_kbt:
        kbt_hoy = float(row_kbt["total"])

    # referidos: activos y totales
    referidos_totales = 0
    referidos_activos = 0
    row_ref = ejecutar_sql_unico(
        "select count(*) as total from referidos where referidor_id = ?",
        (usuario_id,),
    )
    if row_ref:
        referidos_totales = row_ref["total"]

    row_ref_act = ejecutar_sql_unico(
        "select count(*) as total from referidos r "
        "join usuarios u on u.id = r.referido_id "
        "where r.referidor_id = ? and u.activo = 1",
        (usuario_id,),
    )
    if row_ref_act:
        referidos_activos = row_ref_act["total"]

    # modo actual
    modo_actual = str(usuario.get("modo", "conectado"))

    return {
        "exito": True,
        "usuario": dict(usuario),
        "balance": balance,
        "saldo_pen": saldo_pen,
        "perfiles_activos": perfiles_activos,
        "perfiles_totales": perfiles_totales,
        "kbt_hoy": kbt_hoy,
        "kbt_total_minado": minado_total,
        "referidos_activos": referidos_activos,
        "referidos_totales": referidos_totales,
        "modo_actual": modo_actual,
        "codigo_referido": usuario.get("codigo_referido", ""),
        "referido_por": usuario.get("referido_por", ""),
    }


@router.get("/precios_marketplace")
async def api_precios_marketplace(sesion: dict = Depends(verificar_token_dependencia)):
    """devuelve el precio mas alto y mas bajo de ordenes activas en marketplace."""
    # precio mas alto de ventas activas
    row_max = ejecutar_sql_unico(
        "select max(precio_pen) as precio_max from ordenes_p2p "
        "where estado = 'abierta' and tipo = 'venta'",
    )
    precio_max = float(row_max["precio_max"]) if row_max and row_max["precio_max"] else 0.0

    # precio mas bajo de compras activas
    row_min = ejecutar_sql_unico(
        "select min(precio_pen) as precio_min from ordenes_p2p "
        "where estado = 'abierta' and tipo = 'compra'",
    )
    precio_min = float(row_min["precio_min"]) if row_min and row_min["precio_min"] else 0.0

    return {
        "exito": True,
        "precio_max_venta": precio_max,
        "precio_min_compra": precio_min,
    }


@router.get("/mi_estado")
async def api_mi_estado(sesion: dict = Depends(verificar_token_dependencia)):
    """estado detallado del usuario autenticado (datos sensibles excluidos)."""
    usuario_id = sesion["usuario_id"]

    # excluir password_hash por seguridad
    usuario = ejecutar_sql_unico(
        "select id, email, username, rol, wallet, codigo_referido, referido_por, "
        "referido_cambiado, nivel_fiabilidad, uptime_horas, pcbot_id, modo, "
        "ultimo_login, fecha_registro, activo from usuarios where id = ?",
        (usuario_id,),
    )
    wallet = ejecutar_sql_unico(
        "select id, usuario_id, balance, minado_total, recolectado_total, "
        "comprado_total, retirado_total, staking_total, staking_desde, actualizado "
        "from wallets where usuario_id = ?",
        (usuario_id,),
    )
    # obtener comandos pendientes para el pcbot del usuario
    pcbot_id = usuario["pcbot_id"] if usuario else None
    comandos_pendientes = []
    if pcbot_id:
        comandos_pendientes = listar_comandos_pendientes(pcbot_id)

    return {
        "exito": True,
        "usuario": dict(usuario) if usuario else {},
        "wallet": dict(wallet) if wallet else {},
        "comandos_pendientes": comandos_pendientes,
    }


@router.get("/mis_pcs")
async def api_mis_pcs(sesion: dict = Depends(verificar_token_dependencia)):
    """lista los pcs registrados del usuario autenticado."""
    usuario_id = sesion["usuario_id"]

    usuario = ejecutar_sql_unico(
        "select id, pcbot_id, modo, uptime_horas from usuarios where id = ?",
        (usuario_id,),
    )
    pcs = []
    if usuario and usuario["pcbot_id"]:
        perfiles = ejecutar_sql(
            "select count(*) as total from perfiles where usuario_id = ?",
            (usuario_id,),
        )
        total_perfiles = perfiles[0]["total"] if perfiles else 0

        pc_item = {
            "pcbot_id": usuario["pcbot_id"],
            "modo": usuario["modo"],
            "perfiles_activos": total_perfiles,
            "uptime_horas": usuario["uptime_horas"] or 0,
        }
        pcs.append(pc_item)

    return {"exito": True, "pcs": pcs}


@router.get("/mis_perfiles")
async def api_mis_perfiles(sesion: dict = Depends(verificar_token_dependencia)):
    """lista los perfiles del usuario autenticado con progreso de 62 min."""
    usuario_id = sesion["usuario_id"]

    perfiles = ejecutar_sql(
        "select id, nombre_perfil, tipo, estado, horas_conexion, horas_en_uso, "
        "ultimo_heartbeat from perfiles where usuario_id = ?",
        (usuario_id,),
    )

    resultado = []
    ciclo_minutos = 62

    for p in perfiles:
        progreso = 0
        if p["ultimo_heartbeat"] and p["estado"] == "activo":
            try:
                from datetime import datetime
                last = datetime.strptime(p["ultimo_heartbeat"], "%Y-%m-%d %H:%M:%S")
                ahora = datetime.now()
                diff_min = (ahora - last).total_seconds() / 60.0
                if diff_min < ciclo_minutos:
                    progreso = round((diff_min / ciclo_minutos) * 100, 1)
                else:
                    progreso = 100.0
            except (ValueError, TypeError):
                progreso = 0

        resultado.append({
            "id": p["id"],
            "nombre_perfil": p["nombre_perfil"],
            "tipo": p["tipo"],
            "estado": p["estado"],
            "horas_conexion": p["horas_conexion"] or 0,
            "horas_en_uso": p["horas_en_uso"] or 0,
            "ultimo_heartbeat": p["ultimo_heartbeat"] or "",
            "progreso_62min": progreso,
        })

    # obtener pcs del usuario
    pcs = []
    usuario = ejecutar_sql_unico(
        "select id, pcbot_id, modo, uptime_horas from usuarios where id = ?",
        (usuario_id,),
    )
    if usuario and usuario["pcbot_id"]:
        rows = ejecutar_sql(
            "select count(*) as total from perfiles where usuario_id = ?",
            (usuario_id,),
        )
        total = rows[0]["total"] if rows else 0
        pcs.append({
            "pcbot_id": usuario["pcbot_id"],
            "modo": usuario["modo"],
            "perfiles_activos": total,
            "uptime_horas": usuario["uptime_horas"] or 0,
        })

    return {"exito": True, "perfiles": resultado, "pcs": pcs}