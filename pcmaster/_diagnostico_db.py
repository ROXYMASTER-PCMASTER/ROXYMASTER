import sqlite3
conn = sqlite3.connect('pcmaster/data/roxymaster.db')
conn.row_factory = sqlite3.Row

u = conn.execute('select id, email, username, pcbot_id, roxy_api_key, roxy_workspace_id from usuarios where email = ?', ('prueba1@roxymaster.local',)).fetchone()
if u:
    print('=== USUARIO ===')
    for k in u.keys():
        print(f'  {k}: {u[k]}')
    
    uid = u['id']
    
    comps = conn.execute('select * from computadoras where usuario_id = ?', (uid,)).fetchall()
    print(f'\n=== COMPUTADORAS ({len(comps)}) ===')
    for c in comps:
        for k in c.keys():
            print(f'  {k}: {c[k]}')
        print('---')
    
    perfiles = conn.execute('select * from perfiles where usuario_id = ?', (uid,)).fetchall()
    print(f'\n=== PERFILES ({len(perfiles)}) ===')
    for p in perfiles:
        print(f'  id={p["id"]} nombre={p["nombre_perfil"]} estado={p["estado"]} hash_id={p["hash_id"]} pcbot_id={p["pcbot_id"]}')
    
    apks = conn.execute('select * from apikeys_roxybrowser where usuario_id = ?', (uid,)).fetchall()
    print(f'\n=== APIKEYS_ROXYBROWSER ({len(apks)}) ===')
    for a in apks:
        for k in a.keys():
            print(f'  {k}: {a[k]}')

    # perfiles_roxy_ext
    ext = conn.execute('select * from perfiles_roxy_ext where usuario_id = ?', (uid,)).fetchall()
    print(f'\n=== PERFILES_ROXY_EXT ({len(ext)}) ===')
    for e in ext:
        for k in e.keys():
            print(f'  {k}: {e[k]}')
        print('---')
else:
    print('USUARIO NO ENCONTRADO')

conn.close()