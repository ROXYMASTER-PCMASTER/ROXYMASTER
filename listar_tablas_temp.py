import sqlite3
conn = sqlite3.connect('c:/users/pcmaster/desktop/roxymaster/pcmaster/data/roxymaster.db')
rows = conn.execute("select name from sqlite_master where type='table'").fetchall()
for r in rows:
    print(r[0])
conn.close()