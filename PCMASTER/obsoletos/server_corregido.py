import sys
import os
import json
import asyncio
import websockets
import threading
import time
import random
import hashlib
import secrets
import io
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime
from collections import deque
from urllib.parse import urlparse, parse_qs
import requests

BASE_DIR = os.path.join(os.environ["USERPROFILE"], "Desktop", "ROXYMASTER", "PCMASTER")
sys.path.insert(0, os.path.join(BASE_DIR, "scripts"))

from variables_globales import *

# Importar motor KBT
try:
    from tokenomics import Tokenomics
    KBT_AVAILABLE = True
except ImportError:
    KBT_AVAILABLE = False
    print("[!] Tokenomics no disponible")

# Capa de seguridad SHS (Secret Handshake Protocol)
try:
    from shs import SecretManager
    SHS_AVAILABLE = True
except ImportError:
    SHS_AVAILABLE = False
    print("[!] SHS no disponible - mensajes sin firma")

with open(os.path.join(BASE_DIR, "config.json"), "r", encoding="utf-8-sig") as f:
    config = json.load(f)

PUERTO = config["server"]["ws_port"]
IP = config["server"]["ip_servidor"]
HTTP_PORT = 8086

pcbots = {}
perfiles_map = {}
grupos = {}
pool_comentarios = {}  # url -> lista de comentarios
loop = None
start_time = time.time()
pcbots_info = {}  # Guarda datos de cada PCBOT para el dashboard
kbt = None  # Motor KBT, se inicializa en main()

# Marketplace P2P de tokens KBT
# { oferta_id: { vendedor, tokens, precio_soles, precio_token, fecha, estado (activa/vendida/cancelada), comprador } }
ofertas_p2p = {}
_p2p_id_counter = 1

# Inicializar SecretManager SHS
if SHS_AVAILABLE:
    secret_manager = SecretManager()
    print(f"[SHS] SecretManager inicializado - {len(secret_manager._cache)} clientes conocidos")
else:
    secret_manager = None

# ============================================================================
# AUTENTICACION - Sesiones simples (sin validación de email)
# ============================================================================

SESIONES = {}  # token -> {"email": str, "rol": str, "creado": float, "pcbot_id": str}
USUARIOS = {}  # email -> {"password_hash": str, "rol": str, "pcbot_id": str}

# Admin por defecto
ADMIN_EMAIL = "PCMASTER"
ADMIN_PASS_HASH = hashlib.sha256("Abc123$_".encode()).hexdigest()
if ADMIN_EMAIL not in USUARIOS:
    USUARIOS[ADMIN_EMAIL] = {
        "password_hash": ADMIN_PASS_HASH,
        "rol": "admin",
        "pcbot_id": "PCMASTER"
    }

def generar_token():
    return secrets.token_hex(32)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def autenticar_token(token):
    """Verifica si un token de sesión es válido"""
    if token in SESIONES:
        sesion = SESIONES[token]
        # Token expira después de 24 horas
        if time.time() - sesion["creado"] < 86400:
            return sesion
        else:
            del SESIONES[token]
    return None

def obtener_info_sesion(token):
    """Retorna info de la sesión o datos del PCBOT asociado"""
    sesion = autenticar_token(token)
    if not sesion:
        return None

    info = {
        "email": sesion["email"],
        "rol": sesion["rol"],
        "pcbot_id": sesion.get("pcbot_id", ""),
        "creado": sesion["creado"]
    }

    # Si es un PCBOT, agregar info de KBT y perfiles
    if kbt and sesion.get("pcbot_id"):
        granjero = kbt.obtener_granjero(sesion["pcbot_id"])
        if granjero:
            info["kbt"] = {
                "saldo_tokens": round(granjero[3], 4) if granjero[3] else 0,
                "saldo_soles": round(granjero[4], 2) if granjero[4] else 0,
                "nivel_fiabilidad": granjero[5] if len(granjero) > 5 else "Bronce",
                "uptime_horas": round(granjero[6], 2) if len(granjero) > 6 else 0,
                "fecha_registro": granjero[7] if len(granjero) > 7 else datetime.now().isoformat()
            }

    return info

# ============================================================================
# JARVIS
# ============================================================================

class Jarvis:
    def __init__(self, prompts_dir):
        self.prompts_dir = prompts_dir
        self.prompt_maestro = self._cargar_prompt()
        self.memoria_por_url = {}
        self.stats = {"generados": 0}
        self.ultimos_comentarios = deque(maxlen=20)
        self.pool_por_url = {}
        print(f"[JARVIS] Activado")

    def _cargar_prompt(self):
        path = os.path.join(self.prompts_dir, "maestro.txt")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8-sig") as f:
                return f.read()
        return "Eres un comentarista de streams."

    def _get_memoria(self, url):
        if url not in self.memoria_por_url:
            self.memoria_por_url[url] = deque(maxlen=50)
        return self.memoria_por_url[url]

    def _get_pool(self, url):
        if url not in self.pool_por_url:
            self.pool_por_url[url] = deque(maxlen=500)
        return self.pool_por_url[url]

    def aprender(self, texto, url):
        if texto and len(texto) > 5:
            memoria = self._get_memoria(url)
            memoria.append({"texto": texto, "ts": time.time()})

    def generar(self, url):
        pool = self._get_pool(url)

        # Limpiar comentarios antiguos (>45 segundos)
        ahora = time.time()
        while pool and ahora - pool[0]["ts"] > 45:
            pool.popleft()

        # Si hay suficientes comentarios en el pool, usar uno
        if len(pool) > 0:
            candidato = pool[-1]["texto"]
            if candidato not in self.ultimos_comentarios:
                self.ultimos_comentarios.append(candidato)
                self.stats["generados"] += 1
                return candidato[:60]

        memoria = self._get_memoria(url)
        contexto = ""
        contextos = [m["texto"] for m in memoria if ahora - m["ts"] <= 30]
        if contextos:
            contexto = "\n".join(list(contextos)[-10:])

        prompt = f"""{self.prompt_maestro}

CONTEXTO:
{contexto[:500] if contexto else "Stream en vivo"}

Genera UN comentario corto (max 60 caracteres). Se natural. Diferente a comentarios anteriores."""

        try:
            r = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3.2",
                    "prompt": prompt,
                    "stream": False,
                    "max_tokens": 80,
                    "temperature": 0.9
                },
                timeout=15
            )
            if r.status_code == 200:
                txt = r.json().get("response", "").strip()
                if txt and txt not in self.ultimos_comentarios:
                    self.ultimos_comentarios.append(txt)
                    self.stats["generados"] += 1
                    return txt[:60]
        except Exception as e:
            print(f"[JARVIS] Error: {e}")

        fallback = random.choice(["no se ve 🔥", "vamooo 🔥", "oyeee 🔥", "buena esa", "dale con todo", "jajaja"])
        return fallback

    def get_stats(self):
        return self.stats

