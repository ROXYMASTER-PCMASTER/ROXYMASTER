# api_computadoras.py - endpoints de computadoras y vinculacion. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

import json
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, WebSocket
from db import ejecutar_sql, ejecutar_sql_unico, ejecutar_insercion, get_db_context
from auth import verificar_token_opcional, obtener_usuario_desde_request
from pydantic import BaseModel

router = APIRouter(prefix="/api/computadoras", tags=["computadoras"])


# ---------------------------------------------------------------------------
# modelos
# ---------------------------------------------------------------------------
class ComputadoraRegistro(BaseModel):
    pcbot_id: str
    hostname: str = ""
    ip_wan: str = ""
    ip_local: str = ""
    mac: str = ""
    sistema_operativo: str = ""
    pais: str = ""


class ComputadoraVincular(BaseModel):
    pcbot_id: str


class ApiKeyRoxyInput(BaseModel):
    api_key: str
    workspace_id: str = ""
    computadora_id: int = None


class ApiKeyRoxyUpdate(BaseModel):
    api_key: str = None
    workspace_id: str = None
    estado: str = None


# ---------------------------------------------------------------------------
# endpoint publico: registrar computadora (sin autenticacion, llamado por pcbot al iniciar)
# ---------------------------------------------------------------------------
@router.post("/registrar")
async def registrar_computadora(data: ComputadoraRegistro, request: Request = None):
    """
    endpoint publico llamado por el pcbot al iniciar por primera vez.
    registra la computadora y devuelve un codigo de vinculacion.
    """
    # verificar si ya existe
    existente = ejecutar_sql_unico(
        "select id, pcbot_id, usuario_id, estado from computadoras where pcbot_id = ?",
        (data.pcbot_id,),
    )
    if existente:
        if existente.get("usuario_id"):
            return {
                "exito": True,
                "computadora_id": existente["id"],
                "titular": existente["usuario_id"],
                "mensaje": "computadora ya registrada y vinculada",
                "estado": existente["estado"],
            }
        return {
            "exito": True,
            "computadora_id": existente["id"],
            "mensaje": "computadora ya registrada, pendiente de vinculacion",
            "codigo_vinculacion": _get_codigo_vinculacion(data.pcbot_id),
            "estado": existente["estado"],
        }

    # registrar nueva computadora
    id_comp = ejecutar_insercion(
        """insert into computadoras
           (pcbot_id, hostname, ip_wan, ip_local, mac, sistema_operativo, pais, estado)
           values (?, ?, ?, ?, ?, ?, ?, 'pendiente')""",
        (
            data.pcbot_id,
            data.hostname,
            data.ip_wan,
            data.ip_local,
            data.mac,
            data.sistema_operativo,
            data.pais,
        ),
    )

    if not id_comp:
        raise HTTPException(status_code=500, detail="error al registrar computadora")

    return {
        "exito": True,
        "computadora_id": id_comp,
        "mensaje": "computadora registrada, pendiente de vinculacion",
        "codigo_vinculacion": _generar_codigo_vinculacion(data.pcbot_id),
        "estado": "pendiente",
    }


def _generar_codigo_vinculacion(pcbot_id: str) -> str:
    """genera un codigo de 6 caracteres para vincular la computadora a un usuario."""
    codigo = uuid.uuid4().hex[:6].upper()
    # persistir codigo en variables_globales para validacion posterior
    ejecutar_sql(
        "insert or replace into variables_globales (clave, valor) values (?, ?)",
        (f"codigo_vinculacion_{pcbot_id}", codigo),
    )
    return codigo


def _get_codigo_vinculacion(pcbot_id: str) -> str:
    """obtiene el codigo de vinculacion existente."""
    row = ejecutar_sql_unico(
        "select valor from variables_globales where clave = ?",
        (f"codigo_vinculacion_{pcbot_id}",),
    )
    return row["valor"] if row else ""


# rutas dinámicas: ubicacion del codigo de vinculacion
RUTA_CODIGO_VINCULACION = _generar_codigo_vinculacion("_template_").replace(
    "_template_", ""
)


# ---------------------------------------------------------------------------
# endpoint autenticado: vincular computadora al usuario logueado
# ---------------------------------------------------------------------------
@router.post("/vincular")
async def vincular_computadora(data: ComputadoraVincular, request: Request = None):
    """vincula una computadora registrada al usuario autenticado."""
    usuario = await obtener_usuario_desde_request(request)
    if not usuario:
        raise HTTPException(status_code=401, detail="no autenticado")

    usuario_id = usuario["id"]

    # verificar que la computadora existe
    comp = ejecutar_sql_unico(
        "select id, pcbot_id, estado, usuario_id from computadoras where pcbot_id = ?",
        (data.pcbot_id,),
    )
    if not comp:
        raise HTTPException(status_code=404, detail="computadora no encontrada")

    if comp.get("usuario_id"):
        if comp["usuario_id"] == usuario_id:
            return {"exito": True, "mensaje": "computadora ya vinculada a tu cuenta"}
        raise HTTPException(
            status_code=409,
            detail="computadora ya vinculada a otro usuario",
        )

    # vincular
    ahora = datetime.now().isoformat()
    ejecutar_sql(
        """update computadoras set
           usuario_id = ?, estado = 'activo', fecha_vinculacion = ?
           where pcbot_id = ?""",
        (usuario_id, ahora, data.pcbot_id),
    )

    # si el usuario tiene pcbot_id null, asignarlo
    user = ejecutar_sql_unico(
        "select pcbot_id from usuarios where id = ?", (usuario_id,)
    )
    if user and not user.get("pcbot_id"):
        ejecutar_sql(
            "update usuarios set pcbot_id = ? where id = ?",
            (data.pcbot_id, usuario_id),
        )

    # eliminar codigo de vinculacion usado
    ejecutar_sql(
        "delete from variables_globales where clave = ?",
        (f"codigo_vinculacion_{data.pcbot_id}",),
    )

    return {
        "exito": True,
        "mensaje": "computadora vinculada exitosamente",
        "computadora_id": comp["id"],
    }


