# database.py - inicializacion de bases de datos roxymaster v8.3
import sqlite3, os, json, hashlib
from pathlib import Path

_base_dir = Path(__file__).parent.parent.absolute()
_data_dir = _base_dir / "data"
_db_path = _data_dir / "roxymaster.db"

_data_dir.mkdir(parents=True, exist_ok=True)


def init_all_databases():
    """inicializa todas las tablas necesarias."""
    conn = sqlite3.connect(str(_db_path))
    c = conn.cursor()

    # tabla de usuarios
    c.execute('''
        create table if not exists usuarios (
            uid integer primary key autoincrement,
            email text unique not null,
            password text not null,
            username text not null,
            rol text default 'usuario',
            creado text default (datetime('now', 'localtime')),
            ultimo_login text,
            activo integer default 1,
            referido_por text default 'pcmaster',
            referido_cambiado integer default 0,
            codigo_referido text unique,
            nivel_fiabilidad text default 'bronce',
            uptime_horas real default 0
        )
    ''')

    # tabla de wallets (billeteras kbt)
    c.execute('''
        create table if not exists wallets (
            id integer primary key autoincrement,
            uid integer not null,
            balance real default 0,
            minado_total real default 0,
            recolectado_total real default 0,
            comprado_total real default 0,
            retirado_total real default 0,
            actualizado text default (datetime('now', 'localtime')),
            foreign key (uid) references usuarios(uid)
        )
    ''')

    # tabla de reserva (fondo de recoleccion)
    c.execute('''
        create table if not exists reserva (
            id integer primary key check(id=1),
            tokens real default 0,
            soles real default 0
        );
        insert or ignore into reserva (id, tokens, soles) values (1, 0, 0);
    ''')

    # tabla de genesis (suministro inicial por etapas)
    c.execute('''
        create table if not exists genesis (
            id integer primary key,
            etapa integer unique,
            porcentaje real,
            tokens real generated always as (15000000.0 * porcentaje) stored,
            liberado integer default 0,
            fecha_liberacion text
        );
        insert or ignore into genesis (id, etapa, porcentaje) values (1,1,0.30);
        insert or ignore into genesis (id, etapa, porcentaje) values (2,2,0.30);
        insert or ignore into genesis (id, etapa, porcentaje) values (3,3,0.20);
        insert or ignore into genesis (id, etapa, porcentaje) values (4,4,0.20);
    ''')

    # tabla de perfiles
    c.execute('''
        create table if not exists perfiles (
            id integer primary key autoincrement,
            uid integer not null,
            nombre_perfil text,
            tipo text default 'local',
            estado text default 'inactivo',
            ip_wan text,
            horas_conexion real default 0,
            horas_en_uso real default 0,
            horas_hh real default 0,
            ultimo_heartbeat text,
            foreign key (uid) references usuarios(uid)
        )
    ''')

    # tabla de transacciones
    c.execute('''
        create table if not exists transacciones (
            id integer primary key autoincrement,
            uid_origen integer,
            uid_destino integer,
            tipo text not null,
            monto real not null,
            concepto text,
            fecha text default (datetime('now', 'localtime')),
            foreign key (uid_origen) references usuarios(uid),
            foreign key (uid_destino) references usuarios(uid)
        )
    ''')

    # tabla de transacciones kbt (legado)
    c.execute('''
        create table if not exists transacciones_kbt (
            id integer primary key autoincrement,
            email text not null,
            tipo text not null,
            cantidad real not null,
            fecha text default (datetime('now'))
        )
    ''')

    # tabla de marketplace (ofertas p2p)
    c.execute('''
        create table if not exists ofertas_marketplace (
            id integer primary key autoincrement,
            uid_vendedor integer not null,
            cantidad_kbt real not null,
            precio_pen real not null,
            tipo text default 'venta',
            activo integer default 1,
            creado text default (datetime('now', 'localtime')),
            foreign key (uid_vendedor) references usuarios(uid)
        )
    ''')

    # tabla de ordenes marketplace (legado)
    c.execute('''
        create table if not exists ordenes_marketplace (
            id integer primary key autoincrement,
            tipo text not null,
            wallet_vendedor text,
            wallet_comprador text,
            vendedor_uid integer,
            comprador_uid integer,
            vendedor text,
            comprador text,
            cantidad real not null,
            precio_unitario real not null,
            total real,
            estado text default 'activa',
            fecha_creacion text default (datetime('now','localtime')),
            fecha_ejecucion text,
            fecha_cancelacion text,
            foreign key (vendedor_uid) references usuarios(uid),
            foreign key (comprador_uid) references usuarios(uid)
        )
    ''')

    # tabla de referidos
    c.execute('''
        create table if not exists referidos (
            id integer primary key autoincrement,
            uid_referidor integer not null,
            uid_referido integer not null unique,
            comision_pendiente real default 0,
            fecha text default (datetime('now', 'localtime')),
            foreign key (uid_referidor) references usuarios(uid),
            foreign key (uid_referido) references usuarios(uid)
        )
    ''')

    # tabla de codigos de referido
    c.execute('''
        create table if not exists codigos_referido (
            uid integer primary key,
            codigo text unique not null,
            activo integer default 1,
            foreign key (uid) references usuarios(uid)
        )
    ''')

    # tabla de retiros
    c.execute('''
        create table if not exists retiros (
            id integer primary key autoincrement,
            uid integer not null,
            cantidad_kbt real not null,
            cantidad_pen real not null,
            comision real not null,
            estado text default 'pendiente',
            fecha_solicitud text default (datetime('now','localtime')),
            fecha_procesado text,
            foreign key (uid) references usuarios(uid)
        )
    ''')

    # tabla de happy hour
    c.execute('''
        create table if not exists happy_hour (
            id integer primary key autoincrement,
            multiplicador real default 2.0,
            fecha_inicio text not null,
            fecha_fin text not null,
            activo integer default 1
        )
    ''')

    # tabla de variables globales
    c.execute('''
        create table if not exists variables_globales (
            clave text primary key,
            valor text not null
        )
    ''')

    # tabla de sesiones
    c.execute('''
        create table if not exists sesiones (
            token text primary key,
            uid integer not null,
            username text,
            rol text default 'usuario',
            creado text default (datetime('now', 'localtime')),
            expira text,
            foreign key (uid) references usuarios(uid)
        )
    ''')

    # crear admin por defecto si no existe
    c.execute("select count(*) from usuarios where email='pcmaster'")
    if c.fetchone()[0] == 0:
        pw_hash = hashlib.sha256("abc123$_".encode()).hexdigest()
        c.execute(
            "insert into usuarios (email, password, username, rol, codigo_referido) values (?, ?, ?, ?, ?)",
            ("pcmaster", pw_hash, "pcmaster", "admin", "pcmaster"),
        )
        c.execute("select uid from usuarios where email='pcmaster'")
        uid = c.fetchone()[0]
        c.execute(
            "insert into wallets (uid, balance, minado_total) values (?, ?, ?)",
            (uid, 1000000.0, 1000000.0),
        )

    conn.commit()
    conn.close()


def get_db():
    """devuelve una conexion a la base de datos con row_factory."""
    conn = sqlite3.connect(str(_db_path))
    conn.row_factory = sqlite3.Row
    return conn