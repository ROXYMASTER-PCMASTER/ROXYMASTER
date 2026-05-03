import asyncio, json

async def find_workspaceid():
    import aiohttp
    async with aiohttp.ClientSession() as session:
        # 1. login
        login_data = {'email':'admin@roxymaster.com','password':'admin123'}
        async with session.post('http://127.0.0.1:50000/api/login', json=login_data) as resp:
            print('login:', resp.status, await resp.text())
        
        # 2. probar GET /api/browsers sin header
        async with session.get('http://127.0.0.1:50000/api/browsers') as resp:
            print('browsers:', resp.status, await resp.text()[:500])
        
        # 3. probar GET /api/info
        async with session.get('http://127.0.0.1:50000/api/info') as resp:
            print('info:', resp.status, await resp.text()[:500])
        
        # 4. probar GET /api/workspace
        async with session.get('http://127.0.0.1:50000/api/workspace') as resp:
            print('workspace:', resp.status, await resp.text()[:500])
        
        # 5. probar GET /api/status
        async with session.get('http://127.0.0.1:50000/api/status') as resp:
            print('status:', resp.status, await resp.text()[:500])
        
        # 6. probar GET /api/config
        async with session.get('http://127.0.0.1:50000/api/config') as resp:
            print('config:', resp.status, await resp.text()[:500])

if __name__ == '__main__':
    asyncio.run(find_workspaceid())