#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ROXYMASTER v6.2 — PCMASTER SERVER
==================================
Servidor WebSocket + HTTP API + SQLite + JWT + bcrypt + Economía de Tokens

Arquitectura:
  - WebSocket en :5006 (conexión con PCBOTs)
  - HTTP API en :8086 (portal web, login, dashboard, comandos)
  - SQLite para persistencia (usuarios, sesiones, transacciones, tokens)
  - JARVIS con Ollama para comentarios automáticos
"""

import asyncio
import websockets
import json
import time
import os
import sys
import hashlib
import hmac
import secrets
import threading
import http.server
import socketserver
import socket
import sqlite3
import re
import random
import requests
import logging
from datetime import datetime, timedelta
from urllib.parse import urlparse
from pathlib import Path

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

# Intentar importar bcrypt (fallback simple si no está)
try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False
    print("[!] bcrypt no instalado. Usando hash SHA256 (instalar: pip install bcrypt)")

# Intento de importar PyJWT
try:
    import jwt as pyjwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    print("[!] PyJWT no instalado. Usando tokens simulados (instalar: pip install PyJWT)")

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('PCMASTER')

# Directorios
BASE_DIR = Path(__file__).parent.parent.absolute()
SCRIPTS_DIR = BASE_DIR / "scripts"
DB_PATH = BASE_DIR / "data" / "roxy_master.db"
PROMPTS_DIR = BASE_DIR / "prompts"

# Crear directorios
(BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
PROMPTS_DIR.mkdir(parents=True, exist_ok=True)

# IP y puertos
IP = "0.0.0.0"
PUERTO = 5006
HTTP_PORT = 8086

# Secreto JWT
JWT_SECRET = secrets.token_hex(32)  # Se regenera en cada inicio (o usar fijo)

# ============================================================================
# BASE DE DATOS SQLite
# ============================================================================

def init_db():
    """Inicializa la base de datos SQLite"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            rol TEXT DEFAULT 'usuario',
            tokens_comprados INTEGER DEFAULT 0,
            tokens_ganados INTEGER DEFAULT 0,
            tokens_gastados INTEGER DEFAULT 0,
            pcbot_id TEXT,
            modo TEXT DEFAULT 'conectado',
            fecha_registro TEXT DEFAULT (datetime('now')),
            ultimo_login TEXT
        );

        CREATE TABLE IF NOT EXISTS sesiones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            ip_origen TEXT,
            fecha_inicio TEXT DEFAULT (datetime('now')),
            fecha_expiracion TEXT,
            activo INTEGER DEFAULT 1,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        );

        CREATE TABLE IF NOT EXISTS transacciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            cantidad INTEGER NOT NULL,
            motivo TEXT,
            fecha TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
        );

        CREATE TABLE IF NOT EXISTS tasa_quema (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT NOT NULL,
            tokens_quemados INTEGER DEFAULT 0
        );
    """)

    # Crear admin por defecto si no existe
    admin_email = "PCMASTER"
    cursor.execute("SELECT id FROM usuarios WHERE email = ?", (admin_email,))
    if not cursor.fetchone():
        admin_hash = hash_password("Abc123$_")
        cursor.execute(
            "INSERT INTO usuarios (email, password_hash, rol, tokens_comprados) VALUES (?, ?, 'admin', 150000)",
            (admin_email, admin_hash)
        )
        logger.info("[DB] Usuario admin PCMASTER creado (150,000 tokens)")

    conn.commit()
    conn.close()
    logger.info("[DB] Base de datos inicializada")

# ============================================================================
# HASH DE CONTRASEÑAS
# ============================================================================

def hash_password(password):
    """Hashea contraseña con bcrypt o SHA256"""
    if BCRYPT_AVAILABLE:
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    else:
        # Fallback simple (no recomendado para producción)
        return hashlib.sha256(f"roxy_salt_{password}".encode()).hexdigest()

def verify_password(password, password_hash):
    """Verifica contraseña"""
    if BCRYPT_AVAILABLE:
        try:
            return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
        except:
            pass
    # Fallback SHA256
    return password_hash == hashlib.sha256(f"roxy_salt_{password}".encode()).hexdigest()

# ============================================================================
# JWT TOKENS
# ============================================================================

def generar_token(usuario_id, email, rol, duracion_horas=24):
    """Genera token JWT"""
    if JWT_AVAILABLE:
        payload = {
            "sub": usuario_id,
            "email": email,
            "rol": rol,
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(hours=duracion_horas)
        }
        return pyjwt.encode(payload, JWT_SECRET, algorithm="HS256")
    else:
        # Fallback: token simple (no seguro para producción)
        raw = f"{usuario_id}:{email}:{rol}:{time.time()}"
        token = hashlib.sha256(f"{JWT_SECRET}{raw}".encode()).hexdigest()
        return f"sim_{token}"

def verificar_token(token):
    """Verifica token JWT y retorna (usuario_id, email, rol) o None"""
    if not token:
        return None

    # Token simulado
    if token.startswith("sim_"):
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT u.id, u.email, u.rol FROM sesiones s JOIN usuarios u ON s.usuario_id = u.id "
            "WHERE s.token = ? AND s.activo = 1",
            (token,)
        )
        row = cursor.fetchone()
        conn.close()
        return row if row else None

    # JWT real
    if JWT_AVAILABLE:
        try:
            payload = pyjwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            return (payload["sub"], payload["email"], payload["rol"])
        except Exception:
            pass

    # Verificar en DB como fallback
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute(
        "SELECT u.id, u.email, u.rol FROM sesiones s JOIN usuarios u ON s.usuario_id = u.id "
        "WHERE s.token = ? AND s.activo = 1 AND datetime(s.fecha_expiracion) > datetime('now')",
        (token,)
    )
    row = cursor.fetchone()
    conn.close()
    return row if row else None

# ============================================================================
# ECONOMÍA DE TOKENS
# ============================================================================

def acreditar_tokens_db(usuario_id, cantidad, motivo="ganado_por_tiempo"):
    """Acredita tokens a un usuario (ganados = se queman)"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    if motivo.startswith("compra"):
        cursor.execute(
            "UPDATE usuarios SET tokens_comprados = tokens_comprados + ? WHERE id = ?",
            (cantidad, usuario_id)
        )
    else:
        cursor.execute(
            "UPDATE usuarios SET tokens_ganados = tokens_ganados + ? WHERE id = ?",
            (cantidad, usuario_id)
        )

    # Registrar transacción
    cursor.execute(
        "INSERT INTO transacciones (usuario_id, tipo, cantidad, motivo) VALUES (?, ?, ?, ?)",
        (usuario_id, "ganado" if not motivo.startswith("compra") else "comprado", cantidad, motivo)
    )

    conn.commit()
    conn.close()
    logger.info(f"[TOKENS] +{cantidad} tokens a usuario_id={usuario_id} ({motivo})")

