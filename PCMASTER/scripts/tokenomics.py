# ============================================================================
# tokenomics.py - motor economico kbt completo roxymaster v8.3
# genesis, minado, quemado, p2p, referidos, formulas, fondo de recoleccion
# ============================================================================

import sqlite3
import os
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# configuracion
# ---------------------------------------------------------------------------
_base_dir = Path(__file__).parent.parent.absolute()
_data_dir = _base_dir / "data"
_db_path = _data_dir / "roxymaster.db"

# ---------------------------------------------------------------------------
# parametros predeterminados (importados de variables_globales si existen)
# ---------------------------------------------------------------------------
try:
    from variables_globales import parametros_kbt_predeterminados
except ImportError:
    parametros_kbt_predeterminados = {
        "k": 20.00, "fx": 3.70, "p_token": 1.00,
        "banda_min": 0.94, "banda_max": 1.06,
        "h": 720, "e": 0.005,
        "g_mes_1_3": 9.00, "g_mes_4_6": 7.50, "g_mes_7_adelante": 6.00,
        "beta": 0.0, "alfa_nuevo": 0.5, "gamma": 0.5,
        "comision_marketplace": 0.15,
        "comision_retiro_0_30": 0.33, "comision_retiro_31_60": 0.25,
        "comision_retiro_61_90": 0.15, "comision_retiro_90_plus": 0.00,
        "comision_referido": 0.10,
        "limite_retiro_mensual_usd": 999.0,
        "limite_perfiles_por_pc": 5,
        "hh_mult": 2.0,
        "nivel_bronce_uptime": 0.90, "nivel_plata_uptime": 0.95,
        "nivel_oro_uptime": 0.99,
        "w_bronce": 1.1, "w_plata": 1.2, "w_oro": 1.3,
        "penalizacion_inactividad_porcentaje": 0.05,
        "tolerancia_reinicio_minutos": 30,
        "ventana_penalizacion_dias": 7,
        "horas_inactividad_dispara": 11,
        "mins_validacion_consecutivos": 62,
        "gracia_oro_desconexion_min": 30,
        "duracion_penalizacion_dias": 30,
        "staking_recompensa_anual": 0.05,
        "re_limite_intervencion_mensual": 0.10,
        "re_excedente_retirable_mensual": 0.01,
        "re_colchon_estabilidad": 0.20,
        "niveles_streamer": {
            0: {"min_seguidores": 0, "max_seguidores": 4999, "p_sys": 9.00},
            1: {"min_seguidores": 5000, "max_seguidores": 14999, "p_sys": 10.00},
            2: {"min_seguidores": 15000, "max_seguidores": 49999, "p_sys": 11.00},
            3: {"min_seguidores": 50000, "max_seguidores": 499999, "p_sys": 12.00},
            4: {"min_seguidores": 500000, "max_seguidores": 999999, "p_sys": 14.00},
            5: {"min_seguidores": 1000000, "max_seguidores": 999999999, "p_sys": 16.00},
        },
        "bloques_por_perfil_mes": 0.72,
    }


