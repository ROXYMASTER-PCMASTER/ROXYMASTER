# ver_tablas.py
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from db import ejecutar_sql
rows = ejecutar_sql("select name from sqlite_master where type='table' order by name")
for r in rows:
    print(r["name"])