import sqlite3, os, time, math, json
from datetime import datetime
from config import DATA_DIR
DB_PATH = os.path.join(DATA_DIR, "roxymaster.db")

class Tokenomics:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.params = {
            "K": 20.0, "FX": 3.70, "P_token": 1.00, "H": 720, "E": 0.005,
            "beta": 0.0, "G": 9.0, "HH_mult": 2.0, "alfa_nuevo": 0.5, "gamma": 0.5,
            "comision_retiro_0_30": 0.33, "comision_retiro_31_60": 0.25,
            "comision_retiro_61_90": 0.15, "comision_retiro_90_plus": 0.0,
            "comision_marketplace": 0.15, "comision_referido": 0.10,
            "tasa_quema_mensual": 5.0, "limite_retiro_mensual_usd": 999.0,
            "niveles_streamer": {"0": 9.0, "1": 10.0, "2": 11.0, "3": 12.0, "4": 14.0, "5": 16.0},
            "w_bronce": 1.1, "w_plata": 1.2, "w_oro": 1.3,
            "uptime_bronce": 0.90, "uptime_plata": 0.95, "uptime_oro": 0.99,
            "happy_hour_activo": False, "bonus_happy_hour": 20
        }
        self._start_time = time.time()
        self._init_db()

    def _init_db(self):
        self.conn.executescript('''
            create table if not exists genesis (id integer primary key, etapa integer, porcentaje real, liberado integer default 0);
            create table if not exists reserva (id integer primary key check(id=1), tokens real default 0, soles real default 0);
            create table if not exists referidos_comisiones (id integer primary key autoincrement, referidor text, referido text, cantidad real, fecha text default (datetime('now')));
            insert or ignore into genesis values (1,1,0.30,0),(2,2,0.30,0),(3,3,0.20,0),(4,4,0.20,0);
            insert or ignore into reserva (id, tokens, soles) values (1,0,0);
        ''')
        self.conn.commit()

    def get_saldo(self, email):
        row = self.conn.execute("select saldo_tokens from auth_users where email=?", (email.lower(),)).fetchone()
        return row[0] if row else 0

    def get_referido(self, email):
        row = self.conn.execute("select referido_por from auth_users where email=?", (email.lower(),)).fetchone()
        return row[0] if row else "pcmaster"

    def acreditar_tokens(self, email, cantidad, motivo="recarga_manual"):
        self.conn.execute("update auth_users set saldo_tokens = saldo_tokens + ? where email=?", (cantidad, email.lower()))
        self.conn.execute("insert into transacciones_kbt (email, tipo, cantidad) values (?,?,?)", (email.lower(), "acreditado", cantidad))
        self.conn.commit()

    def transferir(self, vendedor, comprador, tokens):
        saldo_v = self.get_saldo(vendedor)
        if saldo_v < tokens:
            raise Exception("saldo insuficiente")
        self.conn.execute("update auth_users set saldo_tokens = saldo_tokens - ? where email=?", (tokens, vendedor.lower()))
        self.conn.execute("update auth_users set saldo_tokens = saldo_tokens + ? where email=?", (tokens, comprador.lower()))
        self.conn.execute("insert into transacciones_kbt (email, tipo, cantidad) values (?,?,?)", (vendedor.lower(), "transferencia_enviada", -tokens))
        self.conn.execute("insert into transacciones_kbt (email, tipo, cantidad) values (?,?,?)", (comprador.lower(), "transferencia_recibida", tokens))
        self.conn.commit()

    def listar_granjeros(self):
        rows = self.conn.execute("select email, saldo_tokens, referido_por, fecha_registro from auth_users where rol='granjero'").fetchall()
        return [{"id": r["email"], "nombre": r["email"], "saldo_tokens": r["saldo_tokens"], "referido_por": r["referido_por"], "fecha_registro": r["fecha_registro"]} for r in rows]

    def arbol_referidos(self, email):
        directos = self.conn.execute("select email, saldo_tokens from auth_users where referido_por=?", (email.lower(),)).fetchall()
        return {"id": email, "saldo_tokens": self.get_saldo(email), "referidos_directos": len(directos), "hijos": [{"id": d["email"], "saldo_tokens": d["saldo_tokens"], "referidos_directos": 0, "hijos": []} for d in directos]}

    def get_stats(self):
        total_g = self.conn.execute("select count(*) from auth_users where rol='granjero'").fetchone()[0]
        total_t = self.conn.execute("select coalesce(sum(saldo_tokens),0) from auth_users where rol='granjero'").fetchone()[0]
        res = self.conn.execute("select tokens, soles from reserva where id=1").fetchone()
        return {"total_granjeros": total_g, "tokens_en_circulacion": total_t, "reserva_tokens": res["tokens"] if res else 0, "reserva_soles": res["soles"] if res else 0, "tokens_quemables_total": total_t, "tokens_comprados_total": 0, "precio_ancla": self.params["P_token"], "total_perfiles": 0, "total_transacciones": 0}

    def guardar_params(self):
        pass

    def reset_params(self):
        self.__init__()
