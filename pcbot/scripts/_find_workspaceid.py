import os, sqlite3

base='C:/Users/CYBER/AppData/Roaming/RoxyBrowser/browser-cache/2e137cbf9db8a38c6b6d244556adfd47/Default'
for fname in ['Web Data','Login Data','Cookies']:
    fpath = os.path.join(base, fname)
    if os.path.isfile(fpath):
        try:
            conn=sqlite3.connect(fpath)
            cur=conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables=[r[0] for r in cur.fetchall()]
            print(f'=== {fname}: {tables[:5]} ===')
            for t in tables[:5]:
                try:
                    cur.execute(f'SELECT * FROM "{t}" LIMIT 2')
                    rows=cur.fetchall()
                    if rows:
                        desc=[d[0] for d in cur.description]
                        for i in range(min(len(desc),5)):
                            print(f'  {t}.{desc[i]} = {str(rows[0][i])[:100]}')
                except: pass
            conn.close()
        except Exception as e:
            print(f'{fname}: error {e}')

# buscar en archivos .json plano
print('=== buscando workspace en archivos ===')
for root, dirs, files in os.walk('C:/Users/CYBER/AppData/Roaming/RoxyBrowser'):
    for f in files:
        if f.endswith('.json') or f == 'Preferences':
            fpath=os.path.join(root,f)
            try:
                sz=os.path.getsize(fpath)
                if sz<500000:
                    with open(fpath,'r',encoding='utf-8',errors='ignore') as fp:
                        data=fp.read()
                        if 'workspace' in data.lower():
                            idx=data.lower().find('workspace')
                            print(f'{f}: ...{data[max(0,idx-50):idx+200]}...')
            except: pass