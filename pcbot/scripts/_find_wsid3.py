import asyncio, json

async def get_workspaceid():
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get('http://127.0.0.1:9238/json') as resp:
            targets = await resp.json()
            if not targets:
                print('no targets')
                return
            tgt = targets[0]
            ws_url = tgt.get('webSocketDebuggerUrl')
            if not ws_url:
                print('no ws url')
                return
            async with session.ws_connect(ws_url) as ws2:
                # obtener process.argv en electron
                cmd = json.dumps({
                    'id': 1,
                    'method': 'Runtime.evaluate',
                    'params': {
                        'expression': 'process.argv',
                        'returnByValue': True
                    }
                })
                await ws2.send_str(cmd)
                resp2 = await ws2.receive()
                print('argv:', resp2.data[:1500])
                
                # obtener process.env
                cmd2 = json.dumps({
                    'id': 2,
                    'method': 'Runtime.evaluate',
                    'params': {
                        'expression': 'process.env.HOME || process.env.USERPROFILE',
                        'returnByValue': True
                    }
                })
                await ws2.send_str(cmd2)
                resp3 = await ws2.receive()
                print('home:', resp3.data[:500])
                
                # obtener globalThis
                cmd3 = json.dumps({
                    'id': 3,
                    'method': 'Runtime.evaluate',
                    'params': {
                        'expression': 'Object.keys(require.cache).filter(k => k.includes(\"workspace\") || k.includes(\"roxy\") || k.includes(\"browser\")).slice(0,10)',
                        'returnByValue': True
                    }
                })
                await ws2.send_str(cmd3)
                resp4 = await ws2.receive()
                print('cached modules:', resp4.data[:500])

if __name__ == '__main__':
    asyncio.run(get_workspaceid())