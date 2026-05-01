# script temporal para inyectar tokens en pcmaster
import sqlite3

db_path = r"c:\users\pcmaster\desktop\roxymaster\pcmaster\data\roxymaster.db"
conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute(
    "update wallets set saldo_tokens = 1500.0, tokens_minados_total = 1500.0 "
    "where wallet = 'kbt_3452c4cd9200faf2'"
)
conn.commit()

c.execute(
    "select wallet, saldo_tokens, tokens_minados_total "
    "from wallets where wallet = 'kbt_3452c4cd9200faf2'"
)
row = c.fetchone()
print(f"resultado: {row}")
conn.close()