def gastar_tokens_db(usuario_id, cantidad, motivo="gasto"):
    """Gasta tokens de un usuario (primero ganados, luego comprados)"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    cursor.execute("SELECT tokens_ganados, tokens_comprados FROM usuarios WHERE id = ?", (usuario_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False

    ganados, comprados = row
    total = ganados + comprados
    if total < cantidad:
        conn.close()
        return False

    # Gastar primero de ganados
    gastar_ganados = min(ganados, cantidad)
    gastar_comprados = cantidad - gastar_ganados

    if gastar_ganados > 0:
        cursor.execute("UPDATE usuarios SET tokens_ganados = tokens_ganados - ? WHERE id = ?",
                       (gastar_ganados, usuario_id))
    if gastar_comprados > 0:
        cursor.execute("UPDATE usuarios SET tokens_comprados = tokens_comprados - ? WHERE id = ?",
                       (gastar_comprados, usuario_id))

    cursor.execute(
        "INSERT INTO transacciones (usuario_id, tipo, cantidad, motivo) VALUES (?, 'gastado', ?, ?)",
        (usuario_id, cantidad, motivo)
    )

    conn.commit()
    conn.close()
    return True

def ejecutar_quema_diaria():
    """Quema 1% de tokens ganados cada 24h (solo tokens ganados, no comprados)"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    hoy = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("SELECT id FROM tasa_quema WHERE fecha = ?", (hoy,))
    if cursor.fetchone():
        conn.close()
        return  # Ya se ejecutó hoy

    total_quemados = 0
    cursor.execute("SELECT id, tokens_ganados FROM usuarios WHERE tokens_ganados > 0")
    for uid, ganados in cursor.fetchall():
        quemar = max(1, int(ganados * 0.01))  # 1% o al menos 1 token
        cursor.execute("UPDATE usuarios SET tokens_ganados = tokens_ganados - ? WHERE id = ?",
                       (quemar, uid))
        total_quemados += quemar
        cursor.execute(
            "INSERT INTO transacciones (usuario_id, tipo, cantidad, motivo) VALUES (?, 'quemado', ?, 'tasa_quema_diaria_1pct')",
            (uid, quemar)
        )

    cursor.execute("INSERT INTO tasa_quema (fecha, tokens_quemados) VALUES (?, ?)", (hoy, total_quemados))
    conn.commit()
    conn.close()

    if total_quemados > 0:
        logger.info(f"[QUEMA] {total_quemados} tokens quemados hoy (1% tasa diaria)")

# ============================================================================
# JARVIS - AGENTE IA
# ============================================================================

