"""
JARVIS v6.1 — Generador de comentarios contextuales para streams.
Usa Ollama (llama3.2) con caché anti-repeticiones, variabilidad de
temperatura y respaldo de frases si el modelo no responde.
"""
import os
import json
import time
import random
import threading
import requests
from collections import deque

# ============================================================================
# RESPALDOS — 15 frases variadas si Ollama no responde
# ============================================================================
RESPALDOS = [
    "no seee 🔥",
    "vamooo papá 🔥",
    "durísimo 🔥",
    "oyeee 🔥",
    "qué locura 🔥",
    "dale con todo 🔥",
    "no puedo más 🔥",
    "jajaja qué risa 🔥",
    "ese es el nivel 🔥",
    "crack total 🔥",
    "a otra cosa 🔥",
    "tremendo 🔥",
    "uffff sin palabras 🔥",
    "god mode 🔥",
    "se pasó 🔥",
]


class Jarvis:
    """Generador de comentarios con caché y anti-repeticiones."""

    def __init__(self, prompts_dir):
        self.prompts_dir = prompts_dir
        self.prompt_maestro = self._cargar_prompt()
        # Caché de últimos 100 comentarios generados (anti-repetición)
        self._cache_generados = deque(maxlen=100)
        # Memoria de contexto por URL (lo que ocurre en el stream)
        self._memoria_por_url = {}
        # Lock para proteger generación concurrente
        self._lock = threading.Lock()
        # Estadísticas
        self.stats = {"generados": 0, "fallbacks": 0, "errores": 0}
        print(f"[JARVIS v6.1] Activado. Prompt: {len(self.prompt_maestro)} caracteres")

    # ------------------------------------------------------------------
    # INICIALIZACIÓN
    # ------------------------------------------------------------------
    def _cargar_prompt(self):
        """Carga el prompt maestro desde prompts/maestro.txt."""
        path = os.path.join(self.prompts_dir, "maestro.txt")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8-sig") as f:
                return f.read()
        return "Eres un comentarista de streams. Sé natural, variado y entretenido."

    # ------------------------------------------------------------------
    # MEMORIA DE CONTEXTO POR URL
    # ------------------------------------------------------------------
    def _get_memoria(self, url):
        if url not in self._memoria_por_url:
            self._memoria_por_url[url] = deque(maxlen=50)
        return self._memoria_por_url[url]

    def aprender(self, texto, url):
        """Almacena texto del stream como contexto para futuros comentarios."""
        if texto and len(texto) > 5:
            memoria = self._get_memoria(url)
            memoria.append({"texto": texto, "ts": time.time()})

    # ------------------------------------------------------------------
    # CACHÉ DE COMENTARIOS GENERADOS
    # ------------------------------------------------------------------
    def _ultimos_str(self, n=10):
        """Devuelve los últimos N comentarios generados como string
        para inyectarlos en el prompt y evitar repeticiones."""
        if not self._cache_generados:
            return ""
        ultimos = list(self._cache_generados)[-n:]
        return "\n".join(f"- {c}" for c in ultimos)

    def _registrar_generado(self, comentario):
        """Registra un comentario en la caché anti-repetición."""
        if comentario and len(comentario) > 3:
            self._cache_generados.append(comentario)

    # ------------------------------------------------------------------
    # GENERACIÓN PRINCIPAL
    # ------------------------------------------------------------------
    def generar(self, url):
        """
        Genera un comentario contextual para una URL de stream.
        Usa temperatura variable: 0.95 con contexto, 0.85 sin él.
        Si Ollama falla, devuelve una frase de respaldo aleatoria.
        """
        with self._lock:
            return self._generar_interno(url)

    def _generar_interno(self, url):
        """Lógica interna de generación (ya dentro del lock)."""
        memoria = self._get_memoria(url)
        ahora = time.time()

        # Contexto reciente (últimos 30 segundos)
        contextos = [
            m["texto"]
            for m in memoria
            if ahora - m["ts"] <= 30
        ]
        contexto = ""
        if contextos:
            contexto = "\n".join(list(contextos)[-10:])

        # Últimos comentarios generados (anti-repetición)
        ultimos = self._ultimos_str(8)

        # Variabilidad de temperatura: más creatividad con contexto
        temperatura = 0.95 if contexto else 0.85

        prompt = f"""{self.prompt_maestro}

CONTEXTO DEL STREAM:
{contexto[:500] if contexto else "Stream en vivo — sin contexto aún."}

ÚLTIMOS COMENTARIOS ENVIADOS (NO repitas estos):
{ultimos if ultimos else "(ninguno aún)"}

Genera UN comentario corto (máximo 60 caracteres). Sé natural, variado y NO repitas los comentarios anteriores."""

        # Intentar con Ollama
        try:
            r = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3.2",
                    "prompt": prompt,
                    "stream": False,
                    "max_tokens": 80,
                    "temperature": temperatura,
                },
                timeout=15,
            )
            if r.status_code == 200:
                txt = r.json().get("response", "").strip()
                if txt and len(txt) >= 3:
                    txt = txt[:60]
                    self._registrar_generado(txt)
                    self.stats["generados"] += 1
                    return txt
        except requests.exceptions.Timeout:
            print("[JARVIS v6.1] Timeout en Ollama — usando respaldo")
            self.stats["errores"] += 1
        except requests.exceptions.ConnectionError:
            print("[JARVIS v6.1] Conexión rechazada por Ollama — usando respaldo")
            self.stats["errores"] += 1
        except Exception as e:
            print(f"[JARVIS v6.1] Error inesperado: {type(e).__name__}: {e}")
            self.stats["errores"] += 1

        # Respaldo
        self.stats["fallbacks"] += 1
        fallback = random.choice(RESPALDOS)
        self._registrar_generado(fallback)
        self.stats["generados"] += 1
        return fallback

    # ------------------------------------------------------------------
    # ESTADÍSTICAS
    # ------------------------------------------------------------------
    def get_stats(self):
        """Devuelve diccionario con estadísticas de generación."""
        return dict(self.stats)