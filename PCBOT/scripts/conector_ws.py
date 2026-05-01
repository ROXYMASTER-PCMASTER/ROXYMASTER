import asyncio, json, websockets, time
class WSClient:
    def __init__(self, uri, pcbot_id, on_comando):
        self.uri = uri
        self.pcbot_id = pcbot_id
        self.on_comando = on_comando
        self.connected = False
    async def connect(self):
        while True:
            try:
                async with websockets.connect(self.uri) as ws:
                    self.connected = True
                    await ws.send(json.dumps({"type":"identify","data":{"pc_id":self.pcbot_id}}))
                    async for msg in ws:
                        data = json.loads(msg)
                        await self.on_comando(data.get("type"), data.get("data", {}))
            except:
                self.connected = False
                await asyncio.sleep(5)