class Jarvis:
    """Agente IA que genera comentarios usando Ollama"""
    def __init__(self):
        self.ollama_url = "http://localhost:11434/api/generate"
        self.modelo = "llama3.2"
        self.memoria_por_url = {}
        self.comentarios_generados = 0
        self.ultimo_uso = 0
        self._cargar_prompt()

    def _cargar_prompt(self):
        prompt_path = PROMPTS_DIR / "maestro.txt"
        if prompt_path.exists():
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.maestro_prompt = f.read()
        else:
            self.maestro_prompt = "Eres un asistente que genera comentarios naturales y variados para streams en vivo."

    def generar_comentario(self, contexto_previo=None, url=None, nivel="medio"):
        """Genera un comentario usando Ollama"""
        ahora = time.time()
        if ahora - self.ultimo_uso < 10:
            return None  # Rate limit: 1 cada 10s

        self.ultimo_uso = ahora

        prompt = f"""{self.maestro_prompt}

Contexto del stream: {contexto_previo if contexto_previo else 'Nuevo stream'}
URL: {url if url else 'No especificada'}
Nivel de interacción: {nivel}

Genera UN SOLO comentario corto (máximo 60 caracteres) en español, natural y variado.
No uses hashtags. No repitas comentarios anteriores.
Comentario:"""

        try:
            r = requests.post(self.ollama_url, json={
                "model": self.modelo,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.9, "max_tokens": 50}
            }, timeout=30)

            if r.status_code == 200:
                comentario = r.json().get("response", "").strip()
                comentario = re.sub(r'[^\w\sáéíóúñüÁÉÍÓÚÑÜ.,!?¿¡@# ]', '', comentario)
                comentario = comentario[:60].strip()

                if comentario:
                    self.comentarios_generados += 1
                    if url:
                        if url not in self.memoria_por_url:
                            self.memoria_por_url[url] = []
                        self.memoria_por_url[url].append(comentario)
                        if len(self.memoria_por_url[url]) > 50:
                            self.memoria_por_url[url].pop(0)
                    logger.info(f"[JARVIS] Comentario: {comentario}")
                    return comentario
        except Exception as e:
            logger.error(f"[JARVIS] Error: {e}")

        return None

    def get_stats(self):
        return {
            "generados": self.comentarios_generados,
            "modelo": self.modelo,
            "contextos_activos": len(self.memoria_por_url)
        }

# ============================================================================
# ESTADO GLOBAL DEL SERVIDOR
# ============================================================================

# PCBOTs conectados
pcbots = {}           # {pcbot_id: websocket}
pcbots_info = {}      # {pcbot_id: {ip_local, ip_tailscale, perfiles, start_time, ...}}
pcbots_perfiles = {}  # {pcbot_id: [perfil_info, ...]}

# Perfiles globales
perfiles_map = {}     # {pcbot_id::dirId: {name, dirId, pcbot, estado, url_actual, ultimo_uso, ...}}

# Grupos / sesiones activas
grupos = {}           # {url: {perfiles: [], comentarios: bool, inicio: float, duracion: float}}

# Tokens por PCBOT usuario
pcbot_tokens = {}     # {pcbot_id: {ganados: 0, comprados: 0, hoy: 0}}

# Instancia JARVIS
jarvis = Jarvis()

# ============================================================================
# MANEJO DE CONEXIONES WebSocket (PCBOTs)
# ============================================================================

