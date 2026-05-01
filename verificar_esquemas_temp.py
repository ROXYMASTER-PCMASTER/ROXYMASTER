"""consulta los esquemas reales de las tablas en roxymaster.db."""
import sqlite3
import os

DB = r"C:\users\pcmaster\desktop\roxymaster\pcmaster\data\roxymaster.db"

conn = sqlite3.connect(DB)

tablas = ["wallets", "ordenes_marketplace", "usuarios", "perfiles", "referidos", "sesiones", "parametros", "reserva"]

for tabla in tablas:
    try:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({tabla})").fetchall()]
        print(f"{tabla}: {cols}")
    except Exception as e:
        print(f"{tabla}: ERROR - {e}")

conn.close()
print("\nlisto.")