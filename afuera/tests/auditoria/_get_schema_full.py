import sqlite3

db_path = r"pcmaster\data\roxymaster.db"
conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [t[0] for t in c.fetchall()]
for t in tables:
    print(f'=== {t} ===')
    c.execute(f'PRAGMA table_info({t})')
    cols = c.fetchall()
    for col in cols:
        print(f'  {col[1]} ({col[2]}) nullable={not col[3]} default={col[4]} pk={col[5]}')
    print()
conn.close()