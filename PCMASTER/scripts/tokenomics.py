import sqlite3, os, time, json
from config import DATA_DIR
DB_PATH = os.path.join(DATA_DIR, "roxymaster.db")

# ==================== funciones wrapper para server.py v8.3 ====================

def init_tokenomics_db():
    """inicializa las tablas de tokenomics."""
    conn = sqlite3.connect(DB_PATH)
    conn.executescript('''
        create table if not exists wallets (
            id integer primary key autoincrement,
            wallet text unique not null,
            usuario_id integer not null,
            saldo_tokens real default 0,
            tokens_minados real default 0,
            tokens_retirados real default 0,
            fecha_creacion text default (datetime('now','localtime')),
            ultima_actividad text default (datetime('now','localtime')),
            foreign key (usuario_id) references usuarios(id)
        );
        create table if not exists transacciones (
            id integer primary key autoincrement,
            wallet_origen text,
            wallet_destino text,
            cantidad real not null,
            tipo text not null,
            concepto text,
            fecha text default (datetime('now','localtime')),
            orden_id integer,
            foreign key (orden_id) references ordenes_marketplace(id)
        );
        create table if not exists transacciones_kbt (
            id integer primary key autoincrement,
            wallet text not null,
            cantidad real not null,
            tipo text not null,
            concepto text,
            fecha text default (datetime('now','localtime'))
        );
        create table if not exists retiros (
            id integer primary key autoincrement,
            wallet text not null,
            cantidad real not null,
            estado text default 'pendiente',
            fecha_solicitud text default (datetime('now','localtime')),
            fecha_procesado text,
            metodo text,
            datos_pago text
        );
        create table if not exists fondo_recoleccion (
            id integer primary key autoincrement,
            wallet text not null,
            cantidad real not null,
            fecha text default (datetime('now','localtime')),
            concepto text
        );
    ''')
    conn.commit()
    conn.close()

def obtener_balance(uid):
    """obtiene el balance de tokens de un usuario por su id."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "select coalesce(w.saldo_tokens, 0) as saldo from usuarios u left join wallets w on w.usuario_id = u.id where u.id = ?",
        (uid,)
    ).fetchone()
    conn.close()
    return row["saldo"] if row else 0

def obtener_wallet_por_usuario(uid):
    """obtiene el wallet del usuario por su id."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("select * from wallets where usuario_id = ?", (uid,)).fetchone()
    conn.close()
    return dict(row) if row else None

def obtener_wallet_por_email(email):
    """obtiene el wallet del usuario por su email."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "select w.* from wallets w join usuarios u on w.usuario_id = u.id where lower(u.email) = lower(?)",
        (email.strip(),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def acreditar_tokens(uid, cantidad, concepto="acreditacion_manual"):
    """acredita tokens al wallet del usuario."""
    conn = sqlite3.connect(DB_PATH)
    wallet = conn.execute("select wallet, saldo_tokens from wallets where usuario_id = ?", (uid,)).fetchone()
    if not wallet:
        conn.close()
        return {"ok": False, "error": "wallet no encontrada"}
    wallet_id, saldo = wallet
    nuevo_saldo = saldo + cantidad
    conn.execute("update wallets set saldo_tokens = ?, ultima_actividad = datetime('now','localtime') where usuario_id = ?",
                 (nuevo_saldo, uid))
    conn.execute("insert into transacciones (wallet_destino, monto, tipo, concepto) values (?,?,?,?)",
                 (wallet_id, cantidad, "credito", concepto))
    conn.commit()
    conn.close()
    return {"ok": True, "saldo": nuevo_saldo, "cantidad": cantidad}

def debitar_tokens(uid, cantidad, concepto="debito_manual"):
    """debita tokens del wallet del usuario."""
    conn = sqlite3.connect(DB_PATH)
    wallet = conn.execute("select wallet, saldo_tokens from wallets where usuario_id = ?", (uid,)).fetchone()
    if not wallet:
        conn.close()
        return {"ok": False, "error": "wallet no encontrada"}
    wallet_id, saldo = wallet
    if saldo < cantidad:
        conn.close()
        return {"ok": False, "error": "saldo insuficiente"}
    nuevo_saldo = saldo - cantidad
    conn.execute("update wallets set saldo_tokens = ?, ultima_actividad = datetime('now','localtime') where usuario_id = ?",
                 (nuevo_saldo, uid))
    conn.execute("insert into transacciones (wallet_origen, monto, tipo, concepto) values (?,?,?,?)",
                 (wallet_id, cantidad, "debito", concepto))
    conn.commit()
    conn.close()
    return {"ok": True, "saldo": nuevo_saldo, "cantidad": cantidad}

def crear_wallet(uid, wallet_id=None):
    """crea un wallet para un usuario."""
    if not wallet_id:
        import secrets
        wallet_id = f"wallet_{uid}_{secrets.token_hex(4)}"
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("insert or ignore into wallets (wallet, usuario_id, saldo_tokens) values (?,?,0)",
                     (wallet_id, uid))
        conn.commit()
        conn.execute("update usuarios set wallet = ? where id = ?", (wallet_id, uid))
        conn.commit()
        conn.close()
        return {"ok": True, "wallet": wallet_id}
    except Exception as e:
        conn.close()
        return {"ok": False, "error": str(e)}

def registrar_mineria(uid, tokens, horas, nivel_uptime="bronce"):
    """registra mineria de tokens."""
    wallet = obtener_wallet_por_usuario(uid)
    if not wallet:
        return {"ok": False, "error": "wallet no encontrada"}
    acreditar_tokens(uid, tokens, f"mineria_{horas}h_{nivel_uptime}")
    return {"ok": True, "tokens": tokens, "horas": horas, "nivel": nivel_uptime}

def obtener_historial_token(uid, limite=50):
    """obtiene el historial de transacciones de un usuario."""
    wallet = obtener_wallet_por_usuario(uid)
    if not wallet:
        return []
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "select * from transacciones where wallet_origen = ? or wallet_destino = ? order by fecha desc limit ?",
        (wallet["wallet"], wallet["wallet"], limite)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def obtener_estadisticas_kbt():
    """obtiene estadisticas globales del token kbt."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    total_emitido = conn.execute("select coalesce(sum(cantidad),0) from transacciones where tipo='credito'").fetchone()[0]
    total_quemado = conn.execute("select coalesce(sum(cantidad),0) from transacciones where tipo='debito'").fetchone()[0]
    total_usuarios = conn.execute("select count(*) from usuarios where activo=1").fetchone()[0]
    total_wallets = conn.execute("select count(*) from wallets where saldo_tokens > 0").fetchone()[0]
    total_retiros = conn.execute("select coalesce(sum(cantidad),0) from retiros where estado='completado'").fetchone()[0]
    conn.close()
    return {
        "total_emitido": total_emitido,
        "total_quemado": total_quemado,
        "total_usuarios": total_usuarios,
        "total_wallets_activos": total_wallets,
        "total_retirado": total_retiros,
        "circulacion_efectiva": max(0, total_emitido - total_quemado - (total_retiros or 0)),
    }

