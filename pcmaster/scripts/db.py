# db.py - inicializador de base de datos unificada roxymaster v8.3
# todas las tablas en una sola base sqlite: data/roxymaster.db
# todos los nombres en minusculas, utf-8 sin bom

import sqlite3
from config_loader import ruta_db
from contextlib import contextmanager

_db_path = ruta_db

# ---------------------------------------------------------------------------
# esquema unificado (26 tablas - agregadas: personas, computadoras, apikeys_roxybrowser, perfiles_roxy_ext, billeteras, retiros_billetera)
# ---------------------------------------------------------------------------
esquema_sql = """
pragma journal_mode=WAL;
pragma foreign_keys=ON;

-- tabla 0: personas fisicas (1 persona real -> N cuentas)
create table if not exists personas (
    id integer primary key autoincrement,
    nombre_real text default '',
    dni text default '',
    telefono text default '',
    pais text default '',
    fecha_registro text default (datetime('now','localtime'))
);

create table if not exists usuarios (
    id integer primary key autoincrement,
    persona_id integer references personas(id),
    email text unique not null,
    password_hash text not null,
    username text,
    rol text default 'usuario',
    wallet text unique,
    codigo_referido text unique,
    referido_por text default 'pcmaster',
    referido_cambiado integer default 0,
    nivel_fiabilidad text default 'bronce',
    uptime_horas real default 0,
    pcbot_id text,
    modo text default 'conectado',
    ultimo_login text,
    fecha_registro text default (datetime('now','localtime')),
    roxy_api_key text default '',
    roxy_workspace_id text default '',
    activo integer default 1
);

create table if not exists sesiones (
    token text primary key,
    usuario_id integer not null,
    email text not null,
    rol text not null,
    fecha_creacion text default (datetime('now','localtime')),
    fecha_expiracion text not null,
    foreign key (usuario_id) references usuarios(id)
);

-- tabla: billeteras (cada usuario puede tener varias billeteras de distintos tipos)
create table if not exists billeteras (
    id integer primary key autoincrement,
    usuario_id integer not null,
    tipo text default 'kbt',  -- kbt, sol, usdt
    balance real default 0,
    minado_total real default 0,
    recolectado_total real default 0,
    comprado_total real default 0,
    retirado_total real default 0,
    staking_total real default 0,
    staking_desde text,
    actualizado text default (datetime('now','localtime')),
    foreign key (usuario_id) references usuarios(id)
);

create table if not exists transacciones (
    id integer primary key autoincrement,
    origen_id integer,
    destino_id integer,
    tipo text not null,
    monto real not null,
    concepto text,
    fecha text default (datetime('now','localtime')),
    foreign key (origen_id) references usuarios(id),
    foreign key (destino_id) references usuarios(id)
);

create table if not exists reserva (
    id integer primary key check(id=1),
    tokens real default 0,
    soles real default 0
);

create table if not exists genesis (
    id integer primary key,
    etapa integer unique,
    porcentaje real,
    tokens real generated always as (15000000.0 * porcentaje) stored,
    liberado integer default 0,
    fecha_liberacion text
);

create table if not exists perfiles (
    id integer primary key autoincrement,
    usuario_id integer not null,
    nombre_perfil text,
    tipo text default 'local',
    estado text default 'inactivo',
    ip_wan text,
    horas_conexion real default 0,
    horas_en_uso real default 0,
    horas_hh real default 0,
    ultimo_heartbeat text,
    workspace_id text default '',
    hash_id text default '',
    name_id text default '',
    total_perfiles_roxy integer default 0,
    computadora_id integer,
    foreign key (usuario_id) references usuarios(id)
);

create table if not exists referidos (
    id integer primary key autoincrement,
    referidor_id integer not null,
    referido_id integer not null unique,
    nivel integer not null,
    comisiones_generadas real default 0,
    fecha_activacion text,
    foreign key (referidor_id) references usuarios(id),
    foreign key (referido_id) references usuarios(id)
);

create table if not exists codigos_referido (
    usuario_id integer primary key,
    codigo text unique not null,
    activo integer default 1,
    foreign key (usuario_id) references usuarios(id)
);

create table if not exists ordenes_p2p (
    id integer primary key autoincrement,
    vendedor_id integer not null,
    comprador_id integer,
    cantidad_kbt real not null,
    precio_pen real not null,
    tipo text default 'venta',
    estado text default 'abierta',
    fecha_creacion text default (datetime('now','localtime')),
    fecha_escrow text,
    fecha_completada text,
    foreign key (vendedor_id) references usuarios(id),
    foreign key (comprador_id) references usuarios(id)
);

create table if not exists retiros_wallet (
    id integer primary key autoincrement,
    usuario_id integer not null,
    billetera_id integer not null,
    cantidad_kbt real not null,
    cantidad_pen real not null,
    comision real not null,
    estado text default 'pendiente',
    fecha_solicitud text default (datetime('now','localtime')),
    fecha_procesado text,
    foreign key (usuario_id) references usuarios(id),
    foreign key (billetera_id) references billeteras(id)
);

create table if not exists happy_hour (
    id integer primary key autoincrement,
    multiplicador real default 2.0,
    fecha_inicio text not null,
    fecha_fin text not null,
    activo integer default 1
);

create table if not exists variables_globales (
    clave text primary key,
    valor text not null
);

create table if not exists comandos (
    id integer primary key autoincrement,
    comando_id text unique not null,
    tipo text not null,
    parametros text,
    estado text default 'pendiente',
    fecha_creacion text default (datetime('now','localtime')),
    fecha_ejecucion text,
    resultado text,
    streamer text,
    pcbot_id text
);

create table if not exists urls_asignadas (
    id integer primary key autoincrement,
    url text not null,
    streamer text,
    perfiles_asignados integer default 0,
    duracion_min integer default 60,
    comentarios_activos integer default 0,
    estado text default 'activa',
    fecha_asignacion text default (datetime('now','localtime')),
    fecha_fin text,
    pcbot_id text
);

create table if not exists sesiones_activas (
    id integer primary key autoincrement,
    perfil_id text not null,
    url text,
    streamer text,
    estado text default 'activo',
    inicio text default (datetime('now','localtime')),
    fin text
);

create table if not exists eventos_seguridad (
    id integer primary key autoincrement,
    tipo text not null,
    pcbot_id text,
    detalle text,
    ip_origen text,
    fecha text default (datetime('now','localtime'))
);

create table if not exists mensajes (
    id integer primary key autoincrement,
    origen_id integer not null,
    destino_id integer not null,
    texto text not null,
    leido integer default 0,
    asunto text default '',
    fecha text default (datetime('now','localtime')),
    foreign key (origen_id) references usuarios(id),
    foreign key (destino_id) references usuarios(id)
);

-- tabla: computadoras (cada PC del usuario, registrada antes o despues del login)
create table if not exists computadoras (
    id integer primary key autoincrement,
    pcbot_id text unique not null,
    usuario_id integer,
    hostname text,
    ip_wan text,
    ip_local text,
    mac text default '',
    sistema_operativo text,
    pais text default '',
    api_key_roxy text default '',
    workspace_id text default '',
    estado text default 'pendiente',
    instalado_el text default (datetime('now','localtime')),
    ultimo_heartbeat text,
    ultima_conexion text,
    fecha_vinculacion text,
    foreign key (usuario_id) references usuarios(id)
);

-- tabla: apikeys_roxybrowser (api keys separadas por computadora)
create table if not exists apikeys_roxybrowser (
    id integer primary key autoincrement,
    usuario_id integer not null,
    computadora_id integer,
    api_key text not null,
    workspace_id text default '',
    estado text default 'activa',
    fecha_agregada text default (datetime('now','localtime')),
    fecha_vencimiento text,
    foreign key (usuario_id) references usuarios(id),
    foreign key (computadora_id) references computadoras(id)
);

-- tabla: perfiles_roxy_ext (perfiles reales sincronizados desde roxybrowser)
create table if not exists perfiles_roxy_ext (
    id integer primary key autoincrement,
    computadora_id integer not null,
    usuario_id integer not null,
    apikey_id integer,
    hash_id text,
    name_id text,
    workspace_id text,
    nombre text,
    estado text default 'activo',
    ultima_sincronizacion text,
    foreign key (computadora_id) references computadoras(id),
    foreign key (usuario_id) references usuarios(id),
    foreign key (apikey_id) references apikeys_roxybrowser(id)
);

-- tabla: pcbots_registrados (mantenida para compatibilidad, ahora con FK)
create table if not exists pcbots_registrados (
    id integer primary key autoincrement,
    pcbot_id text unique not null,
    hostname text,
    usuario text,
    ip_local text,
    ip_tailscale text,
    ip_wan text,
    workspace_id text,
    perfiles_roxy text,
    perfiles_vip text,
    navegadores text,
    browser_path text,
    user_data_dir text,
    debugging_port integer,
    session_exists integer default 0,
    modo text default 'desconocido',
    version_agente text,
    estado text default 'conectado',
    ultimo_heartbeat text,
    ultima_conexion text default (datetime('now','localtime')),
    kbt_acumulados real default 0,
    perfiles_activos integer default 0,
    uptime_segundos integer default 0,
    secreto_shs text default ''
);

-- indices para busquedas frecuentes
create index if not exists idx_mensajes_destino on mensajes(destino_id);
create index if not exists idx_sesiones_usuario on sesiones(usuario_id);
create index if not exists idx_transacciones_origen on transacciones(origen_id);
create index if not exists idx_transacciones_destino on transacciones(destino_id);
create index if not exists idx_transacciones_fecha on transacciones(fecha);
create index if not exists idx_referidos_referidor on referidos(referidor_id);
create index if not exists idx_referidos_referido on referidos(referido_id);
create index if not exists idx_retiros_usuario on retiros_wallet(usuario_id);
create index if not exists idx_retiros_estado on retiros_wallet(estado);
create index if not exists idx_perfiles_usuario on perfiles(usuario_id);
create index if not exists idx_comandos_estado on comandos(estado);
create index if not exists idx_comandos_pcbot on comandos(pcbot_id);
create index if not exists idx_urls_streamer on urls_asignadas(streamer);
create index if not exists idx_urls_estado on urls_asignadas(estado);
create index if not exists idx_sesiones_activas_perfil on sesiones_activas(perfil_id);
create index if not exists idx_eventos_pcbot on eventos_seguridad(pcbot_id);
create index if not exists idx_computadoras_usuario on computadoras(usuario_id);
create index if not exists idx_computadoras_pcbot on computadoras(pcbot_id);
create index if not exists idx_apikeys_usuario on apikeys_roxybrowser(usuario_id);
create index if not exists idx_apikeys_computadora on apikeys_roxybrowser(computadora_id);
create index if not exists idx_perfiles_ext_computadora on perfiles_roxy_ext(computadora_id);
create index if not exists idx_personas_dni on personas(dni);
"""


