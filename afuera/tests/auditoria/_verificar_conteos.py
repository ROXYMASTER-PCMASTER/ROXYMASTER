import sqlite3

conn = sqlite3.connect(r"pcmaster\data\roxymaster.db")
c = conn.cursor()

tables = [
    "usuarios", "wallets", "perfiles", "sesiones",
    "ordenes_p2p", "transacciones", "referidos", "mensajes",
    "retiros", "comandos", "codigos_referido",
    "urls_asignadas", "sesiones_activas"
]

print("=== conteos generales ===")
for t in tables:
    c.execute("SELECT COUNT(*) FROM " + t)
    cnt = c.fetchone()[0]
    print("  " + t + ": " + str(cnt))

print("\n=== usuarios test_ ===")
c.execute("SELECT id, email, username, rol, nivel_fiabilidad, modo FROM usuarios WHERE email LIKE 'test_%' ORDER BY id")
rows = c.fetchall()
print("  total: " + str(len(rows)))
for r in rows:
    print("  id=" + str(r[0]) + " email=" + r[1] + " rol=" + r[4] + " modo=" + r[5])

conn.close()