import asyncio, json

async def get_workspaceid():
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get('http://127.0.0.1:9238/json') as resp:
            targets = await resp.json()
            print('targets count:', len(targets))
            for t in targets[:5]:
                title = t.get('title', '?')[:80]
                ws = t.get('webSocketDebuggerUrl', '?')
                print(f'  title={title} ws={ws}')
            # buscar workspaceId via CDP en la pagina de RoxyBrowser
            # tomar el target principal
            if targets:
                tgt = targets[0]
                ws_url = tgt.get('webSocketDebuggerUrl')
                if ws_url:
                    async with session.ws_connect(ws_url) as ws2:
                        # enviar comando Runtime.evaluate para obtener localStorage
                        cmd = json.dumps({
                            'id': 1,
                            'method': 'Runtime.evaluate',
                            'params': {
                                'expression': 'JSON.stringify(localStorage)',
                                'returnByValue': True
                            }
                        })
                        await ws2.send_str(cmd)
                        resp2 = await ws2.receive()
                        print('localStorage response:', resp2.data[:500])
                        
                        # buscar location.href
                        cmd2 = json.dumps({
                            'id': 2,
                            'method': 'Runtime.evaluate',
                            'params': {
                                'expression': 'window.location.href',
                                'returnByValue': True
                            }
                        })
                        await ws2.send_str(cmd2)
                        resp3 = await ws2.receive()
                        print('location:', resp3.data[:500])

if __name__ == '__main__':
    asyncio.run(get_workspaceid())