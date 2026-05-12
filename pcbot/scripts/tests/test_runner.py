"""
roxymaster v8.3 - pcbot test runner (zombie)
ejecuta pruebas periodicas de humo sobre el dominio publico wafabot.com
registra resultados en z:\logs\pruebas.log
compatible con python 3.10, utf-8 sin bom.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_DOMAIN = "https://www.wafabot.com"
_CREDENTIALS = {
    "email": "prueba1@roxymaster.local",
    "password": "12345678",
}
_ROXYBROWSER_API_KEY = "8ce112f7ebbb0fba6e9e290194f8e117"
_PRUEBAS_LOG = os.path.join("Z:", "logs", "pruebas.log")
_SCREENSHOTS_DIR = os.path.join("Z:", "logs", "screenshots")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _log_path() -> str:
    return _PRUEBAS_LOG


def _ts_file(prefix: str, ext: str = ".png") -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{ts}{ext}"


class TestRunner:
    """ejecuta pruebas de humo sobre wafabot.com."""

    def __init__(self):
        self._token: Optional[str] = None
        self._resultados: list = []
        os.makedirs(_SCREENSHOTS_DIR, exist_ok=True)

    async def ejecutar_todas(self) -> list:
        """ejecuta todas las pruebas y retorna lista de resultados."""
        self._resultados = []
        logger.info("iniciando bateria de pruebas de humo")

        try:
            import aiohttp
        except ImportError:
            logger.error("aiohttp no instalado. no se pueden ejecutar pruebas.")
            self._registrar("import", False, "aiohttp no instalado")
            return self._resultados

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
                await self._prueba_login(session)
                if self._token:
                    await self._prueba_perfiles(session)
                    await self._prueba_sync(session)
                    await self._prueba_pedido(session)
        except Exception as e:
            logger.error(f"error general en pruebas: {e}")
            self._registrar("general", False, str(e))

        await self._guardar_resultados()
        return self._resultados

    async def _prueba_login(self, session) -> None:
        """prueba 1: login con credenciales de prueba."""
        url = f"{_DOMAIN}/api/login"
        payload = _CREDENTIALS
        try:
            async with session.post(url, json=payload) as resp:
                status = resp.status
                texto = await resp.text()
                if status == 200:
                    try:
                        data = json.loads(texto)
                        token = data.get("token") or data.get("access_token")
                        if token:
                            self._token = token
                            self._registrar("login", True, f"token obtenido ({len(token)} chars)")
                        else:
                            self._registrar("login", False, "respuesta 200 pero sin token")
                    except json.JSONDecodeError:
                        self._registrar("login", False, f"respuesta 200 pero json invalido: {texto[:200]}")
                else:
                    self._registrar("login", False, f"http {status}: {texto[:200]}")
        except asyncio.TimeoutError:
            self._registrar("login", False, "timeout (30s)")
        except Exception as e:
            self._registrar("login", False, str(e))

    async def _prueba_perfiles(self, session) -> None:
        """prueba 2: obtener perfiles desde dashboard."""
        url = f"{_DOMAIN}/api/roxy/profiles"
        headers = {"Authorization": f"Bearer {self._token}"}
        try:
            async with session.get(url, headers=headers) as resp:
                status = resp.status
                texto = await resp.text()
                if status == 200:
                    try:
                        data = json.loads(texto)
                        perfiles = data if isinstance(data, list) else data.get("profiles", [])
                        self._registrar("perfiles", True, f"{len(perfiles)} perfiles obtenidos")
                    except json.JSONDecodeError:
                        self._registrar("perfiles", False, f"json invalido: {texto[:200]}")
                else:
                    self._registrar("perfiles", False, f"http {status}: {texto[:200]}")
        except asyncio.TimeoutError:
            self._registrar("perfiles", False, "timeout")
        except Exception as e:
            self._registrar("perfiles", False, str(e))

    async def _prueba_sync(self, session) -> None:
        """prueba 3: sincronizar perfiles."""
        url = f"{_DOMAIN}/api/roxy/sync_profiles"
        headers = {"Authorization": f"Bearer {self._token}"}
        payload = {"api_key": _ROXYBROWSER_API_KEY}
        try:
            async with session.post(url, json=payload, headers=headers) as resp:
                status = resp.status
                texto = await resp.text()
                ok = status in (200, 202)
                self._registrar("sync", ok, f"http {status}" if not ok else f"http {status}: {texto[:100]}")
        except asyncio.TimeoutError:
            self._registrar("sync", False, "timeout")
        except Exception as e:
            self._registrar("sync", False, str(e))

    async def _prueba_pedido(self, session) -> None:
        """prueba 4: crear pedido de ejemplo."""
        url = f"{_DOMAIN}/api/pedidos/crear"
        headers = {"Authorization": f"Bearer {self._token}"}
        payload = {
            "url": "https://ejemplo.com",
            "cantidad": 1,
            "tipo": "visita",
        }
        try:
            async with session.post(url, json=payload, headers=headers) as resp:
                status = resp.status
                texto = await resp.text()
                ok = status in (200, 201, 202)
                self._registrar("pedido", ok, f"http {status}" if not ok else f"http {status}: {texto[:100]}")
        except asyncio.TimeoutError:
            self._registrar("pedido", False, "timeout")
        except Exception as e:
            self._registrar("pedido", False, str(e))

    def _registrar(self, prueba: str, exito: bool, detalle: str):
        """registra un resultado en memoria."""
        entry = {
            "prueba": prueba,
            "exito": exito,
            "detalle": detalle,
            "timestamp": _utc_now(),
        }
        self._resultados.append(entry)
        estado = "ok" if exito else "fallo"
        logger.info(f"prueba {prueba}: {estado} - {detalle}")

    async def _guardar_resultados(self):
        """guarda los resultados en z:\logs\pruebas.log."""
        try:
            with open(_PRUEBAS_LOG, "a", encoding="utf-8") as f:
                for r in self._resultados:
                    linea = (
                        f"[{r['timestamp']}] prueba={r['prueba']} "
                        f"resultado={'ok' if r['exito'] else 'fallo'} "
                        f"detalle={r['detalle']}\n"
                    )
                    f.write(linea)
            logger.info(f"resultados guardados en {_PRUEBAS_LOG}")
        except (OSError, PermissionError) as e:
            logger.error(f"no se pudo guardar pruebas.log: {e}")

    def hay_errores_recurrentes(self, max_fallos: int = 3) -> Optional[str]:
        """verifica si alguna prueba ha fallado mas de max_fallos veces seguidas.
        requiere leer el log de pruebas.
        """
        if not os.path.isfile(_PRUEBAS_LOG):
            return None
        try:
            with open(_PRUEBAS_LOG, "r", encoding="utf-8") as f:
                lineas = f.readlines()
        except (OSError, PermissionError):
            return None

        from collections import defaultdict
        conteo: dict = defaultdict(int)
        for linea in reversed(lineas):
            if "resultado=fallo" in linea:
                for prueba in ["login", "perfiles", "sync", "pedido"]:
                    if f"prueba={prueba}" in linea:
                        conteo[prueba] += 1
                        break
            else:
                # si hay un ok, resetea contador
                for prueba in ["login", "perfiles", "sync", "pedido"]:
                    if f"prueba={prueba}" in linea:
                        conteo[prueba] = 0
                        break

        for prueba, fallos in conteo.items():
            if fallos >= max_fallos:
                return prueba
        return None