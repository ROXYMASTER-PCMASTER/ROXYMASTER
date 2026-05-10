# _fondear_pruebas.py - agregar fondos a prueba1 y al dueno
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))
from db import ejecutar_sql, ejecutar_sql_unico, ejecutar_insercion

# ---------------------------------------------------------------------------
# 1. prueba1@roxymaster.local: +20000 tokens kbt, +15000 soles
# ---------------------------------------------------------------------------
u1 = ejecutar_sql_unico("select id from usuarios where email=?", ("prueba1@roxymaster.local",))
if not u1:
    print("error: no existe prueba1@roxymaster.local")
    sys.exit(1)
uid1 = u1["id"]

# ver si ya tiene billeteras
b1_kbt = ejecutar_sql_unico("select id from billeteras where usuario_id=? and tipo='kbt'", (uid1,))
if b1_kbt:
    ejecutar_sql("update billeteras set balance=balance+20000 where id=?", (b1_kbt["id"],))
    print(f"  +20000 kbt a prueba1 (billetera {b1_kbt['id']})")
else:
    ejecutar_insercion(
        "insert into billeteras (usuario_id, tipo, balance) values (?, 'kbt', 20000)",
        (uid1,)
    )
    print(f"  billetera kbt creada +20000 para prueba1")

b1_sol = ejecutar_sql_unico("select id from billeteras where usuario_id=? and tipo='sol'", (uid1,))
if b1_sol:
    ejecutar_sql("update billeteras set balance=balance+15000 where id=?", (b1_sol["id"],))
    print(f"  +15000 soles a prueba1 (billetera {b1_sol['id']})")
else:
    ejecutar_insercion(
        "insert into billeteras (usuario_id, tipo, balance) values (?, 'sol', 15000)",
        (uid1,)
    )
    print(f"  billetera sol creada +15000 para prueba1")

# ---------------------------------------------------------------------------
# 2. dueno (superadmin): +1500000 tokens, +3000 soles, +3000 usdt
# ---------------------------------------------------------------------------
u2 = ejecutar_sql_unico("select id, email from usuarios where email='pcmaster@roxymaster.local'")
if not u2:
    u2 = ejecutar_sql_unico("select id, email from usuarios where rol='superadmin' order by id asc limit 1")
if not u2:
    print("error: no se encontro al dueno (superadmin)")
    sys.exit(1)
uid2 = u2["id"]
print(f"dueno encontrado: {u2['email']} (id={uid2})")

for tipo, monto in [("kbt", 1500000), ("sol", 3000), ("usdt", 3000)]:
    b = ejecutar_sql_unico("select id from billeteras where usuario_id=? and tipo=?", (uid2, tipo))
    if b:
        ejecutar_sql("update billeteras set balance=balance+? where id=?", (monto, b["id"]))
        print(f"  +{monto} {tipo} a dueno (billetera {b['id']})")
    else:
        ejecutar_insercion(
            "insert into billeteras (usuario_id, tipo, balance) values (?, ?, ?)",
            (uid2, tipo, monto)
        )
        print(f"  billetera {tipo} creada +{monto} para dueno")

# ---------------------------------------------------------------------------
# 3. actualizar reserva general
# ---------------------------------------------------------------------------
res = ejecutar_sql_unico("select id from reserva where id=1")
if res:
    ejecutar_sql("update reserva set tokens=tokens+1500000+20000, soles=soles+15000+3000 where id=1")
    print("  reserva actualizada (+1,520,000 tokens, +18,000 soles)")
else:
    ejecutar_insercion("insert into reserva (id, tokens, soles) values (1, 1520000, 18000)")
    print("  reserva creada con +1,520,000 tokens, +18,000 soles")

print()
print("=== resumen final ===")
for email in ("prueba1@roxymaster.local", u2["email"]):
    u = ejecutar_sql_unico("select id, email from usuarios where email=?", (email,))
    if not u:
        continue
    bs = ejecutar_sql("select tipo, balance from billeteras where usuario_id=?", (u["id"],))
    for b in bs:
        print(f"  {email} -> {b['tipo']}: {b['balance']:,.2f}")
print("[ok] fondos agregados exitosamente")