# api_tokenomics.py - router fastapi para panel de tokenomia editable. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from api_auth import verificar_admin_dependencia, verificar_token_dependencia
from db import ejecutar_sql, ejecutar_sql_unico, ejecutar_insercion
from tokenomics import (
    emitir_kbt_admin,
    iniciar_happy_hour,
    hh_activo,
    estado_reserva,
    generar_proyecciones,
    verificar_liberacion_genesis,
    calcular_recompensa_granjero,
)

router = APIRouter(prefix="/api/admin/tokenomics", tags=["admin_tokenomics"])


# ---------------------------------------------------------------------------
# modelos pydantic
# ---------------------------------------------------------------------------
class VariablesUpdateRequest(BaseModel):
    clave: str
    valor: str


class GenesisLiberarRequest(BaseModel):
    id: int


class HappyHourCrearRequest(BaseModel):
    multiplicador: float = 2.0
    duracion_horas: int = 2


class EmitirKbtRequest(BaseModel):
    usuario_id: int
    cantidad: float
    concepto: str = "emision_admin"


# ---------------------------------------------------------------------------
# endpoint: listar todas las variables economicas
# ---------------------------------------------------------------------------
@router.get("/variables")
async def api_listar_variables(sesion: dict = Depends(verificar_admin_dependencia)):
    """lista todas las variables economicas del sistema."""
    filas = ejecutar_sql("select clave, valor from variables_globales order by clave")
    variables = {}
    for f in filas:
        variables[f["clave"]] = f["valor"]
    return {"exito": True, "variables": variables}


