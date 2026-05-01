import sqlite3, os, time, secrets
from config import DATA_DIR
DB_PATH = os.path.join(DATA_DIR, "roxymaster.db")

# ==================== funciones wrapper para server.py v8.3 ====================

def init_marketplace_db():
    """inicializa las tablas del marketplace."""
    conn = sqlite3.connect(DB_PATH)
    conn.executescript('''
        create table if not exists ordenes_marketplace (
            id integer primary key autoincrement,
            tipo text not null,
            wallet_vendedor text,
            wallet_comprador text,
            vendedor_uid integer,
            comprador_uid integer,
            vendedor text,
            comprador text,
            cantidad real not null,
            precio_unitario real not null,
            total real,
            estado text default 'activa',
            fecha_creacion text default (datetime('now','localtime')),
            fecha_ejecucion text,
            fecha_cancelacion text,
            foreign key (vendedor_uid) references usuarios(id),
            foreign key (comprador_uid) references usuarios(id)
        );
    ''')
    conn.commit()
    conn.close()

def crear_orden(tipo, wallet_id, uid, cantidad, precio, vendedor_email=None):
    """crea una orden en el marketplace."""
    conn = sqlite3.connect(DB_PATH)
    total = cantidad * precio
    if tipo == "venta":
        conn.execute(
            "insert into ordenes_marketplace (tipo, wallet_vendedor, vendedor_uid, cantidad, precio_unitario, total, estado, vendedor) values (?,?,?,?,?,?,?,?)",
            (tipo, wallet_id, uid, cantidad, precio, total, "activa", vendedor_email)
        )
    else:
        conn.execute(
            "insert into ordenes_marketplace (tipo, wallet_comprador, comprador_uid, cantidad, precio_unitario, total, estado, comprador) values (?,?,?,?,?,?,?,?)",
            (tipo, wallet_id, uid, cantidad, precio, total, "activa", vendedor_email)
        )
    conn.commit()
    orden_id = conn.execute("select last_insert_rowid()").fetchone()[0]
    conn.close()
    return {"ok": True, "orden_id": orden_id, "tipo": tipo, "cantidad": cantidad, "precio_unitario": precio, "total": total}

def cancelar_orden(orden_id):
    """cancela una orden activa."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "update ordenes_marketplace set estado='cancelada', fecha_cancelacion=datetime('now','localtime') where id=? and estado='activa'",
        (orden_id,)
    )
    cambios = conn.total_changes
    conn.commit()
    conn.close()
    if cambios == 0:
        return {"ok": False, "error": "orden no encontrada o ya no esta activa"}
    return {"ok": True, "mensaje": "orden cancelada"}

def ejecutar_orden(orden_id, wallet_comprador, comprador_uid):
    """ejecuta una orden de compra del marketplace."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    orden = conn.execute("select * from ordenes_marketplace where id=? and estado='activa'", (orden_id,)).fetchone()
    if not orden:
        conn.close()
        return {"ok": False, "error": "orden no encontrada o ya no esta activa"}
    orden = dict(orden)
    # verificar que el comprador tiene saldo suficiente
    saldo_comprador = conn.execute("select saldo_tokens from wallets where wallet=?", (wallet_comprador,)).fetchone()
    if not saldo_comprador or saldo_comprador[0] < orden["total"]:
        conn.close()
        return {"ok": False, "error": "saldo insuficiente"}

    # debitar comprador
    conn.execute("update wallets set saldo_tokens = saldo_tokens - ?, ultima_actividad=datetime('now','localtime') where wallet=?",
                 (orden["total"], wallet_comprador))
    # acreditar vendedor
    conn.execute("update wallets set saldo_tokens = saldo_tokens + ?, ultima_actividad=datetime('now','localtime') where wallet=?",
                 (orden["total"], orden["wallet_vendedor"]))
    # marcar orden como completada
    conn.execute(
        "update ordenes_marketplace set estado='completada', wallet_comprador=?, comprador_uid=?, fecha_ejecucion=datetime('now','localtime') where id=?",
        (wallet_comprador, comprador_uid, orden_id))
    # registrar transacciones
    conn.execute("insert into transacciones (wallet_origen, wallet_destino, cantidad, tipo, concepto, orden_id) values (?,?,?,?,?,?)",
                 (wallet_comprador, orden["wallet_vendedor"], orden["total"], "compra_marketplace", f"orden_{orden_id}", orden_id))
    conn.commit()
    conn.close()
    return {"ok": True, "mensaje": "orden ejecutada", "orden_id": orden_id, "total": orden["total"]}

def listar_ordenes_activas(tipo=None):
    """lista ordenes activas del marketplace."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if tipo:
        rows = conn.execute("select * from ordenes_marketplace where estado='activa' and tipo=? order by fecha_creacion desc", (tipo,)).fetchall()
    else:
        rows = conn.execute("select * from ordenes_marketplace where estado='activa' order by fecha_creacion desc").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def obtener_orden(orden_id):
    """obtiene una orden por su id."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("select * from ordenes_marketplace where id=?", (orden_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def obtener_historial_ordenes(limite=50):
    """obtiene el historial de ordenes del marketplace."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("select * from ordenes_marketplace order by fecha_creacion desc limit ?", (limite,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def obtener_estadisticas_marketplace():
    """obtiene estadisticas del marketplace."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    activas = conn.execute("select count(*) as c from ordenes_marketplace where estado='activa'").fetchone()["c"]
    completadas = conn.execute("select count(*) as c from ordenes_marketplace where estado='completada'").fetchone()["c"]
    total_volumen = conn.execute("select coalesce(sum(total),0) as s from ordenes_marketplace where estado='completada'").fetchone()["s"]
    conn.close()
    return {
        "ordenes_activas": activas,
        "ordenes_completadas": completadas,
        "volumen_total": total_volumen,
    }

# ==================== clase MarketplaceManager para api_endpoints.py ====================

class MarketplaceManager:
    def __init__(self):
        init_marketplace_db()

    def crear_oferta(self, email, tokens, precio_soles):
        """crea una oferta de venta."""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        user = conn.execute("select id, wallet from usuarios where lower(email)=lower(?)", (email.strip(),)).fetchone()
        if not user:
            conn.close()
            return {"ok": False, "error": "usuario no encontrado"}
        wallet = conn.execute("select wallet, saldo_tokens from wallets where usuario_id=?", (user["id"],)).fetchone()
        if not wallet:
            conn.close()
            return {"ok": False, "error": "wallet no encontrada"}
        conn.close()
        return crear_orden("venta", wallet["wallet"], user["id"], tokens, precio_soles, email)

    def listar_activas(self, tipo=None):
        return listar_ordenes_activas(tipo)

    def historial(self, limite=50):
        return obtener_historial_ordenes(limite)

    def estadisticas(self):
        return obtener_estadisticas_marketplace()