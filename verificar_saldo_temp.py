import sqlite3
conn = sqlite3.connect('c:/users/pcmaster/desktop/roxymaster/pcmaster/data/roxymaster.db')
row = conn.execute("select saldo_tokens from wallets where usuario_id = 7").fetchone()
if row:
    print(row[0])
else:
    print('no encontrado')
conn.close()