def init_db():
    """crea todas las tablas si no existen y llena datos iniciales."""
    conn = sqlite3.connect(_db_path)
    conn.executescript(esquema_sql)
    conn.commit()

    # migraciones para columnas agregadas en versiones posteriores
    migraciones = [
        ("usuarios", "roxy_api_key", "text default ''"),
        ("usuarios", "roxy_workspace_id", "text default ''"),
        ("usuarios", "persona_id", "integer references personas(id)"),
        ("mensajes", "asunto", "text default ''"),
        ("perfiles", "workspace_id", "text default ''"),
        ("perfiles", "hash_id", "text default ''"),
        ("perfiles", "name_id", "text default ''"),
        ("perfiles", "total_perfiles_roxy", "integer default 0"),
        ("perfiles", "computadora_id", "integer"),
    ]
    for tabla, columna, tipo in migraciones:
        try:
            cursor = conn.execute(f"pragma table_info({tabla})")
            columnas_existentes = [fila[1] for fila in cursor.fetchall()]
            if columna not in columnas_existentes:
                conn.execute(f"alter table {tabla} add column {columna} {tipo}")
                print(f"migracion: columna {columna} agregada a {tabla}")
        except Exception as e:
            print(f"migracion omitida para {tabla}.{columna}: {e}")
    conn.commit()

    # insertar reserva si no existe
    conn.execute(
        "insert or ignore into reserva (id, tokens, soles) values (1, 0, 0)"
    )
    # insertar etapas genesis si no existen (15M tokens)
    etapas_genesis = [
        (1, 1, 0.100, 0, "2026-06-01"),
        (2, 2, 0.070, 0, "2026-09-01"),
        (3, 3, 0.060, 0, "2026-12-01"),
        (4, 4, 0.060, 0, "2027-03-01"),
        (5, 5, 0.050, 0, "2027-06-01"),
        (6, 6, 0.050, 0, "2027-09-01"),
        (7, 7, 0.050, 0, "2027-12-01"),
        (8, 8, 0.040, 0, "2028-03-01"),
        (9, 9, 0.030, 0, "2028-06-01"),
        (10, 10, 0.020, 0, "2028-09-01"),
        (11, 11, 0.020, 0, "2028-12-01"),
        (12, 12, 0.010, 0, "2029-03-01"),
    ]
    for etapa in etapas_genesis:
        conn.execute(
            "insert or ignore into genesis (id, etapa, porcentaje, liberado, fecha_liberacion) values (?, ?, ?, ?, ?)",
            etapa,
        )
    conn.commit()
    conn.close()


