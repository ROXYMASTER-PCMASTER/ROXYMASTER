# ejecutor.py - playwright, inyeccion de comentarios, manejo de paginas
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import asyncio, random, logging
logger = logging.getLogger("ejecutor")
