import os
import json
import time
import random
import requests
from collections import deque

class Jarvis:
    def __init__(self, prompts_dir):
        self.prompts_dir = prompts_dir
        self.prompt_maestro = self._cargar_prompt()
        self.memoria_por_url = {}
        self.stats = {"generados": 0}
        print(f"[JARVIS] Activado. Prompt: {len(self.prompt_maestro)} caracteres")
    
    def _cargar_prompt(self):
        path = os.path.join(self.prompts_dir, "maestro.txt")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8-sig") as f:
                return f.read()
        return "Eres un comentarista de streams. Se natural."
    
    def _get_memoria(self, url):
        if url not in self.memoria_por_url:
            self.memoria_por_url[url] = deque(maxlen=50)
        return self.memoria_por_url[url]
    
    def aprender(self, texto, url):
        if texto and len(texto) > 5:
            memoria = self._get_memoria(url)
            memoria.append({"texto": texto, "ts": time.time()})
    
    def generar(self, url):
        memoria = self._get_memoria(url)
        contexto = ""
        ahora = time.time()
        contextos = [m["texto"] for m in memoria if ahora - m["ts"] <= 30]
        if contextos:
            contexto = "\n".join(list(contextos)[-10:])
        
        prompt = f"""{self.prompt_maestro}

CONTEXTO DEL STREAM:
{contexto[:500] if contexto else "Stream en vivo"}

Genera UN comentario corto (max 60 caracteres). Se natural."""
        
        try:
            r = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3.2",
                    "prompt": prompt,
                    "stream": False,
                    "max_tokens": 80,
                    "temperature": 0.85
                },
                timeout=15
            )
            if r.status_code == 200:
                txt = r.json().get("response", "").strip()
                if txt:
                    self.stats["generados"] += 1
                    return txt[:60]
        except Exception as e:
            print(f"[JARVIS] Error: {e}")
        
        return random.choice(["no see 🔥", "vamooo 🔥", "oyeee 🔥"])
    
    def get_stats(self):
        return self.stats