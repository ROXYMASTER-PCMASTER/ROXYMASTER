# api_admin_ext.py - endpoints admin con rutas exactas del listado. roxymaster v8.3
# utf-8 sin bom, todo en minusculas, <= 400 lineas
# provee aliases para rutas exactas: GET /api/admin/variables, POST /api/admin/kbt/emitir, etc.

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from api_auth import verificar_admin_dependencia
from db import ejecutar_sql, ejecutar_sql_unico
from tokenomics import emitir_kbt_admin
from variables_globales import restablecer_variables_predeterminadas, obtener_variables, actualizar_variable

router = APIRouter(prefix="/api/admin", tags=["admin_ext"])


# ---------------------------------------------------------------------------
# modelos pydantic
# ---------------------------------------------------------------------------
class EmitirKbtRequest(BaseModel):
    usuario_id: int
    cantidad: float
    concepto: str = "emision_admin"


class VariableUpdateRequest(BaseModel):
    valor: str


# ---------------------------------------------------------------------------
# 1. GET /api/admin/variables - listar todas las variables economicas
# ---------------------------------------------------------------------------
@router.get("/variables")
async def api_admin_listar_variables(
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """lista todas las variables economicas del sistema (ruta exacta /api/admin/variables)."""
    filas = ejecutar_sql("select clave, valor from variables_globales order by clave")
    variables = {}
    for f in filas:
        variables[f["clave"]] = f["valor"]
    return {"exito": True, "variables": variables}


# ---------------------------------------------------------------------------
# 2. PUT /api/admin/variables/{clave} - actualizar una variable
# ---------------------------------------------------------------------------
@router.put("/variables/{clave}")
async def api_admin_actualizar_variable(
    clave: str,
    req: VariableUpdateRequest,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """actualiza el valor de una variable economica."""
    existente = ejecutar_sql_unico(
        "select clave from variables_globales where clave = ?", (clave,)
    )
    if not existente:
        raise HTTPException(status_code=404, detail="variable no encontrada")
    actualizar_variable(clave, req.valor)
    return {"exito": True, "clave": clave, "nuevo_valor": req.valor}


# ---------------------------------------------------------------------------
# 3. POST /api/admin/kbt/emitir - emitir kbt administrativamente
# ---------------------------------------------------------------------------
@router.post("/kbt/emitir")
async def api_admin_emitir_kbt(
    req: EmitirKbtRequest,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """emite kbt a un usuario especifico (ruta exacta /api/admin/kbt/emitir)."""
    resultado = emitir_kbt_admin(req.usuario_id, req.cantidad, req.concepto)
    if not resultado.get("exito"):
        raise HTTPException(status_code=400, detail=resultado.get("error", "error al emitir"))
    return {"exito": True, "resultado": resultado}


# ---------------------------------------------------------------------------
# 4. GET /api/admin/estadisticas_globales - resumen publico para admin
# ---------------------------------------------------------------------------
@router.get("/estadisticas_globales")
async def api_admin_estadisticas_globales(
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """resumen global: usuarios activos, kbt minados, reserva actual, etc."""
    total_usuarios = ejecutar_sql_unico("select count(*) as c from usuarios")["c"]
    usuarios_activos = ejecutar_sql_unico("select count(*) as c from usuarios where activo = 1")["c"]
    tokens_circulando = ejecutar_sql_unico("select coalesce(sum(balance), 0) as c from wallets")["c"]
    total_minado = ejecutar_sql_unico(
        "select coalesce(sum(monto), 0) as c from transacciones where tipo = 'minado'"
    )["c"]
    reserva = ejecutar_sql_unico("select * from reserva where id = 1")
    return {
        "exito": True,
        "total_usuarios": total_usuarios,
        "usuarios_activos": usuarios_activos,
        "tokens_circulando": round(tokens_circulando, 4),
        "total_minado": round(total_minado, 4),
        "reserva_tokens": round(reserva["tokens"], 4) if reserva else 0,
        "reserva_soles": round(reserva["soles"], 4) if reserva else 0,
    }


# ---------------------------------------------------------------------------
# 5. GET /api/admin/retiros - listar retiros pendientes
# ---------------------------------------------------------------------------
@router.get("/retiros")
async def api_admin_listar_retiros(
    estado: Optional[str] = None,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """lista retiros con filtro opcional por estado."""
    if estado:
        filas = ejecutar_sql(
            "select r.*, u.email, u.username from retiros r "
            "join usuarios u on r.usuario_id = u.id "
            "where r.estado = ? order by r.fecha_solicitud desc",
            (estado,),
        )
    else:
        filas = ejecutar_sql(
            "select r.*, u.email, u.username from retiros r "
            "join usuarios u on r.usuario_id = u.id "
            "order by r.fecha_solicitud desc"
        )
    return {"exito": True, "retiros": [dict(f) for f in filas], "total": len(filas)}


# ---------------------------------------------------------------------------
# 6. GET /api/admin/transacciones - historial de transacciones
# ---------------------------------------------------------------------------
@router.get("/transacciones")
async def api_admin_listar_transacciones(
    tipo: Optional[str] = None,
    limite: int = 100,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """lista transacciones del sistema con filtro opcional por tipo."""
    if tipo:
        filas = ejecutar_sql(
            "select t.*, o.email as origen_email, d.email as destino_email "
            "from transacciones t "
            "left join usuarios o on t.origen_id = o.id "
            "left join usuarios d on t.destino_id = d.id "
            "where t.tipo = ? order by t.fecha desc limit ?",
            (tipo, limite),
        )
    else:
        filas = ejecutar_sql(
            "select t.*, o.email as origen_email, d.email as destino_email "
            "from transacciones t "
            "left join usuarios o on t.origen_id = o.id "
            "left join usuarios d on t.destino_id = d.id "
            "order by t.fecha desc limit ?",
            (limite,),
        )
    return {"exito": True, "transacciones": [dict(f) for f in filas], "total": len(filas)}


# ---------------------------------------------------------------------------
# 7. GET /api/admin/reserva - estado de la reserva
# ---------------------------------------------------------------------------
@router.get("/reserva")
async def api_admin_ver_reserva(
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """devuelve el estado actual de la reserva."""
    reserva = ejecutar_sql_unico("select * from reserva where id = 1")
    if not reserva:
        return {"exito": True, "reserva": {"tokens": 0, "soles": 0}}
    return {"exito": True, "reserva": dict(reserva)}


# fin api_admin_ext.py