def calcular_recompensa_mineria(uid, horas, nivel_uptime="bronce", es_happy_hour=False):
    """calcula y acredita recompensa de mineria."""
    multiplicadores = {"bronce": 1.0, "plata": 1.2, "oro": 1.5, "diamante": 2.0}
    mult = multiplicadores.get(nivel_uptime.lower(), 1.0)
    if es_happy_hour:
        mult *= 2
    tokens = horas * 10 * mult
    resultado = acreditar_tokens(uid, tokens, f"mineria_{horas}h_{nivel_uptime}{'_hh' if es_happy_hour else ''}")
    resultado["horas"] = horas
    resultado["nivel"] = nivel_uptime
    resultado["happy_hour"] = es_happy_hour
    return resultado

def ejecutar_quema_inactividad():
    """ejecuta quema de tokens por inactividad."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # quemar 1% de saldo a wallets inactivas por mas de 7 dias
    rows = conn.execute(
        "select w.usuario_id, w.wallet, w.saldo_tokens from wallets w where w.ultima_actividad < datetime('now','localtime','-7 days') and w.saldo_tokens > 0"
    ).fetchall()
    total_quemado = 0
    for row in rows:
        quema = max(1, row["saldo_tokens"] * 0.01)
        conn.execute("update wallets set saldo_tokens = saldo_tokens - ? where wallet = ?", (quema, row["wallet"]))
        conn.execute("insert into transacciones (wallet_origen, monto, tipo, concepto) values (?,?,?,?)",
                     (row["wallet"], quema, "quema", "quema_por_inactividad"))
        total_quemado += quema
    conn.commit()
    conn.close()
    return {"ok": True, "quemado": total_quemado, "wallets_afectadas": len(rows)}

def procesar_retiro(uid, cantidad):
    """procesa una solicitud de retiro."""
    wallet = obtener_wallet_por_usuario(uid)
    if not wallet:
        return {"ok": False, "error": "wallet no encontrada"}
    if wallet["saldo_tokens"] < cantidad:
        return {"ok": False, "error": "saldo insuficiente"}
    conn = sqlite3.connect(DB_PATH)
    conn.execute("insert into retiros (wallet, cantidad, estado) values (?,?,?)",
                 (wallet["wallet"], cantidad, "pendiente"))
    conn.commit()
    conn.close()
    return {"ok": True, "mensaje": f"retiro de {cantidad} kbt solicitado"}

# ==================== clase TokenomicsManager para api_endpoints.py ====================

class TokenomicsManager:
    def __init__(self):
        init_tokenomics_db()

    def obtener_balance(self, email):
        wallet = obtener_wallet_por_email(email)
        if wallet:
            return wallet["saldo_tokens"]
        return 0

    def recargar(self, email, cantidad, concepto="recarga_manual"):
        wallet = obtener_wallet_por_email(email)
        if not wallet:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            user = conn.execute("select id from usuarios where lower(email)=lower(?)", (email,)).fetchone()
            conn.close()
            if user:
                crear_wallet(user["id"])
                wallet = obtener_wallet_por_email(email)
            else:
                return {"ok": False, "error": "usuario no encontrado"}
        return acreditar_tokens(wallet["usuario_id"], cantidad, concepto)

    def estadisticas(self):
        return obtener_estadisticas_kbt()

    def kbt_stats(self):
        return obtener_estadisticas_kbt()