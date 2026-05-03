from fastapi import APIRouter, Depends

# api_dashboard.py - router fastapi para dashboard y mi_estado. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

from api_auth import verificar_token_dependencia
from auth import verificar_token
from db import ejecutar_sql_unico, ejecutar_sql
from tokenomics import obtener_balance as consultar_balance
from orchestrator import listar_pcbots_conectados, listar_comandos_pendientes

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
async def api_dashboard(sesion: dict = Depends(verificar_token_dependencia)):
    """dashboard principal con resumen del sistema."""
    usuario_id = sesion["usuario_id"]

    # datos del usuario (sin password_hash)
    usuario = ejecutar_sql_unico(
        "select id, email, username, rol, nivel_fiabilidad, uptime_horas, pcbot_id, modo, "
        "codigo_referido, referido_por, fecha_registro from usuarios where id = ?",
        (usuario_id,),
    )
    balance = consultar_balance(usuario_id)

    return {
        "exito": True,
        "usuario": dict(usuario) if usuario else {},
        "balance": balance,
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
        "select id, pcbot_id, modo from usuarios where id = ?",
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
        pcs.append({
            "pcbot_id": usuario["pcbot_id"],
            "modo": usuario["modo"],
            "perfiles_activos": total_perfiles,
        })

    return {"ok": True, "pcs": pcs}


@router.get("/mis_referidos")
async def api_mis_referidos(sesion: dict = Depends(verificar_token_dependencia)):
    """lista los referidos del usuario autenticado."""
    usuario_id = sesion["usuario_id"]

    # obtener codigo de referido del usuario
    codigo_row = ejecutar_sql_unico(
        "select codigo from codigos_referido where usuario_id = ?",
        (usuario_id,),
    )
    codigo = codigo_row["codigo"] if codigo_row else ""

    # obtener referidor (quien refirio a este usuario)
    referidor_row = ejecutar_sql_unico(
        "select u.email from usuarios u "
        "join referidos r on u.id = r.referidor_id "
        "where r.referido_id = ?",
        (usuario_id,),
    )
    referidor = referidor_row["email"] if referidor_row else "pcmaster"

    # obtener lista de referidos de este usuario
    referidos = ejecutar_sql(
        "select u.email, r.nivel, r.comisiones_generadas "
        "from usuarios u "
        "join referidos r on u.id = r.referido_id "
        "where r.referidor_id = ?",
        (usuario_id,),
    )

    return {
        "ok": True,
        "codigo": codigo,
        "referidor": referidor,
        "referidos": referidos,
    }