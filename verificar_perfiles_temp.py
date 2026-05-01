import sqlite3
conn = sqlite3.connect('c:/users/pcmaster/desktop/roxymaster/pcmaster/data/roxymaster.db')
rows = conn.execute("select * from perfiles").fetchall()
print("cantidad de perfiles:", len(rows))
for r in rows[:5]:
    print(r)
conn.close()