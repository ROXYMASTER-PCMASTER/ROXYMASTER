import asyncio
import time
from playwright.async_api import async_playwright

class CapturadorChat:
    def __init__(self, url):
        self.url = url
        self.ultimos_comentarios = []
        self.ejecutando = False
    
    async def iniciar(self):
        self.ejecutando = True
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(self.url)
            print(f"[CHAT] Capturando chat de {self.url}")
            
            while self.ejecutando:
                try:
                    comentarios = await page.eval_on_selector_all(
                        'span.font-normal',
                        '(elements) => elements.map(el => el.innerText)'
                    )
                    nuevos = [c for c in comentarios if c not in self.ultimos_comentarios[-20:]]
                    for c in nuevos[-5:]:
                        print(f"[CHAT] {c[:50]}")
                        self.ultimos_comentarios.append(c)
                    await asyncio.sleep(2)
                except:
                    await asyncio.sleep(2)
    
    def detener(self):
        self.ejecutando = False
    
    def obtener_contexto(self):
        return "\n".join(self.ultimos_comentarios[-15:])