jarvis = Jarvis(os.path.join(BASE_DIR, "prompts"))

# ============================================================================
# FUNCIONES BASE
# ============================================================================

async def enviar(pcbot_id, cmd, data):
    """Envia comando a PCBOT con firma SHS"""
    if pcbot_id in pcbots:
        try:
            msg = {"type": cmd, "data": data}
            # Firmar con SHS si esta disponible y el cliente es conocido
            if SHS_AVAILABLE and secret_manager and pcbot_id in secret_manager._cache:
                msg = secret_manager.sign_for(pcbot_id, msg)
            await pcbots[pcbot_id].send(json.dumps(msg))
            return True
        except:
            pass
    return False

async def manejar_conexion(ws):
    cid = None
    try:
        msg = await asyncio.wait_for(ws.recv(), timeout=30)
        data = json.loads(msg)
        if data.get("type") == "identify":
            cid = data.get("client_id")
            perfiles = data.get("profiles", [])
            pcbots[cid] = ws

            # Guardar info para dashboard
            pcbots_info[cid] = {
                "id": cid,
                "ip_local": data.get("ip_local", "?"),
                "ip_tailscale": data.get("ip_tailscale", "?"),
                "perfiles": len(perfiles),
                "uptime": "0s",
                "start_time": time.time(),
                "perfiles_raw": perfiles
            }

            for p in perfiles:
                key = f"{cid}|{p['name']}"
                perfiles_map[key] = {
                    "pcbot": cid,
                    "name": p["name"],
                    "dirId": p.get("dirId", ""),
                    "estado": "inactivo",
                    "url_actual": "",
                    "ultimo_uso": 0
                }

            # Registrar granjero en KBT si existe
            if kbt:
                kbt.registrar_granjero(cid, cid)

            print(f"[+] PCBOT {cid} conectado con {len(perfiles)} perfiles "
                  f"(local={data.get('ip_local')} ts={data.get('ip_tailscale')})")

            # Confirmar handshake
            respuesta = {"type": "welcome", "data": {"server": "PCMASTER v6.2", "time": time.time()}}
            if SHS_AVAILABLE and secret_manager and cid in secret_manager._cache:
                respuesta = secret_manager.sign_for(cid, respuesta)
            await ws.send(json.dumps(respuesta))

            # Recibir heartbeats y reportes
            async for raw in ws:
                try:
                    msg_data = json.loads(raw)
                    tipo = msg_data.get("type", "")

                    if tipo == "heartbeat":
                        # Actualizar estados de perfiles
                        estados = msg_data.get("estados", {})
                        if cid in pcbots_info:
                            pcbots_info[cid]["uptime"] = f"{int(time.time() - pcbots_info[cid]['start_time'])}s"
                            pcbots_info[cid]["perfiles_activos"] = estados.get("activos", 0)
                            pcbots_info[cid]["perfiles_inactivos"] = estados.get("inactivos", 0)
                            pcbots_info[cid]["perfiles_colgados"] = estados.get("colgados", 0)

                        # Actualizar perfil individual
                        for key, pinfo in perfiles_map.items():
                            if pinfo["pcbot"] == cid:
                                # Buscar en estados
                                perfil_estado = estados.get("detalle", {}).get(pinfo["name"])
                                if perfil_estado:
                                    pinfo["estado"] = perfil_estado.get("estado", pinfo["estado"])
                                    pinfo["url_actual"] = perfil_estado.get("url", pinfo["url_actual"])
                                    pinfo["ultimo_uso"] = perfil_estado.get("ultimo_uso", pinfo["ultimo_uso"])

                        # Enviar ACK
                        await ws.send(json.dumps({"type": "heartbeat_ack", "data": {"time": time.time()}}))

                    elif tipo == "reporte_perfil":
                        perfil = msg_data.get("perfil", {})
                        nombre = perfil.get("name", "")
                        key = f"{cid}|{nombre}"
                        if key in perfiles_map:
                            perfiles_map[key]["estado"] = perfil.get("estado", perfiles_map[key]["estado"])
                            perfiles_map[key]["url_actual"] = perfil.get("url", perfiles_map[key]["url_actual"])

                    elif tipo == "log_comentario":
                        texto = msg_data.get("texto", "")
                        url = msg_data.get("url", "")
                        if texto:
                            jarvis.aprender(texto, url)
                            pool = jarvis._get_pool(url)
                            pool.append({"texto": texto, "ts": time.time()})

                except json.JSONDecodeError:
                    pass

        else:
            print(f"[!] Mensaje inesperado: {data.get('type')}")
            await ws.close()

    except asyncio.TimeoutError:
        print(f"[!] Timeout esperando identify")
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        print(f"[!] Error en conexion: {type(e).__name__} - {e}")
    finally:
        if cid:
            pcbots.pop(cid, None)
            pcbots_info.pop(cid, None)
            # Marcar perfiles como inactivos
            for key in list(perfiles_map.keys()):
                if key.startswith(f"{cid}|"):
                    perfiles_map[key]["estado"] = "inactivo"
            print(f"[-] PCBOT {cid} desconectado")

