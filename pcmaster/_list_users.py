# _list_users.py - listar usuarios con su pcbot_id
import sys
sys.path.insert(0, r'c:\Users\PCMASTER\Desktop\roxymaster\pcmaster\scripts')
from db import ejecutar_sql

users = ejecutar_sql("select id, username, email, pcbot_id, rol from usuarios limit 20")
if not users:
    print("no se encontraron usuarios")
else:
    for u in users:
        print(f"id={u['id']}, username={u['username']}, email={u['email']}, pcbot_id={u['pcbot_id']}, rol={u['rol']}")