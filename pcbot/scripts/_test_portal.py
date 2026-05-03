"""test rapido del portal http usando aiohttp como cliente"""
import sys, os, json, asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from http_portal import PortalServer
from aiohttp import ClientSession

async def main():
    p = PortalServer()
    await p.start_async(8089)
    async with ClientSession() as session:
        await asyncio.sleep(2)
        async with session.get("http://127.0.0.1:8089/api/estado") as resp:
            d = await resp.json()
            print("status:", resp.status)
            print("data keys:", list(d.keys()))
            print("pcbot_id:", d.get("pcbot_id"))
    p.stop()

if __name__ == "__main__":
    asyncio.run(main())