# ============================================================================
# FUNCIONES DE ORQUESTACION
# ============================================================================

async def ejecutar_asignar(cant, url, dur):
    """Asigna N perfiles libres a una URL por una duracion"""
    libres = [(k, v) for k, v in perfiles_map.items() if v["estado"] == "inactivo"]
    if len(libres) < cant:
        return f"Solo hay {len(libres)} perfiles libres (se necesitan {cant})"

    import random as _random
    seleccionados = _random.sample(libres, cant)

    # Agrupar perfiles por PCBOT
    por_pcbot = {}
    for key, info in seleccionados:
        pcbot = info["pcbot"]
        if pcbot not in por_pcbot:
            por_pcbot[pcbot] = []
        por_pcbot[pcbot].append(info["name"])

    grupo_id = f"g_{int(time.time())}"
    grupos[grupo_id] = {
        "url": url,
        "duracion": dur,
        "perfiles": [],
        "pcbots": list(por_pcbot.keys()),
        "inicio": time.time(),
        "comentarios_activos": False
    }

    for pcbot_id, nombres in por_pcbot.items():
        ok = await enviar(pcbot_id, "asignar_url", {
            "url": url,
            "duracion": dur,
            "perfiles": nombres,
            "grupo_id": grupo_id
        })

        if ok:
            for nombre in nombres:
                key = f"{pcbot_id}|{nombre}"
                grupos[grupo_id]["perfiles"].append(key)
                if key in perfiles_map:
                    perfiles_map[key]["estado"] = "activo"
                    perfiles_map[key]["url_actual"] = url
                    perfiles_map[key]["ultimo_uso"] = time.time()

    return f"Asignados {len(seleccionados)} perfiles a {url} por {dur} min (grupo {grupo_id})"

async def ejecutar_comentarios_activar(url, nivel="medio"):
    """Activa Jarvis para una URL"""
    # Frecuencias de comentarios según nivel
    frecuencias = {"bajo": 120, "medio": 60, "alto": 30}
    intervalo = frecuencias.get(nivel, 60)

    # Encontrar el grupo asociado a esta URL
    grupo_encontrado = None
    for gid, ginfo in grupos.items():
        if ginfo["url"] == url:
            grupo_encontrado = gid
            ginfo["comentarios_activos"] = True
            ginfo["comentarios_intervalo"] = intervalo
            ginfo["comentarios_nivel"] = nivel
            break

    if grupo_encontrado:
        # Notificar a los PCBOTs del grupo
        for pcbot_id in grupos[grupo_encontrado]["pcbots"]:
            await enviar(pcbot_id, "comentarios_activar", {
                "url": url,
                "nivel": nivel,
                "intervalo": intervalo,
                "grupo_id": grupo_encontrado
            })
        return f"Comentarios activados para {url} (nivel={nivel}, cada {intervalo}s)"
    return f"No se encontro grupo activo para {url}"

async def ejecutar_comentarios_desactivar(url):
    """Desactiva Jarvis para una URL"""
    for gid, ginfo in grupos.items():
        if ginfo["url"] == url:
            ginfo["comentarios_activos"] = False
            for pcbot_id in ginfo["pcbots"]:
                await enviar(pcbot_id, "comentarios_desactivar", {"url": url, "grupo_id": gid})
            return f"Comentarios desactivados para {url}"
    return f"No se encontro grupo activo para {url}"

async def ejecutar_detener(url):
    """Detiene todos los perfiles en una URL"""
    grupos_a_eliminar = []
    for gid, ginfo in list(grupos.items()):
        if ginfo["url"] == url:
            for key in ginfo["perfiles"]:
                if key in perfiles_map:
                    perfiles_map[key]["estado"] = "inactivo"
                    perfiles_map[key]["url_actual"] = ""
            for pcbot_id in ginfo["pcbots"]:
                await enviar(pcbot_id, "detener_url", {"url": url, "grupo_id": gid})
            grupos_a_eliminar.append(gid)

    for gid in grupos_a_eliminar:
        grupos.pop(gid, None)

    if grupos_a_eliminar:
        return f"Detenidos {len(grupos_a_eliminar)} grupos en {url}"
    return f"No se encontro grupo activo para {url}"

async def tarea_enviar_comentarios():
    """Envia comentarios generados por Jarvis a los PCBOTs periodicamente"""
    while True:
        await asyncio.sleep(5)
        for gid, ginfo in list(grupos.items()):
            if ginfo.get("comentarios_activos") and ginfo.get("url"):
                # Verificar si es momento de enviar comentario
                ultimo = ginfo.get("ultimo_comentario", 0)
                intervalo = ginfo.get("comentarios_intervalo", 60)
                if time.time() - ultimo >= intervalo:
                    comentario = jarvis.generar(ginfo["url"])
                    if comentario:
                        ginfo["ultimo_comentario"] = time.time()
                        for pcbot_id in ginfo["pcbots"]:
                            await enviar(pcbot_id, "enviar_comentario", {
                                "url": ginfo["url"],
                                "comentario": comentario,
                                "grupo_id": gid
                            })

