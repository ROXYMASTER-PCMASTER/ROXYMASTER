"""ver esquema de usuarios para saber columnas reales"""
import sqlite3
conn = sqlite3.connect(r"C:\users\pcmaster\desktop\roxymaster\pcmaster\data\roxymaster.db")
rows = conn.execute("pragma table_info(usuarios)").fetchall()
for r in rows:
    print(r)
conn.close()