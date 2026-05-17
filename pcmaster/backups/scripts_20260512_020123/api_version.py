# api_version.py - auto-actualizacion (version y actualizacion). roxymaster v8.3
# utf-8 sin bom, nombres en minusculas, <= 400 lineas

import json
import os
import subprocess
import sys
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config_loader import cargar_configuracion

router = APIRouter(prefix="/api/version", tags=["version"])

VERSION_ACTUAL = "8.3.0"
REPO_URL = "https://github.com/ROXYMASTER-PCMASTER/ROXYMASTER.git"


@router.get("/")
async def version_info():
    """devuelve informacion de la version actual."""
    return {
        "exito": True,
        "version": VERSION_ACTUAL,
        "repositorio": REPO_URL,
        "rama": "main",
        "ultima_actualizacion": _ultima_fecha_git(),
    }


@router.post("/verificar")
async def verificar_actualizacion():
    """verifica si hay una version mas reciente en el repositorio."""
    try:
        # hacer fetch ligero para ver cambios
        result = subprocess.run(
            ["git", "fetch", "--dry-run"],
            capture_output=True, text=True, timeout=10,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        hay_cambios = bool(result.stdout.strip())
        return {
            "exito": True,
            "hay_actualizacion": hay_cambios,
            "detalle": "cambios remotos detectados" if hay_cambios else "sin cambios remotos",
        }
    except Exception as e:
        return {"exito": False, "error": str(e)}


@router.post("/actualizar")
async def aplicar_actualizacion():
    """aplica git pull para actualizar al ultimo commit."""
    try:
        result = subprocess.run(
            ["git", "pull", "origin", "main"],
            capture_output=True, text=True, timeout=30,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        if result.returncode == 0:
            return {
                "exito": True,
                "mensaje": "actualizacion aplicada correctamente",
                "salida": result.stdout[:500],
            }
        else:
            return {
                "exito": False,
                "error": result.stderr[:500],
            }
    except subprocess.TimeoutExpired:
        return {"exito": False, "error": "tiempo de espera agotado al ejecutar git pull"}
    except Exception as e:
        return {"exito": False, "error": str(e)}


def _ultima_fecha_git() -> str:
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cd"],
            capture_output=True, text=True, timeout=5,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        return result.stdout.strip() if result.returncode == 0 else "desconocido"
    except Exception:
        return "desconocido"