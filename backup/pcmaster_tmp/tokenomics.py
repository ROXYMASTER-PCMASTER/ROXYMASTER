# tokenomics.py - Motor económico KBT para ROXYMASTER v6.1
import sqlite3
import os
import json
import math
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'roxymaster.db')

# ========== PARÁMETROS GLOBALES (se pueden sobrescribir desde BD) ==========
DEFAULT_PARAMS = {
    "K": 20.00,           # USD que Kick paga al streamer por 1000 espectadores-hora
    "FX": 3.70,           # PEN por USD
    "P_token": 1.00,      # Precio ancla del token (PEN)
    "H": 720,             # horas/mes (24*30)
    "E": 0.005,           # costo eléctrico PEN/hora-perfil
    "beta": 0.0,          # fracción de pagos de streamers en KBT (0 al inicio)
    "G": 9.00,            # USD que recibe el granjero por bloque (según mes)
    "HH_mult": 2.0,       # multiplicador de horas en Happy Hour (por defecto 2.0)
    "alfa_nuevo": 0.5,    # fracción de emisión nueva que se vende en marketplace
    "gamma": 0.5,         # fracción de transferencias KBT que pasan por marketplace
    "comision_retiro_0_30": 0.33,
    "comision_retiro_31_60": 0.25,
    "comision_retiro_61_90": 0.15,
    "comision_retiro_90_plus": 0.0,
    "comision_marketplace": 0.15,  # 15% para el dueño
    "comision_referido": 0.10,     # 10% de los tokens minados del referido
    "limite_retiro_mensual_USD": 999.0,
    "nivel_bronce_uptime": 0.90,
    "nivel_plata_uptime": 0.95,
    "nivel_oro_uptime": 0.99,
    "w_bronce": 1.1,
    "w_plata": 1.2,
    "w_oro": 1.3,
    "penalizacion_inactividad_porcentaje": 0.05,  # 5% mensual
    "tolerancia_reinicio_minutos": 30,
    "ventana_penalizacion_dias": 7,
    "horas_inactividad_dispara": 11,
    "mins_validacion_consecutivos": 62,
    "gracia_oro_desconexion_min": 30,
    # Niveles de streamers y precios P_sys (USD)
    "niveles_streamer": {
        0: {"min": 0, "max": 4999, "P_sys": 9.0},
        1: {"min": 5000, "max": 14999, "P_sys": 10.0},
        2: {"min": 15000, "max": 49999, "P_sys": 11.0},
        3: {"min": 50000, "max": 499999, "P_sys": 12.0},
        4: {"min": 500000, "max": 999999, "P_sys": 14.0},
        5: {"min": 1000000, "max": 999999999, "P_sys": 16.0}
    }
}