def get_db() -> sqlite3.Connection:
    """devuelve una conexion a la base de datos con row_factory habilitado."""
    conn = sqlite3.connect(_db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys=ON")
    return conn


@contextmanager
def get_db_context():
    """context manager para conexion segura a la base de datos."""
    conn = get_db()
    try:
        yield conn
    finally:
        conn.close()


def ejecutar_sql(sql: str, params: tuple = ()) -> list:
    """ejecuta una consulta sql y devuelve todos los resultados como lista de diccionarios."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.commit()
    conn.close()
    return rows


def ejecutar_sql_unico(sql: str, params: tuple = ()) -> dict:
    """ejecuta una consulta sql y devuelve un unico registro como diccionario, o None."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def ejecutar_insercion(sql: str, params: tuple = ()) -> int:
    """ejecuta una insercion sql y devuelve el lastrowid."""
    conn = sqlite3.connect(_db_path)
    cursor = conn.cursor()
    cursor.execute(sql, params)
    conn.commit()
    last_id = cursor.lastrowid
    conn.close()
    return last_id


def obtener_todas_variables():
    conn = get_db()
    rows = conn.execute("SELECT clave, valor FROM variables_globales").fetchall()
    conn.close()
    return {row["clave"]: row["valor"] for row in rows}


def obtener_computadoras_por_usuario(usuario_id: int) -> list:
    """devuelve todas las computadoras asociadas a un usuario."""
    return ejecutar_sql(
        "select pcbot_id, hostname, ip_wan, ip_local, api_key_roxy, estado "
        "from computadoras where usuario_id = ?",
        (usuario_id,),
    )


def guardar_perfiles(usuario_id: int, pcbot_id: str, perfiles: list, workspace_id: str = "") -> int:
    """inserta o actualiza perfiles de roxybrowser.
    devuelve cantidad de perfiles procesados."""
    contador = 0
    for perfil in perfiles:
        hash_id = perfil.get("hash_id", perfil.get("dirId", ""))
        nombre = perfil.get("nombre", perfil.get("name", ""))
        username = perfil.get("userName", "")
        estado = perfil.get("estado", perfil.get("state", "desconocido"))
        horas = perfil.get("horas_conectado", 0) or 0

        existente = ejecutar_sql_unico(
            "select id from perfiles_roxy_ext where usuario_id = ? and hash_id = ?",
            (usuario_id, hash_id),
        )
        if existente:
            ejecutar_sql(
                "update perfiles_roxy_ext set nombre=?, estado=?, ultima_sincronizacion=datetime('now','localtime') "
                "where id=?",
                (nombre, estado, existente["id"]),
            )
        else:
            ejecutar_insercion(
                "insert into perfiles_roxy_ext (usuario_id, hash_id, name_id, workspace_id, nombre, estado, "
                "ultima_sincronizacion) values (?, ?, ?, ?, ?, ?, datetime('now','localtime'))",
                (usuario_id, hash_id, username, workspace_id, nombre, estado),
            )
        contador += 1
    return contador
