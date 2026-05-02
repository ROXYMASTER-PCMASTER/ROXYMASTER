import sqlite3, os
db = r"c:\users\pcmaster\desktop\roxymaster\pcmaster\data\roxymaster.db"
if os.path.exists(db):
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    print("tablas:", tables)
    for t in tables:
        cur.execute(f"PRAGMA table_info({t})")
        cols = [(r[1], r[2]) for r in cur.fetchall()]
        print(f"  {t}: {cols}")
else:
    print("db no existe:", db)