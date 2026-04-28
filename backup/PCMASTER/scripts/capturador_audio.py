import sounddevice as sd
import numpy as np
import time
import threading
from faster_whisper import WhisperModel

class CapturadorAudio:
    def __init__(self, device_id=1):
        self.device_id = device_id
        self.ultimas_transcripciones = []
        self.ejecutando = False
        self.model = WhisperModel("base", device="cpu", compute_type="int8")
        print("[AUDIO] Whisper cargado")
    
    def iniciar(self):
        self.ejecutando = True
        self._loop()
    
    def _loop(self):
        while self.ejecutando:
            try:
                audio = sd.rec(int(2 * 16000), samplerate=16000, channels=1, device=self.device_id, dtype=np.float32)
                sd.wait()
                nivel = np.abs(audio).max()
                if nivel > 0.01:
                    audio_norm = audio / (nivel + 0.001)
                    segments, _ = self.model.transcribe(audio_norm.flatten(), beam_size=3, language="es")
                    texto = " ".join([seg.text.strip() for seg in segments])
                    if texto and len(texto) > 3:
                        self.ultimas_transcripciones.append({"texto": texto, "ts": time.time()})
                        print(f"[AUDIO] {texto}")
                time.sleep(0.5)
            except:
                time.sleep(1)
    
    def detener(self):
        self.ejecutando = False
    
    def obtener_contexto(self):
        ahora = time.time()
        textos = [t["texto"] for t in self.ultimas_transcripciones if ahora - t["ts"] <= 30]
        return "\n".join(textos[-10:])