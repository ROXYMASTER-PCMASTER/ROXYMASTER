"""ver esquemas de tablas relevantes"""
import sqlite3
conn = sqlite3.connect(r"C:\users\pcmaster\desktop\roxymaster\pcmaster\data\roxymaster.db")
for tabla in ["wallets", "sesiones", "ordenes_marketplace", "perfiles", "referidos", "granjeros"]:
    try:
        rows = conn.execute(f"pragma table_info({tabla})").fetchall()
        print(f"\n=== {tabla} ===")
        for r in rows:
            print(r)
    except Exception as e:
        print(f"\n=== {tabla} === ERROR: {e}")
conn.close()