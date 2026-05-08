# marketplace.py - ordenes p2p, escrow, comision 15%. roxymaster v8.3
# todos los nombres en minusculas, utf-8 sin bom, <= 400 lineas

from datetime import datetime
from db import ejecutar_sql, ejecutar_sql_unico, ejecutar_insercion
from variables_globales import comision_marketplace


def _ahora_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# crear orden de venta p2p
# ---------------------------------------------------------------------------
def crear_orden(
    vendedor_id: int,
    cantidad_kbt: float,
    precio_pen: float,
    tipo: str = "venta",
    comentario: str = None,
) -> dict:
    """
    crea una orden p2p. el vendedor bloquea los kbt en escrow.
    tipo puede ser 'venta' o 'compra'.
    """
    if cantidad_kbt <= 0 or precio_pen <= 0:
        return {"exito": False, "error": "cantidad y precio deben ser positivos"}

    if tipo not in ("venta", "compra"):
        return {"exito": False, "error": "tipo invalido, debe ser 'venta' o 'compra'"}

    # verificar saldo del vendedor si es venta
    if tipo == "venta":
        wallet = ejecutar_sql_unico("select balance from wallets where usuario_id = ?", (vendedor_id,))
        if not wallet or wallet["balance"] < cantidad_kbt:
            return {"exito": False, "error": "saldo insuficiente para crear la orden"}
        # bloquear tokens en escrow (debitar del balance)
        ejecutar_sql("update wallets set balance = balance - ? where usuario_id = ?",
                     (cantidad_kbt, vendedor_id))

    orden_id = ejecutar_insercion(
        """insert into ordenes_p2p (vendedor_id, comprador_id, cantidad_kbt, precio_pen, tipo, estado, fecha_creacion)
           values (?, null, ?, ?, ?, 'abierta', ?)""",
        (vendedor_id, cantidad_kbt, precio_pen, tipo, _ahora_str()),
    )

    if not orden_id:
        # revertir si fallo
        if tipo == "venta":
            ejecutar_sql("update wallets set balance = balance + ? where usuario_id = ?",
                         (cantidad_kbt, vendedor_id))
        return {"exito": False, "error": "error al crear la orden"}

    return {
        "exito": True,
        "orden_id": orden_id,
        "cantidad_kbt": cantidad_kbt,
        "precio_pen": precio_pen,
        "total_pen": round(cantidad_kbt * precio_pen, 2),
        "comision_pct": comision_marketplace * 100,
    }


# ---------------------------------------------------------------------------
# tomar orden de compra (aceptar una orden abierta)
# ---------------------------------------------------------------------------
def tomar_orden(comprador_id: int, orden_id: int) -> dict:
    """un comprador acepta una orden abierta y la marca como 'en_escrow'."""
    orden = ejecutar_sql_unico(
        "select * from ordenes_p2p where id = ? and estado = 'abierta'", (orden_id,)
    )
    if not orden:
        return {"exito": False, "error": "orden no encontrada o ya no esta disponible"}

    if orden["vendedor_id"] == comprador_id:
        return {"exito": False, "error": "no puedes comprar tu propia orden"}

    # verificar saldo del comprador si la orden es de venta
    if orden["tipo"] == "venta":
        total_pen = orden["cantidad_kbt"] * orden["precio_pen"]
        wallet_comprador = ejecutar_sql_unico(
            "select balance from wallets where usuario_id = ?", (comprador_id,)
        )
        if not wallet_comprador or wallet_comprador["balance"] < total_pen:
            return {"exito": False, "error": "saldo insuficiente para comprar esta orden"}

    # marcar orden como en escrow
    ejecutar_sql(
        "update ordenes_p2p set comprador_id = ?, estado = 'en_escrow', fecha_escrow = ? where id = ?",
        (comprador_id, _ahora_str(), orden_id),
    )

    return {
        "exito": True,
        "orden_id": orden_id,
        "vendedor_id": orden["vendedor_id"],
        "comprador_id": comprador_id,
        "cantidad_kbt": orden["cantidad_kbt"],
        "precio_pen": orden["precio_pen"],
        "estado": "en_escrow",
    }


