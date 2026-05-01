import sqlite3
conn = sqlite3.connect('c:/users/pcmaster/desktop/roxymaster/pcmaster/data/roxymaster.db')
print("=== wallets schema ===")
rows = conn.execute("pragma table_info('wallets')").fetchall()
for r in rows:
    print(r)
print("\n=== wallets data ===")
rows = conn.execute("select * from wallets").fetchall()
for r in rows:
    print(r)
conn.close()