# ============================================================================
# DASHBOARD DATA
# ============================================================================

def get_dashboard_data():
    """Retorna datos completos del dashboard"""
    ahora = time.time()

    # Contar perfiles por estado
    activos = sum(1 for v in perfiles_map.values() if v["estado"] == "activo")
    inactivos = sum(1 for v in perfiles_map.values() if v["estado"] == "inactivo")
    colgados = sum(1 for v in perfiles_map.values() if v["estado"] == "colgado")

    # Lista de perfiles detallada
    perfiles_lista = []
    for key, info in perfiles_map.items():
        perfiles_lista.append({
            "id": key,
            "nombre": info["name"],
            "pcbot": info["pcbot"],
            "estado": info["estado"],
            "url_actual": info.get("url_actual", ""),
            "tiempo_sin_uso": f"{int(ahora - info.get('ultimo_uso', 0))}s" if info.get("ultimo_uso") else "N/A"
        })

    # URLs activas
    urls_activas = []
    for gid, ginfo in grupos.items():
        urls_activas.append({
            "grupo_id": gid,
            "url": ginfo["url"],
            "perfiles": len(ginfo.get("perfiles", [])),
            "duracion": ginfo.get("duracion", 0),
            "inicio": datetime.fromtimestamp(ginfo.get("inicio", ahora)).strftime("%H:%M:%S"),
            "comentarios_activos": ginfo.get("comentarios_activos", False)
        })

    # Sesiones activas (perfiles en uso)
    sesiones = []
    for key, info in perfiles_map.items():
        if info["estado"] == "activo" and info.get("url_actual"):
            sesiones.append({
                "id": info["name"],
                "pcbot": info["pcbot"],
                "url": info["url_actual"],
                "inicio": datetime.fromtimestamp(info.get("ultimo_uso", ahora)).strftime("%H:%M:%S") if info.get("ultimo_uso") else "N/A"
            })

    return {
        "pcbots_conectados": len(pcbots),
        "perfiles_totales": len(perfiles_map),
        "perfiles_activos": activos,
        "perfiles_inactivos": inactivos,
        "perfiles_colgados": colgados,
        "grupos_activos": len(grupos),
        "jarvis_comentarios": jarvis.get_stats()["generados"],
        "uptime_servidor": f"{int(ahora - start_time)}s",
        "pcbots": [{
            "id": pid,
            "ip_local": info.get("ip_local", "?"),
            "ip_tailscale": info.get("ip_tailscale", "?"),
            "perfiles": info.get("perfiles", 0),
            "uptime": info.get("uptime", "0s"),
            "activos": info.get("perfiles_activos", 0),
            "inactivos": info.get("perfiles_inactivos", 0),
            "colgados": info.get("perfiles_colgados", 0)
        } for pid, info in pcbots_info.items()],
        "perfiles_lista": perfiles_lista,
        "urls_activas": urls_activas,
        "sesiones": sesiones
    }

# ============================================================================
# SERVIDOR HTTP (Dashboard + API + Portal)
# ============================================================================

