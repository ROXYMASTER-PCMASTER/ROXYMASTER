# api_superadmin.py - endpoints extendidos de administrador. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

import uuid
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from api_auth import verificar_admin_dependencia
from db import ejecutar_sql, ejecutar_sql_unico, ejecutar_insercion
from variables_globales import obtener_variables, actualizar_variable
from tokenomics import _g_actual

router = APIRouter(prefix="/api/admin", tags=["superadmin"])


def _ahora_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# modelos de peticion
# ---------------------------------------------------------------------------
class ProcesarRetiroRequest(BaseModel):
    retiro_id: int
    accion: str  # "aprobar" o "rechazar"


class MensajeRequest(BaseModel):
    email_destino: str
    texto: str


class HappyHourRequest(BaseModel):
    multiplicador: float = 2.0
    fecha_inicio: str
    fecha_fin: str


class ToggleUsuarioRequest(BaseModel):
    activo: int  # 0 o 1


# ---------------------------------------------------------------------------
# 1. proyecciones kbt a 3, 9, 18 meses
# ---------------------------------------------------------------------------
@router.get("/proyecciones")
async def api_proyecciones(sesion: dict = Depends(verificar_admin_dependencia)):
    """
    genera escenarios a 3, 9 y 18 meses con las formulas kbt.
    usa parametros actuales de variables_globales.
    """
    vars_dict = obtener_variables()
    k = float(vars_dict.get("K", 20))
    fx = float(vars_dict.get("FX", 3.70))
    p_token = float(vars_dict.get("P_token", 1.00))
    h = float(vars_dict.get("H", 720))
    e = float(vars_dict.get("E", 0.005))
    g = float(vars_dict.get("G", _g_actual()))
    hh_mult = float(vars_dict.get("HH_mult", 2.0))
    beta = float(vars_dict.get("beta", 0.10))
    comision_mkt = float(vars_dict.get("comision_marketplace", 0.15))
    limite_retiro = float(vars_dict.get("limite_retiro_usd", 999))

    # datos actuales
    total_usuarios = ejecutar_sql_unico("select count(*) as c from usuarios")["c"]
    total_perfiles = ejecutar_sql_unico("select count(*) as c from perfiles")["c"]
    tokens_circulando = ejecutar_sql_unico("select coalesce(sum(balance),0) as c from wallets")["c"]

    escenarios = []
    for meses in [3, 9, 18]:
        # estimacion de crecimiento compuesto
        factor_crecimiento = (1 + e) ** meses
        usuarios_est = int(total_usuarios * factor_crecimiento)
        perfiles_est = int(total_perfiles * factor_crecimiento * 1.2)

        # tokens minables en el periodo
        # estimamos horas totales: perfiles_est * H mensual * meses
        horas_habiles = perfiles_est * h * meses
        tokens_emitidos = horas_habiles * fx * g / k if k > 0 else 0

        # margen dueno = 1 - beta del total minado
        margen_dueno = tokens_emitidos * (1 - beta)

        # ganancia granjeros = beta del total minado
        ganancia_granjeros = tokens_emitidos * beta

        # volumen market estimado (10% del circulante)
        volumen_market = (tokens_circulando + tokens_emitidos) * 0.10

        # comisiones marketplace sobre volumen
        comisiones_est = volumen_market * comision_mkt

        escenarios.append({
            "meses": meses,
            "usuarios_estimados": usuarios_est,
            "perfiles_estimados": perfiles_est,
            "tokens_emitidos_periodo": round(tokens_emitidos, 4),
            "tokens_circulantes_est": round(tokens_circulando + tokens_emitidos, 4),
            "margen_dueno": round(margen_dueno, 4),
            "ganancia_granjeros": round(ganancia_granjeros, 4),
            "volumen_market_est": round(volumen_market, 4),
            "comisiones_est": round(comisiones_est, 4),
            "g_actual": g,
            "horas_habiles_est": round(horas_habiles, 0),
        })

    return {
        "exito": True,
        "datos_actuales": {
            "total_usuarios": total_usuarios,
            "total_perfiles": total_perfiles,
            "tokens_circulando": round(tokens_circulando, 4),
        },
        "escenarios": escenarios,
    }


