# jarvis_core.py - nucleo del asistente jarvis. roxymaster v8.3
# utf-8 sin bom, nombres en minusculas, <= 400 lineas

import asyncio
import json
import time
import os
from datetime import datetime

# ---------------------------------------------------------------------------
# constantes
# ---------------------------------------------------------------------------
_jarvis_state = {
    "activo": False,
    "tarea_actual": None,       # dict con {id, tipo, parametros, progreso}
    "historial": [],            # list de dict con resultado de tareas
    "cola": [],                 # cola de tareas pendientes
    "modo": "standby",          # standby | procesando | pausa
    "ultima_actividad": None,
    "max_historial": 20,
}

_tiempo_maximo_por_tarea = 300  # 5 minutos
_intervalo_revision = 3          # segundos entre revisiones de cola


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _ahora_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ts() -> int:
    return int(time.time())


# ---------------------------------------------------------------------------
# registro de comandos que jarvis entiende (expandible)
# ---------------------------------------------------------------------------
_comandos_registrados = set()


def registrar_comando(tipo: str):
    """registra un tipo de comando que jarvis puede procesar."""
    _comandos_registrados.add(tipo)


def comando_registrado(tipo: str) -> bool:
    return tipo in _comandos_registrados


# registrar comandos base
registrar_comando("asignar")
registrar_comando("estado")
registrar_comando("detener")
registrar_comando("open_url")
registrar_comando("comentarios_activar")
registrar_comando("analizar")
registrar_comando("reportar")


# ---------------------------------------------------------------------------
# logica central de jarvis
# ---------------------------------------------------------------------------
async_tareas = None  # sera inyectado por server.py: {tipo: funcion async}


def inyectar_tareas(tareas: dict):
    """inyecta el dict de funciones async que resuelven cada tipo de comando."""
    global async_tareas
    async_tareas = tareas


async def iniciar_jarvis():
    """inicia el bucle principal de jarvis en segundo plano."""
    if _jarvis_state["activo"]:
        return {"exito": False, "error": "jarvis ya esta activo"}
    _jarvis_state["activo"] = True
    _jarvis_state["modo"] = "standby"
    _jarvis_state["ultima_actividad"] = _ahora_str()
    asyncio.create_task(_bucle_principal())
    return {"exito": True, "mensaje": "jarvis iniciado"}


async def detener_jarvis():
    """detiene el bucle principal de jarvis."""
    _jarvis_state["activo"] = False
    _jarvis_state["modo"] = "standby"
    _jarvis_state["tarea_actual"] = None
    return {"exito": True, "mensaje": "jarvis detenido"}


async def _bucle_principal():
    """bucle infinito que revisa la cola y procesa tareas."""
    while _jarvis_state["activo"]:
        if _jarvis_state["modo"] == "pausa":
            await asyncio.sleep(_intervalo_revision)
            continue

        # tomar siguiente tarea de la cola
        if _jarvis_state["cola"] and not _jarvis_state["tarea_actual"]:
            tarea = _jarvis_state["cola"].pop(0)
            _jarvis_state["tarea_actual"] = tarea
            _jarvis_state["modo"] = "procesando"
            asyncio.create_task(_ejecutar_tarea(tarea))

        await asyncio.sleep(_intervalo_revision)


