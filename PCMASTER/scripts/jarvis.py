"""
ROXYMASTER v8.0 - JARVIS IA (PCMASTER)
Agente IA que se autoeduca usando Ollama.
Aprende de conversaciones de live, genera comentarios, analiza contexto.
Modelo por defecto: llama3.2 (configurable).
"""

import json
import logging
import os
import threading
import time

from pcmaster.scripts.config_loader import MODELO_OLLAMA, DATA_DIR

logger = logging.getLogger(__name__)

MEMORIA_FILE = os.path.join(DATA_DIR, "jarvis_memoria.json")

try:
    import requests
    OLLAMA_OK = True
except ImportError:
    OLLAMA_OK = False


class Jarvis:
    """
    IA autoeducable que aprende de lives y genera comentarios.
    Usa Ollama como backend de LLM.
    """

    def __init__(self, modelo: str = None):
        self.modelo = modelo or MODELO_OLLAMA
        self.memoria = []
        self.contexto = {}
        self.lock = threading.Lock()
        self.ollama_url = "http://127.0.0.1:11434/api/generate"
        self._load_memoria()

    def _load_memoria(self):
        if os.path.isfile(MEMORIA_FILE):
            try:
                with open(MEMORIA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.memoria = data.get("memoria", [])[-500:]
            except Exception:
                pass

    def _save_memoria(self):
        try:
            with open(MEMORIA_FILE, "w", encoding="utf-8") as f:
                json.dump({"memoria": self.memoria}, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _ollama(self, prompt: str, system: str = "") -> str:
        if not OLLAMA_OK:
            return ""

        full_prompt = prompt
        if system:
            full_prompt = f"{system}\n\n{prompt}"

        try:
            resp = requests.post(
                self.ollama_url,
                json={
                    "model": self.modelo,
                    "prompt": full_prompt,
                    "stream": False,
                    "options": {
                        "num_predict": 150,
                        "temperature": 0.8
                    }
                },
                timeout=30
            )
            if resp.status_code == 200:
                return resp.json().get("response", "").strip()
            logger.warning(f"Ollama status {resp.status_code}")
            return ""
        except requests.ConnectionError:
            logger.warning("Ollama no detectado en 127.0.0.1:11434")
            return ""
        except Exception as e:
            logger.error(f"Error Ollama: {e}")
            return ""

    # ------------------------------------------------------------------
    # Autoeducacion: Aprender de conversaciones
    # ------------------------------------------------------------------
    def aprender(self, texto: str, fuente: str = "live_chat"):
        """
        Aprende de un texto leido en un live (chat, titulo, descripcion).
        """
        with self.lock:
            self.memoria.append({
                "texto": texto[:500],
                "fuente": fuente,
                "timestamp": time.time()
            })
            if len(self.memoria) > 1000:
                self.memoria = self.memoria[-500:]
            self._save_memoria()

        logger.info(f"Jarvis aprendio de {fuente}: {texto[:80]}...")

    # ------------------------------------------------------------------
    # Generar comentario para un live
    # ------------------------------------------------------------------
    def generar_comentario(self, contexto_live: dict) -> str:
        """
        Genera un comentario natural en español para un live.
        contexto_live: {titulo, categoria, ultimos_chats[], streamer}
        """
        titulo = contexto_live.get("titulo", "stream")
        categoria = contexto_live.get("categoria", "general")
        streamer = contexto_live.get("streamer", "el streamer")
        ultimos = contexto_live.get("ultimos_chats", [])

        prompt = f"""Eres un espectador en un live de {categoria}.
Streamer: {streamer}
Titulo del live: {titulo}
Ultimos comentarios del chat: {json.dumps(ultimos[-5:], ensure_ascii=False)}

Genera UN SOLO comentario en español, natural, corto (max 40 palabras), que parezca escrito por un humano viendo el live. No uses emojis excesivos. No hagas spam. Se autentico.

Comentario:"""

        system = "Eres un espectador de lives de Kick/TikTok que comenta de forma natural y autentica en español latino."

        comentario = self._ollama(prompt, system)

        if comentario:
            self.aprender(comentario, fuente="comentario_generado")

        return comentario or "🔥 Que buen contenido!"

    # ------------------------------------------------------------------
    # Analizar sentimiento del chat
    # ------------------------------------------------------------------
    def analizar_sentimiento(self, chats: list) -> dict:
        texto = "\n".join(chats[-20:])
        if not texto:
            return {"sentimiento": "neutral", "confianza": 0.5}

        prompt = f"Analiza el sentimiento general de estos comentarios de live:\n{texto}\n\nResponde SOLO con un JSON: {{\"sentimiento\": \"positivo|negativo|neutral\", \"confianza\": 0.0-1.0}}"

        resp = self._ollama(prompt)
        try:
            return json.loads(resp)
        except json.JSONDecodeError:
            return {"sentimiento": "neutral", "confianza": 0.5}

    # ------------------------------------------------------------------
    # Resumir live para el admin
    # ------------------------------------------------------------------
    def resumir_live(self, url: str, chats: list) -> str:
        prompt = f"Resume en 3 lineas lo que esta pasando en este live ({url}) basado en los ultimos chats:\n{json.dumps(chats[-30:], ensure_ascii=False)}"

        return self._ollama(prompt) or "Live activo sin suficientes datos."

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------
    def get_status(self) -> dict:
        return {
            "modelo": self.modelo,
            "memoria_entradas": len(self.memoria),
            "ollama_activo": self._ollama("ping") != "" if OLLAMA_OK else False
        }