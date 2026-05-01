import sqlite3
conn = sqlite3.connect('c:/users/pcmaster/desktop/roxymaster/pcmaster/data/roxymaster.db')
conn.execute("update wallets set saldo_tokens = saldo_tokens + 1500 where usuario_id = 7")
conn.commit()
conn.close()
print('ok')