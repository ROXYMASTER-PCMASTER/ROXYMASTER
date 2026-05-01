from playwright.async_api import async_playwright
import asyncio, random, logging
logger = logging.getLogger("ejecutor")
async def inyectar_comentario(page, comentario):
    try:
        selectores = ['textarea[placeholder*="Message"]', 'div[role="textbox"]']
        for sel in selectores:
            if await page.locator(sel).count() > 0:
                await page.click(sel)
                await page.type(sel, comentario, delay=random.uniform(30,100))
                await page.keyboard.press("Enter")
                return True
    except Exception as e:
        logger.error(f"error inyectando: {e}")
    return False
async def abrir_url(page, url):
    await page.goto(url, timeout=30000, wait_until="domcontentloaded")