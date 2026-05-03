# api_tokenomia.py - router fastapi para tokenomia, proyecciones, happy hour, kpi. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from api_auth import verificar_admin_dependencia
from db import ejecutar_sql, ejecutar_sql_unico, ejecutar_insercion, obtener_todas_variables

router = APIRouter(prefix="/api/admin", tags=["admin_tokenomia"])


# ---------------------------------------------------------------------------
# modelos pydantic
# ---------------------------------------------------------------------------
class VariableUpdateRequest(BaseModel):
    clave: str
    valor: str


# ---------------------------------------------------------------------------
# variables economicas
# ---------------------------------------------------------------------------
@router.get("/variables")
async def api_obtener_variables(sesion: dict = Depends(verificar_admin_dependencia)):
    """devuelve todas las variables economicas del sistema."""
    variables = obtener_todas_variables()
    return {"exito": True, "variables": variables}


@router.put("/variables")
async def api_actualizar_variable(
    req: VariableUpdateRequest,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """actualiza una variable economica individualmente."""
    claves_permitidas = {
        "k", "fx", "p_token", "g_default", "h", "hh_mult",
        "min_uptime", "min_fiabilidad", "max_perfiles_pc",
        "comision_marketplace", "comision_retiro_0_30",
        "comision_retiro_31_60", "comision_retiro_61_90",
        "comision_retiro_90_plus", "comision_referido",
        "limite_retiro_mensual_usd", "tasa_recoleccion_mensual",
        "w_bronce", "w_plata", "w_oro",
        "uptime_bronce", "uptime_plata", "uptime_oro",
        "happy_hour_activo", "beta",
    }
    if req.clave not in claves_permitidas:
        raise HTTPException(status_code=400, detail="clave no permitida")
    ejecutar_sql(
        "insert or replace into variables (clave, valor) values (?, ?)",
        (req.clave, req.valor),
    )
    return {"exito": True, "clave": req.clave, "valor": req.valor}


@router.post("/variables/restablecer")
async def api_restablecer_variables(sesion: dict = Depends(verificar_admin_dependencia)):
    """restablece todas las variables a sus valores predeterminados."""
    defaults = {
        "k": "20",
        "fx": "3.7",
        "p_token": "1.0",
        "g_default": "9",
        "h": "720",
        "hh_mult": "2",
        "min_uptime": "0.95",
        "min_fiabilidad": "0.95",
        "max_perfiles_pc": "50",
        "comision_marketplace": "0.05",
        "comision_retiro_0_30": "0.08",
        "comision_retiro_31_60": "0.06",
        "comision_retiro_61_90": "0.04",
        "comision_retiro_90_plus": "0.02",
        "comision_referido": "0.01",
        "limite_retiro_mensual_usd": "1000",
        "tasa_recoleccion_mensual": "0.02",
        "w_bronce": "1",
        "w_plata": "2",
        "w_oro": "3",
        "uptime_bronce": "0.90",
        "uptime_plata": "0.95",
        "uptime_oro": "0.99",
        "happy_hour_activo": "0",
        "beta": "0.5",
    }
    for clave, valor in defaults.items():
        ejecutar_sql(
            "insert or replace into variables (clave, valor) values (?, ?)",
            (clave, valor),
        )
    return {"exito": True, "mensaje": "variables restablecidas a valores predeterminados"}


# ---------------------------------------------------------------------------
# proyecciones
# ---------------------------------------------------------------------------
@router.get("/proyecciones")
async def api_proyecciones(sesion: dict = Depends(verificar_admin_dependencia)):
    """calcula escenarios de proyeccion a 3, 9 y 18 meses usando tokenomics."""
    from tokenomics import obtener_balance
    total_w = ejecutar_sql_unico("select sum(balance) as total from wallets")
    circulando = (total_w["total"] or 0) if total_w else 0
    total_u = ejecutar_sql_unico("select count(*) as total from usuarios")
    n_actual = total_u["total"] if total_u else 0
    variables = obtener_todas_variables()
    k = float(variables.get("k", 20))
    fx = float(variables.get("fx", 3.7))
    p_token = float(variables.get("p_token", 1))
    g = float(variables.get("g_default", 9))
    hh = float(variables.get("hh_mult", 2))
    h = float(variables.get("h", 720))
    escenarios = []
    for meses in [3, 9, 18]:
        factor = meses / 3
        n_est = n_actual * (1 + 0.5 * factor) if n_actual else 10 * (1 + 0.5 * factor)
        perf_est = n_est * 2
        tokens_emit = (perf_est * 0.72 * h * k) / p_token * meses
        circulante_est = circulando + tokens_emit * 0.7
        margen = tokens_emit * p_token * 0.15 / fx
        ganancia = tokens_emit * p_token * 0.40 / fx
        comisiones = tokens_emit * p_token * 0.10 / fx
        escenarios.append({
            "meses": meses,
            "usuarios_estimados": round(n_est),
            "perfiles_estimados": round(perf_est),
            "tokens_emitidos_periodo": f"{tokens_emit:,.2f}",
            "tokens_circulantes_est": f"{circulante_est:,.2f}",
            "margen_dueno": f"${margen:,.2f}",
            "ganancia_granjeros": f"${ganancia:,.2f}",
            "comisiones_est": f"${comisiones:,.2f}",
        })
    return {"exito": True, "escenarios": escenarios}


# ---------------------------------------------------------------------------
# happy hour
# ---------------------------------------------------------------------------
@router.post("/happy_hour/activar")
async def api_activar_hh(req: dict, sesion: dict = Depends(verificar_admin_dependencia)):
    """activa happy hour con multiplicador y fechas opcionales."""
    ejecutar_insercion(
        "insert into happy_hour (multiplicador, fecha_inicio, fecha_fin, activo) values (?, ?, ?, 1)",
        (req.get("multiplicador", 2.0), req.get("fecha_inicio", ""), req.get("fecha_fin", "")),
    )
    return {"exito": True, "mensaje": "happy hour activado"}


@router.post("/happy_hour/desactivar")
async def api_desactivar_hh(sesion: dict = Depends(verificar_admin_dependencia)):
    """desactiva todas las happy hour activas."""
    ejecutar_sql("update happy_hour set activo = 0 where activo = 1")
    return {"exito": True, "mensaje": "happy hour desactivado"}


@router.get("/happy_hour/historial")
async def api_historial_hh(sesion: dict = Depends(verificar_admin_dependencia)):
    """devuelve el historial de happy hours."""
    rows = ejecutar_sql("select * from happy_hour order by id desc limit 50")
    return {"exito": True, "historial": [dict(r) for r in rows]}


@router.get("/happy_hour")
async def api_estado_hh(sesion: dict = Depends(verificar_admin_dependencia)):
    """devuelve el estado actual y el historial de happy hour."""
    activa = ejecutar_sql_unico("select * from happy_hour where activo = 1 order by id desc limit 1")
    historial = ejecutar_sql("select * from happy_hour order by id desc limit 50")
    return {
        "exito": True,
        "happy_hour": dict(activa) if activa else None,
        "historial": [dict(r) for r in historial],
    }


# ---------------------------------------------------------------------------
# kpi general
# ---------------------------------------------------------------------------
@router.get("/kpi")
async def api_kpi(sesion: dict = Depends(verificar_admin_dependencia)):
    """devuelve el panel kpi general con todos los indicadores."""
    total_usuarios = ejecutar_sql_unico("select count(*) as total from usuarios")
    activos = ejecutar_sql_unico("select count(*) as total from usuarios where activo = 1")
    admins = ejecutar_sql_unico("select count(*) as total from usuarios where rol = 'admin'")
    total_wallets = ejecutar_sql_unico("select sum(balance) as total from wallets")
    total_minado = ejecutar_sql_unico("select sum(minado_total) as total from wallets")
    reserva = ejecutar_sql_unico("select * from reserva where id = 1")
    retiros_pend = ejecutar_sql_unico("select count(*) as total from retiros where estado = 'pendiente'")
    total_perfiles = ejecutar_sql_unico("select count(*) as total from perfiles")
    perfiles_activos = ejecutar_sql_unico("select count(*) as total from perfiles where estado = 'activo'")
    hh_activo = ejecutar_sql_unico("select * from happy_hour where activo = 1 order by id desc limit 1")
    from orchestrator import gestor_websockets
    pcbots_conectados = len(gestor_websockets)
    vol_24h = ejecutar_sql_unico(
        "select coalesce(sum(monto), 0) as total from transacciones "
        "where fecha >= datetime('now', '-1 day', 'localtime')"
    )
    return {
        "exito": True,
        "usuarios": {
            "total": total_usuarios["total"] if total_usuarios else 0,
            "activos": activos["total"] if activos else 0,
            "admin": admins["total"] if admins else 0,
        },
        "kbt": {
            "circulando": (total_wallets["total"] or 0) if total_wallets else 0,
            "total_minado": (total_minado["total"] or 0) if total_minado else 0,
            "reserva_tokens": reserva["tokens"] if reserva else 0,
            "reserva_soles": reserva["soles"] if reserva else 0,
        },
        "operaciones": {
            "retiros_pendientes": retiros_pend["total"] if retiros_pend else 0,
            "volumen_24h": vol_24h["total"] if vol_24h else 0,
        },
        "happy_hour": {
            "activo": hh_activo is not None,
            "multiplicador": hh_activo["multiplicador"] if hh_activo else 2.0,
        },
        "pcbots": {"conectados": pcbots_conectados},
        "perfiles": {
            "total": total_perfiles["total"] if total_perfiles else 0,
            "activos": perfiles_activos["total"] if perfiles_activos else 0,
        },
    }