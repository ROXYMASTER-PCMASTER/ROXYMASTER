import asyncio, json

async def find_workspaceid():
    import aiohttp
    
    # 1. listar todos los targets posibles
    async with aiohttp.ClientSession() as session:
        async with session.get('http://127.0.0.1:9238/json/list') as resp:
            targets = await resp.json()
            print(f'total targets: {len(targets)}')
            for i, t in enumerate(targets):
                print(f'target {i}: type={t.get("type")} title={t.get("title","?")[:60]} url={t.get("url","?")[:80]}')
        
        print()
        # 2. probar con varios workspaceId
        for wsid in ['pcmaster', 'pcbot', 'default', 'cyber', 'roxymaster', 'workspace-1', 'my-workspace']:
            async with session.get('http://127.0.0.1:50000/api/browsers', headers={'X-Workspace-Id': wsid}) as resp:
                txt = (await resp.text())[:200]
                print(f'X-Workspace-Id={wsid}: {txt}')
        
        print()
        # 3. probar varios endpoints
        endpoints = ['/api/version', '/api/health', '/api/profile', '/api/session', '/api/browser', '/api/status', '/api/config', '/api/ws', '/api/settings', '/api/user']
        for ep in endpoints:
            async with session.get(f'http://127.0.0.1:50000{ep}') as resp:
                txt = (await resp.text())[:200]
                print(f'{ep}: {txt}')

if __name__ == '__main__':
    asyncio.run(find_workspaceid())