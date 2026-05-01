# conector_ws.py - cliente websocket hacia pcmaster
import asyncio, json, websockets, time, logging
logger = logging.getLogger("conector_ws")
class WSClient:
