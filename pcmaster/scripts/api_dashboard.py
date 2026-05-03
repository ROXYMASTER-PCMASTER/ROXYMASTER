from fastapi import Request
# api_dashboard.py - router fastapi para dashboard y mi_estado. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

from fastapi import APIRouter, Depends

from api_auth import verificar_token_dependencia
from auth import verificar_token
from db import ejecutar_sql_unico
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
@router.get("/api/mis_pcs")
async def mis_pcs(request: Request):
    auth = await verificar_auth(request)
    if not auth: return {"ok": False, "error": "no autenticado"}
    uid, _, _ = auth
    conn = get_db()
    pcs = conn.execute("SELECT pcbot_id, hostname, ip_local, ip_tailscale, modo, uptime_horas, perfiles_activos FROM pcbots_registrados WHERE usuario_id=?", (uid,)).fetchall()
    conn.close()
    return {"ok": True, "pcs": [dict(p) for p in pcs]}

@router.get("/api/mis_referidos")
async def mis_referidos(request: Request):
    auth = await verificar_auth(request)
    if not auth: return {"ok": False, "error": "no autenticado"}
    uid, _, _ = auth
    conn = get_db()
    codigo = conn.execute("SELECT codigo FROM codigos_referido WHERE usuario_id=?", (uid,)).fetchone()
    referidor = conn.execute("SELECT u.email FROM usuarios u JOIN referidos r ON u.id=r.referidor_id WHERE r.referido_id=?", (uid,)).fetchone()
    referidos = conn.execute("SELECT u.email, r.nivel, r.comisiones_generadas FROM usuarios u JOIN referidos r ON u.id=r.referido_id WHERE r.referidor_id=?", (uid,)).fetchall()
    conn.close()
    return {"ok": True, "codigo": codigo[0] if codigo else "", "referidor": referidor[0] if referidor else "pcmaster", "referidos": [dict(r) for r in referidos]}