# ---------------------------------------------------------------------------
# liberar orden (el comprador confirma recepcion)
# ---------------------------------------------------------------------------
def liberar_orden(comprador_id: int, orden_id: int) -> dict:
    """
    el comprador confirma que recibio el pago/fiat y libera los kbt al vendedor.
    aplica la comision del 15% al marketplace.
    """
    orden = ejecutar_sql_unico(
        "select * from ordenes_p2p where id = ? and estado = 'en_escrow' and comprador_id = ?",
        (orden_id, comprador_id),
    )
    if not orden:
        return {"exito": False, "error": "orden no encontrada o no esta en escrow para este comprador"}

    cantidad = orden["cantidad_kbt"]
    comision = round(cantidad * comision_marketplace, 8)
    cantidad_neta = round(cantidad - comision, 8)

    if orden["tipo"] == "venta":
        # transferir kbt al comprador, comision a reserva
        ejecutar_sql("update wallets set balance = balance + ? where usuario_id = ?",
                     (cantidad_neta, comprador_id))
        ejecutar_sql("update wallets set comprado_total = comprado_total + ? where usuario_id = ?",
                     (cantidad_neta, comprador_id))
        # comision al fondo de reserva
        ejecutar_sql("update reserva set tokens = tokens + ? where id = 1", (comision,))
    else:
        # orden de compra: devolver kbt al vendedor mas el pago
        ejecutar_sql("update wallets set balance = balance + ? where usuario_id = ?",
                     (cantidad_neta, orden["vendedor_id"]))

    # registrar transacciones
    ejecutar_insercion(
        "insert into transacciones (origen_id, destino_id, tipo, monto, concepto) values (?, ?, 'p2p_venta', ?, ?)",
        (orden["vendedor_id"], comprador_id, cantidad_neta,
         f"p2p orden #{orden_id}: {cantidad_neta} kbt transferidos"),
    )
    if comision > 0:
        ejecutar_insercion(
            "insert into transacciones (origen_id, destino_id, tipo, monto, concepto) values (?, null, 'comision_p2p', ?, ?)",
            (orden["vendedor_id"], comision, f"comision p2p orden #{orden_id}"),
        )

    ejecutar_sql(
        "update ordenes_p2p set estado = 'completada', fecha_completada = ? where id = ?",
        (_ahora_str(), orden_id),
    )

    return {
        "exito": True,
        "orden_id": orden_id,
        "cantidad_transferida": cantidad_neta,
        "comision": comision,
        "comision_pct": comision_marketplace * 100,
    }


# ---------------------------------------------------------------------------
# cancelar orden
# ---------------------------------------------------------------------------
def cancelar_orden(usuario_id: int, orden_id: int) -> dict:
    """cancela una orden abierta y devuelve los kbt al vendedor."""
    orden = ejecutar_sql_unico(
        "select * from ordenes_p2p where id = ? and vendedor_id = ? and estado in ('abierta', 'en_escrow')",
        (orden_id, usuario_id),
    )
    if not orden:
        return {"exito": False, "error": "orden no encontrada o no puedes cancelarla"}

    # devolver kbt al vendedor
    if orden["tipo"] == "venta":
        ejecutar_sql("update wallets set balance = balance + ? where usuario_id = ?",
                     (orden["cantidad_kbt"], usuario_id))

    ejecutar_sql(
        "update ordenes_p2p set estado = 'cancelada', fecha_completada = ? where id = ?",
        (_ahora_str(), orden_id),
    )

    return {"exito": True, "orden_id": orden_id, "estado": "cancelada"}


# ---------------------------------------------------------------------------
# listar ordenes
# ---------------------------------------------------------------------------
def listar_ordenes(estado: str = None, usuario_id: int = None) -> list:
    """lista ordenes p2p con filtros opcionales."""
    query = "select o.*, u.email as vendedor_email, u2.email as comprador_email from ordenes_p2p o left join usuarios u on o.vendedor_id = u.id left join usuarios u2 on o.comprador_id = u2.id where 1=1"
    params = []
    if estado:
        query += " and o.estado = ?"
        params.append(estado)
    if usuario_id:
        query += " and (o.vendedor_id = ? or o.comprador_id = ?)"
        params.extend([usuario_id, usuario_id])
    query += " order by o.fecha_creacion desc"
    return ejecutar_sql(query, tuple(params))


def obtener_orden(orden_id: int) -> dict:
    """obtiene una orden especifica por id."""
    orden = ejecutar_sql_unico(
        "select o.*, u.email as vendedor_email, u2.email as comprador_email "
        "from ordenes_p2p o left join usuarios u on o.vendedor_id = u.id "
        "left join usuarios u2 on o.comprador_id = u2.id where o.id = ?",
        (orden_id,),
    )
    return dict(orden) if orden else None


# ---------------------------------------------------------------------------
# disputa (admin)
# ---------------------------------------------------------------------------
def resolver_disputa(orden_id: int, a_favor_de: str, admin_id: int) -> dict:
    """
    resuelve una disputa de una orden en escrow.
    a_favor_de: 'vendedor' o 'comprador'.
    """
    orden = ejecutar_sql_unico(
        "select * from ordenes_p2p where id = ? and estado = 'en_escrow'", (orden_id,)
    )
    if not orden:
        return {"exito": False, "error": "orden no encontrada o no esta en escrow"}

    cantidad = orden["cantidad_kbt"]
    comision = round(cantidad * comision_marketplace, 8)
    cantidad_neta = round(cantidad - comision, 8)

    if a_favor_de == "comprador":
        # devolver kbt al comprador
        ejecutar_sql("update wallets set balance = balance + ? where usuario_id = ?",
                     (cantidad, orden["comprador_id"]))
    else:
        # liberar al vendedor
        ejecutar_sql("update wallets set balance = balance + ? where usuario_id = ?",
                     (cantidad_neta, orden["vendedor_id"]))
        # comision a reserva
        ejecutar_sql("update reserva set tokens = tokens + ? where id = 1", (comision,))

    ejecutar_sql(
        "update ordenes_p2p set estado = 'resuelta', fecha_completada = ? where id = ?",
        (_ahora_str(), orden_id),
    )

    return {"exito": True, "orden_id": orden_id, "resuelta_a_favor_de": a_favor_de}