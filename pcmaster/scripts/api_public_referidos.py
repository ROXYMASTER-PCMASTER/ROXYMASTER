# api_public_referidos.py - endpoints de referidos y codigos para dashboard publico
# roxymaster v8.3 - todo en minusculas, utf-8 sin bom, <= 400 lineas

from fastapi import APIRouter, Depends

from api_auth import verificar_token_dependencia
from db import ejecutar_sql_unico, ejecutar_sql, ejecutar_insercion

router = APIRouter(prefix="/api", tags=["public_referidos"])


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _generar_codigo(usuario_id: int, email: str) -> str:
    """genera un codigo de referido unico basado en email + id."""
    import hashlib
    raw = f"{email}:{usuario_id}:roxymaster2026"
    codigo = hashlib.sha256(raw.encode()).hexdigest()[:10].upper()
    # verificar unicidad
    existente = ejecutar_sql_unico(
        "select usuario_id from codigos_referido where codigo = ?",
        (codigo,),
    )
    if existente:
        return _generar_codigo(usuario_id, email + "x")
    return codigo


# ---------------------------------------------------------------------------
# referidos
# ---------------------------------------------------------------------------
@router.get("/referidos")
async def api_listar_referidos(sesion: dict = Depends(verificar_token_dependencia)):
    """lista referidos directos e indirectos del usuario."""
    usuario_id = sesion["usuario_id"]

    rows = ejecutar_sql(
        "select r.id, u.username, r.nivel, r.comisiones_generadas, r.fecha_activacion "
        "from referidos r join usuarios u on u.id = r.referido_id "
        "where r.referidor_id = ? order by r.nivel, r.fecha_activacion",
        (usuario_id,),
    )

    referidos = []
    for r in rows:
        referidos.append({
            "id": r["id"],
            "username": r.get("username", ""),
            "nivel": r["nivel"],
            "comisiones_generadas": float(r["comisiones_generadas"]) if r["comisiones_generadas"] else 0.0,
            "fecha_activacion": r["fecha_activacion"] or "",
        })

    return {"exito": True, "referidos": referidos}


@router.get("/referidos/estadisticas")
async def api_referidos_estadisticas(sesion: dict = Depends(verificar_token_dependencia)):
    """resumen de referidos: cantidad por nivel, total comisiones."""
    usuario_id = sesion["usuario_id"]

    # contar por nivel
    niveles = ejecutar_sql(
        "select nivel, count(*) as cantidad from referidos "
        "where referidor_id = ? group by nivel order by nivel",
        (usuario_id,),
    )

    referidos_por_nivel = {}
    for n in niveles:
        referidos_por_nivel[str(n["nivel"])] = n["cantidad"]

    # total comisiones
    total_comisiones = ejecutar_sql_unico(
        "select coalesce(sum(comisiones_generadas), 0) as total "
        "from referidos where referidor_id = ?",
        (usuario_id,),
    )
    total_comisiones = float(total_comisiones["total"]) if total_comisiones else 0.0

    # total referidos
    total = ejecutar_sql_unico(
        "select count(*) as total from referidos where referidor_id = ?",
        (usuario_id,),
    )
    total_referidos = total["total"] if total else 0

    return {
        "exito": True,
        "total_referidos": total_referidos,
        "referidos_por_nivel": referidos_por_nivel,
        "total_comisiones_generadas": total_comisiones,
    }


# ---------------------------------------------------------------------------
# codigo referido
# ---------------------------------------------------------------------------
@router.get("/codigo_referido")
async def api_obtener_codigo_referido(sesion: dict = Depends(verificar_token_dependencia)):
    """obtiene el codigo de referido del usuario. si no tiene, genera uno."""
    usuario_id = sesion["usuario_id"]

    codigo = ejecutar_sql_unico(
        "select c.codigo, c.activo from codigos_referido c where c.usuario_id = ?",
        (usuario_id,),
    )

    if codigo:
        return {
            "exito": True,
            "codigo": codigo["codigo"],
            "activo": bool(codigo["activo"]),
        }

    # si no tiene codigo, generarlo
    usuario = ejecutar_sql_unico(
        "select email from usuarios where id = ?",
        (usuario_id,),
    )
    if not usuario:
        return {"exito": False, "mensaje": "usuario no encontrado"}

    nuevo_codigo = _generar_codigo(usuario_id, usuario["email"])
    ejecutar_insercion(
        "insert into codigos_referido (usuario_id, codigo, activo) values (?, ?, 1)",
        (usuario_id, nuevo_codigo),
    )

    # actualizar en usuarios tambien
    ejecutar_sql(
        "update usuarios set codigo_referido = ? where id = ?",
        (nuevo_codigo, usuario_id),
    )

    return {
        "exito": True,
        "codigo": nuevo_codigo,
        "activo": True,
        "mensaje": "codigo generado",
    }


@router.post("/codigo_referido/regenerar")
async def api_regenerar_codigo_referido(sesion: dict = Depends(verificar_token_dependencia)):
    """regenera codigo de referido solo si no ha sido usado."""
    usuario_id = sesion["usuario_id"]

    # verificar si el codigo actual ha sido usado
    usado = ejecutar_sql_unico(
        "select count(*) as total from usuarios where referido_por = "
        "(select codigo from codigos_referido where usuario_id = ?) ",
        (usuario_id,),
    )
    if usado and usado["total"] > 0:
        return {"exito": False, "mensaje": "no puedes regenerar: el codigo ya fue usado"}

    usuario = ejecutar_sql_unico(
        "select email from usuarios where id = ?",
        (usuario_id,),
    )
    if not usuario:
        return {"exito": False, "mensaje": "usuario no encontrado"}

    nuevo_codigo = _generar_codigo(usuario_id, usuario["email"] + "new")
    ejecutar_sql(
        "update codigos_referido set codigo = ? where usuario_id = ?",
        (nuevo_codigo, usuario_id),
    )
    ejecutar_sql(
        "update usuarios set codigo_referido = ? where id = ?",
        (nuevo_codigo, usuario_id),
    )

    return {
        "exito": True,
        "codigo": nuevo_codigo,
        "mensaje": "codigo regenerado",
    }


# ---------------------------------------------------------------------------
# metricas
# ---------------------------------------------------------------------------
@router.get("/metrics/uptime")
async def api_metrics_uptime(sesion: dict = Depends(verificar_token_dependencia)):
    """tiempo total conectado (suma horas_conexion de todos sus perfiles)."""
    usuario_id = sesion["usuario_id"]

    row = ejecutar_sql_unico(
        "select coalesce(sum(horas_conexion), 0) as total_horas "
        "from perfiles where usuario_id = ?",
        (usuario_id,),
    )
    total_horas = float(row["total_horas"]) if row else 0.0

    return {
        "exito": True,
        "uptime_horas": round(total_horas, 2),
    }