# ============================================================================
# tokenomics engine
# ============================================================================
class TokenomicsEngine:
    """motor economico kbt completo."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(_db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()
        self.params = self.cargar_parametros()

    # -----------------------------------------------------------------------
    # inicializacion de base de datos
    # -----------------------------------------------------------------------
    def _init_db(self):
        """crea todas las tablas economicas."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # tabla de parametros economicos
        c.execute("""CREATE TABLE IF NOT EXISTS parametros_kbt (
                        clave TEXT PRIMARY KEY,
                        valor TEXT)""")

        # fondo de recoleccion (re_tokens y re_soles)
        c.execute("""CREATE TABLE IF NOT EXISTS fondo_recoleccion (
                        id INTEGER PRIMARY KEY CHECK(id=1),
                        re_tokens REAL DEFAULT 0.0,
                        re_soles REAL DEFAULT 0.0,
                        fecha_actualizacion TEXT DEFAULT (datetime('now', 'localtime')))""")

        # transacciones kbt
        c.execute("""CREATE TABLE IF NOT EXISTS transacciones_kbt (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        wallet_origen TEXT,
                        wallet_destino TEXT,
                        cantidad REAL NOT NULL,
                        tipo TEXT NOT NULL,
                        concepto TEXT,
                        comision REAL DEFAULT 0.0,
                        fecha TEXT DEFAULT (datetime('now', 'localtime')))""")

        # ordenes marketplace
        c.execute("""CREATE TABLE IF NOT EXISTS ordenes_marketplace (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tipo TEXT NOT NULL CHECK(tipo IN ('compra','venta')),
                        wallet TEXT NOT NULL,
                        usuario_id INTEGER NOT NULL,
                        cantidad REAL NOT NULL,
                        precio_pen REAL NOT NULL,
                        estado TEXT DEFAULT 'activa'
                            CHECK(estado IN ('activa','escrow','completada','cancelada')),
                        fecha_creacion TEXT DEFAULT (datetime('now', 'localtime')),
                        fecha_cierre TEXT)""")

        # retiros (conversion a fiat)
        c.execute("""CREATE TABLE IF NOT EXISTS retiros (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        usuario_id INTEGER NOT NULL,
                        wallet TEXT NOT NULL,
                        cantidad_tokens REAL NOT NULL,
                        comision_porcentaje REAL NOT NULL,
                        comision_tokens REAL NOT NULL,
                        tokens_netos REAL NOT NULL,
                        pen_recibidos REAL NOT NULL,
                        estado TEXT DEFAULT 'pendiente',
                        fecha_solicitud TEXT DEFAULT (datetime('now', 'localtime')),
                        fecha_procesado TEXT)""")

        # happy hour activo
        c.execute("""CREATE TABLE IF NOT EXISTS happy_hour (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        activo INTEGER DEFAULT 0,
                        multiplicador REAL DEFAULT 2.0,
                        hora_inicio TEXT,
                        hora_fin TEXT,
                        fecha_anuncio TEXT DEFAULT (datetime('now', 'localtime')))""")

        # horas trabajadas por perfil
        c.execute("""CREATE TABLE IF NOT EXISTS horas_perfil (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        perfil_key TEXT NOT NULL,
                        granjero_id INTEGER,
                        horas_normales REAL DEFAULT 0.0,
                        horas_hh REAL DEFAULT 0.0,
                        w_fiabilidad REAL DEFAULT 1.0,
                        fecha_actualizacion TEXT DEFAULT (datetime('now', 'localtime')))""")

        # uptime tracker
        c.execute("""CREATE TABLE IF NOT EXISTS uptime_tracker (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        perfil_key TEXT NOT NULL,
                        granjero_id INTEGER,
                        minutos_conectado REAL DEFAULT 0.0,
                        minutos_total REAL DEFAULT 0.0,
                        desconexiones INTEGER DEFAULT 0,
                        ultima_conexion TEXT,
                        ultima_desconexion TEXT,
                        en_penalizacion INTEGER DEFAULT 0,
                        fecha_inicio_penalizacion TEXT,
                        fecha_fin_penalizacion TEXT,
                        validado INTEGER DEFAULT 0)""")

        # semilla fondo recoleccion
        c.execute("INSERT OR IGNORE INTO fondo_recoleccion (id, re_tokens, re_soles) "
                  "VALUES (1, 0.0, 0.0)")

        conn.commit()
        conn.close()

    # -----------------------------------------------------------------------
    # parametros
    # -----------------------------------------------------------------------
    def cargar_parametros(self) -> dict:
        """carga parametros desde db, con fallback a predeterminados."""
        params = dict(parametros_kbt_predeterminados)
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("SELECT clave, valor FROM parametros_kbt")
            for clave, valor in c.fetchall():
                try:
                    params[clave] = float(valor)
                except ValueError:
                    params[clave] = valor
            conn.close()
        except sqlite3.Error:
            pass
        return params

    def actualizar_parametro(self, clave: str, valor) -> bool:
        """actualiza un parametro economico."""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO parametros_kbt (clave, valor) VALUES (?, ?)",
                      (clave, str(valor)))
            conn.commit()
            conn.close()
            self.params[clave] = valor if isinstance(valor, (int, float)) else float(valor)
            return True
        except (sqlite3.Error, ValueError):
            return False

    def restablecer_parametros(self) -> bool:
        """restablece todos los parametros a predeterminados."""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("DELETE FROM parametros_kbt")
            for clave, valor in parametros_kbt_predeterminados.items():
                c.execute("INSERT OR REPLACE INTO parametros_kbt (clave, valor) VALUES (?, ?)",
                          (clave, str(valor)))
            conn.commit()
            conn.close()
            self.recargar_parametros()
            return True
        except sqlite3.Error:
            return False

    def recargar_parametros(self):
        """recarga parametros desde la db."""
        self.params = self.cargar_parametros()

    # -----------------------------------------------------------------------
    # metodos de consulta economica
    # -----------------------------------------------------------------------
    def obtener_g_actual(self, mes_operacion: int = 1) -> float:
        """retorna el valor G segun el mes de operacion."""
        if mes_operacion <= 3:
            return float(self.params.get("g_mes_1_3", 9.00))
        elif mes_operacion <= 6:
            return float(self.params.get("g_mes_4_6", 7.50))
        else:
            return float(self.params.get("g_mes_7_adelante", 6.00))

    def obtener_p_sys(self, seguidores: int) -> float:
        """retorna el precio P_sys segun nivel de streamer."""
        niveles = self.params.get("niveles_streamer", {})
        if isinstance(niveles, dict):
            for nivel, datos in sorted(niveles.items()):
                if isinstance(datos, dict):
                    mini = datos.get("min_seguidores", 0)
                    maxi = datos.get("max_seguidores", 0)
                    if mini <= seguidores <= maxi:
                        return float(datos.get("p_sys", 9.00))
        return 9.00

    def obtener_nivel_streamer(self, seguidores: int) -> int:
        """retorna el nivel de streamer segun seguidores."""
        niveles = self.params.get("niveles_streamer", {})
        if isinstance(niveles, dict):
            for nivel, datos in sorted(niveles.items()):
                if isinstance(datos, dict):
                    mini = datos.get("min_seguidores", 0)
                    maxi = datos.get("max_seguidores", 0)
                    if mini <= seguidores <= maxi:
                        return int(nivel)
        return 0

    def obtener_w_fiabilidad(self, nivel_fiabilidad: str) -> float:
        """retorna el multiplicador de fiabilidad."""
        nivel = nivel_fiabilidad.lower()
        if nivel == "oro":
            return float(self.params.get("w_oro", 1.3))
        elif nivel == "plata":
            return float(self.params.get("w_plata", 1.2))
        elif nivel == "bronce":
            return float(self.params.get("w_bronce", 1.1))
        return 1.0

    # -----------------------------------------------------------------------
    # operaciones de wallet y balance
    # -----------------------------------------------------------------------
    def obtener_saldo_wallet(self, wallet: str) -> dict:
        """retorna el saldo completo de una wallet."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM wallets WHERE wallet = ?", (wallet,))
        row = c.fetchone()
        conn.close()
        if row:
            return dict(row)
        return {"saldo_tokens": 0.0, "saldo_tokens_quemables": 0.0,
                "saldo_tokens_comprados": 0.0, "saldo_soles": 0.0}

    def obtener_saldo_kbt(self, wallet: str) -> float:
        """retorna solo el saldo de tokens."""
        saldo = self.obtener_saldo_wallet(wallet)
        return float(saldo.get("saldo_tokens", 0.0))

    def acreditar_tokens(self, wallet: str, cantidad: float, tipo: str = "minado",
                         concepto: str = ""):
        """acredita tokens a una wallet."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("UPDATE wallets SET saldo_tokens = saldo_tokens + ?, "
                  "fecha_actualizacion = datetime('now', 'localtime') "
                  "WHERE wallet = ?", (cantidad, wallet))
        c.execute("INSERT INTO transacciones_kbt (wallet_origen, wallet_destino, "
                  "cantidad, tipo, concepto) VALUES ('sistema', ?, ?, ?, ?)",
                  (wallet, cantidad, tipo, concepto))
        conn.commit()
        conn.close()

    def debitar_tokens(self, wallet: str, cantidad: float, tipo: str = "pago",
                       concepto: str = ""):
        """debita tokens de una wallet."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("UPDATE wallets SET saldo_tokens = saldo_tokens - ?, "
                  "fecha_actualizacion = datetime('now', 'localtime') "
                  "WHERE wallet = ? AND saldo_tokens >= ?",
                  (cantidad, wallet, cantidad))
        if c.rowcount > 0:
            c.execute("INSERT INTO transacciones_kbt (wallet_origen, wallet_destino, "
                      "cantidad, tipo, concepto) VALUES (?, 'sistema', ?, ?, ?)",
                      (wallet, cantidad, tipo, concepto))
        conn.commit()
        conn.close()

    # -----------------------------------------------------------------------
    # mineria y reparto mensual
    # -----------------------------------------------------------------------
    def calcular_recompensa_mensual(self, mes: int = None, anio: int = None) -> dict:
        """calcula las recompensas teoricas del mes."""
        params = self.params
        g = self.obtener_g_actual(mes or 1)
        fx = float(params.get("fx", 3.70))
        beta = float(params.get("beta", 0.0))
        alfa_nuevo = float(params.get("alfa_nuevo", 0.5))
        gamma = float(params.get("gamma", 0.5))
        comision_mkt = float(params.get("comision_marketplace", 0.15))

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM usuarios WHERE activo = 1")
        total_usuarios = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM horas_perfil WHERE granjero_id IS NOT NULL")
        perfiles_activos = c.fetchone()[0] or 0
        conn.close()

        bp = float(params.get("bloques_por_perfil_mes", 0.72))
        b = bp * max(perfiles_activos, 1)
        r_total = b * g * fx
        e_nueva = (1 - beta) * b * g * fx
        return {
            "mes": mes or 1,
            "total_usuarios": total_usuarios,
            "perfiles_activos": perfiles_activos,
            "b_bloques": b,
            "g": g,
            "r_total_kbt": r_total,
            "e_nueva": e_nueva,
        }

    def ejecutar_reparto_mensual(self, mes: int = None, anio: int = None) -> dict:
        """ejecuta el reparto mensual de tokens minados."""
        params = self.params
        g = self.obtener_g_actual(mes or 1)
        fx = float(params.get("fx", 3.70))
        comision_ref = float(params.get("comision_referido", 0.10))

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # sumar horas ponderadas
        c.execute("""
            SELECT granjero_id, SUM(horas_normales * w_fiabilidad) as h_normal_pond,
                   SUM(horas_hh * w_fiabilidad) as h_hh_pond
            FROM horas_perfil WHERE granjero_id IS NOT NULL
            GROUP BY granjero_id
        """)
        filas = c.fetchall()
        if not filas:
            conn.close()
            return {"ok": False, "error": "sin granjeros para repartir"}

        hh = float(params.get("hh_mult", 2.0))
        suma_total = 0.0
        ponderadas = {}
        for f in filas:
            hp = float(f["h_normal_pond"]) + float(f["h_hh_pond"]) * hh
            ponderadas[f["granjero_id"]] = hp
            suma_total += hp

        bp = float(params.get("bloques_por_perfil_mes", 0.72))
        n = len(filas)
        b = bp * n
        r_total = b * g * fx

        repartido = 0.0
        for gid, hp in ponderadas.items():
            tokens_i = (hp / suma_total) * r_total if suma_total > 0 else 0
            c.execute("SELECT wallet FROM usuarios WHERE id = ?", (gid,))
            urow = c.fetchone()
            if urow:
                wallet = urow["wallet"]
                # comision de referidos
                self._pagar_comisiones_referidos(c, gid, tokens_i, comision_ref)
                c.execute("UPDATE wallets SET saldo_tokens = saldo_tokens + ?, "
                          "tokens_minados_total = tokens_minados_total + ?, "
                          "fecha_actualizacion = datetime('now', 'localtime') "
                          "WHERE usuario_id = ?", (tokens_i, tokens_i, gid))
                c.execute("INSERT INTO transacciones_kbt (wallet_origen, wallet_destino, "
                          "cantidad, tipo, concepto) VALUES ('sistema', ?, ?, 'minado', "
                          "'reparto_mensual')", (wallet, tokens_i))
                repartido += tokens_i

        conn.commit()
        conn.close()
        return {"ok": True, "repartido_total": repartido, "granjeros": len(filas)}

    def _pagar_comisiones_referidos(self, cursor, referido_id: int,
                                    tokens_minados: float, comision_ref: float):
        """paga comisiones a los referidos ascendentes (3 niveles)."""
        nivel_porcentajes = {1: 0.05, 2: 0.03, 3: 0.02}
        for nivel in range(1, 4):
            cursor.execute(
                "SELECT usuario_id FROM referidos WHERE referido_id = ? AND nivel = ?",
                (referido_id, nivel)
            )
            ref = cursor.fetchone()
            if ref:
                comision = tokens_minados * nivel_porcentajes.get(nivel, 0.02)
                cursor.execute("SELECT wallet FROM usuarios WHERE id = ?", (ref["usuario_id"],))
                urow = cursor.fetchone()
                if urow:
                    cursor.execute("UPDATE wallets SET saldo_tokens = saldo_tokens + ?, "
                                  "fecha_actualizacion = datetime('now', 'localtime') "
                                  "WHERE wallet = ?", (comision, urow["wallet"]))
                    cursor.execute("UPDATE referidos SET comisiones_generadas = "
                                  "comisiones_generadas + ? WHERE usuario_id = ? AND "
                                  "referido_id = ? AND nivel = ?",
                                  (comision, ref["usuario_id"], referido_id, nivel))

    # -----------------------------------------------------------------------
    # fondo de recoleccion (re)
    # -----------------------------------------------------------------------
    def obtener_re(self) -> dict:
        """retorna el estado del fondo de recoleccion."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM fondo_recoleccion WHERE id = 1")
        row = c.fetchone()
        conn.close()
        if row:
            return dict(row)
        return {"re_tokens": 0.0, "re_soles": 0.0}

    def depositar_re_tokens(self, cantidad: float, concepto: str = ""):
        """deposita tokens en el fondo de recoleccion."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("UPDATE fondo_recoleccion SET re_tokens = re_tokens + ?, "
                  "fecha_actualizacion = datetime('now', 'localtime') WHERE id = 1",
                  (cantidad,))
        conn.commit()
        conn.close()

    def depositar_re_soles(self, cantidad: float, concepto: str = ""):
        """deposita soles en el fondo de recoleccion."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("UPDATE fondo_recoleccion SET re_soles = re_soles + ?, "
                  "fecha_actualizacion = datetime('now', 'localtime') WHERE id = 1",
                  (cantidad,))
        conn.commit()
        conn.close()

    def estabilizar_precio(self, precio_mercado: float) -> dict:
        """interviene en el mercado para estabilizar el precio del kbt."""
        banda_min = float(self.params.get("banda_min", 0.94))
        banda_max = float(self.params.get("banda_max", 1.06))
        limite = float(self.params.get("re_limite_intervencion_mensual", 0.10))
        re = self.obtener_re()
        re_tokens = float(re.get("re_tokens", 0.0))
        re_soles = float(re.get("re_soles", 0.0))

        if precio_mercado < banda_min and re_soles > 0:
            max_intervencion = re_soles * limite
            return {"accion": "compra", "precio_objetivo": banda_min,
                    "max_gasto_soles": max_intervencion}
        elif precio_mercado > banda_max and re_tokens > 0:
            max_intervencion = re_tokens * limite
            return {"accion": "venta", "precio_objetivo": banda_max,
                    "max_venta_tokens": max_intervencion}
        return {"accion": "ninguna", "precio_estable": True}

    # -----------------------------------------------------------------------
    # ordenes marketplace (metodos de engine)
    # -----------------------------------------------------------------------
    def crear_orden(self, tipo: str, wallet: str, usuario_id: int,
                    cantidad: float, precio_pen: float) -> dict:
        """crea una orden en el marketplace."""
        try:
            conn = sqlite3.connect(self.db_path)
            c = conn.cursor()
            c.execute("INSERT INTO ordenes_marketplace (tipo, wallet, usuario_id, "
                      "cantidad, precio_pen) VALUES (?, ?, ?, ?, ?)",
                      (tipo, wallet, usuario_id, cantidad, precio_pen))
            orden_id = c.lastrowid
            conn.commit()
            conn.close()
            return {"ok": True, "orden_id": orden_id}
        except sqlite3.Error as e:
            return {"ok": False, "error": str(e)}

    def ejecutar_orden(self, orden_id: int, comprador_wallet: str,
                       comprador_id: int) -> dict:
        """ejecuta una orden de marketplace."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM ordenes_marketplace WHERE id = ? AND estado = 'activa'",
                  (orden_id,))
        orden = c.fetchone()
        if not orden:
            conn.close()
            return {"ok": False, "error": "orden no encontrada o no activa"}

        cantidad = float(orden["cantidad"])
        precio = float(orden["precio_pen"])
        comision_mkt = float(self.params.get("comision_marketplace", 0.15))

        if orden["tipo"] == "venta":
            total_pen = cantidad * precio
            comision = total_pen * comision_mkt
            total_comprador = total_pen + comision

            c.execute("UPDATE wallets SET saldo_soles = saldo_soles - ? "
                      "WHERE wallet = ? AND saldo_soles >= ?",
                      (total_comprador, comprador_wallet, total_comprador))
            if c.rowcount == 0:
                conn.close()
                return {"ok": False, "error": "saldo insuficiente en soles del comprador"}

            c.execute("UPDATE wallets SET saldo_tokens = saldo_tokens - ?, "
                      "saldo_tokens_comprados = saldo_tokens_comprados + ? "
                      "WHERE wallet = ? AND saldo_tokens >= ?",
                      (cantidad, cantidad, orden["wallet"], cantidad))
            c.execute("UPDATE wallets SET saldo_tokens = saldo_tokens + ? "
                      "WHERE wallet = ?", (cantidad, comprador_wallet))
            c.execute("UPDATE wallets SET saldo_soles = saldo_soles + ? "
                      "WHERE wallet = ?", (total_pen, orden["wallet"]))

            self.depositar_re_tokens(comision, "comision_marketplace")

        elif orden["tipo"] == "compra":
            c.execute("UPDATE wallets SET saldo_tokens = saldo_tokens - ? "
                      "WHERE wallet = ? AND saldo_tokens >= ?",
                      (cantidad, comprador_wallet, cantidad))
            if c.rowcount == 0:
                conn.close()
                return {"ok": False, "error": "saldo insuficiente de tokens"}

            total_pen = cantidad * precio
            c.execute("UPDATE wallets SET saldo_tokens = saldo_tokens + ? "
                      "WHERE wallet = ?", (cantidad, orden["wallet"]))
            c.execute("UPDATE wallets SET saldo_soles = saldo_soles - ? "
                      "WHERE wallet = ? AND saldo_soles >= ?",
                      (total_pen, orden["wallet"], total_pen))
            c.execute("UPDATE wallets SET saldo_soles = saldo_soles + ? "
                      "WHERE wallet = ?", (total_pen, comprador_wallet))

        c.execute("UPDATE ordenes_marketplace SET estado = 'completada', "
                  "fecha_cierre = datetime('now', 'localtime') WHERE id = ?",
                  (orden_id,))
        conn.commit()
        conn.close()
        return {"ok": True, "orden_id": orden_id}

    def cancelar_orden(self, orden_id: int) -> dict:
        """cancela una orden activa."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("UPDATE ordenes_marketplace SET estado = 'cancelada', "
                  "fecha_cierre = datetime('now', 'localtime') WHERE id = ? "
                  "AND estado = 'activa'", (orden_id,))
        if c.rowcount == 0:
            conn.close()
            return {"ok": False, "error": "orden no encontrada o no activa"}
        conn.commit()
        conn.close()
        return {"ok": True}

    def listar_ordenes_activas(self) -> list:
        """lista todas las ordenes activas en el marketplace."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM ordenes_marketplace WHERE estado = 'activa' ORDER BY fecha_creacion DESC")
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows

    # -----------------------------------------------------------------------
    # retiros
    # -----------------------------------------------------------------------
    def solicitar_retiro(self, usuario_id: int, wallet: str,
                         cantidad_tokens: float) -> dict:
        """solicita un retiro de tokens a fiat (pen)."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("SELECT saldo_tokens FROM wallets WHERE wallet = ? AND usuario_id = ?",
                  (wallet, usuario_id))
        row = c.fetchone()
        if not row or row[0] < cantidad_tokens:
            conn.close()
            return {"ok": False, "error": "saldo insuficiente"}

        # determinar comision por antiguedad
        c.execute("SELECT fecha FROM transacciones_kbt WHERE wallet_destino = ? "
                  "AND tipo = 'minado' ORDER BY fecha ASC LIMIT 1", (wallet,))
        primera = c.fetchone()
        if primera:
            try:
                fecha_minado = datetime.strptime(primera[0], "%Y-%m-%d %H:%M:%S")
                dias = (datetime.now() - fecha_minado).days
                if dias <= 30:
                    comision_pct = float(self.params.get("comision_retiro_0_30", 0.33))
                elif dias <= 60:
                    comision_pct = float(self.params.get("comision_retiro_31_60", 0.25))
                elif dias <= 90:
                    comision_pct = float(self.params.get("comision_retiro_61_90", 0.15))
                else:
                    comision_pct = float(self.params.get("comision_retiro_90_plus", 0.0))
            except (ValueError, TypeError):
                comision_pct = float(self.params.get("comision_retiro_0_30", 0.33))
        else:
            comision_pct = float(self.params.get("comision_retiro_0_30", 0.33))

        comision_tokens = cantidad_tokens * comision_pct
        tokens_netos = cantidad_tokens - comision_tokens
        pen_recibidos = tokens_netos * 1.0

        c.execute("UPDATE wallets SET saldo_tokens = saldo_tokens - ? WHERE wallet = ?",
                  (cantidad_tokens, wallet))
        c.execute("INSERT INTO retiros (usuario_id, wallet, cantidad_tokens, "
                  "comision_porcentaje, comision_tokens, tokens_netos, pen_recibidos, "
                  "estado) VALUES (?, ?, ?, ?, ?, ?, ?, 'pendiente')",
                  (usuario_id, wallet, cantidad_tokens, comision_pct, comision_tokens,
                   tokens_netos, pen_recibidos))

        self.depositar_re_tokens(comision_tokens, "comision_retiro")
        conn.commit()
        conn.close()
        return {"ok": True, "tokens_netos": tokens_netos, "pen_recibidos": pen_recibidos,
                "comision_porcentaje": comision_pct}

    # -----------------------------------------------------------------------
    # quema por inactividad
    # -----------------------------------------------------------------------
    def ejecutar_quema_penalizacion(self, usuario_id: int, wallet: str) -> float:
        """quema tokens por inactividad. retorna cantidad quemada."""
        pct = float(self.params.get("penalizacion_inactividad_porcentaje", 0.05))
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT saldo_tokens FROM wallets WHERE usuario_id = ?", (usuario_id,))
        row = c.fetchone()
        if not row or row[0] <= 0:
            conn.close()
            return 0.0
        saldo = row[0]
        quemar = saldo * pct / 30.0
        c.execute("UPDATE wallets SET saldo_tokens = saldo_tokens - ?, "
                  "saldo_tokens_quemables = saldo_tokens_quemables + ? "
                  "WHERE usuario_id = ? AND saldo_tokens >= ?",
                  (quemar, quemar, usuario_id, quemar))
        if c.rowcount > 0:
            self.depositar_re_tokens(quemar, "quema_inactividad")
        conn.commit()
        conn.close()
        return quemar if c.rowcount > 0 else 0.0

    # -----------------------------------------------------------------------
    # happy hour
    # -----------------------------------------------------------------------
    def activar_happy_hour(self, duracion_minutos: int = 60,
                           multiplicador: float = None):
        """activa el happy hour."""
        if multiplicador is None:
            multiplicador = float(self.params.get("hh_mult", 2.0))
        ahora = datetime.now()
        fin = ahora + timedelta(minutes=duracion_minutos)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("UPDATE happy_hour SET activo = 0")
        c.execute("INSERT INTO happy_hour (activo, multiplicador, hora_inicio, hora_fin) "
                  "VALUES (1, ?, ?, ?)",
                  (multiplicador, ahora.strftime("%Y-%m-%d %H:%M:%S"),
                   fin.strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()

    def desactivar_happy_hour(self) -> dict:
        """desactiva el happy hour."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("UPDATE happy_hour SET activo = 0 WHERE activo = 1")
        conn.commit()
        conn.close()
        return {"ok": True}

    def estado_happy_hour(self) -> dict:
        """retorna el estado actual del happy hour."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM happy_hour WHERE activo = 1 ORDER BY id DESC LIMIT 1")
        row = c.fetchone()
        conn.close()
        if row:
            return dict(row)
        return {"activo": 0, "multiplicador": 2.0}

    # -----------------------------------------------------------------------
    # estadisticas globales
    # -----------------------------------------------------------------------
    def estadisticas_globales(self) -> dict:
        """retorna estadisticas globales del ecosistema kbt."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM usuarios WHERE activo = 1")
        total_usuarios = c.fetchone()[0] or 0
        c.execute("SELECT SUM(saldo_tokens), SUM(saldo_tokens_quemables), "
                  "SUM(saldo_tokens_comprados) FROM wallets")
        sumas = c.fetchone()
        total_tokens = float(sumas[0] or 0)
        total_quemables = float(sumas[1] or 0)
        total_comprados = float(sumas[2] or 0)
        c.execute("SELECT COUNT(*) FROM ordenes_marketplace WHERE estado = 'activa'")
        ordenes_activas = c.fetchone()[0] or 0
        re = self.obtener_re()
        conn.close()
        return {
            "total_usuarios": total_usuarios,
            "total_tokens_circulacion": total_tokens,
            "total_tokens_quemables": total_quemables,
            "total_tokens_comprados": total_comprados,
            "ordenes_activas": ordenes_activas,
            "re_tokens": float(re.get("re_tokens", 0)),
            "re_soles": float(re.get("re_soles", 0)),
        }

    # -----------------------------------------------------------------------
    # staking
    # -----------------------------------------------------------------------
    def procesar_staking_recompensa(self, usuario_id: int, wallet: str):
        """procesa recompensa de staking para un usuario."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT tokens_en_staking, staking_desde FROM wallets "
                  "WHERE usuario_id = ?", (usuario_id,))
        row = c.fetchone()
        if not row or not row[0]:
            conn.close()
            return

        tokens_staking = row[0]
        desde_str = row[1]
        try:
            desde = datetime.strptime(desde_str, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            conn.close()
            return

        ahora = datetime.now()
        dias = (ahora - desde).days
        if dias <= 90:
            conn.close()
            return

        recompensa_anual = float(self.params.get("staking_recompensa_anual", 0.05))
        recompensa = tokens_staking * recompensa_anual * (dias / 365.0)
        c.execute("UPDATE wallets SET saldo_tokens = saldo_tokens + ?, "
                  "tokens_en_staking = tokens_en_staking + ?, "
                  "staking_desde = datetime('now', 'localtime') "
                  "WHERE usuario_id = ?", (recompensa, recompensa, usuario_id))
        conn.commit()
        conn.close()

    # -----------------------------------------------------------------------
    # proyeccion de escenarios
    # -----------------------------------------------------------------------
    def proyectar_escenario(self, mes: int, usuarios: int, perfiles_por_usuario: int,
                            horas_en_uso_pct: float = 1.0) -> dict:
        """proyecta ingresos para un escenario dado."""
        params = self.params
        n = usuarios * perfiles_por_usuario
        bp = float(params.get("bloques_por_perfil_mes", 0.72))
        b = bp * n * horas_en_uso_pct
        g = self.obtener_g_actual(mes)
        fx = float(params.get("fx", 3.70))
        beta = float(params.get("beta", 0.0))
        alfa_nuevo = float(params.get("alfa_nuevo", 0.5))
        gamma = float(params.get("gamma", 0.5))
        comision_mkt = float(params.get("comision_marketplace", 0.15))
        e = float(params.get("e", 0.005))
        h = float(params.get("h", 720))

        p_sys_prom = 12.0

        r_total = b * g * fx
        e_nueva = (1 - beta) * b * g * fx
        transferencia_kbt = beta * b * g * fx
        margen_fiat_dueno = (1 - beta) * b * (p_sys_prom - g) * fx
        margen_kbt = beta * b * (p_sys_prom - g) * fx
        v_mkt = alfa_nuevo * e_nueva + gamma * beta * b * p_sys_prom * fx
        comision_marketplace_total = v_mkt * comision_mkt
        coste_electrico_total = n * h * e
        ganancia_granjeros_total = r_total - coste_electrico_total
        ganancia_por_granjero = ganancia_granjeros_total / max(usuarios, 1)
        beneficio_dueno = margen_fiat_dueno + comision_marketplace_total

        return {
            "mes": mes,
            "usuarios": usuarios,
            "n_perfiles": n,
            "b_bloques": b,
            "g": g,
            "p_sys_prom": p_sys_prom,
            "r_total_kbt": r_total,
            "e_nueva": e_nueva,
            "margen_fiat_dueno_pen": margen_fiat_dueno,
            "margen_kbt_a_re": margen_kbt,
            "v_mkt": v_mkt,
            "comision_marketplace": comision_marketplace_total,
            "coste_electrico_total": coste_electrico_total,
            "ganancia_granjeros_total_pen": ganancia_granjeros_total,
            "ganancia_por_granjero_pen": ganancia_por_granjero,
            "beneficio_dueno_pen": beneficio_dueno,
        }


# ---------------------------------------------------------------------------
# instancia singleton para uso en otros modulos
# ---------------------------------------------------------------------------
_tokenomics_instance = None


def get_tokenomics(db_path: str = None) -> TokenomicsEngine:
    """retorna la instancia singleton del motor tokenomics."""
    global _tokenomics_instance
    if _tokenomics_instance is None:
        _tokenomics_instance = TokenomicsEngine(db_path)
    return _tokenomics_instance


# ============================================================================
# wrappers para server.py - funciones de nivel modulo
# ============================================================================

def obtener_balance(wallet: str) -> dict:
    """devuelve {saldo_tokens, saldo_quemables, saldo_comprados, saldo_soles}."""
    engine = get_tokenomics()
    return engine.obtener_saldo_wallet(wallet)


def obtener_wallet_por_usuario(usuario_id: int) -> dict:
    """devuelve la wallet y saldo para un usuario_id.
    retorna {wallet, saldo_tokens, ...} o {}."""
    engine = get_tokenomics()
    conn = sqlite3.connect(engine.db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT wallet FROM usuarios WHERE id = ?", (usuario_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return engine.obtener_saldo_wallet(row["wallet"])
    return {}


def crear_wallet(usuario_id: int, email: str) -> str:
    """crea una wallet para un usuario existente. retorna la direccion."""
    import hashlib
    base = email.strip().lower().encode("utf-8")
    wallet = "kbt_" + hashlib.sha256(base).hexdigest()[:16]
    engine = get_tokenomics()
    conn = sqlite3.connect(engine.db_path)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO wallets (wallet, usuario_id) VALUES (?, ?)",
              (wallet, usuario_id))
    conn.commit()
    conn.close()
    return wallet


def acreditar_tokens(wallet: str, cantidad: float, tipo: str = "minado",
                     concepto: str = ""):
    """acredita tokens a una wallet (wrapper de engine)."""
    engine = get_tokenomics()
    engine.acreditar_tokens(wallet, cantidad, tipo, concepto)


def debitar_tokens(wallet: str, cantidad: float, tipo: str = "pago",
                   concepto: str = ""):
    """debita tokens de una wallet (wrapper de engine)."""
    engine = get_tokenomics()
    engine.debitar_tokens(wallet, cantidad, tipo, concepto)


def registrar_mineria(perfil_key: str, granjero_id: int,
                      horas: float, es_happy_hour: bool = False):
    """registra horas de mineria para un perfil."""
    engine = get_tokenomics()
    conn = sqlite3.connect(engine.db_path)
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    col = "horas_hh" if es_happy_hour else "horas_normales"
    c.execute(f"INSERT INTO horas_perfil (perfil_key, granjero_id, {col}, fecha_actualizacion) "
              f"VALUES (?, ?, ?, ?)", (perfil_key, granjero_id, horas, now))
    conn.commit()
    conn.close()


def obtener_historial_token(wallet: str, limite: int = 50, offset: int = 0) -> list:
    """obtiene el historial de transacciones de una wallet."""
    engine = get_tokenomics()
    conn = sqlite3.connect(engine.db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM transacciones_kbt WHERE wallet_origen = ? OR wallet_destino = ? "
              "ORDER BY fecha DESC LIMIT ? OFFSET ?", (wallet, wallet, limite, offset))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def obtener_estadisticas_kbt() -> dict:
    """retorna estadisticas globales del ecosistema kbt."""
    engine = get_tokenomics()
    return engine.estadisticas_globales()


def calcular_recompensa_mineria(mes: int = None, anio: int = None) -> dict:
    """calcula las recompensas de mineria para el mes actual."""
    engine = get_tokenomics()
    return engine.calcular_recompensa_mensual(mes, anio)


def ejecutar_quema_inactividad():
    """ejecuta la quema de tokens por inactividad para todos los usuarios."""
    engine = get_tokenomics()
    conn = sqlite3.connect(engine.db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT id, wallet FROM usuarios WHERE activo = 1")
    usuarios = c.fetchall()
    conn.close()
    total_quemado = 0.0
    for u in usuarios:
        total_quemado += engine.ejecutar_quema_penalizacion(u["id"], u["wallet"])
    return {"quemado_total": total_quemado}


def procesar_retiro(usuario_id: int, wallet: str, cantidad_tokens: float) -> dict:
    """procesa una solicitud de retiro de tokens a fiat."""
    engine = get_tokenomics()
    return engine.solicitar_retiro(usuario_id, wallet, cantidad_tokens)


def init_tokenomics_db():
    """inicializa la base de datos de tokenomics (crea singleton)."""
    get_tokenomics()