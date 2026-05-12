# api_dashboard.py - router fastapi para dashboard y mi_estado. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api_auth import verificar_token_dependencia
from auth import verificar_token
from db import ejecutar_sql_unico, ejecutar_sql
from variables_globales import obtener_variables
from orchestrator import listar_pcbots_conectados, listar_comandos_pendientes, enviar_recargar_perfiles
from db import obtener_computadoras_por_usuario, guardar_perfiles
from variables_globales import obtener_variables

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
async def api_dashboard(sesion: dict = Depends(verificar_token_dependencia)):
    """dashboard principal con resumen del sistema y kpis del usuario."""
    usuario_id = sesion["usuario_id"]

    # datos del usuario (sin password_hash)
    usuario = ejecutar_sql_unico(
        "select id, email, username, rol, nivel_fiabilidad, uptime_horas, pcbot_id, modo, "
        "codigo_referido, referido_por, fecha_registro from usuarios where id = ?",
        (usuario_id,),
    )
    if not usuario:
        return {"exito": False, "mensaje": "usuario no encontrado"}

    # balance real desde wallets con coalesce
    row_wallet = ejecutar_sql_unico(
        "select coalesce(balance, 0) as balance, coalesce(minado_total, 0) as minado_total, "
        "coalesce(comprado_total, 0) as comprado_total, coalesce(retirado_total, 0) as retirado_total, "
        "coalesce(balance_fiat, 0) as balance_fiat from wallets where usuario_id = ?",
        (usuario_id,),
    )
    balance = float(row_wallet["balance"]) if row_wallet else 0.0
    minado_total = float(row_wallet["minado_total"]) if row_wallet else 0.0
    balance_fiat = float(row_wallet["balance_fiat"]) if row_wallet else 0.0
    retirado_total = float(row_wallet["retirado_total"]) if row_wallet else 0.0

    # precio token desde variables_globales
    vars_sistema = obtener_variables()
    p_token = float(vars_sistema.get("p_token", 1.0))
    saldo_pen = round(balance * p_token, 2)

    # contar perfiles activos
    perfiles_activos = 0
    perfiles_totales = 0
    row_perfiles = ejecutar_sql_unico(
        "select count(*) as total from perfiles where usuario_id = ? and estado = 'activo'",
        (usuario_id,),
    )
    if row_perfiles:
        perfiles_activos = row_perfiles["total"]

    row_perfiles_totales = ejecutar_sql_unico(
        "select count(*) as total from perfiles where usuario_id = ?",
        (usuario_id,),
    )
    if row_perfiles_totales:
        perfiles_totales = row_perfiles_totales["total"]

    # kbt minados hoy
    comprado_total = float(row_wallet["comprado_total"]) if row_wallet else 0.0
    total_tokens = balance + minado_total + comprado_total
    precio_token = float(obtener_variables().get("p_token", 1.0))
    total_fiat = round(total_tokens * precio_token, 2)
    kbt_hoy = 0.0
    row_kbt = ejecutar_sql_unico(
        "select coalesce(sum(monto), 0) as total from transacciones "
        "where (origen_id = ? or destino_id = ?) and tipo = 'minado' and date(fecha) = date('now')",
        (usuario_id, usuario_id),
    )
    if row_kbt:
        kbt_hoy = float(row_kbt["total"])

    # referidos: activos y totales
    referidos_totales = 0
    referidos_activos = 0
    row_ref = ejecutar_sql_unico(
        "select count(*) as total from referidos where referidor_id = ?",
        (usuario_id,),
    )
    if row_ref:
        referidos_totales = row_ref["total"]

    row_ref_act = ejecutar_sql_unico(
        "select count(*) as total from referidos r "
        "join usuarios u on u.id = r.referido_id "
        "where r.referidor_id = ? and u.activo = 1",
        (usuario_id,),
    )
    if row_ref_act:
        referidos_activos = row_ref_act["total"]

    # modo actual
    modo_actual = str(usuario.get("modo", "conectado"))

    return {
        "exito": True,
        "usuario": dict(usuario),
        "balance": balance,
        "balance_fiat": balance_fiat,
        "saldo_pen": saldo_pen,
        "precio_token": precio_token,
        "total_tokens": total_tokens,
        "total_fiat": total_fiat,
        "perfiles_activos": perfiles_activos,
        "perfiles_totales": perfiles_totales,
        "kbt_hoy": kbt_hoy,
        "kbt_total_minado": minado_total,
        "retirado_total": retirado_total,
        "referidos_activos": referidos_activos,
        "referidos_totales": referidos_totales,
        "modo_actual": modo_actual,
        "codigo_referido": usuario.get("codigo_referido", ""),
        "referido_por": usuario.get("referido_por", ""),
    }


