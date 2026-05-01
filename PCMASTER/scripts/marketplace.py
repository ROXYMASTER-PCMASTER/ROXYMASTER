# ============================================================================
# marketplace.py - modulo de gestion de ordenes p2p roxymaster v8.3
# envuelve las funciones del motor tokenomics para el marketplace
# ============================================================================

import sqlite3
from pathlib import Path
from datetime import datetime

# ---------------------------------------------------------------------------
# configuracion
# ---------------------------------------------------------------------------
_base_dir = Path(__file__).parent.parent.absolute()
_data_dir = _base_dir / 'data'
_db_path = _data_dir / 'roxymaster.db'


# ---------------------------------------------------------------------------
# funciones alias para compatibilidad con server.py
# ---------------------------------------------------------------------------

def crear_orden(tipo: str, wallet: str, usuario_id: int, cantidad: float,
                precio_pen: float = 1.00) -> dict:
    """crea una orden generica (compra o venta) en el marketplace.
    esta funcion existe para compatibilidad con server.py.
    """
    from tokenomics import get_tokenomics
    tk = get_tokenomics()
    return tk.crear_orden(tipo, wallet, usuario_id, cantidad, precio_pen)


def obtener_historial_ordenes(limite: int = 100) -> list:
    """alias de historial_completadas para compatibilidad con server.py."""
    return historial_completadas(limite)


def obtener_estadisticas_marketplace() -> dict:
    """alias de estadisticas_marketplace para compatibilidad con server.py."""
    return estadisticas_marketplace()


# ---------------------------------------------------------------------------
# funciones originales del marketplace
# ---------------------------------------------------------------------------

def crear_orden_compra(wallet: str, usuario_id: int, cantidad: float,
                        precio_pen: float = 1.00) -> dict:
    """crea una orden de compra en el marketplace."""
    from tokenomics import get_tokenomics
    tk = get_tokenomics()
    return tk.crear_orden('compra', wallet, usuario_id, cantidad, precio_pen)


def crear_orden_venta(wallet: str, usuario_id: int, cantidad: float,
                       precio_pen: float = 1.00) -> dict:
    """crea una orden de venta en el marketplace."""
    from tokenomics import get_tokenomics
    tk = get_tokenomics()
    return tk.crear_orden('venta', wallet, usuario_id, cantidad, precio_pen)


def ejecutar_orden(orden_id: int, comprador_wallet: str, comprador_id: int) -> dict:
    """ejecuta una orden del marketplace (compra)."""
    from tokenomics import get_tokenomics
    tk = get_tokenomics()
    return tk.ejecutar_orden(orden_id, comprador_wallet, comprador_id)


def cancelar_orden(orden_id: int) -> dict:
    """cancela una orden activa."""
    from tokenomics import get_tokenomics
    tk = get_tokenomics()
    return tk.cancelar_orden(orden_id)


def listar_ordenes_activas(tipo: str = None) -> list:
    """lista todas las ordenes activas en el marketplace.
    admite filtro opcional por tipo ('compra' o 'venta')."""
    from tokenomics import get_tokenomics
    tk = get_tokenomics()
    ordenes = tk.listar_ordenes_activas()
    if tipo:
        ordenes = [o for o in ordenes if o.get('tipo') == tipo]
    return ordenes