# ---------------------------------------------------------------------------
# endpoint autenticado: listar computadoras del usuario
# ---------------------------------------------------------------------------
@router.get("/mis-computadoras")
async def mis_computadoras(request: Request = None):
    """lista todas las computadoras vinculadas al usuario autenticado."""
    usuario = await obtener_usuario_desde_request(request)
    if not usuario:
        raise HTTPException(status_code=401, detail="no autenticado")

    usuario_id = usuario["id"]
    computadoras = ejecutar_sql(
        """select id, pcbot_id, hostname, ip_wan, ip_local, mac, sistema_operativo,
                  pais, api_key_roxy, workspace_id, estado, instalado_el,
                  ultimo_heartbeat, ultima_conexion, fecha_vinculacion
           from computadoras
           where usuario_id = ?
           order by instalado_el desc""",
        (usuario_id,),
    )

    return {"exito": True, "computadoras": computadoras}


# ---------------------------------------------------------------------------
# endpoint autenticado: detalle de una computadora
# ---------------------------------------------------------------------------
@router.get("/{computadora_id}")
async def detalle_computadora(computadora_id: int, request: Request = None):
    """detalle de una computadora especifica."""
    usuario = await obtener_usuario_desde_request(request)
    if not usuario:
        raise HTTPException(status_code=401, detail="no autenticado")

    comp = ejecutar_sql_unico(
        """select c.*, 
                  (select count(*) from apikeys_roxybrowser a where a.computadora_id = c.id) as total_apikeys,
                  (select count(*) from perfiles_roxy_ext p where p.computadora_id = c.id) as total_perfiles
           from computadoras c
           where c.id = ? and c.usuario_id = ?""",
        (computadora_id, usuario["id"]),
    )

    if not comp:
        raise HTTPException(status_code=404, detail="computadora no encontrada")

    # obtener apikeys y perfiles de esta computadora
    apikeys = ejecutar_sql(
        "select * from apikeys_roxybrowser where computadora_id = ?",
        (computadora_id,),
    )
    perfiles = ejecutar_sql(
        "select * from perfiles_roxy_ext where computadora_id = ?",
        (computadora_id,),
    )

    comp["apikeys"] = apikeys
    comp["perfiles_ext"] = perfiles

    return {"exito": True, "computadora": comp}


# ---------------------------------------------------------------------------
# endpoint autenticado: agregar api key de roxybrowser a una computadora
# ---------------------------------------------------------------------------
@router.post("/{computadora_id}/api-keys")
async def agregar_api_key(
    computadora_id: int, data: ApiKeyRoxyInput, request: Request = None
):
    """agrega una api key de roxybrowser a una computadora."""
    usuario = await obtener_usuario_desde_request(request)
    if not usuario:
        raise HTTPException(status_code=401, detail="no autenticado")
    usuario_id = usuario["id"]

    # verificar computadora
    comp = ejecutar_sql_unico(
        "select id, pcbot_id from computadoras where id = ? and usuario_id = ?",
        (computadora_id, usuario_id),
    )
    if not comp:
        raise HTTPException(status_code=404, detail="computadora no encontrada")

    # verificar que no exista la misma api_key
    existente = ejecutar_sql_unico(
        "select id from apikeys_roxybrowser where api_key = ?",
        (data.api_key,),
    )
    if existente:
        raise HTTPException(status_code=409, detail="api key ya registrada")

    ahora = datetime.now().isoformat()
    vencimiento = (datetime.now() + timedelta(days=365)).isoformat()

    apikey_id = ejecutar_insercion(
        """insert into apikeys_roxybrowser
           (usuario_id, computadora_id, api_key, workspace_id, estado, fecha_agregada, fecha_vencimiento)
           values (?, ?, ?, ?, 'activa', ?, ?)""",
        (usuario_id, computadora_id, data.api_key, data.workspace_id, ahora, vencimiento),
    )

    # sincronizar api_key a la computadora
    ejecutar_sql(
        "update computadoras set api_key_roxy = ?, workspace_id = ? where id = ?",
        (data.api_key, data.workspace_id, computadora_id),
    )

    # notificar via websocket si el pcbot esta conectado
    try:
        from ws_manager import enviar_a_pcbot
        pcbot_id = comp["pcbot_id"]
        await enviar_a_pcbot(
            pcbot_id,
            {
                "tipo": "api_key_actualizada",
                "api_key": data.api_key,
                "workspace_id": data.workspace_id,
            },
        )
    except Exception:
        pass  # si no hay ws, no importa

    return {
        "exito": True,
        "apikey_id": apikey_id,
        "mensaje": "api key agregada correctamente",
    }