@router.get("/precios_marketplace")
async def api_precios_marketplace(sesion: dict = Depends(verificar_token_dependencia)):
    """devuelve el precio mas alto y mas bajo de ordenes activas en marketplace."""
    # precio mas alto de ventas activas (tabla real: ordenes_p2p, columna real: precio_pen)
    row_max = ejecutar_sql_unico(
        "select max(precio_pen) as precio_max from ordenes_p2p "
        "where estado = 'abierta' and tipo = 'venta'",
    )
    precio_max = float(row_max["precio_max"]) if row_max and row_max["precio_max"] else 0.0

    # precio mas bajo de compras activas
    row_min = ejecutar_sql_unico(
        "select min(precio_pen) as precio_min from ordenes_p2p "
        "where estado = 'abierta' and tipo = 'compra'",
    )
    precio_min = float(row_min["precio_min"]) if row_min and row_min["precio_min"] else 0.0

    return {
        "exito": True,
        "precio_max_venta": precio_max,
        "precio_min_compra": precio_min,
    }


@router.get("/mi_estado")
async def api_mi_estado(sesion: dict = Depends(verificar_token_dependencia)):
    """estado detallado del usuario autenticado (datos sensibles excluidos)."""
    usuario_id = sesion["usuario_id"]

    # excluir password_hash por seguridad
    usuario = ejecutar_sql_unico(
        "select id, email, username, rol, wallet, codigo_referido, referido_por, "
        "referido_cambiado, nivel_fiabilidad, uptime_horas, pcbot_id, modo, "
        "ultimo_login, fecha_registro, activo from usuarios where id = ?",
        (usuario_id,),
    )
    wallet = ejecutar_sql_unico(
        "select id, usuario_id, balance, minado_total, recolectado_total, "
        "comprado_total, retirado_total, staking_total, staking_desde, actualizado "
        "from wallets where usuario_id = ?",
        (usuario_id,),
    )
    # obtener comandos pendientes para el pcbot del usuario
    pcbot_id = usuario["pcbot_id"] if usuario else None
    comandos_pendientes = []
    if pcbot_id:
        comandos_pendientes = listar_comandos_pendientes(pcbot_id)

    return {
        "exito": True,
        "usuario": dict(usuario) if usuario else {},
        "wallet": dict(wallet) if wallet else {},
        "comandos_pendientes": comandos_pendientes,
    }


@router.get("/mis_pcs")
async def api_mis_pcs(sesion: dict = Depends(verificar_token_dependencia)):
    """lista los pcs registrados del usuario autenticado."""
    usuario_id = sesion["usuario_id"]

    # datos del pc desde la tabla usuarios (pcbot_id, modo)
    usuario = ejecutar_sql_unico(
        "select id, pcbot_id, modo, uptime_horas from usuarios where id = ?",
        (usuario_id,),
    )
    # contar perfiles asociados al usuario
    pcs = []
    if usuario and usuario["pcbot_id"]:
        perfiles = ejecutar_sql(
            "select count(*) as total from perfiles where usuario_id = ?",
            (usuario_id,),
        )
        total_perfiles = perfiles[0]["total"] if perfiles else 0

        pc_item = {
            "pcbot_id": usuario["pcbot_id"],
            "modo": usuario["modo"],
            "perfiles_activos": total_perfiles,
            "uptime_horas": usuario["uptime_horas"] or 0,
        }
        pcs.append(pc_item)

    return {"exito": True, "pcs": pcs}


