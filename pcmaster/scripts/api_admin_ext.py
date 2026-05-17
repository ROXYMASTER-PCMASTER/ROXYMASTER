# api_admin_ext.py - parte extendida del modulo api_admin.
# endpoints para gestion de variables globales por el administrador.
# roxymaster v8.3 - utf-8 sin bom, nombres en minusculas, <= 400 lineas

import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Request

from db import ejecutar_sql, ejecutar_sql_unico
from auth import verificar_admin_dependencia
from variables_globales import (
    obtener_variables,
    actualizar_variable,
    restablecer_variables_predeterminadas,
    parametros_kbt_predeterminados,
)

logger = logging.getLogger("roxymaster.api_admin_ext")

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# get /api/admin/variables_globales
# ---------------------------------------------------------------------------
@router.get("/variables_globales")
async def get_variables_globales(admin: dict = Depends(verificar_admin_dependencia)):
    """devuelve todas las variables globales del sistema."""
    variables = obtener_variables()
    return {
        "exito": True,
        "variables": variables,
    }


# ---------------------------------------------------------------------------
# put /api/admin/variables_globales
# ---------------------------------------------------------------------------
@router.put("/variables_globales")
async def update_variables_globales(request: Request,
                                    admin: dict = Depends(verificar_admin_dependencia)):
    """actualiza una variable global. body: {clave: valor}"""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="cuerpo invalido")

    resultados = []
    errores = []

    for clave, valor in body.items():
        ok = actualizar_variable(clave, valor)
        if ok:
            resultados.append({"clave": clave, "valor": valor, "exito": True})
            logger.info(f"variable global actualizada: {clave}={valor} por admin {admin['usuario_id']}")
        else:
            errores.append({"clave": clave, "error": "no se pudo actualizar"})

    return {
        "exito": len(errores) == 0,
        "actualizadas": resultados,
        "errores": errores if errores else None,
    }


# ---------------------------------------------------------------------------
# post /api/admin/variables_globales/restablecer
# ---------------------------------------------------------------------------
@router.post("/variables_globales/restablecer")
async def restablecer_variables(admin: dict = Depends(verificar_admin_dependencia)):
    """restablece todas las variables a sus valores predeterminados."""
    ok = restablecer_variables_predeterminadas()
    if not ok:
        raise HTTPException(status_code=500, detail="error al restablecer variables")
    logger.info(f"variables restablecidas por admin {admin['usuario_id']}")
    return {
        "exito": True,
        "mensaje": "variables restablecidas a valores predeterminados",
    }


# ---------------------------------------------------------------------------
# get /api/admin/variables_globales/{clave}
# ---------------------------------------------------------------------------
@router.get("/variables_globales/{clave}")
async def get_variable(clave: str, admin: dict = Depends(verificar_admin_dependencia)):
    """devuelve el valor de una variable global especifica."""
    variables = obtener_variables()
    if clave not in variables:
        raise HTTPException(status_code=404, detail=f"variable '{clave}' no encontrada")
    return {
        "exito": True,
        "clave": clave,
        "valor": variables[clave],
    }