class DashboardHandler(BaseHTTPRequestHandler):
    """Maneja todas las rutas HTTP del servidor"""

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # === SERVIR ARCHIVOS ESTATICOS ===
        if path == "/" or path == "/dashboard" or path == "/admin":
            self._servir_html("admin_portal.html")
            return
        elif path == "/portal" or path == "/portal.html":
            self._servir_html("portal.html")
            return
        elif path == "/dashboard.html":
            self._servir_html("dashboard.html")
            return
        elif path == "/admin_portal.html":
            self._servir_html("admin_portal.html")
            return

        # === API DASHBOARD ===
        elif path == "/api/dashboard":
            d = get_dashboard_data()
            response = json.dumps(d).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response)
            return

        # === API VERIFY TOKEN ===
        elif path == "/api/verify":
            token = self.headers.get("Authorization", "").replace("Bearer ", "")
            if not token:
                token = params.get("token", [""])[0]
            sesion = autenticar_token(token)
            if sesion:
                info = obtener_info_sesion(token)
                response = json.dumps({"valid": True, "usuario": sesion["email"], "rol": sesion["rol"], "info": info}).encode("utf-8")
            else:
                response = json.dumps({"valid": False, "error": "Token invalido"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response)
            return

        # === API MI ESTADO (PCBOT) ===
        elif path == "/api/mi_estado":
            token = self.headers.get("Authorization", "").replace("Bearer ", "")
            if not token:
                token = params.get("token", [""])[0]
            sesion = autenticar_token(token)
            if not sesion:
                response = json.dumps({"error": "No autenticado"}).encode("utf-8")
            else:
                info = obtener_info_sesion(token) or {}
                # Agregar estado de perfiles del PCBOT
                pcbot_id = sesion.get("pcbot_id", sesion["email"])
                mis_perfiles = []
                for key, pinfo in perfiles_map.items():
                    if pinfo["pcbot"] == pcbot_id or pinfo["pcbot"] == sesion["email"]:
                        mis_perfiles.append({
                            "nombre": pinfo["name"],
                            "estado": pinfo["estado"],
                            "url_actual": pinfo.get("url_actual", ""),
                            "tiempo_sin_uso": f"{int(time.time() - pinfo.get('ultimo_uso', 0))}s" if pinfo.get("ultimo_uso") else "N/A"
                        })
                info["perfiles"] = mis_perfiles
                info["pcbot_id"] = pcbot_id
                response = json.dumps(info).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response)
            return

        # === API KBT ===
        elif path == "/api/kbt/stats":
            if kbt:
                stats = kbt.get_stats()
                response = json.dumps(stats).encode("utf-8")
            else:
                response = json.dumps({"error": "KBT no disponible"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response)
            return

        elif path == "/api/kbt/granjeros":
            if kbt:
                rows = kbt.obtener_todos_granjeros()
                granjeros = [{
                    "id": r[0],
                    "nombre": r[1],
                    "referido_por": r[2],
                    "saldo_tokens": round(r[3], 4) if r[3] else 0,
                    "saldo_soles": round(r[4], 2) if r[4] else 0,
                    "nivel_fiabilidad": r[5] if len(r) > 5 else "Bronce",
                    "uptime_horas": round(r[6], 2) if len(r) > 6 else 0,
                    "fecha_registro": r[7] if len(r) > 7 else ""
                } for r in rows]
                response = json.dumps(granjeros).encode("utf-8")
            else:
                response = json.dumps({"error": "KBT no disponible"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response)
            return

        elif path == "/api/kbt/parametros":
            if kbt:
                params_kbt = kbt.load_parameters()
                response = json.dumps(params_kbt).encode("utf-8")
            else:
                response = json.dumps({"error": "KBT no disponible"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response)
            return

        elif path == "/api/kbt/saldo":
            granjero_id = params.get("granjero_id", [""])[0]
            if kbt and granjero_id:
                granjero = kbt.obtener_granjero(granjero_id)
                if granjero:
                    info = {
                        "id": granjero[0],
                        "nombre": granjero[1],
                        "saldo_tokens": round(granjero[3], 4) if granjero[3] else 0,
                        "saldo_soles": round(granjero[4], 2) if granjero[4] else 0,
                        "nivel_fiabilidad": granjero[5] if len(granjero) > 5 else "Bronce",
                        "fecha_registro": granjero[7] if len(granjero) > 7 else ""
                    }
                    response = json.dumps(info).encode("utf-8")
                else:
                    response = json.dumps({"error": "Granjero no encontrado"}).encode("utf-8")
            else:
                response = json.dumps({"error": "Falta granjero_id o KBT no disponible"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response)
            return

        elif path == "/api/comando":
            cmd_str = params.get("cmd", [""])[0]
            if not cmd_str:
                response = json.dumps({"resultado": "Comando vacio"}).encode("utf-8")
            else:
                resultado = self._procesar_comando_api(cmd_str)
                response = json.dumps({"resultado": resultado}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response)
            return

        # === MARKETPLACE P2P GET ===
        elif path == "/api/kbt/ofertas":
            activas = [o for o in ofertas_p2p.values() if o.get("estado") == "activa"]
            response = json.dumps(activas).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response)
            return

        elif path == "/api/kbt/historial_ofertas":
            granjero_id = params.get("granjero_id", [""])[0]
            historial = [o for o in ofertas_p2p.values() if o.get("vendedor") == granjero_id or o.get("comprador") == granjero_id]
            response = json.dumps(historial).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response)
            return

        elif path == "/api/kbt/saldo_detallado":
            granjero_id = params.get("granjero_id", [""])[0]
            if kbt and granjero_id:
                saldo = kbt.obtener_saldo_detallado(granjero_id)
                if saldo:
                    response = json.dumps({
                        "granjero_id": granjero_id,
                        "saldo_quemable": saldo["quemable"],
                        "saldo_comprado": saldo["comprado"],
                        "saldo_total": saldo["total"],
                        "soles_acumulados": saldo["soles"],
                        "tasa_quema_mensual": kbt.params.get("tasa_quema_mensual", 5.0)
                    }).encode("utf-8")
                else:
                    response = json.dumps({"error": "Granjero no encontrado"}).encode("utf-8")
            else:
                response = json.dumps({"error": "Falta granjero_id"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response)
            return

        elif path == "/api/recordatorios":
            granjero_id = params.get("granjero_id", [""])[0]
            # Obtener sesiones activas desde KBT (más preciso que el mapa en memoria)
            recordatorios = []
            if kbt:
                sesiones = kbt.obtener_sesiones_activas(granjero_id)
                for s in sesiones:
                    faltante = max(0, 62 - s["minutos"])
                    recordatorios.append({
                        "sesion_id": s["id"],
                        "perfil": s.get("perfil_nombre", f"Perfil_{s['perfil_id']}"),
                        "minutos_acumulados": s["minutos"],
                        "faltante_62min": faltante,
                        "estado": "contando" if faltante > 0 else "validado",
                        "recompensa_pendiente": s["recompensa"] if s["validada"] else 0
                    })
            response = json.dumps(recordatorios).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response)
            return

        elif path == "/api/kbt/sesiones":
            granjero_id = params.get("granjero_id", [""])[0]
            if kbt and granjero_id:
                sesiones = kbt.obtener_sesiones_activas(granjero_id)
                # Enriquecer con info de perfiles del mapa
                resultado = []
                for s in sesiones:
                    entry = {
                        "sesion_id": s["id"],
                        "perfil_id": s["perfil_id"],
                        "minutos_acumulados": s["minutos"],
                        "faltante_62min": max(0, 62 - s["minutos"]),
                        "validada": s["validada"],
                        "recompensa_kbt": s["recompensa"],
                        "perfil_nombre": s.get("perfil_nombre", f"Perfil_{s['perfil_id']}")
                    }
                    resultado.append(entry)
                response = json.dumps({"sesiones": resultado, "total": len(resultado)}).encode("utf-8")
            else:
                response = json.dumps({"error": "Falta granjero_id o KBT no disponible"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response)
            return

        elif path == "/api/kbt/reporte_minutos":
            # Reporte de contador 62min para todos los granjeros (vista admin)
            if kbt:
                sesiones = kbt.obtener_sesiones_activas()
                reporte = {}
                for s in sesiones:
                    gid = s["granjero_id"]
                    if gid not in reporte:
                        reporte[gid] = {"perfiles_contando": 0, "perfiles_validados": 0, "detalles": []}
                    if s["validada"]:
                        reporte[gid]["perfiles_validados"] += 1
                    else:
                        reporte[gid]["perfiles_contando"] += 1
                    reporte[gid]["detalles"].append({
                        "perfil_id": s["perfil_id"],
                        "nombre": s.get("perfil_nombre", "?"),
                        "minutos": s["minutos"],
                        "faltante": max(0, 62 - s["minutos"]),
                        "validada": s["validada"]
                    })
                response = json.dumps(reporte).encode("utf-8")
            else:
                response = json.dumps({"error": "KBT no disponible"}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response)
            return

        self.send_error(404, "Not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Leer body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b"{}"
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = {}

        # === AUTENTICACION ===
        if path == "/api/login":
            email = data.get("email", "").strip()
            password = data.get("password", "")
            pass_hash = hash_password(password)

            if email in USUARIOS and USUARIOS[email]["password_hash"] == pass_hash:
                token = generar_token()
                SESIONES[token] = {
                    "email": email,
                    "rol": USUARIOS[email]["rol"],
                    "pcbot_id": USUARIOS[email].get("pcbot_id", email),
                    "creado": time.time()
                }
                response = json.dumps({
                    "token": token,
                    "usuario": email,
                    "rol": USUARIOS[email]["rol"],
                    "pcbot_id": USUARIOS[email].get("pcbot_id", email)
                }).encode("utf-8")
            else:
                response = json.dumps({"error": "Credenciales invalidas"}).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response)
            return

        elif path == "/api/register":
            email = data.get("email", "").strip()
            password = data.get("password", "")

            if not email or not password:
                response = json.dumps({"error": "Email y password requeridos"}).encode("utf-8")
            elif email in USUARIOS:
                response = json.dumps({"error": "El usuario ya existe"}).encode("utf-8")
            else:
                USUARIOS[email] = {
                    "password_hash": hash_password(password),
                    "rol": "usuario",
                    "pcbot_id": email
                }
                # Registrar en KBT
                if kbt:
                    kbt.registrar_granjero(email, email)

                # Generar token automáticamente
                token = generar_token()
                SESIONES[token] = {
                    "email": email,
                    "rol": "usuario",
                    "pcbot_id": email,
                    "creado": time.time()
                }
                response = json.dumps({
                    "ok": True,
                    "token": token,
                    "usuario": email,
                    "rol": "usuario",
                    "pcbot_id": email
                }).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response)
            return

        # === API COMANDO ===
        elif path == "/api/comando":
            cmd_str = data.get("comando", "")
            resultado = self._procesar_comando_api(cmd_str)
            response = json.dumps({"resultado": resultado}).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response)
            return

        # === RUTAS KBT POST ===
        elif path == "/api/kbt/registrar":
            granjero_id = data.get("granjero_id", "")
            nombre = data.get("nombre", granjero_id)
            referido = data.get("referido_por", None)
            if kbt and granjero_id:
                ok = kbt.registrar_granjero(granjero_id, nombre, referido)
                response = json.dumps({"ok": ok, "granjero_id": granjero_id}).encode("utf-8")
            else:
                response = json.dumps({"error": "Falta granjero_id"}).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response)
            return

        elif path == "/api/kbt/transferir":
            vendedor = data.get("vendedor", "")
            comprador = data.get("comprador", "")
            tokens = float(data.get("tokens", 0))
            if kbt and vendedor and comprador and tokens > 0:
                kbt.realizar_transferencia_p2p(vendedor, comprador, tokens)
                response = json.dumps({"ok": True, "tokens": tokens}).encode("utf-8")
            else:
                response = json.dumps({"error": "Faltan datos"}).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response)
            return

        # === MARKETPLACE P2P POST ===
        elif path == "/api/kbt/crear_oferta":
            global _p2p_id_counter
            vendedor = data.get("vendedor", "")
            tokens = float(data.get("tokens", 0))
            precio_soles = float(data.get("precio_soles", 0))
            if vendedor and tokens > 0 and precio_soles > 0:
                # Verificar saldo
                if kbt:
                    g = kbt.obtener_granjero(vendedor)
                    saldo = g[3] if g else 0
                    if saldo < tokens:
                        response = json.dumps({"error": f"Saldo insuficiente. Tienes {round(saldo,2)} KBT"}).encode("utf-8")
                    else:
                        oferta_id = _p2p_id_counter
                        _p2p_id_counter += 1
                        ofertas_p2p[oferta_id] = {
                            "id": oferta_id,
                            "vendedor": vendedor,
                            "tokens": tokens,
                            "precio_soles": precio_soles,
                            "precio_token": round(precio_soles / tokens, 4),
                            "fecha": datetime.now().isoformat(),
                            "estado": "activa",
                            "comprador": None
                        }
                        response = json.dumps({"ok": True, "oferta": ofertas_p2p[oferta_id]}).encode("utf-8")
                else:
                    response = json.dumps({"error": "KBT no disponible"}).encode("utf-8")
            else:
                response = json.dumps({"error": "Datos incompletos"}).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response)
            return

        elif path == "/api/kbt/comprar_oferta":
            oferta_id = int(data.get("oferta_id", 0))
            comprador = data.get("comprador", "")
            if oferta_id in ofertas_p2p and comprador:
                oferta = ofertas_p2p[oferta_id]
                if oferta["estado"] != "activa":
                    response = json.dumps({"error": "Oferta no disponible"}).encode("utf-8")
                elif oferta["vendedor"] == comprador:
                    response = json.dumps({"error": "No puedes comprar tu propia oferta"}).encode("utf-8")
                else:
                    # Comision 5% para el sistema
                    comision = round(oferta["tokens"] * 0.05, 4)
                    tokens_comprador = round(oferta["tokens"] - comision, 4)
                    tokens_vendedor_recibe = round(oferta["tokens"] - comision, 4)

                    if kbt:
                        # Transferir tokens (vendedor -> comprador)
                        kbt.realizar_transferencia_p2p(oferta["vendedor"], comprador, tokens_comprador)
                        # La comision va a la reserva del sistema
                        if hasattr(kbt, 'reserva'):
                            kbt.reserva["tokens"] = kbt.reserva.get("tokens", 0) + comision

                    oferta["estado"] = "vendida"
                    oferta["comprador"] = comprador

                    response = json.dumps({
                        "ok": True,
                        "tokens_transferidos": tokens_comprador,
                        "comision_sistema": comision,
                        "vendedor": oferta["vendedor"],
                        "comprador": comprador
                    }).encode("utf-8")
            else:
                response = json.dumps({"error": "Oferta no encontrada o falta comprador"}).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response)
            return

        elif path == "/api/kbt/cancelar_oferta":
            oferta_id = int(data.get("oferta_id", 0))
            vendedor = data.get("vendedor", "")
            if oferta_id in ofertas_p2p:
                oferta = ofertas_p2p[oferta_id]
                if oferta["vendedor"] != vendedor:
                    response = json.dumps({"error": "Solo el vendedor puede cancelar"}).encode("utf-8")
                elif oferta["estado"] != "activa":
                    response = json.dumps({"error": "Oferta ya no esta activa"}).encode("utf-8")
                else:
                    oferta["estado"] = "cancelada"
                    response = json.dumps({"ok": True, "mensaje": "Oferta cancelada"}).encode("utf-8")
            else:
                response = json.dumps({"error": "Oferta no encontrada"}).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response)
            return

        self.send_error(404, "Not found")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def _servir_html(self, filename):
        """Sirve un archivo HTML desde el directorio PCMASTER"""
        filepath = os.path.join(BASE_DIR, filename)
        if not os.path.exists(filepath):
            # Intentar desde el directorio PCBOT (si PCMASTER comparte portal.html)
            alt_path = os.path.join(os.environ["USERPROFILE"], "Desktop", "ROXYMASTER", "PCBOT", filename)
            if os.path.exists(alt_path):
                filepath = alt_path

        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                contenido = f.read()
            response = contenido.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(response))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response)
        else:
            self.send_error(404, f"Archivo {filename} no encontrado")

    def _procesar_comando_api(self, cmd_str):
        """Procesa comandos desde la API HTTP"""
        cmd_parts = cmd_str.strip().split()
        if not cmd_parts:
            return "Comando vacio"

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
                return future.result(timeout=5)
            except Exception as e:
                return f"Error: {e}. Uso: asignar <N> url <URL> duracion <MIN>"

        elif accion == "comentarios_activar":
            try:
                url = cmd_parts[2]
                nivel = cmd_parts[4] if len(cmd_parts) > 4 else "medio"
                future = asyncio.run_coroutine_threadsafe(ejecutar_comentarios_activar(url, nivel), loop)
                return future.result(timeout=5)
            except Exception as e:
                return f"Error: {e}. Uso: comentarios_activar url <URL> nivel <bajo/medio/alto>"

        elif accion == "comentarios_desactivar":
            try:
                url = cmd_parts[2]
                future = asyncio.run_coroutine_threadsafe(ejecutar_comentarios_desactivar(url), loop)
                return future.result(timeout=5)
            except Exception as e:
                return f"Error: {e}. Uso: comentarios_desactivar url <URL>"

        elif accion == "detener":
            try:
                url = cmd_parts[2]
                future = asyncio.run_coroutine_threadsafe(ejecutar_detener(url), loop)
                return future.result(timeout=5)
            except Exception as e:
                return f"Error: {e}. Uso: detener url <URL>"

        elif accion == "reiniciar_pcbot":
            try:
                pcbot_id = cmd_parts[1]
                ws = pcbots.get(pcbot_id)
                if ws:
                    asyncio.run_coroutine_threadsafe(
                        ws.send(json.dumps({"type": "reconnect", "data": {}})),
                        loop
                    )
                    return f"Reinicio enviado a {pcbot_id}"
                return f"PCBOT {pcbot_id} no encontrado"
            except Exception as e:
                return f"Error: {e}"

        elif accion == "listar_usuarios":
            return f"Usuarios registrados: {len(USUARIOS)} | {', '.join(list(USUARIOS.keys())[:10])}"

        else:
            return f"Comando desconocido: {accion}. Comandos: estado, perfiles, asignar, comentarios_activar, comentarios_desactivar, detener, reiniciar_pcbot, listar_usuarios"

    def log_message(self, format, *args):
        pass  # Silenciar logs HTTP