@router.get("/mis_perfiles")
async def api_mis_perfiles(sesion: dict = Depends(verificar_token_dependencia)):
    """lista los perfiles del usuario autenticado agrupados por computadora, con progreso de 62 min."""
    usuario_id = sesion["usuario_id"]

    # validar que el usuario existe
    usuario = ejecutar_sql_unico(
        "select id from usuarios where id = ?", (usuario_id,)
    )
    if not usuario:
        return {"exito": False, "mensaje": "usuario no encontrado"}

    # obtener todas las computadoras del usuario
    computadoras = ejecutar_sql(
        "select pcbot_id, hostname, ip_wan, ip_local, estado "
        "from computadoras where usuario_id = ?",
        (usuario_id,),
    )

    resultado = []
    total_global = 0
    ciclo_minutos = 62

    for pc in computadoras:
        pcbot_id = pc["pcbot_id"]
        perfiles = ejecutar_sql(
            "select id, nombre_perfil, tipo, estado, horas_conexion, horas_en_uso, "
            "ultimo_heartbeat, hash_id, workspace_id "
            "from perfiles where usuario_id = ? and pcbot_id = ? order by id",
            (usuario_id, pcbot_id),
        )

        perfiles_procesados = []
        for p in perfiles:
            progreso = 0
            if p["ultimo_heartbeat"] and p["estado"] == "activo":
                try:
                    from datetime import datetime
                    last = datetime.strptime(p["ultimo_heartbeat"], "%Y-%m-%d %H:%M:%S")
                    ahora = datetime.now()
                    diff_min = (ahora - last).total_seconds() / 60.0
                    if diff_min < ciclo_minutos:
                        progreso = round((diff_min / ciclo_minutos) * 100, 1)
                    else:
                        progreso = 100.0
                except (ValueError, TypeError):
                    progreso = 0

            perfiles_procesados.append({
                "id": p["id"],
                "nombre_perfil": p["nombre_perfil"],
                "tipo": p["tipo"],
                "estado": p["estado"],
                "horas_conexion": p["horas_conexion"] or 0,
                "horas_en_uso": p["horas_en_uso"] or 0,
                "ultimo_heartbeat": p["ultimo_heartbeat"] or "",
                "progreso_62min": progreso,
                "hash_id": p["hash_id"] or "",
                "workspace_id": p["workspace_id"] or "",
            })

        total = len(perfiles_procesados)
        activos = sum(1 for p in perfiles_procesados if p["estado"] == "activo")
        inactivos = total - activos
        total_global += total

        resultado.append({
            "pcbot_id": pcbot_id,
            "hostname": pc["hostname"] or pcbot_id,
            "ip_wan": pc["ip_wan"] or "",
            "ip_local": pc["ip_local"] or "",
            "estado_pc": pc["estado"] or "desconocido",
            "total_perfiles": total,
            "activos": activos,
            "inactivos": inactivos,
            "perfiles": perfiles_procesados,
        })

    return {
        "exito": True,
        "computadoras": resultado,
        "total_global": total_global,
    }


@router.get("/mis_referidos")
async def api_mis_referidos(sesion: dict = Depends(verificar_token_dependencia)):
    """lista los referidos del usuario autenticado."""
    usuario_id = sesion["usuario_id"]

    # obtener codigo de referido del usuario
    usuario = ejecutar_sql_unico(
        "select codigo_referido, referido_por, referido_cambiado from usuarios where id = ?",
        (usuario_id,),
    )

    codigo = usuario["codigo_referido"] if usuario and usuario["codigo_referido"] else ""
    referido_por = usuario["referido_por"] if usuario and usuario["referido_por"] else "pcmaster"
    referido_cambiado = usuario["referido_cambiado"] if usuario else 0

    # obtener lista de referidos directos de este usuario
    referidos_directos = ejecutar_sql(
        "select u.email, r.nivel, r.comisiones_generadas "
        "from usuarios u "
        "join referidos r on u.id = r.referido_id "
        "where r.referidor_id = ?",
        (usuario_id,),
    )

    # arbol: nivel 1 y 2
    arbol = []
    for rd in referidos_directos:
        arbol.append({
            "email": rd["email"],
            "nivel": rd["nivel"],
            "comisiones": rd["comisiones_generadas"],
        })
        # nivel 2: referidos de mis referidos
        sub = ejecutar_sql(
            "select u.email, r.nivel, r.comisiones_generadas "
            "from usuarios u "
            "join referidos r on u.id = r.referido_id "
            "join usuarios ref on ref.id = r.referidor_id "
            "where ref.email = ?",
            (rd["email"],),
        )
        for s in sub:
            arbol.append({
                "email": s["email"],
                "nivel": 2,
                "comisiones": s["comisiones_generadas"],
            })

    # conteo de referidos
    ref_totales = len(referidos_directos)
    ref_activos = ejecutar_sql_unico(
        "select count(*) as total from referidos r "
        "join usuarios u on u.id = r.referido_id "
        "where r.referidor_id = ? and u.activo = 1",
        (usuario_id,),
    )

    return {
        "exito": True,
        "codigo_referido": codigo,
        "referido_por": referido_por,
        "referido_cambiado": referido_cambiado,
        "referidos_directos": [dict(r) for r in referidos_directos],
        "referidos_totales": ref_totales,
        "referidos_activos": ref_activos["total"] if ref_activos else 0,
        "arbol": arbol,
    }


