import json, secrets, time, hashlib, os, logging
from fastapi import FastAPI, Request, HTTPException, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from auth import AuthManager
from orchestrator import ejecutar_asignar, ejecutar_comentarios_activar, ejecutar_comentarios_desactivar, ejecutar_detener, grupos
from tokenomics import Tokenomics
from marketplace import Marketplace
from ws_handler import pcbots, perfiles_map
from config import DATA_DIR

logger = logging.getLogger("api_endpoints")
app = FastAPI(title="roxymaster api")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
auth = AuthManager()
kbt = Tokenomics()
market = Marketplace(kbt)

PORTAL_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "portal.html")

# ==================== HELPERS ====================
def get_current_user(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    sesion = auth.validar_token(token)
    if not sesion.get("valido"):
        raise HTTPException(status_code=401, detail="token invalido")
    return sesion

def get_admin(request: Request):
    user = get_current_user(request)
    if user.get("rol") != "admin":
        raise HTTPException(status_code=403, detail="solo admin")
    return user

# ==================== AUTENTICACIÓN ====================
@app.post("/api/login")
async def login(data: dict):
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    res = auth.login(email, password)
    if res.get("ok"): return {"token": res["token"], "rol": res["rol"], "email": email}
    raise HTTPException(status_code=401, detail=res.get("error", "credenciales invalidas"))

@app.post("/api/register")
async def register(data: dict):
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    referido_por = data.get("referido_por", "pcmaster").lower()
    res = auth.registrar(email, password, referido_por)
    if res.get("ok"): return {"token": res["token"], "rol": res["rol"], "email": email}
    raise HTTPException(status_code=400, detail=res.get("error", "error al registrar"))

@app.get("/api/verify")
async def verify(token: str = Query(None), request: Request = None):
    if not token:
        token = (request.headers.get("Authorization", "") if request else "").replace("Bearer ", "")
    sesion = auth.validar_token(token)
    if sesion.get("valido"): return {"valido": True, "email": sesion["email"], "rol": sesion["rol"]}
    raise HTTPException(status_code=401, detail="token invalido o expirado")

@app.post("/api/logout")
async def logout(token: str = ""):
    auth.cerrar_sesion(token)
    return {"ok": True}

# ==================== DASHBOARD ====================
@app.get("/api/dashboard")
async def dashboard(user=Depends(get_admin)):
    ahora = time.time()
    activos = sum(1 for v in perfiles_map.values() if v.get("estado") == "activo")
    inactivos = sum(1 for v in perfiles_map.values() if v.get("estado") != "activo")
    stats = kbt.get_stats()
    return {
        "pcbots_conectados": len(pcbots),
        "pcbots_total": len(pcbots),
        "perfiles_totales": len(perfiles_map),
        "perfiles_activos": activos,
        "perfiles_inactivos": inactivos,
        "perfiles_colgados": 0,
        "urls_activas": [{"url": u, "perfiles_asignados": len(g["perfiles"]), "tiempo_restante": max(0, int(g.get("duracion", 0) - (ahora - g["inicio"])) // 60), "comentarios_activos": g.get("comentarios", False), "inicio": time.strftime("%H:%M:%S", time.localtime(g["inicio"]))} for u, g in grupos.items()],
        "grupos": len(grupos),
        "uptime": int(ahora) if hasattr(kbt, "_start_time") else 0,
        "ip_servidor": "192.168.1.17",
        "kbt": stats,
        "pcbots": [{"id": cid, "ip_local": "192.168.1.x", "ip_tailscale": "100.x.x.x", "perfiles": len(perfiles_map), "estado": "conectado", "activos": activos, "inactivos": inactivos, "colgados": 0, "last_heartbeat": ahora} for cid in pcbots]
    }

@app.get("/api/mi_estado")
async def mi_estado(user=Depends(get_current_user)):
    email = user["email"]
    saldo = kbt.get_saldo(email)
    stats = kbt.get_stats()
    return {
        "email": email,
        "tokens_acumulados": saldo,
        "tokens_quemables": saldo,
        "tokens_comprados": 0,
        "tokens_hoy": 0,
        "modo": "conectado",
        "total_perfiles": 0,
        "perfiles_activos": 0,
        "perfiles_inactivos": 0,
        "pc_name": email,
        "ip_local": "0.0.0.0",
        "ip_tailscale": "0.0.0.0",
        "conectado_pcmaster": email in [v.get("email", "") for v in auth.usuarios.values()],
        "referido_por": kbt.get_referido(email),
        "perfiles": []
    }

# ==================== COMANDOS ====================
@app.post("/api/comando")
async def comando(data: dict, user=Depends(get_admin)):
    cmd_line = data.get("comando", "").strip()
    if not cmd_line: raise HTTPException(status_code=400, detail="comando vacio")
    args = cmd_line.split()
    cmd = args[0].lower()
    try:
        if cmd == "asignar":
            cant = int(args[1]); url = args[3]; dur = int(args[5])
            res = await ejecutar_asignar(cant, url, dur)
        elif cmd == "comentarios_activar":
            url = args[2]; nivel = args[4] if len(args) > 4 else "medio"
            res = await ejecutar_comentarios_activar(url, nivel)
        elif cmd == "comentarios_desactivar":
            url = args[2]; res = await ejecutar_comentarios_desactivar(url)
        elif cmd == "detener":
            url = args[2]; res = await ejecutar_detener(url)
        elif cmd == "broadcast":
            texto = " ".join(args[1:])
            res = f"broadcast: {texto}"
        elif cmd == "estado":
            res = f"pcbots: {len(pcbots)}, perfiles: {len(perfiles_map)}, grupos: {len(grupos)}"
        elif cmd == "perfiles":
            res = f"total: {len(perfiles_map)}"
        else:
            res = f"comando desconocido: {cmd}"
    except Exception as e:
        res = f"error: {e}"
    return {"resultado": res}

@app.post("/api/switch")
async def switch_mode(data: dict, user=Depends(get_current_user)):
    modo = data.get("modo", "conectado")
    return {"resultado": f"modo cambiado a {modo}"}

# ==================== ADMIN ====================
@app.get("/api/admin/estado_usuarios")
async def estado_usuarios(user=Depends(get_admin)):
    usuarios = auth.listar_usuarios()
    return {"usuarios": usuarios}

@app.post("/api/admin/enviar_recordatorio")
async def enviar_recordatorio(data: dict, user=Depends(get_admin)):
    email = data.get("email", "")
    return {"mensaje": f"recordatorio enviado a {email}"}

@app.post("/api/admin/recargar_saldo")
async def recargar_saldo(data: dict, user=Depends(get_admin)):
    email = data.get("email", "").lower()
    cantidad = data.get("cantidad", 0)
    motivo = data.get("motivo", "recarga_manual")
    try:
        kbt.acreditar_tokens(email, cantidad, motivo)
        return {"ok": True, "email": email, "cantidad": cantidad, "saldo_actual": kbt.get_saldo(email)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/admin/parametros_kbt")
async def get_parametros(user=Depends(get_admin)):
    return kbt.params

@app.post("/api/admin/parametros_kbt")
async def set_parametros(data: dict, user=Depends(get_admin)):
    for k, v in data.items():
        if k in kbt.params:
            kbt.params[k] = v
    kbt.guardar_params()
    return {"ok": True, "params": kbt.params}

@app.post("/api/admin/reset_parametros")
async def reset_parametros(user=Depends(get_admin)):
    kbt.reset_params()
    return {"ok": True, "params": kbt.params}

# ==================== KBT ====================
@app.get("/api/kbt/stats")
async def kbt_stats():
    return kbt.get_stats()

@app.get("/api/kbt/granjeros")
async def kbt_granjeros():
    return kbt.listar_granjeros()

@app.get("/api/kbt/parametros")
async def kbt_parametros():
    return kbt.params

@app.get("/api/kbt/saldo")
async def kbt_saldo(granjero_id: str = Query()):
    saldo = kbt.get_saldo(granjero_id)
    return {"email": granjero_id, "saldo_tokens": saldo, "saldo_soles": 0, "nivel_fiabilidad": "bronce"}

@app.post("/api/kbt/transferir")
async def kbt_transferir(data: dict, user=Depends(get_admin)):
    vendedor = data.get("vendedor", "").lower()
    comprador = data.get("comprador", "").lower()
    tokens = data.get("tokens", 0)
    try:
        kbt.transferir(vendedor, comprador, tokens)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ==================== MARKETPLACE ====================
@app.get("/api/kbt/ofertas")
async def listar_ofertas():
    return market.listar_activas()

@app.post("/api/kbt/crear_oferta")
async def crear_oferta(data: dict, user=Depends(get_current_user)):
    tokens = data.get("tokens", 0)
    precio_soles = data.get("precio_soles", 0)
    res = market.crear_oferta(user["email"], tokens, precio_soles)
    if res.get("ok"): return res
    raise HTTPException(status_code=400, detail=res.get("error", "error"))

@app.post("/api/kbt/comprar_oferta")
async def comprar_oferta(data: dict, user=Depends(get_current_user)):
    oferta_id = data.get("oferta_id", "")
    res = market.comprar_oferta(oferta_id, user["email"])
    if res.get("ok"): return res
    raise HTTPException(status_code=400, detail=res.get("error", "error"))

@app.post("/api/kbt/cancelar_oferta")
async def cancelar_oferta(data: dict, user=Depends(get_current_user)):
    oferta_id = data.get("oferta_id", "")
    res = market.cancelar_oferta(oferta_id, user["email"])
    if res.get("ok"): return res
    raise HTTPException(status_code=400, detail=res.get("error", "error"))

# ==================== REFERIDOS ====================
@app.get("/api/referidos/raiz")
async def referidos_raiz(user=Depends(get_current_user)):
    return kbt.arbol_referidos(user["email"])

@app.get("/api/referidos/arbol")
async def referidos_arbol(user=Depends(get_current_user)):
    return kbt.arbol_referidos(user["email"])

# ==================== PORTAL ====================
@app.get("/portal")
@app.get("/portal.html")
async def portal():
    if os.path.exists(PORTAL_PATH):
        with open(PORTAL_PATH, "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>portal no encontrado</h1>", status_code=404)

@app.get("/")
async def root():
    return portal()
