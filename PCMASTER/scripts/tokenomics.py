# tokenomics.py - motor economico kbt completo roxymaster v8.3
import sqlite3, os, time, math, json, hashlib
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
            "tasa_recoleccion_mensual": 5.0,
            "niveles_streamer": {"0": 9.0, "1": 10.0, "2": 11.0, "3": 12.0, "4": 14.0, "5": 16.0},
            "w_bronce": 1.1, "w_plata": 1.2, "w_oro": 1.3,
            "uptime_bronce": 0.90, "uptime_plata": 0.95, "uptime_oro": 0.99,
            "happy_hour_activo": False,
            "dias_penalizacion_inactividad": 11,
            "ventana_penalizacion_dias": 7,
            "minutos_validacion": 62,
            "limite_retiro_mensual_usd": 999.0,
            "fecha_inicio_sistema": datetime.now().isoformat()
        }
        self._cargar_params()

    def _cargar_params(self):
        """carga parametros desde la base de datos."""
        try:
            rows = self.conn.execute("select clave, valor from variables_globales").fetchall()
            for row in rows:
                try:
                    self.params[row["clave"]] = json.loads(row["valor"])
                except (json.JSONDecodeError, TypeError):
                    self.params[row["clave"]] = row["valor"]
        except:
            pass

    def _guardar_params(self):
        """guarda parametros en la base de datos."""
        for k, v in self.params.items():
            val = json.dumps(v) if not isinstance(v, str) else v
            self.conn.execute("insert or replace into variables_globales (clave, valor) values (?,?)", (k, val))
        self.conn.commit()

    # ========== FUNCIONES DE BALANCE Y WALLET ==========
    def obtener_balance(self, uid):
        """retorna el balance kbt de un usuario."""
        row = self.conn.execute("select balance from wallets where uid=?", (uid,)).fetchone()
        return row["balance"] if row else 0

    def get_saldo(self, email_or_uid):
        """alias de obtener_balance que acepta email o uid."""
        if isinstance(email_or_uid, str) and "@" in email_or_uid:
            row = self.conn.execute("select uid from usuarios where lower(email)=lower(?)", (email_or_uid,)).fetchone()
            if row:
                return self.obtener_balance(row["uid"])
            return 0
        return self.obtener_balance(email_or_uid)

    def acreditar_tokens(self, uid, cantidad, concepto="emision"):
        """acredita tokens a un usuario."""
        self.conn.execute("update wallets set balance = balance + ?, minado_total = minado_total + ? where uid=?",
                          (cantidad, cantidad, uid))
        self.conn.execute("insert into transacciones (uid_destino, tipo, monto, concepto) values (?,?,?,?)",
                          (uid, "acreditado", cantidad, concepto))
        self.conn.commit()

    def debitar_tokens(self, uid, cantidad, concepto="debito"):
        """debita tokens de un usuario."""
        balance = self.obtener_balance(uid)
        if balance < cantidad:
            return {"ok": False, "error": "saldo insuficiente"}
        self.conn.execute("update wallets set balance = balance - ? where uid=?", (cantidad, uid))
        self.conn.execute("insert into transacciones (uid_origen, tipo, monto, concepto) values (?,?,?,?)",
                          (uid, "debitado", -cantidad, concepto))
        self.conn.commit()
        return {"ok": True, "balance": self.obtener_balance(uid)}

    # ========== RECOLECCION (en lugar de quema) ==========
    def recolectar_tokens(self, uid, cantidad, motivo="recoleccion_inactividad"):
        """mueve tokens del usuario al fondo de reserva."""
        balance = self.obtener_balance(uid)
        if balance < cantidad:
            return {"ok": False, "error": "saldo insuficiente"}
        self.conn.execute("update wallets set balance = balance - ?, recolectado_total = recolectado_total + ? where uid=?",
                          (cantidad, cantidad, uid))
        self.conn.execute("update reserva set tokens = tokens + ? where id=1", (cantidad,))
        self.conn.execute("insert into transacciones (uid_origen, tipo, monto, concepto) values (?,?,?,?)",
                          (uid, "recolectado", -cantidad, motivo))
        self.conn.commit()
        return {"ok": True, "recolectado": cantidad}

    def reutilizar_tokens_reserva(self, cantidad, motivo="reinyeccion_sistema"):
        """toma tokens de la reserva y los acredita al admin para redistribuir."""
        reserva = self.conn.execute("select tokens from reserva where id=1").fetchone()
        if not reserva or reserva["tokens"] < cantidad:
            return {"ok": False, "error": "reserva insuficiente"}
        self.conn.execute("update reserva set tokens = tokens - ? where id=1", (cantidad,))
        admin = self.conn.execute("select uid from usuarios where email='pcmaster'").fetchone()
        if admin:
            self.acreditar_tokens(admin["uid"], cantidad, motivo)
        self.conn.commit()
        return {"ok": True, "reutilizados": cantidad}

    def ejecutar_recoleccion_inactividad(self):
        """ejecuta recoleccion mensual por inactividad en lugar de quema."""
        total_recolectado = 0
        rows = self.conn.execute("select uid, balance from wallets where balance > 0").fetchall()
        for row in rows:
            cantidad = row["balance"] * (self.params["tasa_recoleccion_mensual"] / 100)
            if cantidad > 0:
                result = self.recolectar_tokens(row["uid"], cantidad)
                if result["ok"]:
                    total_recolectado += cantidad
        return {"ok": True, "total_recolectado": round(total_recolectado, 4)}

    ejecutar_quema_inactividad = ejecutar_recoleccion_inactividad

    # ========== WALLET ==========
    def obtener_wallet_por_usuario(self, uid):
        """retorna la wallet de un usuario."""
        row = self.conn.execute("select id, balance from wallets where uid=?", (uid,)).fetchone()
        return {"id": row["id"], "balance": row["balance"]} if row else None

    def crear_wallet(self, uid):
        """crea una wallet para un usuario nuevo."""
        self.conn.execute("insert or ignore into wallets (uid, balance) values (?, 0)", (uid,))
        self.conn.commit()

    # ========== HISTORIAL Y ESTADISTICAS ==========
    def obtener_historial_token(self, uid, limite=50):
        """retorna el historial de transacciones de un usuario."""
        rows = self.conn.execute(
            "select * from transacciones where uid_origen=? or uid_destino=? order by fecha desc limit ?",
            (uid, uid, limite)
        ).fetchall()
        return [dict(r) for r in rows]

    def obtener_estadisticas_kbt(self):
        """retorna estadisticas globales del ecosistema kbt."""
        total_circulante = self.conn.execute("select coalesce(sum(balance),0) from wallets").fetchone()[0]
        total_minado = self.conn.execute("select coalesce(sum(minado_total),0) from wallets").fetchone()[0]
        reserva = self.conn.execute("select tokens, soles from reserva where id=1").fetchone()
        total_usuarios = self.conn.execute("select count(*) from usuarios where rol!='admin'").fetchone()[0]
        return {
            "tokens_en_circulacion": round(total_circulante, 4),
            "total_minado": round(total_minado, 4),
            "reserva_tokens": round(reserva["tokens"], 4) if reserva else 0,
            "reserva_soles": round(reserva["soles"], 2) if reserva else 0,
            "total_usuarios": total_usuarios,
            "precio_ancla": self.params["P_token"],
            "g_actual": self.params["G"],
            "happy_hour_activo": self.params.get("happy_hour_activo", False),
            "sistema_iniciado": self.params.get("fecha_inicio_sistema", ""),
        }

    # ========== MINERIA ==========
    def calcular_recompensa_mineria(self, uid, horas, nivel_uptime="bronce", es_happy_hour=False):
        """calcula la recompensa por mineria."""
        w_map = {"bronce": self.params["w_bronce"], "plata": self.params["w_plata"], "oro": self.params["w_oro"]}
        w = w_map.get(nivel_uptime, 1.1)
        hh_mult = self.params["HH_mult"] if es_happy_hour and self.params.get("happy_hour_activo") else 1.0
        recompensa = horas * w * hh_mult * (self.params["G"] * self.params["FX"] / 1000)
        self.acreditar_tokens(uid, recompensa, f"mineria_{nivel_uptime}")
        return {"ok": True, "recompensa": round(recompensa, 4), "horas": horas, "nivel": nivel_uptime}

    def registrar_mineria(self, uid, horas, recompensa):
        """registra un evento de mineria."""
        self.conn.execute(
            "update wallets set minado_total = minado_total + ? where uid=?", (recompensa, uid))
        self.conn.execute(
            "insert into transacciones (uid_destino, tipo, monto, concepto) values (?,?,?,?)",
            (uid, "mineria", recompensa, f"mineria_{horas}h"))
        self.conn.commit()

    # ========== REFERIDOS ==========
    def procesar_comision_referido(self, uid_referido, cantidad_minada):
        """calcula y acredita comision al referidor."""
        row = self.conn.execute(
            "select u.referido_por from usuarios u where u.uid=?", (uid_referido,)
        ).fetchone()
        if not row or not row["referido_por"]:
            return
        referidor_email = row["referido_por"]
        referidor = self.conn.execute(
            "select uid from usuarios where email=? or codigo_referido=?",
            (referidor_email, referidor_email)
        ).fetchone()
        if referidor:
            comision = cantidad_minada * self.params["comision_referido"]
            self.acreditar_tokens(referidor["uid"], comision, f"comision_referido_{uid_referido}")

    def obtener_referidos(self, uid):
        """retorna los referidos directos de un usuario."""
        rows = self.conn.execute(
            "select u.uid, u.email, w.balance from usuarios u left join wallets w on u.uid=w.uid where u.referido_por in (select codigo_referido from usuarios where uid=?) or u.referido_por in (select email from usuarios where uid=?)",
            (uid, uid)
        ).fetchall()
        return [dict(r) for r in rows]

    def arbol_referidos(self, email_or_uid):
        """retorna el arbol de referidos de un usuario."""
        if isinstance(email_or_uid, str) and "@" in email_or_uid:
            user = self.conn.execute("select uid from usuarios where lower(email)=lower(?)", (email_or_uid,)).fetchone()
            uid = user["uid"] if user else None
        else:
            uid = email_or_uid
        if not uid:
            return {"id": email_or_uid, "saldo_tokens": 0, "referidos_directos": 0, "hijos": []}
        saldo = self.obtener_balance(uid)
        directos = self.conn.execute(
            "select u.uid, u.email, coalesce(w.balance,0) as saldo from usuarios u left join wallets w on u.uid=w.uid where u.referido_por = (select codigo_referido from usuarios where uid=?)",
            (uid,)
        ).fetchall()
        hijos = [{"id": d["email"], "saldo_tokens": d["saldo"], "referidos_directos": 0, "hijos": []} for d in directos]
        return {"id": uid, "saldo_tokens": saldo, "referidos_directos": len(hijos), "hijos": hijos}

    def cambiar_referidor(self, uid, nuevo_referidor_email):
        """cambia el referidor una unica vez."""
        user = self.conn.execute("select referido_cambiado from usuarios where uid=?", (uid,)).fetchone()
        if not user:
            return {"ok": False, "error": "usuario no encontrado"}
        if user["referido_cambiado"]:
            return {"ok": False, "error": "el referido ya fue cambiado anteriormente"}
        self.conn.execute("update usuarios set referido_por=?, referido_cambiado=1 where uid=?",
                          (nuevo_referidor_email, uid))
        self.conn.commit()
        return {"ok": True, "mensaje": "referidor cambiado exitosamente"}

    # ========== RETIROS ==========
    def procesar_retiro(self, uid, cantidad_kbt):
        """procesa un retiro de tokens a fiat."""
        balance = self.obtener_balance(uid)
        if balance < cantidad_kbt:
            return {"ok": False, "error": "saldo insuficiente"}
        antiguedad_dias = self._calcular_antiguedad_tokens(uid)
        if antiguedad_dias <= 30:
            comision_pct = self.params["comision_retiro_0_30"]
        elif antiguedad_dias <= 60:
            comision_pct = self.params["comision_retiro_31_60"]
        elif antiguedad_dias <= 90:
            comision_pct = self.params["comision_retiro_61_90"]
        else:
            comision_pct = self.params["comision_retiro_90_plus"]
        comision = cantidad_kbt * comision_pct
        cantidad_neta = cantidad_kbt - comision
        cantidad_pen = cantidad_neta * self.params["P_token"]
        self.conn.execute("update wallets set balance = balance - ?, retirado_total = retirado_total + ? where uid=?",
                          (cantidad_kbt, cantidad_kbt, uid))
        self.conn.execute("update reserva set tokens = tokens + ? where id=1", (comision,))
        self.conn.execute("insert into retiros (uid, cantidad_kbt, cantidad_pen, comision, estado) values (?,?,?,?,?)",
                          (uid, cantidad_kbt, cantidad_pen, comision, "completado"))
        self.conn.execute("insert into transacciones (uid_origen, tipo, monto, concepto) values (?,?,?,?)",
                          (uid, "retiro", -cantidad_neta, f"retiro_fiat_{cantidad_pen}pen"))
        self.conn.commit()
        return {
            "ok": True, "cantidad_kbt": cantidad_kbt, "comision": comision,
            "cantidad_neta": cantidad_neta, "cantidad_pen": cantidad_pen, "estado": "completado"
        }

    def _calcular_antiguedad_tokens(self, uid):
        """calcula la antiguedad promedio de los tokens de un usuario."""
        row = self.conn.execute(
            "select julianday('now') - julianday(min(fecha)) as dias from transacciones where uid_destino=? and tipo='mineria'",
            (uid,)
        ).fetchone()
        return row["dias"] if row and row["dias"] else 0

    # ========== CRONOGRAMA DE G ==========
    def actualizar_g_segun_cronograma(self):
        """actualiza G segun el cronograma temporal."""
        fecha_inicio = datetime.fromisoformat(self.params.get("fecha_inicio_sistema", datetime.now().isoformat()))
        meses_transcurridos = (datetime.now() - fecha_inicio).days // 30
        if meses_transcurridos <= 3:
            self.params["G"] = 9.0
        elif meses_transcurridos <= 6:
            self.params["G"] = 7.5
        else:
            self.params["G"] = 6.0
        self._guardar_params()

    # ========== HAPPY HOUR ==========
    def activar_happy_hour(self, multiplicador=2.0, duracion_horas=1):
        """activa happy hour."""
        ahora = datetime.now()
        fin = ahora.replace(hour=ahora.hour + duracion_horas)
        self.params["happy_hour_activo"] = True
        self.params["HH_mult"] = multiplicador
        self.conn.execute("insert into happy_hour (multiplicador, fecha_inicio, fecha_fin) values (?,?,?)",
                          (multiplicador, ahora.isoformat(), fin.isoformat()))
        self.conn.commit()
        self._guardar_params()
        return {"ok": True, "multiplicador": multiplicador, "fin": fin.isoformat()}

    def desactivar_happy_hour(self):
        """desactiva happy hour."""
        self.params["happy_hour_activo"] = False
        self._guardar_params()
        return {"ok": True}

    # ========== LISTAR ==========
    def listar_granjeros(self):
        """lista todos los granjeros."""
        rows = self.conn.execute(
            "select u.uid, u.email, u.username, u.nivel_fiabilidad, w.balance, u.creado from usuarios u left join wallets w on u.uid=w.uid where u.rol='usuario'"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self):
        """alias de obtener_estadisticas_kbt."""
        return self.obtener_estadisticas_kbt()

    def get_referido(self, email):
        """retorna el referidor de un usuario."""
        row = self.conn.execute("select referido_por from usuarios where lower(email)=lower(?)", (email,)).fetchone()
        return row["referido_por"] if row else "pcmaster"

    # ========== CIERRE DE CONEXION ==========
    def __del__(self):
        try:
            self.conn.close()
        except:
            pass