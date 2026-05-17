# arrancar.py - inicia el servidor uvicorn
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import uvicorn
uvicorn.run("server:app", host="0.0.0.0", port=8086, log_level="info")