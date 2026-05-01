import sqlite3, os
from config import DATA_DIR
DB_PATH = os.path.join(DATA_DIR, "roxymaster.db")
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
def init_db():
    conn = get_db()
    conn.executescript('''
        create table if not exists auth_users (
            email text primary key,
            password_hash text not null,
            rol text default 'usuario',
            pcbot_id text,
            saldo_tokens real default 0,
            saldo_soles real default 0,
            referido_por text,
            fecha_registro text default (datetime('now'))
        );
        create table if not exists auth_tokens (
            token text primary key,
            email text not null,
            expires text not null
        );
        create table if not exists perfiles (
            id integer primary key autoincrement,
            granjero_id text not null,
            nombre_perfil text,
            tipo text default 'local',
            estado text default 'inactivo',
            ip_wan text,
            horas_conexion real default 0
        );
        create table if not exists transacciones_kbt (
            id integer primary key autoincrement,
            email text not null,
            tipo text not null,
            cantidad real not null,
            fecha text default (datetime('now'))
        );
    ''')
    conn.commit()
    conn.close()