# ---------------------------------------------------------------------------
# endpoint: actualizar una variable economica
# ---------------------------------------------------------------------------
@router.put("/variables/{clave}")
async def api_actualizar_variable(
    clave: str,
    req: VariablesUpdateRequest,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """actualiza el valor de una variable economica."""
    existente = ejecutar_sql_unico(
        "select clave from variables_globales where clave = ?", (clave,)
    )
    if not existente:
        raise HTTPException(status_code=404, detail="variable no encontrada")

    ejecutar_sql(
        "update variables_globales set valor = ? where clave = ?",
        (req.valor, clave),
    )
    return {"exito": True, "clave": clave, "nuevo_valor": req.valor}


# ---------------------------------------------------------------------------
# endpoint: listar variables por grupos (comisiones, economicas, etc)
# ---------------------------------------------------------------------------
@router.get("/variables/grupo/{grupo}")
async def api_variables_por_grupo(
    grupo: str,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """filtra variables por grupo: economicas, comisiones, limites."""
    prefijos = {
        "economicas": ["K", "FX", "P_token", "G", "H", "E", "HH_mult", "beta"],
        "comisiones": ["comision_"],
        "limites": ["limite_", "banda_"],
        "genesis": ["tokens_", "mes_"],
    }
    prefijo = prefijos.get(grupo, [])

    filas = ejecutar_sql("select clave, valor from variables_globales order by clave")
    resultado = {}
    for f in filas:
        if isinstance(prefijo, list):
            if any(f["clave"] == p or f["clave"].startswith(p) for p in prefijo):
                resultado[f["clave"]] = f["valor"]
        else:
            if f["clave"].startswith(prefijo):
                resultado[f["clave"]] = f["valor"]
    return {"exito": True, "grupo": grupo, "variables": resultado}


# ---------------------------------------------------------------------------
# endpoint: estado de genesis
# ---------------------------------------------------------------------------
@router.get("/genesis")
async def api_listar_genesis(sesion: dict = Depends(verificar_admin_dependencia)):
    """lista todas las etapas de genesis."""
    filas = ejecutar_sql("select * from genesis order by id")
    return {"exito": True, "etapas": [dict(f) for f in filas]}


# ---------------------------------------------------------------------------
# endpoint: liberar etapa genesis manualmente
# ---------------------------------------------------------------------------
@router.put("/genesis/{genesis_id}/liberar")
async def api_liberar_genesis(
    genesis_id: int,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """libera una etapa genesis manualmente."""
    etapa = ejecutar_sql_unico(
        "select * from genesis where id = ?", (genesis_id,)
    )
    if not etapa:
        raise HTTPException(status_code=404, detail="etapa genesis no encontrada")
    if etapa["liberado"]:
        return {"exito": True, "mensaje": "etapa ya liberada anteriormente"}

    ejecutar_sql("update genesis set liberado = 1 where id = ?", (genesis_id,))
    ejecutar_sql("update reserva set tokens = tokens + ? where id = 1", (etapa["tokens"],))
    return {
        "exito": True,
        "mensaje": f"etapa {genesis_id} liberada: {etapa['tokens']} kbt",
        "etapa": dict(etapa),
    }


# ---------------------------------------------------------------------------
# endpoint: happy hour - estado actual
# ---------------------------------------------------------------------------
@router.get("/happyhour")
async def api_estado_happy_hour(sesion: dict = Depends(verificar_admin_dependencia)):
    """devuelve el estado actual del happy hour e historial."""
    activo = hh_activo()
    historial = ejecutar_sql(
        "select * from happy_hour order by id desc limit 20"
    )
    return {
        "exito": True,
        "activo": dict(activo) if activo else None,
        "historial": [dict(h) for h in historial],
    }


# ---------------------------------------------------------------------------
# endpoint: iniciar happy hour
# ---------------------------------------------------------------------------
@router.post("/happyhour")
async def api_iniciar_happy_hour(
    req: HappyHourCrearRequest,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """inicia un happy hour."""
    resultado = iniciar_happy_hour(req.multiplicador, req.duracion_horas)
    return {"exito": True, "happy_hour": resultado}


# ---------------------------------------------------------------------------
# endpoint: cancelar happy hour
# ---------------------------------------------------------------------------
@router.delete("/happyhour/{hh_id}")
async def api_cancelar_happy_hour(
    hh_id: int,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """cancela un happy hour activo."""
    hh = ejecutar_sql_unico(
        "select * from happy_hour where id = ? and activo = 1", (hh_id,)
    )
    if not hh:
        raise HTTPException(status_code=404, detail="happy hour no encontrado o ya inactivo")
    ejecutar_sql(
        "update happy_hour set activo = 0 where id = ?", (hh_id,)
    )
    return {"exito": True, "mensaje": f"happy hour #{hh_id} cancelado"}


# ---------------------------------------------------------------------------
# endpoint: emitir kbt admin
# ---------------------------------------------------------------------------
@router.post("/emitir")
async def api_emitir_kbt(
    req: EmitirKbtRequest,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """emite kbt administrativamente a un usuario."""
    resultado = emitir_kbt_admin(req.usuario_id, req.cantidad, req.concepto)
    if not resultado.get("exito"):
        raise HTTPException(status_code=400, detail=resultado.get("error", "error al emitir"))
    return {"exito": True, "resultado": resultado}


# ---------------------------------------------------------------------------
# endpoint: estado de reserva
# ---------------------------------------------------------------------------
@router.get("/reserva")
async def api_estado_reserva(sesion: dict = Depends(verificar_admin_dependencia)):
    """devuelve el estado del fondo de reserva."""
    reserva = estado_reserva()
    return {"exito": True, "reserva": reserva}


# ---------------------------------------------------------------------------
# endpoint: estadisticas globales de staking
# ---------------------------------------------------------------------------
@router.get("/staking")
async def api_staking_global(sesion: dict = Depends(verificar_admin_dependencia)):
    """devuelve estadisticas globales de staking."""
    total_staking = ejecutar_sql_unico(
        "select coalesce(sum(staking_total), 0) as total from wallets"
    )
    usuarios_staking = ejecutar_sql_unico(
        "select count(*) as total from wallets where staking_total > 0"
    )
    recompensas_totales = ejecutar_sql_unico(
        "select coalesce(sum(monto), 0) as total from transacciones where tipo = 'staking_reward'"
    )
    return {
        "exito": True,
        "total_staking": round(total_staking["total"], 2),
        "usuarios_staking": usuarios_staking["total"] if usuarios_staking else 0,
        "recompensas_totales": round(recompensas_totales["total"], 2),
    }


# ---------------------------------------------------------------------------
# endpoint: proyecciones economicas
# ---------------------------------------------------------------------------
@router.get("/proyecciones")
async def api_proyecciones(sesion: dict = Depends(verificar_admin_dependencia)):
    """genera proyecciones economicas a 3, 9 y 18 meses."""
    proyecciones = generar_proyecciones()
    return {"exito": True, "proyecciones": proyecciones}


# ---------------------------------------------------------------------------
# endpoint: estadisticas kbt globales detalladas
# ---------------------------------------------------------------------------
@router.get("/estadisticas")
async def api_estadisticas_kbt(sesion: dict = Depends(verificar_admin_dependencia)):
    """devuelve estadisticas detalladas del ecosistema kbt."""
    from tokenomics import estadisticas_kbt as obtener_estadisticas_kbt
    stats = obtener_estadisticas_kbt()
    return {"exito": True, "estadisticas": stats}


# ---------------------------------------------------------------------------
# endpoint: calcular recompensa simulada para debug
# ---------------------------------------------------------------------------
class SimularRecompensaRequest(BaseModel):
    usuario_id: int
    horas_normales: float = 1.0
    horas_hh: float = 0.0


@router.post("/simular_recompensa")
async def api_simular_recompensa(
    req: SimularRecompensaRequest,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """simula el calculo de recompensa para debugging."""
    resultado = calcular_recompensa_granjero(
        req.usuario_id, req.horas_normales, req.horas_hh
    )
    return {"exito": True, "simulacion": resultado}


# ---------------------------------------------------------------------------
# endpoint: listar tablas de la base de datos
# ---------------------------------------------------------------------------
@router.get("/esquema")
async def api_esquema_db(sesion: dict = Depends(verificar_admin_dependencia)):
    """lista las tablas disponibles en la base de datos."""
    tablas = ejecutar_sql("select name from sqlite_master where type='table' order by name")
    return {
        "exito": True,
        "tablas": [t["name"] for t in tablas],
    }