# modelos
class CambiarReferidorRequest(BaseModel):
    nuevo_codigo: str


@router.post("/cambiar_referidor")
async def api_cambiar_referidor(
    req: CambiarReferidorRequest,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """cambia el referidor del usuario (solo una vez)."""
    usuario_id = sesion["usuario_id"]

    # verificar si ya cambio antes
    usuario = ejecutar_sql_unico(
        "select referido_cambiado from usuarios where id = ?",
        (usuario_id,),
    )
    if not usuario:
        return {"exito": False, "mensaje": "usuario no encontrado"}
    if usuario["referido_cambiado"]:
        return {"exito": False, "mensaje": "ya cambiaste tu referidor anteriormente, solo se permite una vez"}

    # buscar el codigo de referido
    referidor = ejecutar_sql_unico(
        "select id from usuarios where codigo_referido = ?",
        (req.nuevo_codigo,),
    )
    if not referidor:
        return {"exito": False, "mensaje": "codigo de referido no valido"}

    # actualizar
    ejecutar_sql(
        "update usuarios set referido_por = ?, referido_cambiado = 1 where id = ?",
        (req.nuevo_codigo, usuario_id),
    )
    return {"exito": True, "mensaje": "referidor actualizado correctamente"}


# ---- modo toggle ----
class ModoToggleRequest(BaseModel):
    modo: str = ""


@router.post("/modo/toggle")
async def api_modo_toggle(
    req: ModoToggleRequest,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """cambia el modo del usuario entre 'pidiendo_ordenes' y 'uso_personal'."""
    usuario_id = sesion["usuario_id"]

    usuario = ejecutar_sql_unico(
        "select id, modo from usuarios where id = ?",
        (usuario_id,),
    )
    if not usuario:
        return {"exito": False, "mensaje": "usuario no encontrado"}

    modo_actual = str(usuario["modo"]) if usuario["modo"] else "conectado"

    # si se envia modo especifico, usarlo. si no, toggle.
    if req.modo and req.modo in ("pidiendo_ordenes", "uso_personal"):
        nuevo_modo = req.modo
    else:
        nuevo_modo = "uso_personal" if modo_actual == "pidiendo_ordenes" else "pidiendo_ordenes"

    ejecutar_sql(
        "update usuarios set modo = ? where id = ?",
        (nuevo_modo, usuario_id),
    )

    return {
        "exito": True,
        "modo_anterior": modo_actual,
        "modo_nuevo": nuevo_modo,
        "mensaje": f"modo cambiado a {nuevo_modo}",
    }


# ---- recargar perfiles desde roxybrowser ----
class RecargarPerfilesRequest(BaseModel):
    pcbot_id: str = ""


@router.post("/recargar_perfiles")
async def api_recargar_perfiles(
    req: RecargarPerfilesRequest,
    sesion: dict = Depends(verificar_token_dependencia),
):
    """solicita recarga de perfiles roxybrowser a las computadoras del usuario."""
    usuario_id = sesion["usuario_id"]

    # obtener computadoras del usuario
    if req.pcbot_id:
        # filtrar por pc especifica
        computadoras = ejecutar_sql(
            "select pcbot_id, api_key_roxy, estado from computadoras where usuario_id = ? and pcbot_id = ?",
            (usuario_id, req.pcbot_id),
        )
    else:
        # todas las computadoras del usuario
        computadoras = obtener_computadoras_por_usuario(usuario_id)

    if not computadoras:
        return {"exito": False, "mensaje": "no tienes computadoras registradas", "computadoras": []}

    resultados = []
    for pc in computadoras:
        pcbot_id = pc["pcbot_id"]
        api_key = pc.get("api_key_roxy", "")

        if not api_key:
            resultados.append({
                "pcbot_id": pcbot_id,
                "estado": "sin_api_key",
                "mensaje": "no hay api key configurada para esta computadora",
            })
            continue

        envio = await enviar_recargar_perfiles(pcbot_id, api_key)
        if envio.get("exito"):
            resultados.append({
                "pcbot_id": pcbot_id,
                "estado": "enviado",
                "comando_id": envio.get("comando_id", ""),
                "mensaje": "comando enviado, esperando respuesta del agente",
            })
        else:
            resultados.append({
                "pcbot_id": pcbot_id,
                "estado": "offline",
                "mensaje": envio.get("error", "pcbot no conectado"),
            })

    return {
        "exito": True,
        "mensaje": f"comando enviado a {len(resultados)} computadora(s)",
        "resultados": resultados,
    }