# ---------------------------------------------------------------------------
# 2. procesar retiro
# ---------------------------------------------------------------------------
@router.post("/retiros/procesar")
async def api_procesar_retiro(
    req: ProcesarRetiroRequest,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """aprueba o rechaza un retiro pendiente."""
    if req.accion not in ("aprobar", "rechazar"):
        raise HTTPException(status_code=400, detail="accion debe ser 'aprobar' o 'rechazar'")
    retiro = ejecutar_sql_unico("select * from retiros where id = ?", (req.retiro_id,))
    if not retiro:
        raise HTTPException(status_code=404, detail="retiro no encontrado")
    if retiro["estado"] != "pendiente":
        raise HTTPException(status_code=400, detail="el retiro no esta pendiente")
    if req.accion == "rechazar":
        # devolver kbt al usuario
        ejecutar_sql(
            "update wallets set balance = balance + ?, retirado_total = retirado_total - ? where usuario_id = ?",
            (retiro["cantidad_kbt"], retiro["cantidad_kbt"], retiro["usuario_id"]),
        )
        ejecutar_sql(
            "update retiros set estado = 'rechazado', fecha_procesado = ? where id = ?",
            (_ahora_str(), req.retiro_id),
        )
        return {"exito": True, "retiro_id": req.retiro_id, "estado": "rechazado"}
    # aprobar
    ejecutar_sql(
        "update retiros set estado = 'aprobado', fecha_procesado = ? where id = ?",
        (_ahora_str(), req.retiro_id),
    )
    # registrar transaccion
    ejecutar_sql(
        "insert into transacciones (origen_id, destino_id, tipo, monto, concepto) values (?, ?, ?, ?, ?)",
        (retiro["usuario_id"], None, "retiro_aprobado", retiro["cantidad_kbt"], f"retiro id {req.retiro_id}"),
    )
    return {"exito": True, "retiro_id": req.retiro_id, "estado": "aprobado"}


# ---------------------------------------------------------------------------
# 3. enviar mensaje a usuario
# ---------------------------------------------------------------------------
@router.post("/mensajes/enviar")
async def api_enviar_mensaje(
    req: MensajeRequest,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """envia un mensaje a un usuario desde el admin."""
    destino = ejecutar_sql_unico("select id from usuarios where email = ?", (req.email_destino,))
    if not destino:
        raise HTTPException(status_code=404, detail="usuario destino no encontrado")
    admin_id = sesion.get("usuario_id")
    ejecutar_insercion(
        "insert into mensajes (origen_id, destino_id, texto) values (?, ?, ?)",
        (admin_id, destino["id"], req.texto),
    )
    return {"exito": True, "mensaje": "mensaje enviado"}


# ---------------------------------------------------------------------------
# 4. historial de mensajes
# ---------------------------------------------------------------------------
@router.get("/mensajes/historial")
async def api_historial_mensajes(
    pagina: int = 1,
    limite: int = 50,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """devuelve historial de mensajes enviados por administradores."""
    offset = (pagina - 1) * limite
    mensajes = ejecutar_sql(
        "select m.id, m.texto, m.leido, m.fecha, "
        "o.email as origen_email, d.email as destino_email "
        "from mensajes m "
        "join usuarios o on m.origen_id = o.id "
        "join usuarios d on m.destino_id = d.id "
        "order by m.fecha desc limit ? offset ?",
        (limite, offset),
    )
    total = ejecutar_sql_unico("select count(*) as c from mensajes")["c"]
    return {"exito": True, "mensajes": [dict(m) for m in mensajes], "total": total, "pagina": pagina}


# ---------------------------------------------------------------------------
# 5. listar sesiones activas
# ---------------------------------------------------------------------------
@router.get("/sesiones")
async def api_listar_sesiones(sesion: dict = Depends(verificar_admin_dependencia)):
    """lista todas las sesiones activas con datos enmascarados."""
    sesiones = ejecutar_sql(
        "select s.token, s.usuario_id, s.email, s.rol, s.fecha_creacion, s.fecha_expiracion, "
        "u.username, u.pcbot_id from sesiones s "
        "join usuarios u on s.usuario_id = u.id "
        "order by s.fecha_creacion desc"
    )
    resultado = []
    for s in sesiones:
        s_dict = dict(s)
        # enmascarar token: primeros 8 caracteres + ...
        if s_dict.get("token") and len(s_dict["token"]) > 8:
            s_dict["token"] = s_dict["token"][:8] + "..."
        resultado.append(s_dict)
    return {"exito": True, "sesiones": resultado, "total": len(resultado)}


# ---------------------------------------------------------------------------
# 6. cerrar sesion por token
# ---------------------------------------------------------------------------
@router.delete("/sesiones/{token}")
async def api_cerrar_sesion(
    token: str,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """cierra una sesion especifica (revoca el token)."""
    existente = ejecutar_sql_unico("select token from sesiones where token = ?", (token,))
    if not existente:
        raise HTTPException(status_code=404, detail="sesion no encontrada")
    ejecutar_sql("delete from sesiones where token = ?", (token,))
    return {"exito": True, "mensaje": "sesion cerrada"}


# ---------------------------------------------------------------------------
# 7. listar todos los perfiles
# ---------------------------------------------------------------------------
@router.get("/perfiles")
async def api_listar_perfiles(
    estado: Optional[str] = None,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """lista todos los perfiles con filtro opcional por estado."""
    if estado:
        perfiles = ejecutar_sql(
            "select p.*, u.email, u.username from perfiles p "
            "join usuarios u on p.usuario_id = u.id "
            "where p.estado = ? order by p.ultimo_heartbeat desc",
            (estado,),
        )
    else:
        perfiles = ejecutar_sql(
            "select p.*, u.email, u.username from perfiles p "
            "join usuarios u on p.usuario_id = u.id "
            "order by p.ultimo_heartbeat desc"
        )
    return {"exito": True, "perfiles": [dict(p) for p in perfiles], "total": len(perfiles)}


# ---------------------------------------------------------------------------
# 8. pcs registradas (pcbots)
# ---------------------------------------------------------------------------
@router.get("/pcs")
async def api_listar_pcs(sesion: dict = Depends(verificar_admin_dependencia)):
    """lista todas las computadoras (pcbots) registradas."""
    pcs = ejecutar_sql(
        "select u.id, u.email, u.username, u.pcbot_id, u.modo, u.uptime_horas, u.ultimo_login, "
        "count(p.id) as perfiles_asociados "
        "from usuarios u "
        "left join perfiles p on u.id = p.usuario_id "
        "where u.pcbot_id is not null "
        "group by u.id order by u.ultimo_login desc"
    )
    return {"exito": True, "pcs": [dict(p) for p in pcs], "total": len(pcs)}


# ---------------------------------------------------------------------------
# 9. activar happy hour
# ---------------------------------------------------------------------------
@router.post("/happy_hour/activar")
async def api_activar_happy_hour(
    req: HappyHourRequest,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """activa un nuevo periodo de happy hour."""
    # desactivar cualquier happy hour activo
    ejecutar_sql("update happy_hour set activo = 0 where activo = 1")
    ejecutar_insercion(
        "insert into happy_hour (multiplicador, fecha_inicio, fecha_fin, activo) values (?, ?, ?, 1)",
        (req.multiplicador, req.fecha_inicio, req.fecha_fin),
    )
    return {"exito": True, "mensaje": "happy hour activado"}


# ---------------------------------------------------------------------------
# 10. desactivar happy hour
# ---------------------------------------------------------------------------
@router.post("/happy_hour/desactivar")
async def api_desactivar_happy_hour(sesion: dict = Depends(verificar_admin_dependencia)):
    """desactiva el happy hour activo."""
    ejecutar_sql("update happy_hour set activo = 0 where activo = 1")
    return {"exito": True, "mensaje": "happy hour desactivado"}


# ---------------------------------------------------------------------------
# 11. historial happy hour
# ---------------------------------------------------------------------------
@router.get("/happy_hour/historial")
async def api_historial_happy_hour(sesion: dict = Depends(verificar_admin_dependencia)):
    """devuelve el historial completo de happy hours."""
    historial = ejecutar_sql(
        "select * from happy_hour order by fecha_inicio desc"
    )
    return {"exito": True, "historial": [dict(h) for h in historial], "total": len(historial)}


# ---------------------------------------------------------------------------
# 12. kpis extendidos del sistema
# ---------------------------------------------------------------------------
@router.get("/kpi")
async def api_kpis(sesion: dict = Depends(verificar_admin_dependencia)):
    """kpis completos para el dashboard administrativo."""
    total_usuarios = ejecutar_sql_unico("select count(*) as c from usuarios")["c"]
    usuarios_activos = ejecutar_sql_unico("select count(*) as c from usuarios where activo = 1")["c"]
    total_pcbots = ejecutar_sql_unico("select count(*) as c from usuarios where pcbot_id is not null")["c"]
    pcbots_conectados = ejecutar_sql_unico("select count(*) as c from usuarios where modo = 'conectado'")["c"]
    total_perfiles = ejecutar_sql_unico("select count(*) as c from perfiles")["c"]
    perfiles_activos = ejecutar_sql_unico("select count(*) as c from perfiles where estado = 'activo'")["c"]
    tokens_circulando = ejecutar_sql_unico("select coalesce(sum(balance),0) as c from wallets")["c"]
    reserva = ejecutar_sql_unico("select * from reserva where id = 1")
    comandos_pendientes = ejecutar_sql_unico("select count(*) as c from comandos where estado = 'pendiente'")["c"]
    retiros_pendientes = ejecutar_sql_unico("select count(*) as c from retiros where estado = 'pendiente'")["c"]
    sesiones_activas = ejecutar_sql_unico("select count(*) as c from sesiones")["c"]
    hh_activo = ejecutar_sql_unico("select * from happy_hour where activo = 1")
    volumen_24h = ejecutar_sql_unico(
        "select coalesce(sum(monto),0) as c from transacciones "
        "where fecha >= datetime('now','localtime','-1 day')"
    )["c"]
    # total minado (transacciones tipo minado)
    total_minado = ejecutar_sql_unico(
        "select coalesce(sum(monto),0) as c from transacciones where tipo = 'minado'"
    )["c"]
    # total recolectado
    total_recolectado = ejecutar_sql_unico(
        "select coalesce(sum(monto),0) as c from transacciones where tipo = 'recoleccion'"
    )["c"]

    return {
        "exito": True,
        "usuarios": {
            "total": total_usuarios,
            "activos": usuarios_activos,
            "admin": ejecutar_sql_unico("select count(*) as c from usuarios where rol = 'admin'")["c"],
        },
        "pcbots": {
            "total_registrados": total_pcbots,
            "conectados": pcbots_conectados,
        },
        "perfiles": {
            "total": total_perfiles,
            "activos": perfiles_activos,
        },
        "kbt": {
            "circulando": round(tokens_circulando, 4),
            "total_minado": round(total_minado, 4),
            "total_recolectado": round(total_recolectado, 4),
            "reserva_tokens": round(reserva["tokens"], 4) if reserva else 0,
            "reserva_soles": round(reserva["soles"], 4) if reserva else 0,
        },
        "operaciones": {
            "comandos_pendientes": comandos_pendientes,
            "retiros_pendientes": retiros_pendientes,
            "sesiones_activas": sesiones_activas,
            "volumen_24h": round(volumen_24h, 4),
        },
        "happy_hour": dict(hh_activo) if hh_activo else {"activo": False},
    }


# ---------------------------------------------------------------------------
# 13. eventos de seguridad
# ---------------------------------------------------------------------------
@router.get("/seguridad")
async def api_eventos_seguridad(
    tipo: Optional[str] = None,
    pagina: int = 1,
    limite: int = 100,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """ultimos eventos de seguridad con filtro opcional por tipo."""
    offset = (pagina - 1) * limite
    if tipo:
        eventos = ejecutar_sql(
            "select * from eventos_seguridad where tipo = ? "
            "order by fecha desc limit ? offset ?",
            (tipo, limite, offset),
        )
        total = ejecutar_sql_unico(
            "select count(*) as c from eventos_seguridad where tipo = ?", (tipo,)
        )["c"]
    else:
        eventos = ejecutar_sql(
            "select * from eventos_seguridad order by fecha desc limit ? offset ?",
            (limite, offset),
        )
        total = ejecutar_sql_unico("select count(*) as c from eventos_seguridad")["c"]
    return {"exito": True, "eventos": [dict(e) for e in eventos], "total": total, "pagina": pagina}


# ---------------------------------------------------------------------------
# 14. activar / desactivar usuario
# ---------------------------------------------------------------------------
@router.post("/usuarios/{usuario_id}/toggle")
async def api_toggle_usuario(
    usuario_id: int,
    req: ToggleUsuarioRequest,
    sesion: dict = Depends(verificar_admin_dependencia),
):
    """activa o desactiva un usuario."""
    usuario = ejecutar_sql_unico("select id, activo from usuarios where id = ?", (usuario_id,))
    if not usuario:
        raise HTTPException(status_code=404, detail="usuario no encontrado")
    if usuario["id"] == sesion.get("usuario_id"):
        raise HTTPException(status_code=400, detail="no puedes desactivarte a ti mismo")
    ejecutar_sql(
        "update usuarios set activo = ? where id = ?",
        (req.activo, usuario_id),
    )
    estado = "activado" if req.activo else "desactivado"
    return {"exito": True, "usuario_id": usuario_id, "estado": estado}