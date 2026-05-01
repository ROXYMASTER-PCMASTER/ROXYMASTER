# database.py - inicializacion de bases de datos roxymaster v8.3
import sqlite3, os, json
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
            uid text primary key,
            email text unique not null,
            password text not null,
            username text not null,
            rol text default 'usuario',
            creado text default (datetime('now', 'localtime')),
            ultimo_login text,
            activo integer default 1
        )
    ''')

    # tabla de tokens kbt
    c.execute('''
        create table if not exists wallets (
            uid text primary key,
            balance real default 0,
            minado_total real default 0,
            quemado_total real default 0,
            recibido_total real default 0,
            enviado_total real default 0,
            retirado_total real default 0,
            actualizado text default (datetime('now', 'localtime')),
            foreign key (uid) references usuarios(uid)
        )
    ''')

    # tabla de perfiles
    c.execute('''
        create table if not exists perfiles (
            id text primary key,
            uid text not null,
            plataforma text not null,
            url text not null,
            seguidores integer default 0,
            ratio real default 0,
            verificada integer default 0,
            bloque_beta integer default 0,
            streaming_ratio real default 0,
            minado_actual real default 0,
            activo integer default 1,
            creado text default (datetime('now', 'localtime')),
            foreign key (uid) references usuarios(uid)
        )
    ''')

    # tabla de transacciones
    c.execute('''
        create table if not exists transacciones (
            id integer primary key autoincrement,
            uid_origen text,
            uid_destino text,
            tipo text not null,
            cantidad real not null,
            comision real default 0,
            concepto text,
            fecha text default (datetime('now', 'localtime')),
            foreign key (uid_origen) references usuarios(uid),
            foreign key (uid_destino) references usuarios(uid)
        )
    ''')

    # tabla de marketplace (ofertas p2p)
    c.execute('''
        create table if not exists ofertas_marketplace (
            id integer primary key autoincrement,
            uid_vendedor text not null,
            cantidad_kbt real not null,
            precio_pen real not null,
            tipo text default 'venta',
            activo integer default 1,
            creado text default (datetime('now', 'localtime')),
            foreign key (uid_vendedor) references usuarios(uid)
        )
    ''')

    # tabla de referidos
    c.execute('''
        create table if not exists referidos (
            id integer primary key autoincrement,
            uid_referidor text not null,
            uid_referido text not null unique,
            fecha text default (datetime('now', 'localtime')),
            foreign key (uid_referidor) references usuarios(uid),
            foreign key (uid_referido) references usuarios(uid)
        )
    ''')

    # tabla de codigos de referido
    c.execute('''
        create table if not exists codigos_referido (
            uid text primary key,
            codigo text unique not null,
            activo integer default 1,
            foreign key (uid) references usuarios(uid)
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
            uid text not null,
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
        import hashlib
        pw_hash = hashlib.sha256("abc123$_".encode()).hexdigest()
        c.execute(
            "insert into usuarios (uid, email, password, username, rol) values (?, ?, ?, ?, ?)",
            ("pcmaster", "pcmaster", pw_hash, "pcmaster", "admin"),
        )
        c.execute(
            "insert into wallets (uid, balance) values (?, ?)",
            ("pcmaster", 1000000.0),
        )

    conn.commit()
    conn.close()


def get_db():
    """devuelve una conexion a la base de datos con row_factory."""
    conn = sqlite3.connect(str(_db_path))
    conn.row_factory = sqlite3.Row
    return conn