def listar_ordenes_usuario(usuario_id: int) -> list:
    """lista las ordenes de un usuario especifico."""
    conn = sqlite3.connect(str(_db_path))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        'select * from ordenes_marketplace where usuario_id = ? '
        'order by fecha_creacion desc limit 50',
        (usuario_id,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def obtener_orden(orden_id: int) -> dict:
    """obtiene una orden por su id."""
    conn = sqlite3.connect(str(_db_path))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('select * from ordenes_marketplace where id = ?', (orden_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def historial_completadas(limite: int = 100) -> list:
    """devuelve el historial de ordenes completadas."""
    conn = sqlite3.connect(str(_db_path))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "select * from ordenes_marketplace where estado = 'completada' "
        "order by fecha_cierre desc limit ?",
        (limite,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def obtener_libro_ordenes() -> dict:
    """devuelve el libro de ordenes completo (compras y ventas activas)."""
    ordenes = listar_ordenes_activas()
    compras = [o for o in ordenes if o['tipo'] == 'compra']
    ventas = [o for o in ordenes if o['tipo'] == 'venta']
    compras.sort(key=lambda x: x['precio_pen'], reverse=True)
    ventas.sort(key=lambda x: x['precio_pen'])
    return {
        'compras': compras,
        'ventas': ventas,
        'total_activas': len(ordenes),
        'volumen_compras': sum(o['cantidad'] for o in compras),
        'volumen_ventas': sum(o['cantidad'] for o in ventas),
        'precio_compra_max': compras[0]['precio_pen'] if compras else 0,
        'precio_venta_min': ventas[0]['precio_pen'] if ventas else 0,
    }


def emparejar_ordenes() -> list:
    """empareja automaticamente ordenes de compra y venta compatibles."""
    libro = obtener_libro_ordenes()
    operaciones = []
    for venta in libro['ventas']:
        for compra in libro['compras']:
            if (compra['precio_pen'] >= venta['precio_pen']
                    and compra['cantidad'] > 0):
                resultado = ejecutar_orden(
                    venta['id'], compra['wallet'], compra['usuario_id'])
                if resultado.get('ok'):
                    operaciones.append({
                        'venta_id': venta['id'],
                        'compra_id': compra['id'],
                        'cantidad': venta['cantidad'],
                        'precio': venta['precio_pen'],
                        'resultado': resultado,
                    })
                break
    return operaciones


def estadisticas_marketplace() -> dict:
    """devuelve estadisticas del marketplace."""
    conn = sqlite3.connect(str(_db_path))
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "select count(*) as cnt, coalesce(sum(cantidad), 0) as vol "
        "from ordenes_marketplace where estado = 'completada' "
        "and fecha_cierre >= datetime('now', '-24 hours', 'localtime')")
    r24 = dict(c.fetchone())
    c.execute(
        "select count(*) as cnt, coalesce(sum(cantidad), 0) as vol "
        "from ordenes_marketplace where estado = 'completada' "
        "and fecha_cierre >= datetime('now', '-7 days', 'localtime')")
    r7d = dict(c.fetchone())
    c.execute(
        "select count(*) as cnt, coalesce(sum(cantidad), 0) as vol "
        "from ordenes_marketplace where estado = 'completada'")
    rall = dict(c.fetchone())
    c.execute(
        "select avg(precio_pen) as pp from ordenes_marketplace "
        "where estado = 'completada'")
    rp = c.fetchone()
    c.execute(
        "select count(*) as cnt, coalesce(sum(cantidad), 0) as vol "
        "from ordenes_marketplace where estado = 'activa'")
    ract = dict(c.fetchone())
    conn.close()
    return {
        'ultimas_24h_operaciones': r24['cnt'],
        'ultimas_24h_volumen': r24['vol'],
        'ultimos_7d_operaciones': r7d['cnt'],
        'ultimos_7d_volumen': r7d['vol'],
        'total_operaciones': rall['cnt'],
        'total_volumen': rall['vol'],
        'precio_promedio': round(rp['pp'] or 0, 4),
        'ordenes_activas': ract['cnt'],
        'volumen_activo': ract['vol'],
    }


def init_marketplace_db():
    """crea la tabla de ordenes del marketplace si no existe."""
    conn = sqlite3.connect(str(_db_path))
    c = conn.cursor()
    c.execute('''
        create table if not exists ordenes_marketplace (
            id integer primary key autoincrement,
            tipo text not null check(tipo in ('compra', 'venta')),
            wallet text not null,
            usuario_id integer not null,
            cantidad real not null,
            precio_pen real not null,
            estado text default 'activa'
                check(estado in ('activa', 'escrow', 'completada', 'cancelada')),
            fecha_creacion text
                default (datetime('now', 'localtime')),
            fecha_cierre text
        )
    ''')
    conn.commit()
    conn.close()


# inicializar la base de datos al importar el modulo
init_marketplace_db()