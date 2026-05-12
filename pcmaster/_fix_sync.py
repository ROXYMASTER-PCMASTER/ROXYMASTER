import sqlite3
import os
import sys

db_path = os.path.join(os.path.dirname(__file__), 'data', 'roxymaster.db')
conn = sqlite3.connect(db_path)
conn.execute("PRAGMA foreign_keys=OFF")
cur = conn.cursor()

# check data first
cur.execute("SELECT id, usuario_id, pcbot_id FROM computadoras")
print("=== COMPUTADORAS ===")
for r in cur.fetchall():
    print(f"  id={r[0]}, usuario_id={r[1]}, pcbot_id={r[2]}")

cur.execute("SELECT id, email, pcbot_id FROM usuarios WHERE id=30 OR id=29")
print("\n=== USUARIOS RELEVANTES ===")
for r in cur.fetchall():
    print(f"  id={r[0]}, email={r[1]}, pcbot_id={r[2]}")

sqlite_ver = conn.execute("SELECT sqlite_version()").fetchone()[0]
print(f"\nsqlite version: {sqlite_ver}")

# drop existing trigger if any
cur.execute("DROP TRIGGER IF EXISTS trg_computadoras_pcbot_insert")
cur.execute("DROP TRIGGER IF EXISTS trg_computadoras_pcbot_update")

# create two separate triggers (compatible with older sqlite)
cur.execute("""
    CREATE TRIGGER IF NOT EXISTS trg_computadoras_pcbot_insert
    AFTER INSERT ON computadoras
    FOR EACH ROW
    BEGIN
        UPDATE usuarios SET pcbot_id = NEW.pcbot_id WHERE id = NEW.usuario_id;
    END
""")
print("trigger INSERT created")

cur.execute("""
    CREATE TRIGGER IF NOT EXISTS trg_computadoras_pcbot_update
    AFTER UPDATE OF pcbot_id ON computadoras
    FOR EACH ROW
    BEGIN
        UPDATE usuarios SET pcbot_id = NEW.pcbot_id WHERE id = NEW.usuario_id;
    END
""")
print("trigger UPDATE created")

# sync existing data
print("\n=== SINCRONIZANDO DATOS EXISTENTES ===")
cur.execute("""
    UPDATE usuarios 
    SET pcbot_id = (SELECT pcbot_id FROM computadoras WHERE computadoras.usuario_id = usuarios.id LIMIT 1)
    WHERE EXISTS (SELECT 1 FROM computadoras WHERE computadoras.usuario_id = usuarios.id)
""")
conn.commit()
print(f"filas actualizadas: {cur.rowcount}")

# verify
cur.execute("SELECT id, email, pcbot_id FROM usuarios")
print("\n=== USUARIOS DESPUES ===")
for r in cur.fetchall():
    print(f"  id={r[0]}, email={r[1]}, pcbot_id={r[2]}")

conn.close()
print("\n=== OK ===")