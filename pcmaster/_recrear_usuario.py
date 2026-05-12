# _recrear_usuario.py - recrea el usuario prueba1
import sys, os, hashlib, secrets, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))
from db import ejecutar_sql, ejecutar_sql_unico, ejecutar_insercion, init_db

iteraciones = 310000

def hash_pwd(p):
    s = secrets.token_hex(24)
    h = hashlib.pbkdf2_hmac("sha256", p.encode(), s.encode(), iteraciones, dklen=64)
    return f"pbkdf2:{iteraciones}:{s}:{h.hex()}"

init_db()
email = "prueba1@roxymaster.local"
pw = "12345678"
ph = hash_pwd(pw)
uname = "prueba1"
wallet = "kbt_" + uuid.uuid4().hex[:24]
codigo = "prueba1x"
# asegurarse que el codigo no exista ya
ex_cod = ejecutar_sql_unico("select id from codigos_referido where codigo = ?", (codigo,))
while ex_cod:
    codigo = "prueba1x_" + uuid.uuid4().hex[:6]
    ex_cod = ejecutar_sql_unico("select id from codigos_referido where codigo = ?", (codigo,))
rol = "usuario"
nivel = "plata"
uptime = 120.5
pcbot = "pcbot_prueba1"
modo = "conectado"
fecha = "2026-05-08 12:00:00"
login = "2026-05-08 12:30:00"
apikey = secrets.token_hex(32)
wsid = "ws_" + uuid.uuid4().hex[:16]

# si existe, borrar primero
ex = ejecutar_sql_unico("select id from usuarios where email = ?", (email,))
if ex:
    uid = ex["id"]
    print(f"usuario {email} ya existe con id={uid}, eliminando...")
    for t in ["transacciones", "ordenes_p2p", "sesiones", "referidos", "perfiles", "perfiles_roxy", "comandos", "codigos_referido", "wallets", "sessions"]:
        try:
            if t == "transacciones":
                ejecutar_sql("delete from transacciones where origen_id = ? or destino_id = ?", (uid, uid))
            elif t == "ordenes_p2p":
                ejecutar_sql("delete from ordenes_p2p where vendedor_id = ? or comprador_id = ?", (uid, uid))
            elif t in ("referidos",):
                ejecutar_sql("delete from referidos where referidor_id = ? or referido_id = ?", (uid, uid))
            else:
                ejecutar_sql(f"delete from {t} where usuario_id = ?", (uid,))
        except Exception as exx:
            print(f"  saltando {t}: {exx}")
    ejecutar_sql("delete from usuarios where id = ?", (uid,))
    print(f"  usuario {uid} eliminado")

uid = ejecutar_insercion(
    "insert into usuarios (email,password_hash,username,rol,wallet,codigo_referido,referido_por,referido_cambiado,nivel_fiabilidad,uptime_horas,pcbot_id,modo,ultimo_login,fecha_registro,roxy_api_key,roxy_workspace_id,activo) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)",
    (email,ph,uname,rol,wallet,codigo,"superadmin",0,nivel,uptime,pcbot,modo,login,fecha,apikey,wsid),
)
if not uid:
    print("error creando usuario")
    exit(1)

# wallet
ejecutar_insercion(
    "insert into wallets (usuario_id,balance,minado_total,recolectado_total,comprado_total,retirado_total,staking_total,staking_desde) values (?,?,?,?,?,?,?,?)",
    (uid, 5000.0, 2500.0, 1500.0, 1000.0, 200.0, 1000.0, "2026-03-01"),
)
# codigo referido
ejecutar_insercion("insert into codigos_referido (usuario_id,codigo) values (?,?)", (uid, codigo))
# 3 perfiles
ips = ["190.42.113.10", "190.42.113.11", "190.42.113.12"]
perfiles = [
    ("perfil_local_p1", "local", "activo", ips[0]),
    ("perfil_roxy_p1", "roxy", "activo", ips[1]),
    ("perfil_vip_p1", "vip", "inactivo", ips[2]),
]
for n, t, e, ip in perfiles:
    ejecutar_insercion(
        "insert into perfiles (usuario_id,nombre_perfil,tipo,estado,ip_wan,horas_conexion,horas_en_uso,horas_hh) values (?,?,?,?,?,?,?,?)",
        (uid, n, t, e, ip, 120.0, 85.0, 30.0),
    )

print(f"[ok] usuario prueba1 creado:")
print(f"     email:    prueba1@roxymaster.local")
print(f"     password: 12345678")
print(f"     rol:      usuario")
print(f"     balance:  5,000.00 kbt")
print(f"     perfiles: 3")
print(f"     id:       {uid}")
print()
print("verificando pcbot_id en usuarios:")
row = ejecutar_sql_unico("select id, email, pcbot_id from usuarios where email = ?", (email,))
print(f"  id={row['id']}, email={row['email']}, pcbot_id={row['pcbot_id']}")