async def _ejecutar_tarea(tarea: dict):
    """ejecuta una tarea con timeout."""
    tipo = tarea.get("tipo", "")
    parametros = tarea.get("parametros", {})
    tarea_id = tarea.get("id", str(_ts()))

    inicio = _ts()
    try:
        if async_tareas and tipo in async_tareas:
            resultado = await asyncio.wait_for(
                async_tareas[tipo](parametros),
                timeout=_tiempo_maximo_por_tarea,
            )
        elif tipo in _comandos_registrados:
            # placeholder para tipos sin handler
            resultado = {"exito": True, "mensaje": f"tarea '{tipo}' ejecutada (sin handler especifico)"}
            await asyncio.sleep(1)  # simular trabajo
        else:
            resultado = {"exito": False, "error": f"tipo '{tipo}' no registrado"}

        _registrar_resultado(tarea_id, tipo, parametros, resultado, "completado")

    except asyncio.TimeoutError:
        resultado = {"exito": False, "error": "timeout excedido"}
        _registrar_resultado(tarea_id, tipo, parametros, resultado, "timeout")
    except Exception as e:
        resultado = {"exito": False, "error": str(e)}
        _registrar_resultado(tarea_id, tipo, parametros, resultado, "error")
    finally:
        _jarvis_state["tarea_actual"] = None
        _jarvis_state["modo"] = "standby"
        _jarvis_state["ultima_actividad"] = _ahora_str()


def _registrar_resultado(tarea_id: str, tipo: str, parametros: dict, resultado: dict, estado: str = "completado"):
    """registra el resultado de una tarea en el historial."""
    entrada = {
        "id": tarea_id,
        "tipo": tipo,
        "parametros": parametros,
        "resultado": resultado,
        "estado": estado,
        "timestamp": _ahora_str(),
    }
    _jarvis_state["historial"].append(entrada)
    # mantener max_historial
    if len(_jarvis_state["historial"]) > _jarvis_state["max_historial"]:
        _jarvis_state["historial"] = _jarvis_state["historial"][-_jarvis_state["max_historial"]:]


# ---------------------------------------------------------------------------
# api publica para encolar tareas
# ---------------------------------------------------------------------------
async def encolar_tarea(tipo: str, parametros: dict = None) -> dict:
    """encola una tarea para que jarvis la procese."""
    if not _jarvis_state["activo"]:
        return {"exito": False, "error": "jarvis no esta activo"}

    if tipo not in _comandos_registrados:
        return {"exito": False, "error": f"tipo '{tipo}' no registrado en jarvis"}

    tarea = {
        "id": str(uuid_id()),
        "tipo": tipo,
        "parametros": parametros or {},
        "encolado": _ahora_str(),
    }
    _jarvis_state["cola"].append(tarea)
    return {"exito": True, "tarea_id": tarea["id"], "mensaje": f"tarea '{tipo}' encolada"}


def uuid_id() -> str:
    """genera un id corto unico."""
    import uuid
    return str(uuid.uuid4())[:12]


async def pausar_jarvis():
    """pausa el procesamiento de la cola."""
    _jarvis_state["modo"] = "pausa"
    return {"exito": True, "mensaje": "jarvis pausado"}


async def reanudar_jarvis():
    """reanuda el procesamiento de la cola."""
    _jarvis_state["modo"] = "standby"
    return {"exito": True, "mensaje": "jarvis reanudado"}


# ---------------------------------------------------------------------------
# consultar estado
# ---------------------------------------------------------------------------
def estado_jarvis() -> dict:
    """devuelve el estado actual de jarvis."""
    return {
        "activo": _jarvis_state["activo"],
        "modo": _jarvis_state["modo"],
        "tarea_actual": _jarvis_state["tarea_actual"],
        "cola_pendiente": len(_jarvis_state["cola"]),
        "historial_reciente": _jarvis_state["historial"][-5:],
        "ultima_actividad": _jarvis_state["ultima_actividad"],
    }


def limpiar_historial():
    """limpia el historial de tareas."""
    _jarvis_state["historial"] = []
    return {"exito": True, "mensaje": "historial limpiado"}


# ---------------------------------------------------------------------------
# reset completo
# ---------------------------------------------------------------------------
async def reset_jarvis():
    """resetea jarvis a estado inicial."""
    await detener_jarvis()
    _jarvis_state["cola"] = []
    _jarvis_state["historial"] = []
    _jarvis_state["tarea_actual"] = None
    return {"exito": True, "mensaje": "jarvis reseteado"}