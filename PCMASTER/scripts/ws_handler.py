import asyncio, json, websockets, logging, time
logger = logging.getLogger("ws_handler")
pcbots = {}
perfiles_map = {}
async def enviar(pcbot_id, cmd, data):
    if pcbot_id in pcbots:
        try:
            await pcbots[pcbot_id].send(json.dumps({"type": cmd, "data": data}))
        except:
            pass
async def manejar_conexion(websocket, path=None):
    cid = None
    try:
        async for raw in websocket:
            msg = json.loads(raw)
            if msg.get("type") == "identify":
                cid = msg.get("data", {}).get("pc_id") or msg.get("client_id")
                pcbots[cid] = websocket
                perfiles = msg.get("data", {}).get("perfiles_lista", [])
                for p in perfiles:
                    key = f"{cid}|{p['name']}"
                    perfiles_map[key] = {"pcbot": cid, "name": p["name"], "dirId": p.get("dirId", "")}
                await websocket.send(json.dumps({"type": "connected"}))
    except:
        pass
    finally:
        if cid:
            pcbots.pop(cid, None)
            keys = [k for k,v in perfiles_map.items() if v["pcbot"] == cid]
            for k in keys: del perfiles_map[k]