def start_http_server():
    """Inicia el servidor HTTP en un hilo separado"""
    handler = DashboardHandler
    httpd = HTTPServer(("0.0.0.0", HTTP_PORT), handler)
    httpd.allow_reuse_address = True
    print(f"[HTTP] Portal Admin: http://{IP}:{HTTP_PORT}/")
    print(f"[HTTP] Portal PCBOT: http://{IP}:{HTTP_PORT}/portal")
    print(f"[HTTP] Dashboard API: http://{IP}:{HTTP_PORT}/api/dashboard")
    print(f"[HTTP] Login API: http://{IP}:{HTTP_PORT}/api/login")
    print(f"[HTTP] KBT API: http://{IP}:{HTTP_PORT}/api/kbt/stats")
    httpd.serve_forever()

# ============================================================================
# CONSOLA ADMIN
# ============================================================================

def admin_console():
    print("\n" + "=" * 60)
    print("  ROXYMASTER v6.2 - CONSOLA ADMIN")
    print("=" * 60)
    print("  COMANDOS:")
    print("  perfiles              - Listar perfiles")
    print("  usuarios              - Listar usuarios registrados")
    print("  asignar <cant> url <URL> duracion <min>")
    print("  comentarios_activar url <URL> nivel <bajo/medio/alto>")
    print("  comentarios_desactivar url <URL>")
    print("  detener url <URL>")
    print("  estado                - Estado general")
    print("  kbt                   - Estadisticas KBT")
    print("  salir                 - Detener servidor")
    print("-" * 60)

    while True:
        try:
            cmd = input("\n[ADMIN] > ").strip().split()
            if not cmd:
                continue

            if cmd[0] == "perfiles":
                print(f"\n[PERFILES] Total: {len(perfiles_map)}")
                ocupados = set()
                for g in grupos.values():
                    ocupados.update(g["perfiles"])
                for key in list(perfiles_map.keys())[:20]:
                    estado = "OCUPADO" if key in ocupados else "LIBRE"
                    print(f"  {key} : {estado}")

            elif cmd[0] == "usuarios":
                print(f"\n[USUARIOS] Total: {len(USUARIOS)}")
                for email, info in USUARIOS.items():
                    print(f"  {email} : {info['rol']}")

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
                    print("Uso: comentarios_activar url https://kick.com/xxx nivel medio")

            elif cmd[0] == "comentarios_desactivar":
                try:
                    url = cmd[2]
                    asyncio.run_coroutine_threadsafe(ejecutar_comentarios_desactivar(url), loop)
                except:
                    print("Uso: comentarios_desactivar url https://kick.com/xxx")

            elif cmd[0] == "detener":
                try:
                    url = cmd[2]
                    asyncio.run_coroutine_threadsafe(ejecutar_detener(url), loop)
                except:
                    print("Uso: detener url https://kick.com/xxx")

            elif cmd[0] == "estado":
                total = len(perfiles_map)
                ocupados = sum(len(g.get("perfiles", [])) for g in grupos.values())
                print(f"\n[ESTADO]")
                print(f"  Servidor: {IP}:{PUERTO} | HTTP: {IP}:{HTTP_PORT}")
                print(f"  PCBOTs conectados: {len(pcbots)}")
                print(f"  Perfiles totales: {total}")
                print(f"  Perfiles ocupados: {ocupados}")
                print(f"  Perfiles libres: {total - ocupados}")
                print(f"  Grupos activos: {len(grupos)}")
                print(f"  JARVIS comentarios: {jarvis.get_stats()['generados']}")
                print(f"  Sesiones activas: {len(SESIONES)}")
                if kbt:
                    s = kbt.get_stats()
                    print(f"  KBT Granjeros: {s['total_granjeros']} | Circulacion: {s['tokens_en_circulacion']} KBT")

            elif cmd[0] == "kbt":
                if kbt:
                    s = kbt.get_stats()
                    print(f"\n[KBT TOKENOMICS]")
                    print(f"  Granjeros: {s['total_granjeros']}")
                    print(f"  Tokens en circulacion: {s['tokens_en_circulacion']} KBT")
                    print(f"  Reserva: {s['reserva_tokens']} KBT | S/ {s['reserva_soles']}")
                    print(f"  Perfiles registrados: {s['total_perfiles']}")
                    print(f"  Transacciones: {s['total_transacciones']}")
                else:
                    print("KBT no disponible")

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
    global loop, kbt
    loop = asyncio.get_event_loop()

    # Inicializar motor KBT
    if KBT_AVAILABLE:
        kbt = Tokenomics()
        print(f"[KBT] Tokenomics inicializado - {kbt.get_stats()['total_granjeros']} granjeros")
    else:
        print("[KBT] No disponible - funcionalidad limitada")

    # Tareas asincronas
    asyncio.create_task(tarea_enviar_comentarios())

    # Consola admin en hilo separado
    threading.Thread(target=admin_console, daemon=True).start()

    # HTTP server en hilo separado
    threading.Thread(target=start_http_server, daemon=True).start()

    print(f"\n{'='*60}")
    print(f"  ROXYMASTER v6.2 - PCMASTER SERVER")
    print(f"  WS Server: {IP}:{PUERTO}")
    print(f"  Portal Admin: http://{IP}:{HTTP_PORT}/")
    print(f"  Portal PCBOT: http://{IP}:{HTTP_PORT}/portal")
    print(f"  Login Admin: PCMASTER / Abc123$_")
    print(f"{'='*60}\n")

    async with websockets.serve(manejar_conexion, IP, PUERTO):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())