async def manejar_conexion(websocket):
    """Maneja conexión WebSocket de un PCBOT (websockets >=14)"""
    pcbot_id = None

    try:
        async for msg in websocket:
            try:
                data = json.loads(msg)
            except json.JSONDecodeError:
                logger.warning(f"Mensaje JSON inválido: {msg[:100]}")
                continue

            msg_type = data.get("type", "")
            payload = data.get("data", {})

            # ---- IDENTIFY ----
            if msg_type == "identify":
                pc_id = payload.get("pc_id", "unknown")
                pcbot_id = pc_id
                pcbots[pcbot_id] = websocket
                pcbots_info[pcbot_id] = {
                    "ip_local": payload.get("ip_local", "?"),
                    "ip_tailscale": payload.get("ip_tailscale", "?"),
                    "pc_name": payload.get("pc_name", "?"),
                    "perfiles": payload.get("perfiles", 0),
                    "apps": payload.get("apps", {}),
                    "start_time": time.time(),
                    "estado": "conectado"
                }

                # Procesar perfiles enviados por el PCBOT
                perfiles_lista = payload.get("perfiles_lista", [])
                pcbots_perfiles[pcbot_id] = perfiles_lista

                for pf in perfiles_lista:
                    key = f"{pcbot_id}::{pf.get('dirId', pf.get('name', '?'))}"
                    perfiles_map[key] = {
                        "name": pf.get("name", "?"),
                        "dirId": pf.get("dirId", pf.get("name", "?")),
                        "pcbot": pcbot_id,
                        "estado": pf.get("estado", "inactivo"),
                        "url_actual": pf.get("url", ""),
                        "ultimo_uso": time.time() if pf.get("estado") == "activo" else 0
                    }

                # Inicializar tokens para este PCBOT
                if pcbot_id not in pcbot_tokens:
                    pcbot_tokens[pcbot_id] = {"ganados": 0, "comprados": 0, "hoy": 0}

                logger.info(f"[+] PCBOT conectado: {pcbot_id} ({pcbots_info[pcbot_id]['ip_local']}) - {len(perfiles_lista)} perfiles")

                # Responder handshake
                await websocket.send(json.dumps({
                    "type": "identify_ack",
                    "data": {"status": "ok", "server": "PCMASTER v6.2", "pcbot_id": pcbot_id}
                }))

            # ---- HEARTBEAT ----
            elif msg_type == "heartbeat" and pcbot_id:
                if pcbot_id in pcbots_info:
                    pcbots_info[pcbot_id]["ultimo_heartbeat"] = time.time()
                    pcbots_info[pcbot_id]["estado"] = "conectado"

                    # Actualizar conteo de perfiles si viene en el heartbeat
                    estados = payload.get("estados", {})
                    activos = estados.get("activos", 0)
                    inactivos = estados.get("inactivos", 0)
                    colgados = estados.get("colgados", 0)
                    pcbots_info[pcbot_id]["perfiles"] = activos + inactivos + colgados
                    pcbots_info[pcbot_id]["perfiles_activos"] = activos
                    pcbots_info[pcbot_id]["perfiles_inactivos"] = inactivos
                    pcbots_info[pcbot_id]["perfiles_colgados"] = colgados

                    # Procesar tokens ganados
                    tokens_ganados = payload.get("tokens_ganados", 0)
                    if tokens_ganados > 0:
                        # Buscar usuario asociado a este PCBOT
                        conn = sqlite3.connect(str(DB_PATH))
                        cursor = conn.cursor()
                        cursor.execute("SELECT id FROM usuarios WHERE pcbot_id = ?", (pcbot_id,))
                        row = cursor.fetchone()
                        conn.close()
                        if row:
                            acreditar_tokens_db(row[0], tokens_ganados, f"pcbot_{pcbot_id}")

                        if pcbot_id in pcbot_tokens:
                            pcbot_tokens[pcbot_id]["ganados"] += tokens_ganados
                            pcbot_tokens[pcbot_id]["hoy"] += tokens_ganados

                    # Actualizar estados de perfiles
                    for pf_key, estado_info in payload.get("perfiles_estado", {}).items():
                        full_key = f"{pcbot_id}::{pf_key}"
                        if full_key in perfiles_map:
                            perfiles_map[full_key]["estado"] = estado_info.get("estado", "inactivo")
                            perfiles_map[full_key]["url_actual"] = estado_info.get("url", "")

            # ---- PERFIL REPORT (reporte individual de perfil) ----
            elif msg_type == "perfil_report" and pcbot_id:
                perfil = payload.get("perfil", {})
                dir_id = perfil.get("dirId", "")
                full_key = f"{pcbot_id}::{dir_id}"
                if full_key in perfiles_map:
                    perfiles_map[full_key].update({
                        "estado": perfil.get("estado", "inactivo"),
                        "url_actual": perfil.get("url", ""),
                        "ultimo_uso": time.time()
                    })

            # ---- DISCONNECT ----
            elif msg_type == "disconnect" and pcbot_id:
                logger.info(f"[-] PCBOT desconectado: {pcbot_id}")
                break

    except websockets.exceptions.ConnectionClosed:
        logger.info(f"[-] Conexión cerrada: {pcbot_id or 'desconocido'}")
    except Exception as e:
        logger.error(f"[!] Error en WebSocket: {type(e).__name__}: {e}")
    finally:
        if pcbot_id:
            pcbots.pop(pcbot_id, None)
            if pcbot_id in pcbots_info:
                pcbots_info[pcbot_id]["estado"] = "desconectado"
            # Marcar perfiles como inactivos
            for key in list(perfiles_map.keys()):
                if key.startswith(f"{pcbot_id}::"):
                    perfiles_map[key]["estado"] = "inactivo"

# ============================================================================
# COMANDOS
# ============================================================================

async def enviar_a_pcbot(pcbot_id, comando, datos):
    """Envía comando a un PCBOT vía WebSocket"""
    ws = pcbots.get(pcbot_id)
    if ws:
        try:
            msg = json.dumps({"type": comando, "data": datos})
            await ws.send(msg)
            return True
        except Exception as e:
            logger.error(f"Error enviando a {pcbot_id}: {e}")
    return False

async def ejecutar_asignar(cant, url, dur):
    """Asigna N perfiles a una URL por X minutos"""
    libres = []
    ocupados = set()
    for g in grupos.values():
        ocupados.update(g.get("perfiles", []))

    for key, info in perfiles_map.items():
        if key not in ocupados and info.get("estado") != "colgado":
            pcbot_id = info["pcbot"]
            modo = "conectado"
            # Verificar modo del PCBOT
            if pcbot_id in pcbots_info:
                modo = pcbots_info[pcbot_id].get("modo", "conectado")
            if modo == "conectado" or pcbot_id == "PCMASTER":
                libres.append(key)

    sel = libres[:cant]

    if len(sel) < cant:
        logger.warning(f"Solo {len(sel)} perfiles libres de {cant} solicitados")

    if url not in grupos:
        grupos[url] = {"perfiles": [], "comentarios": False, "inicio": time.time(), "duracion": dur * 60}

    for key in sel:
        grupos[url]["perfiles"].append(key)
        info = perfiles_map[key]
        await enviar_a_pcbot(info["pcbot"], "open_url", {
            "url": url,
            "profile": info["name"],
            "dirId": info["dirId"],
            "duracion": dur * 60
        })
        logger.info(f"  Abriendo {key} en {url}")
        await asyncio.sleep(2)

    logger.info(f"Asignados {len(sel)} perfiles a {url} por {dur} minutos")
    return f"Asignados {len(sel)} perfiles a {url} por {dur} minutos"