# ---------------------------------------------------------------------------
# endpoint autenticado: listar api keys de una computadora
# ---------------------------------------------------------------------------
@router.get("/{computadora_id}/api-keys")
async def listar_api_keys(computadora_id: int, request: Request = None):
    """lista las api keys de roxybrowser de una computadora."""
    usuario = await obtener_usuario_desde_request(request)
    if not usuario:
        raise HTTPException(status_code=401, detail="no autenticado")

    comp = ejecutar_sql_unico(
        "select id from computadoras where id = ? and usuario_id = ?",
        (computadora_id, usuario["id"]),
    )
    if not comp:
        raise HTTPException(status_code=404, detail="computadora no encontrada")

    apikeys = ejecutar_sql(
        "select * from apikeys_roxybrowser where computadora_id = ? order by fecha_agregada desc",
        (computadora_id,),
    )

    return {"exito": True, "api_keys": apikeys}


# ---------------------------------------------------------------------------
# endpoint autenticado: actualizar api key (desactivar, cambiar key, etc)
# ---------------------------------------------------------------------------
@router.put("/{computadora_id}/api-keys/{apikey_id}")
async def actualizar_api_key(
    computadora_id: int,
    apikey_id: int,
    data: ApiKeyRoxyUpdate,
    request: Request = None,
):
    """actualiza una api key (desactivar, cambiar workspace, etc)."""
    usuario = await obtener_usuario_desde_request(request)
    if not usuario:
        raise HTTPException(status_code=401, detail="no autenticado")

    apikey = ejecutar_sql_unico(
        "select * from apikeys_roxybrowser where id = ? and computadora_id = ? and usuario_id = ?",
        (apikey_id, computadora_id, usuario["id"]),
    )
    if not apikey:
        raise HTTPException(status_code=404, detail="api key no encontrada")

    updates = []
    params = []
    if data.api_key is not None:
        updates.append("api_key = ?")
        params.append(data.api_key)
    if data.workspace_id is not None:
        updates.append("workspace_id = ?")
        params.append(data.workspace_id)
    if data.estado is not None:
        updates.append("estado = ?")
        params.append(data.estado)

    if updates:
        params.append(apikey_id)
        ejecutar_sql(
            f"update apikeys_roxybrowser set {', '.join(updates)} where id = ?",
            tuple(params),
        )

    return {"exito": True, "mensaje": "api key actualizada"}


# ---------------------------------------------------------------------------
# endpoint autenticado: eliminar computadora (desvincular)
# ---------------------------------------------------------------------------
@router.delete("/{computadora_id}")
async def eliminar_computadora(computadora_id: int, request: Request = None):
    """desvincula una computadora del usuario."""
    usuario = await obtener_usuario_desde_request(request)
    if not usuario:
        raise HTTPException(status_code=401, detail="no autenticado")

    comp = ejecutar_sql_unico(
        "select id, pcbot_id from computadoras where id = ? and usuario_id = ?",
        (computadora_id, usuario["id"]),
    )
    if not comp:
        raise HTTPException(status_code=404, detail="computadora no encontrada")

    # eliminar apikeys y perfiles asociados
    ejecutar_sql("delete from perfiles_roxy_ext where computadora_id = ?", (computadora_id,))
    ejecutar_sql("delete from apikeys_roxybrowser where computadora_id = ?", (computadora_id,))
    ejecutar_sql("delete from computadoras where id = ?", (computadora_id,))

    return {"exito": True, "mensaje": "computadora eliminada"}


# ---------------------------------------------------------------------------
# endpoint publico: verificar codigo de vinculacion (usado por dashboard)
# ---------------------------------------------------------------------------
@router.get("/verificar-codigo/{codigo}")
async def verificar_codigo(codigo: str):
    """verifica si un codigo de vinculacion es valido y devuelve el pcbot_id."""
    # buscar codigo en variables_globales
    rows = ejecutar_sql(
        "select clave, valor from variables_globales where clave like 'codigo_vinculacion_%' and valor = ?",
        (codigo.upper(),),
    )
    for row in rows:
        pcbot_id = row["clave"].replace("codigo_vinculacion_", "")
        computadora = ejecutar_sql_unico(
            "select id, pcbot_id, hostname, estado from computadoras where pcbot_id = ?",
            (pcbot_id,),
        )
        if computadora and not computadora.get("usuario_id"):
            return {
                "exito": True,
                "codigo": codigo,
                "pcbot_id": pcbot_id,
                "computadora_id": computadora["id"],
                "hostname": computadora.get("hostname", ""),
            }

    return {"exito": False, "error": "codigo invalido o computadora ya vinculada"}