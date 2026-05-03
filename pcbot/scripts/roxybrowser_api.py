"""
roxymaster v8.3 - roxybrowser api (puente)
este archivo importa y reexporta desde api/roxybrowser_api.py
para mantener compatibilidad con codigo existente que importa
desde 'roxybrowser_api' directamente.
"""

from api.roxybrowser_api import RoxyBrowserAPI, find_workspace_id

__all__ = ["RoxyBrowserAPI", "find_workspace_id"]