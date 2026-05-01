@echo off
title ROXYMASTER v6.0 - PCMASTER
cd /d "%USERPROFILE%\Desktop\ROXYMASTER\PCMASTER\scripts"
echo Instalando dependencias...
pip install websockets requests sounddevice numpy scipy faster-whisper playwright -q
playwright install chromium
echo.
echo Iniciando Servidor...
python server.py
pause