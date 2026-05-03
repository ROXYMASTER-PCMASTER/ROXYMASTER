# ws_client.py - cliente websocket hacia pcmaster usando secretos
import asyncio, json, logging, time
import websockets
logger = logging.getLogger("pcbot.ws")

class WSClient:
    def __init__(self, ip, puerto, pcbot_id, profile_manager=None, state_tracker=None, token_engine=None):
        self.uri = f"ws://{ip}:{puerto}"
        self.pcbot_id = pcbot_id
        self.pm = profile_manager
        self.st = state_tracker
        self.te = token_engine
        self.ws = None
        self.connected = False
        self.secreto_shs = "r0xym4st3r_s3cr3t0_k3y_v83"

    async def connect(self):
        while True:
            try:
                async with websockets.connect(self.uri, ping_timeout=10, open_timeout=10) as ws:
                    self.ws = ws
                    self.connected = True
                    logger.info(f"conectado a pcmaster: {self.uri}")
                    while True:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=30)
                            logger.info(f"mensaje recibido: {msg[:100]}")
                        except asyncio.TimeoutError:
                            pass
            except Exception as e:
                logger.error(f"error conexion ws: {e}")
                self.connected = False
                await asyncio.sleep(5)