async def ejecutar_comentarios_activar(url, nivel="medio"):
    if url in grupos:
        grupos[url]["comentarios"] = True
        grupos[url]["nivel"] = nivel
        return f"Comentarios activados para {url} (nivel {nivel})"
    return f"Grupo no encontrado: {url}. Usa 'asignar N url {url} duracion M' primero."

async def ejecutar_comentarios_desactivar(url):
    if url in grupos:
        grupos[url]["comentarios"] = False
        return f"Comentarios desactivados para {url}"
    return f"Grupo no encontrado: {url}"

async def ejecutar_detener(url):
    if url in grupos:
        # Notificar a los PCBOTs que detengan
        for key in grupos[url]["perfiles"]:
            info = perfiles_map.get(key)
            if info:
                await enviar_a_pcbot(info["pcbot"], "stop", {
                    "dirId": info["dirId"],
                    "url": url
                })
        del grupos[url]
        return f"Grupo detenido: {url}"
    return f"Grupo no encontrado: {url}"

def get_uptime_str(seconds):
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds/60)}m"
    else:
        h = int(seconds/3600)
        m = int((seconds%3600)/60)
        return f"{h}h {m}m"

# ============================================================================
# DASHBOARD DATA
# ============================================================================

def get_dashboard_data():
    ahora = time.time()

    activos = sum(1 for v in perfiles_map.values() if v.get("estado") == "activo")
    inactivos = sum(1 for v in perfiles_map.values() if v.get("estado") == "inactivo")
    colgados = sum(1 for v in perfiles_map.values() if v.get("estado") == "colgado")

    # URLs activas
    urls_activas = []
    for url, g in grupos.items():
        elapsed = ahora - g["inicio"]
        restante = max(0, g.get("duracion", 0) - elapsed)
        urls_activas.append({
            "url": url,
            "perfiles_asignados": len(g["perfiles"]),
            "tiempo_restante": round(restante / 60, 1),
            "comentarios_activos": g.get("comentarios", False),
            "inicio": datetime.fromtimestamp(g["inicio"]).strftime("%H:%M:%S")
        })

    # PCBOTs
    pcbots_list = []
    for pid, info in pcbots_info.items():
        upt = get_uptime_str(ahora - info.get("start_time", ahora))
        pcbots_list.append({
            "id": pid,
            "ip_local": info.get("ip_local", "?"),
            "ip_tailscale": info.get("ip_tailscale", "?"),
            "perfiles": info.get("perfiles", 0),
            "uptime": upt,
            "estado": info.get("estado", "?")
        })

    # Perfiles
    perfiles_list = []
    for key, v in perfiles_map.items():
        t_sin_uso = get_uptime_str(ahora - v.get("ultimo_uso", 0)) if v.get("ultimo_uso") else "Nunca"
        perfiles_list.append({
            "id": key,
            "nombre": v.get("name", "?"),
            "pcbot": v.get("pcbot", "?"),
            "estado": v.get("estado", "inactivo"),
            "activo": v.get("estado") == "activo",
            "colgado": v.get("estado") == "colgado",
            "url_actual": v.get("url_actual", ""),
            "tiempo_conectado": 0,
            "tokens_ganados": 0
        })

    return {
        "pcbots_conectados": len(pcbots),
        "perfiles_totales": len(perfiles_map),
        "perfiles_activos": activos,
        "perfiles_inactivos": inactivos,
        "perfiles_colgados": colgados,
        "ip_servidor": getattr(get_dashboard_data, '_cached_ip', '0.0.0.0'),
        "jarvis_comentarios": jarvis.get_stats()["generados"],
        "jarvis_contextos": jarvis.get_stats()["contextos_activos"],
        "pcbots": pcbots_list,
        "perfiles": perfiles_list,
        "urls_activas": urls_activas
    }

def get_mi_estado_data(pcbot_id, usuario_id):
    """Dashboard para usuario PCBOT"""
    ahora = time.time()
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    cursor.execute("SELECT tokens_ganados, tokens_comprados, modo FROM usuarios WHERE id = ?", (usuario_id,))
    row = cursor.fetchone()
    conn.close()

    tokens_ganados = row[0] if row else 0
    tokens_comprados = row[1] if row else 0
    modo = row[2] if row else "conectado"

    # Contar perfiles de este PCBOT
    mis_perfiles = [v for k, v in perfiles_map.items() if v.get("pcbot") == pcbot_id]
    activos = sum(1 for p in mis_perfiles if p.get("estado") == "activo")
    inactivos = sum(1 for p in mis_perfiles if p.get("estado") in ("inactivo", None))

    # Perfiles con detalle
    perfiles_list = []
    for v in mis_perfiles:
        perfiles_list.append({
            "nombre": v.get("name", "?"),
            "estado": v.get("estado", "inactivo"),
            "activo": v.get("estado") == "activo",
            "colgado": v.get("estado") == "colgado",
            "url_actual": v.get("url_actual", ""),
            "tiempo_conectado": int(time.time() - v.get("ultimo_inicio", ahora)) if v.get("ultimo_inicio") else 0,
            "tokens_ganados": 0,
            "pcbot": v.get("pcbot", pcbot_id)
        })

    conectado = pcbot_id in pcbots

    return {
        "tokens_acumulados": tokens_ganados + tokens_comprados,
        "tokens_comprados": tokens_comprados,
        "tokens_hoy": pcbot_tokens.get(pcbot_id, {}).get("hoy", 0),
        "modo": modo,
        "total_perfiles": len(mis_perfiles),
        "perfiles_activos": activos,
        "perfiles_inactivos": inactivos,
        "perfiles": perfiles_list,
        "conectado_pcmaster": conectado,
        "pc_name": pcbots_info.get(pcbot_id, {}).get("pc_name", "?"),
        "ip_local": pcbots_info.get(pcbot_id, {}).get("ip_local", "?"),
        "ip_tailscale": pcbots_info.get(pcbot_id, {}).get("ip_tailscale", "?")
    }