class Tokenomics:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._init_db()
        self.params = self.load_parameters()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        # Tabla de parámetros
        c.execute('''CREATE TABLE IF NOT EXISTS parametros (
                        clave TEXT PRIMARY KEY,
                        valor TEXT)''')
        # Tabla de reservas (Fondo de Recolección)
        c.execute('''CREATE TABLE IF NOT EXISTS reserva (
                        id INTEGER PRIMARY KEY CHECK(id=1),
                        tokens REAL DEFAULT 0,
                        soles REAL DEFAULT 0)''')
        # Tabla de granjeros
        c.execute('''CREATE TABLE IF NOT EXISTS granjeros (
                        id TEXT PRIMARY KEY,
                        nombre TEXT,
                        referido_por TEXT,
                        saldo_tokens REAL DEFAULT 0,
                        saldo_tokens_quemables REAL DEFAULT 0,
                        saldo_tokens_comprados REAL DEFAULT 0,
                        saldo_soles REAL DEFAULT 0,
                        uptime_horas REAL DEFAULT 0,
                        horas_ponderadas REAL DEFAULT 0,
                        nivel_fiabilidad TEXT DEFAULT 'Bronce',
                        penalizacion_activa INTEGER DEFAULT 0,
                        fecha_registro TEXT DEFAULT (datetime('now')))''')
        # Tabla de perfiles (por granjero)
        c.execute('''CREATE TABLE IF NOT EXISTS perfiles (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        granjero_id TEXT,
                        nombre_perfil TEXT,
                        tipo TEXT DEFAULT 'local',   -- 'local' o 'roxybrowser'
                        estado TEXT DEFAULT 'desconectado',
                        ip_wan TEXT,
                        proxy_hogar TEXT,
                        horas_conexion REAL DEFAULT 0,
                        horas_en_uso REAL DEFAULT 0,
                        horas_hh REAL DEFAULT 0,
                        ultima_conexion TEXT)''')
        # Tabla de transacciones
        c.execute('''CREATE TABLE IF NOT EXISTS transacciones (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        granjero_id TEXT,
                        tipo TEXT,
                        monto REAL,
                        detalle TEXT,
                        fecha TEXT DEFAULT (datetime('now')))''')
        # Tabla de sesiones de perfil (para validación 62 minutos)
        c.execute('''CREATE TABLE IF NOT EXISTS sesiones_perfil (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        perfil_id INTEGER,
                        granjero_id TEXT,
                        inicio TEXT DEFAULT (datetime('now')),
                        fin TEXT,
                        minutos_acumulados REAL DEFAULT 0,
                        validada INTEGER DEFAULT 0,
                        recompensa_kbt REAL DEFAULT 0)''')
        # Migración: añadir columnas si no existen (para DBs existentes)
        try:
            c.execute("ALTER TABLE granjeros ADD COLUMN saldo_tokens_quemables REAL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE granjeros ADD COLUMN saldo_tokens_comprados REAL DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE transacciones ADD COLUMN detalle TEXT")
        except sqlite3.OperationalError:
            pass
        # Migrar saldos existentes: todo lo acumulado va a quemables
        c.execute("UPDATE granjeros SET saldo_tokens_quemables = saldo_tokens WHERE saldo_tokens_quemables = 0 AND saldo_tokens > 0")
        # Insertar parámetros por defecto si no existen
        for k, v in DEFAULT_PARAMS.items():
            if isinstance(v, dict):
                v = json.dumps(v)
            c.execute("INSERT OR IGNORE INTO parametros (clave, valor) VALUES (?,?)", (k, str(v)))
        c.execute("INSERT OR IGNORE INTO reserva (id, tokens, soles) VALUES (1,0,0)")
        conn.commit()
        conn.close()

    def load_parameters(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        params = {}
        for row in c.execute("SELECT clave, valor FROM parametros"):
            val = row[1]
            try:
                val = json.loads(val)
            except:
                try:
                    val = float(val) if '.' in val else int(val)
                except:
                    pass
            params[row[0]] = val
        conn.close()
        return params

    def set_parameter(self, key, value):
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT OR REPLACE INTO parametros (clave, valor) VALUES (?,?)", (key, str(value)))
        conn.commit()
        conn.close()
        self.params[key] = value

    def reset_parameters(self):
        for k, v in DEFAULT_PARAMS.items():
            self.set_parameter(k, v)

    def get_param(self, key):
        return self.params.get(key, DEFAULT_PARAMS.get(key))

    # ---------- CÁLCULOS ECONÓMICOS ----------
    def calcular_bloques_vendidos(self, N):
        """Número de bloques (1000 espectadores-hora) vendidos si todos los perfiles están en uso."""
        return int(0.72 * N)

    def calcular_recompensa_total_granjeros(self, N, beta, G, FX):
        """R_total en KBT que se reparte entre granjeros."""
        B = self.calcular_bloques_vendidos(N)
        return B * G * FX

    def calcular_emision_nueva(self, N, beta):
        """Tokens nuevos inyectados al ecosistema (1-beta)*B*G*FX"""
        B = self.calcular_bloques_vendidos(N)
        return (1 - beta) * B * self.params['G'] * self.params['FX']

    def calcular_margen_fiat_dueno(self, N, beta, P_sys_prom):
        B = self.calcular_bloques_vendidos(N)
        G = self.params['G']
        FX = self.params['FX']
        return (1 - beta) * B * (P_sys_prom - G) * FX

    def calcular_margen_kbt_to_re(self, N, beta, P_sys_prom):
        """Margen de bloques pagados en KBT que va al Fondo de Recolección."""
        B = self.calcular_bloques_vendidos(N)
        G = self.params['G']
        FX = self.params['FX']
        return beta * B * (P_sys_prom - G) * FX

    def calcular_transferencia_kbt(self, N, beta):
        """Tokens transferidos directamente de streamers (que pagan en KBT) a granjeros."""
        B = self.calcular_bloques_vendidos(N)
        return beta * B * self.params['G'] * self.params['FX']

    def calcular_volumen_marketplace(self, N, beta, P_sys_prom):
        """V_mkt estimado (en PEN) que pasa por el marketplace."""
        alfa = self.params['alfa_nuevo']
        gamma = self.params['gamma']
        E_nueva = self.calcular_emision_nueva(N, beta)
        transf_kbt = self.calcular_transferencia_kbt(N, beta)
        return alfa * E_nueva + gamma * beta * self.calcular_bloques_vendidos(N) * P_sys_prom * self.params['FX']

    def calcular_comision_marketplace(self, N, beta, P_sys_prom):
        V_mkt = self.calcular_volumen_marketplace(N, beta, P_sys_prom)
        return self.params['comision_marketplace'] * V_mkt

    def calcular_nivel_fiabilidad(self, uptime_ratio):
        if uptime_ratio >= self.params['nivel_oro_uptime']:
            return 'Oro', self.params['w_oro']
        elif uptime_ratio >= self.params['nivel_plata_uptime']:
            return 'Plata', self.params['w_plata']
        else:
            return 'Bronce', self.params['w_bronce']

    def repartir_tokens_mensual(self, N, perfiles_con_horas):
        """
        perfiles_con_horas: lista de dicts con:
            granjero_id, nivel_fiabilidad (str), horas_normal, horas_hh
        Retorna lista de (granjero_id, tokens_asignados)
        """
        P = self.params
        B = self.calcular_bloques_vendidos(N)
        R_total = B * P['G'] * P['FX']

        suma_ponderada = 0
        datos = []
        for p in perfiles_con_horas:
            w = P['w_'+p['nivel_fiabilidad'].lower()] if p['nivel_fiabilidad'].lower() in ['bronce','plata','oro'] else P['w_bronce']
            h_pond = w * (p['horas_normal'] + P['HH_mult'] * p.get('horas_hh', 0))
            datos.append({**p, 'w': w, 'h_pond': h_pond})
            suma_ponderada += h_pond
        if suma_ponderada == 0:
            return [(p['granjero_id'], 0) for p in datos]

        reparto = []
        for d in datos:
            tokens = (d['h_pond'] / suma_ponderada) * R_total
            reparto.append((d['granjero_id'], tokens))
        return reparto

    def aplicar_comisiones_retiro(self, tokens, antiguedad_dias):
        if antiguedad_dias <= 30:
            comision = self.params['comision_retiro_0_30']
        elif antiguedad_dias <= 60:
            comision = self.params['comision_retiro_31_60']
        elif antiguedad_dias <= 90:
            comision = self.params['comision_retiro_61_90']
        else:
            comision = self.params['comision_retiro_90_plus']
        return tokens * (1 - comision), tokens * comision

    # ---------- OPERACIONES DE BASE DE DATOS ----------
    def registrar_granjero(self, granjero_id, nombre, referido=None):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        try:
            c.execute("INSERT INTO granjeros (id, nombre, referido_por) VALUES (?,?,?)",
                      (granjero_id, nombre, referido))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def obtener_granjero(self, granjero_id):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT * FROM granjeros WHERE id=?", (granjero_id,))
        row = c.fetchone()
        conn.close()
        return row

    def obtener_todos_granjeros(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT * FROM granjeros")
        rows = c.fetchall()
        conn.close()
        return rows

    def actualizar_saldo(self, granjero_id, delta_tokens):
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE granjeros SET saldo_tokens = saldo_tokens + ? WHERE id=?", (delta_tokens, granjero_id))
        conn.commit()
        conn.close()

    def registrar_perfil(self, granjero_id, nombre_perfil, ip_wan, proxy_hogar, tipo='local'):
        conn = sqlite3.connect(self.db_path)
        conn.execute('''INSERT INTO perfiles (granjero_id, nombre_perfil, tipo, ip_wan, proxy_hogar, estado, ultima_conexion)
                        VALUES (?,?,?,?,?,'conectado',datetime('now'))''',
                     (granjero_id, nombre_perfil, tipo, ip_wan, proxy_hogar))
        conn.commit()
        conn.close()

    def actualizar_horas_perfil(self, perfil_id, horas_normal, horas_hh):
        conn = sqlite3.connect(self.db_path)
        conn.execute('''UPDATE perfiles SET horas_conexion = horas_conexion + ?,
                        horas_en_uso = horas_en_uso + ?,
                        horas_hh = horas_hh + ?,
                        ultima_conexion = datetime('now')
                        WHERE id=?''', (horas_normal + horas_hh, horas_normal, horas_hh, perfil_id))
        conn.commit()
        conn.close()

    def verificar_penalizaciones(self):
        # lógica simplificada: se implementaría el chequeo de 11h en ventana 7d etc.
        pass

    # ---------- MARKETPLACE ----------
    def realizar_transferencia_p2p(self, vendedor_id, comprador_id, tokens):
        comision = tokens * self.params['comision_marketplace']
        self.actualizar_saldo(vendedor_id, -tokens)
        self.actualizar_saldo(comprador_id, tokens - comision)
        # Registrar transacción
        conn = sqlite3.connect(self.db_path)
        conn.execute("INSERT INTO transacciones (granjero_id, tipo, monto) VALUES (?,?,?)",
                     (vendedor_id, 'venta_p2p', tokens))
        conn.execute("INSERT INTO transacciones (granjero_id, tipo, monto) VALUES (?,?,?)",
                     (comprador_id, 'compra_p2p', tokens))
        conn.commit()
        conn.close()

    # ---------- FONDO DE RECOLECCIÓN ----------
    def obtener_reserva(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT tokens, soles FROM reserva WHERE id=1")
        row = c.fetchone()
        conn.close()
        return row if row else (0,0)

    def actualizar_reserva(self, delta_tokens, delta_soles):
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE reserva SET tokens = tokens + ?, soles = soles + ? WHERE id=1", (delta_tokens, delta_soles))
        conn.commit()
        conn.close()

    # ---------- SALDOS SEPARADOS (Quemables vs Comprados) ----------
    def acreditar_tokens_generados(self, granjero_id, tokens):
        """Acredita tokens generados (quemables) por actividad"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE granjeros SET saldo_tokens = saldo_tokens + ?, saldo_tokens_quemables = saldo_tokens_quemables + ? WHERE id=?",
                     (tokens, tokens, granjero_id))
        conn.execute("INSERT INTO transacciones (granjero_id, tipo, monto, detalle) VALUES (?,?,?,?)",
                     (granjero_id, 'generacion', tokens, 'quemable'))
        conn.commit()
        conn.close()

    def comprar_tokens(self, granjero_id, tokens, soles_pagados):
        """Compra de tokens con dinero real (NO quemables)"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE granjeros SET saldo_tokens = saldo_tokens + ?, saldo_tokens_comprados = saldo_tokens_comprados + ?, saldo_soles = saldo_soles + ? WHERE id=?",
                     (tokens, tokens, soles_pagados, granjero_id))
        conn.execute("INSERT INTO transacciones (granjero_id, tipo, monto, detalle) VALUES (?,?,?,?)",
                     (granjero_id, 'compra', tokens, f'comprado S/{soles_pagados:.2f}'))
        # Actualizar reserva
        conn.execute("UPDATE reserva SET soles = soles + ? WHERE id=1", (soles_pagados,))
        conn.commit()
        conn.close()

    def quemar_tokens(self, granjero_id, tokens):
        """Quema tokens del saldo quemable del granjero"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT saldo_tokens_quemables FROM granjeros WHERE id=?", (granjero_id,))
        row = c.fetchone()
        if not row or row[0] < tokens:
            conn.close()
            return False
        conn.execute("UPDATE granjeros SET saldo_tokens = saldo_tokens - ?, saldo_tokens_quemables = saldo_tokens_quemables - ? WHERE id=?",
                     (tokens, tokens, granjero_id))
        conn.execute("INSERT INTO transacciones (granjero_id, tipo, monto, detalle) VALUES (?,?,?,?)",
                     (granjero_id, 'quema', tokens, 'tasa_quema_mensual'))
        conn.commit()
        conn.close()
        return True

    def aplicar_quema_mensual(self, tasa_quema=None):
        """Aplica tasa de quema a todos los saldos quemables"""
        if tasa_quema is None:
            tasa_quema = self.params.get('tasa_quema_mensual', 5.0) / 100.0
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT id, saldo_tokens_quemables FROM granjeros WHERE saldo_tokens_quemables > 0")
        rows = c.fetchall()
        total_quemado = 0
        for gid, saldo_q in rows:
            a_quemar = round(saldo_q * tasa_quema, 4)
            if a_quemar > 0:
                conn.execute("UPDATE granjeros SET saldo_tokens = saldo_tokens - ?, saldo_tokens_quemables = saldo_tokens_quemables - ? WHERE id=?",
                             (a_quemar, a_quemar, gid))
                conn.execute("INSERT INTO transacciones (granjero_id, tipo, monto, detalle) VALUES (?,?,?,?)",
                             (gid, 'quema_mensual', a_quemar, f'tasa {tasa_quema*100:.1f}%'))
                total_quemado += a_quemar
        conn.commit()
        conn.close()
        return total_quemado

    # ---------- SESIONES DE PERFIL (Validación 62 minutos) ----------
    def iniciar_sesion_perfil(self, perfil_id, granjero_id):
        """Inicia una sesión de tracking para un perfil"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("INSERT INTO sesiones_perfil (perfil_id, granjero_id) VALUES (?,?)", (perfil_id, granjero_id))
        sesion_id = c.lastrowid
        conn.commit()
        conn.close()
        return sesion_id

    def acumular_minutos_sesion(self, sesion_id, minutos):
        """Acumula minutos a una sesión activa y verifica si alcanzó 62 minutos"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT minutos_acumulados, validada FROM sesiones_perfil WHERE id=?", (sesion_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return None
        acumulado, validada = row
        if validada:
            conn.close()
            return {'ya_validada': True, 'minutos': acumulado}

        nuevo_total = acumulado + minutos
        mins_requeridos = self.params.get('mins_validacion_consecutivos', 62)

        if nuevo_total >= mins_requeridos and acumulado < mins_requeridos:
            # ¡Validación alcanzada! Calcular recompensa
            recompensa = self._calcular_recompensa_validacion()
            conn.execute("UPDATE sesiones_perfil SET minutos_acumulados = ?, validada = 1, recompensa_kbt = ?, fin = datetime('now') WHERE id=?",
                         (nuevo_total, recompensa, sesion_id))
            # Acreditar tokens quemables al granjero
            conn.execute("UPDATE granjeros SET saldo_tokens = saldo_tokens + ?, saldo_tokens_quemables = saldo_tokens_quemables + ? WHERE id=?",
                         (recompensa, recompensa, granjero_id))
            conn.execute("INSERT INTO transacciones (granjero_id, tipo, monto, detalle) VALUES (?,?,?,?)",
                         (granjero_id, 'validacion_62min', recompensa, f'perfil {perfil_id}'))
            conn.commit()
            conn.close()
            return {'validada': True, 'minutos': nuevo_total, 'recompensa': recompensa}
        else:
            conn.execute("UPDATE sesiones_perfil SET minutos_acumulados = ? WHERE id=?", (nuevo_total, sesion_id))
            conn.commit()
            conn.close()
            return {'validada': False, 'minutos': nuevo_total, 'faltante': max(0, mins_requeridos - nuevo_total)}

    def _calcular_recompensa_validacion(self):
        """Calcula la recompensa en KBT por completar 62 minutos de conexión"""
        # Base: 1 hora de atención vale ~0.01 KBT (escalable)
        return round(0.01 * (1 + (self.params.get('bonus_happy_hour', 0) / 100 if self.params.get('happy_hour_activo', False) else 0)), 4)

    def obtener_sesiones_activas(self, granjero_id=None):
        """Obtiene sesiones no validadas aún"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        if granjero_id:
            c.execute("SELECT s.id, s.perfil_id, s.granjero_id, s.minutos_acumulados, s.validada, s.recompensa_kbt, p.nombre_perfil FROM sesiones_perfil s LEFT JOIN perfiles p ON s.perfil_id = p.id WHERE s.granjero_id = ? AND s.validada = 0", (granjero_id,))
        else:
            c.execute("SELECT s.id, s.perfil_id, s.granjero_id, s.minutos_acumulados, s.validada, s.recompensa_kbt, p.nombre_perfil FROM sesiones_perfil s LEFT JOIN perfiles p ON s.perfil_id = p.id WHERE s.validada = 0")
        rows = c.fetchall()
        conn.close()
        return [{'id': r[0], 'perfil_id': r[1], 'granjero_id': r[2], 'minutos': r[3], 'validada': bool(r[4]), 'recompensa': r[5], 'perfil_nombre': r[6]} for r in rows]

    def obtener_saldo_detallado(self, granjero_id):
        """Obtiene saldo separado (quemable vs comprado)"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT saldo_tokens, saldo_tokens_quemables, saldo_tokens_comprados, saldo_soles FROM granjeros WHERE id=?", (granjero_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        return {
            'total': row[0],
            'quemable': row[1],
            'comprado': row[2],
            'soles': row[3]
        }

    # ---------- ESTADÍSTICAS KBT ----------
    def get_stats(self):
        """Retorna estadísticas generales del motor KBT"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM granjeros")
        total_granjeros = c.fetchone()[0]
        c.execute("SELECT COALESCE(SUM(saldo_tokens),0) FROM granjeros")
        tokens_circulacion = c.fetchone()[0]
        c.execute("SELECT COALESCE(SUM(saldo_tokens_quemables),0) FROM granjeros")
        tokens_quemables_total = c.fetchone()[0]
        c.execute("SELECT COALESCE(SUM(saldo_tokens_comprados),0) FROM granjeros")
        tokens_comprados_total = c.fetchone()[0]
        c.execute("SELECT COALESCE(SUM(saldo_soles),0) FROM granjeros")
        soles_granjeros = c.fetchone()[0]
        c.execute("SELECT tokens, soles FROM reserva WHERE id=1")
        reserva = c.fetchone() or (0, 0)
        c.execute("SELECT COUNT(*) FROM perfiles")
        total_perfiles = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM transacciones")
        total_transacciones = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM sesiones_perfil WHERE validada = 1")
        sesiones_validadas = c.fetchone()[0]
        conn.close()

        return {
            "total_granjeros": total_granjeros,
            "tokens_en_circulacion": round(tokens_circulacion, 4),
            "tokens_quemables_total": round(tokens_quemables_total, 4),
            "tokens_comprados_total": round(tokens_comprados_total, 4),
            "soles_granjeros": round(soles_granjeros, 2),
            "reserva_tokens": round(reserva[0], 4),
            "reserva_soles": round(reserva[1], 2),
            "total_perfiles": total_perfiles,
            "total_transacciones": total_transacciones,
            "sesiones_validadas": sesiones_validadas,
        }
