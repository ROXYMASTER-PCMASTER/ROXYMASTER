# api_admin_config.py - configuracion del sistema para panel superadmin. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 300 lineas

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict as DictType

from api_auth import verificar_admin_dependencia
from db import ejecutar_sql, ejecutar_sql_unico

router = APIRouter(prefix="/api/admin", tags=["admin_config"])


# ---------------------------------------------------------------------------
# 1. obtener todas las variables de configuracion
# ---------------------------------------------------------------------------
@router.get("/config")
async def api_admin_obtener_config(
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """devuelve todas las variables de configuracion del sistema como objeto plano."""
    variables = ejecutar_sql("select clave, valor, descripcion, modificado_por, fecha_modificacion from config")
    config_obj = {}
    for v in variables:
        config_obj[v["clave"]] = v["valor"]
    return {"exito": True, "config": config_obj, "datos": variables}


# ---------------------------------------------------------------------------
# 2. actualizar variables de configuracion (batch - recibe dict completo)
# ---------------------------------------------------------------------------
class ActualizarConfigRequest(BaseModel):
    clave: str
    valor: str
    descripcion: Optional[str] = None


class ConfigUpdateRequest(BaseModel):
    config: dict = {}
    variables: dict = {}


@router.put("/config")
async def api_admin_actualizar_config(
    req: ConfigUpdateRequest,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """actualiza multiples variables de configuracion en una sola llamada.
    recibe un dict {clave: valor} y upsert cada una.
    acepta tanto config como variables (compatibilidad frontend admin.html)."""
    actualizadas = 0
    items = req.config if req.config else req.variables
    for clave, valor in items.items():
        existente = ejecutar_sql_unico("select clave from config where clave = ?", (clave,))
        if existente:
            ejecutar_sql(
                "update config set valor = ?, modificado_por = ?, fecha_modificacion = datetime('now','localtime') "
                "where clave = ?",
                (str(valor), sesion.get("email", "admin"), clave),
            )
        else:
            ejecutar_sql(
                "insert into config (clave, valor, descripcion, modificado_por, fecha_modificacion) "
                "values (?, ?, ?, ?, datetime('now','localtime'))",
                (clave, str(valor), "", sesion.get("email", "admin")),
            )
        actualizadas += 1

    return {"exito": True, "mensaje": f"{actualizadas} variables actualizadas", "actualizadas": actualizadas}


# ---------------------------------------------------------------------------
# 3. actualizar variable individual
# ---------------------------------------------------------------------------
@router.put("/config/{clave}")
async def api_admin_actualizar_config_item(
    clave: str,
    req: ActualizarConfigRequest,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """actualiza una variable de configuracion individual."""
    existente = ejecutar_sql_unico("select clave from config where clave = ?", (clave,))
    if not existente:
        raise HTTPException(status_code=404, detail="variable de configuracion no encontrada")

    ejecutar_sql(
        "update config set valor = ?, modificado_por = ?, fecha_modificacion = datetime('now','localtime') "
        "where clave = ?",
        (req.valor, sesion.get("email", "admin"), clave),
    )

    return {"exito": True, "mensaje": f"config {clave} actualizada a {req.valor}"}


# ---------------------------------------------------------------------------
# 4. restablecer configuracion a valores predeterminados
# ---------------------------------------------------------------------------
@router.post("/config/restablecer")
async def api_admin_restablecer_config(
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """restablece las variables de configuracion a sus valores por defecto."""
    defaults = {
        "intervalo_match": "30",
        "margen_anticipacion": "3",
        "perfiles_por_lote_normal": "1",
        "perfiles_por_lote_vip": "3",
        "timeout_reserva": "120",
        "max_pedidos_por_usuario": "5",
        "version_sistema": "8.3",
        "happy_hour_activo": "0",
        "happy_hour_inicio": "22:00",
        "happy_hour_fin": "06:00",
        "tasa_conversion_kbt": "1.0",
        "logger_nivel": "INFO",
    }
    actualizadas = 0
    for clave, valor in defaults.items():
        existente = ejecutar_sql_unico("select clave from config where clave = ?", (clave,))
        if existente:
            ejecutar_sql(
                "update config set valor = ?, modificado_por = ?, fecha_modificacion = datetime('now','localtime') "
                "where clave = ?",
                (valor, sesion.get("email", "admin"), clave),
            )
        else:
            ejecutar_sql(
                "insert into config (clave, valor, descripcion, modificado_por, fecha_modificacion) "
                "values (?, ?, ?, ?, datetime('now','localtime'))",
                (clave, valor, "", sesion.get("email", "admin")),
            )
        actualizadas += 1

    return {"exito": True, "mensaje": f"{actualizadas} variables restablecidas a valores por defecto"}