# ============================================================================
# TAREAS ASINCRONAS
# ============================================================================

async def tarea_enviar_comentarios():
    """Envía comentarios generados por JARVIS a los perfiles activos"""
    while True:
        await asyncio.sleep(random.uniform(15, 45))

        for url, g in list(grupos.items()):
            if not g.get("comentarios"):
                continue

            nivel = g.get("nivel", "medio")
            comentario = jarvis.generar_comentario(
                contexto_previo="Stream activo",
                url=url,
                nivel=nivel
            )

            if comentario:
                for key in g["perfiles"]:
                    info = perfiles_map.get(key)
                    if info and info.get("estado") == "activo":
                        await enviar_a_pcbot(info["pcbot"], "comentario", {
                            "dirId": info["dirId"],
                            "comentario": comentario
                        })

async def tarea_quema_diaria():
    """Ejecuta quema diaria de tokens"""
    while True:
        await asyncio.sleep(3600)  # Cada hora
        ejecutar_quema_diaria()

# ============================================================================
# HTTP SERVER
# ============================================================================

class DashboardHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Servir portal.html
        if path == "/" or path == "/dashboard":
            dash_path = BASE_DIR / "portal.html"
            if not dash_path.exists():
                dash_path = BASE_DIR / "dashboard.html"
            if dash_path.exists():
                with open(dash_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", len(content))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, "Portal no encontrado")
            return

        # API: Verificar token
        elif path == "/api/verify":
            auth = self._check_auth()
            if auth:
                uid, email, rol = auth
                self._json_resp({"usuario": email, "rol": rol, "valido": True})
            else:
                self._json_resp({"error": "Token inválido"}, 401)
            return

        # API: Dashboard admin
        elif path == "/api/dashboard":
            auth = self._check_auth()
            if not auth:
                self._json_resp({"error": "No autorizado"}, 401)
                return
            _, _, rol = auth
            if rol != "admin":
                self._json_resp({"error": "Solo admin"}, 403)
                return
            data = get_dashboard_data()
            self._json_resp(data)
            return

        # API: Mi estado (usuario PCBOT)
        elif path == "/api/mi_estado":
            auth = self._check_auth()
            if not auth:
                self._json_resp({"error": "No autorizado"}, 401)
                return
            uid, email, rol = auth
            # Buscar pcbot_id asociado
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cursor.execute("SELECT pcbot_id FROM usuarios WHERE id = ?", (uid,))
            row = cursor.fetchone()
            conn.close()
            pcbot_id = row[0] if row else None
            data = get_mi_estado_data(pcbot_id or email, uid)
            self._json_resp(data)
            return

        self.send_error(404, "Not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b"{}"

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._json_resp({"error": "JSON inválido"}, 400)
            return

        # API: Login
        if path == "/api/login":
            email = data.get("email", "").strip()
            password = data.get("password", "")

            if not email or not password:
                self._json_resp({"error": "Email y contraseña requeridos"}, 400)
                return

            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cursor.execute("SELECT id, email, password_hash, rol FROM usuarios WHERE email = ?", (email,))
            row = cursor.fetchone()
            conn.close()

            if row and verify_password(password, row[2]):
                uid, uemail, _, rol = row
                token = generar_token(uid, uemail, rol)

                # Guardar sesión
                conn = sqlite3.connect(str(DB_PATH))
                cursor = conn.cursor()
                exp = (datetime.utcnow() + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute(
                    "INSERT INTO sesiones (usuario_id, token, ip_origen, fecha_expiracion) VALUES (?, ?, ?, ?)",
                    (uid, token, self.client_address[0], exp)
                )
                cursor.execute("UPDATE usuarios SET ultimo_login = datetime('now') WHERE id = ?", (uid,))
                conn.commit()
                conn.close()

                self._json_resp({
                    "token": token,
                    "usuario": uemail,
                    "rol": rol
                })
            else:
                self._json_resp({"error": "Credenciales inválidas"}, 401)
            return

        # API: Registro
        elif path == "/api/register":
            email = data.get("email", "").strip()
            password = data.get("password", "")

            if not email or len(password) < 4:
                self._json_resp({"error": "Email y contraseña (mín 4 caracteres) requeridos"}, 400)
                return

            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM usuarios WHERE email = ?", (email,))
            if cursor.fetchone():
                conn.close()
                self._json_resp({"error": "El email ya está registrado"}, 409)
                return

            pass_hash = hash_password(password)
            cursor.execute(
                "INSERT INTO usuarios (email, password_hash, rol) VALUES (?, ?, 'usuario')",
                (email, pass_hash)
            )
            conn.commit()
            conn.close()
            self._json_resp({"mensaje": "Cuenta creada exitosamente"})
            return

        # API: Comando (admin)
        elif path == "/api/comando":
            auth = self._check_auth()
            if not auth:
                self._json_resp({"error": "No autorizado"}, 401)
                return
            _, _, rol = auth
            if rol != "admin":
                self._json_resp({"error": "Solo admin puede ejecutar comandos"}, 403)
                return

            cmd_str = data.get("comando", "").strip()
            resultado = self._procesar_comando(cmd_str)
            self._json_resp({"resultado": resultado})
            return

        # API: Switch modo (usuario)
        elif path == "/api/switch":
            auth = self._check_auth()
            if not auth:
                self._json_resp({"error": "No autorizado"}, 401)
                return
            uid, email, _ = auth
            modo = data.get("modo", "conectado")

            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cursor.execute("UPDATE usuarios SET modo = ? WHERE id = ?", (modo, uid))
            conn.commit()
            conn.close()

            # Notificar a PCBOT si está conectado
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cursor.execute("SELECT pcbot_id FROM usuarios WHERE id = ?", (uid,))
            row = cursor.fetchone()
            conn.close()
            if row and row[0]:
                asyncio.run_coroutine_threadsafe(
                    enviar_a_pcbot(row[0], "modo_change", {"modo": modo}),
                    loop
                )

            self._json_resp({"modo": modo, "mensaje": f"Modo cambiado a {modo}"})
            return

        # API: Comprar tokens
        elif path == "/api/comprar_tokens":
            auth = self._check_auth()
            if not auth:
                self._json_resp({"error": "No autorizado"}, 401)
                return
            uid, _, _ = auth
            cantidad = data.get("cantidad", 100)

            acreditar_tokens_db(uid, cantidad, "compra_dinero_real")
            self._json_resp({"mensaje": f"Comprados {cantidad} tokens", "tokens_comprados": cantidad})
            return

        self.send_error(404, "Not found")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def _check_auth(self):
        """Verifica token de autenticación"""
        auth_header = self.headers.get("Authorization", "")
        token = None
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        else:
            # También aceptar token como query param
            parsed = urlparse(self.path)
            from urllib.parse import parse_qs
            qs = parse_qs(parsed.query)
            token = qs.get("token", [None])[0]

        if token:
            return verificar_token(token)
        return None

    def _json_resp(self, data, status=200):
        response = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(response))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(response)

    def _procesar_comando(self, cmd_str):
        """Procesa comandos de texto"""
        cmd_parts = cmd_str.strip().split()
        if not cmd_parts:
            return "Comando vacío"

        accion = cmd_parts[0].lower()

        if accion == "estado":
            d = get_dashboard_data()
            return (f"PCBOTs: {d['pcbots_conectados']} | "
                    f"Perfiles: {d['perfiles_totales']} (A:{d['perfiles_activos']} I:{d['perfiles_inactivos']} C:{d['perfiles_colgados']}) | "
                    f"JARVIS: {d['jarvis_comentarios']} comentarios")

        elif accion == "perfiles":
            return f"Total: {len(perfiles_map)} perfiles | {len(grupos)} grupos activos"

        elif accion == "asignar":
            try:
                cant = int(cmd_parts[1])
                url = cmd_parts[3]
                dur = int(cmd_parts[5])
                future = asyncio.run_coroutine_threadsafe(ejecutar_asignar(cant, url, dur), loop)
                return future.result(timeout=10)
            except Exception as e:
                return f"Error: {e}. Uso: asignar N url URL duracion MIN"

        elif accion == "comentarios_activar":
            try:
                url = cmd_parts[2]
                nivel = cmd_parts[4] if len(cmd_parts) > 4 else "medio"
                future = asyncio.run_coroutine_threadsafe(ejecutar_comentarios_activar(url, nivel), loop)
                return future.result(timeout=5)
            except Exception as e:
                return f"Error: {e}. Uso: comentarios_activar url URL nivel bajo/medio/alto"

        elif accion == "comentarios_desactivar":
            try:
                url = cmd_parts[2]
                future = asyncio.run_coroutine_threadsafe(ejecutar_comentarios_desactivar(url), loop)
                return future.result(timeout=5)
            except Exception as e:
                return f"Error: {e}"

        elif accion == "detener":
            try:
                url = cmd_parts[2]
                future = asyncio.run_coroutine_threadsafe(ejecutar_detener(url), loop)
                return future.result(timeout=5)
            except Exception as e:
                return f"Error: {e}"

        elif accion == "reiniciar_pcbot":
            try:
                pcbot_id = cmd_parts[1]
                future = asyncio.run_coroutine_threadsafe(
                    enviar_a_pcbot(pcbot_id, "reconnect", {}),
                    loop
                )
                return f"Reinicio enviado a {pcbot_id}"
            except Exception as e:
                return f"Error: {e}"

        else:
            return (f"Comando desconocido: {accion}. Comandos: estado, perfiles, asignar, "
                    f"comentarios_activar, comentarios_desactivar, detener, reiniciar_pcbot")

    def log_message(self, format, *args):
        pass  # Silenciar logs HTTP

def start_http_server():
    """Inicia el servidor HTTP en un hilo separado"""
    # Configurar SO_REUSEADDR antes de crear el socket
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("0.0.0.0", HTTP_PORT), DashboardHandler)
    logger.info(f"[HTTP] Dashboard: http://{get_local_ip()}:{HTTP_PORT}/")
    logger.info(f"[HTTP] API: http://{get_local_ip()}:{HTTP_PORT}/api/dashboard")
    httpd.serve_forever()

def get_local_ip():
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

# Caché IP
get_dashboard_data._cached_ip = None

# ============================================================================
# CONSOLA ADMIN
# ============================================================================

def admin_console():
    print("\n" + "=" * 60)
    print("  ROXYMASTER v6.2 - PCMASTER SERVER")
    print("=" * 60)
    print("  COMANDOS:")
    print("  estado | perfiles")
    print("  asignar <cant> url <URL> duracion <min>")
    print("  comentarios_activar url <URL> nivel <bajo/medio/alto>")
    print("  comentarios_desactivar url <URL>")
    print("  detener url <URL>")
    print("  salir")
    print("-" * 60)

    while True:
        try:
            cmd = input("\n[ADMIN] > ").strip().split()
            if not cmd:
                continue

            if cmd[0] == "estado":
                total = len(perfiles_map)
                ocupados = sum(len(g.get("perfiles", [])) for g in grupos.values())
                print(f"\n[ESTADO]")
                print(f"  Servidor: {get_local_ip()}:{PUERTO} | HTTP: {get_local_ip()}:{HTTP_PORT}")
                print(f"  PCBOTs: {len(pcbots)} | Perfiles: {total} | Ocupados: {ocupados}")
                print(f"  JARVIS: {jarvis.get_stats()['generados']} comentarios")

            elif cmd[0] == "perfiles":
                print(f"\n[PERFILES] Total: {len(perfiles_map)}")
                ocupados = set()
                for g in grupos.values():
                    ocupados.update(g["perfiles"])
                for key in list(perfiles_map.keys())[:20]:
                    estado = "OCUPADO" if key in ocupados else "LIBRE"
                    print(f"  {key} : {estado}")

            elif cmd[0] == "asignar":
                try:
                    cant = int(cmd[1])
                    url = cmd[3]
                    dur = int(cmd[5])
                    asyncio.run_coroutine_threadsafe(ejecutar_asignar(cant, url, dur), loop)
                except:
                    print("Uso: asignar 2 url https://kick.com/xxx duracion 10")

            elif cmd[0] == "comentarios_activar":
                try:
                    url = cmd[2]
                    nivel = cmd[4] if len(cmd) > 4 else "medio"
                    asyncio.run_coroutine_threadsafe(ejecutar_comentarios_activar(url, nivel), loop)
                except:
                    print("Uso: comentarios_activar url URL nivel medio")

            elif cmd[0] == "comentarios_desactivar":
                try:
                    url = cmd[2]
                    asyncio.run_coroutine_threadsafe(ejecutar_comentarios_desactivar(url), loop)
                except:
                    print("Uso: comentarios_desactivar url URL")

            elif cmd[0] == "detener":
                try:
                    url = cmd[2]
                    asyncio.run_coroutine_threadsafe(ejecutar_detener(url), loop)
                except:
                    print("Uso: detener url URL")

            elif cmd[0] == "salir":
                print("Deteniendo servidor...")
                os._exit(0)

            else:
                print("Comando no reconocido")
        except Exception as e:
            print(f"Error: {e}")

# ============================================================================
# MAIN
# ============================================================================

async def main():
    global loop
    loop = asyncio.get_event_loop()

    # Cachear IP
    get_dashboard_data._cached_ip = get_local_ip()

    # Inicializar DB
    init_db()

    # Ejecutar quema en inicio
    ejecutar_quema_diaria()

    # Tareas asíncronas
    asyncio.create_task(tarea_enviar_comentarios())
    asyncio.create_task(tarea_quema_diaria())

    # Consola admin en hilo separado
    threading.Thread(target=admin_console, daemon=True).start()

    # HTTP server en hilo separado
    threading.Thread(target=start_http_server, daemon=True).start()

    print(f"\n{'='*60}")
    print(f"  ROXYMASTER v6.2 - PCMASTER SERVER")
    print(f"  WS Server: {get_local_ip()}:{PUERTO}")
    print(f"  Dashboard: http://{get_local_ip()}:{HTTP_PORT}/")
    print(f"  Admin: PCMASTER / Abc123$_")
    print(f"{'='*60}\n")

    async with websockets.serve(manejar_conexion, IP, PUERTO,
                                  ping_interval=30,
                                  ping_timeout=10,
                                  close_timeout=5):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())