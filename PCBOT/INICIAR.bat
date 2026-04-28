@echo off
title ROXYMASTER v6.0 - PCBOT
cd /d "%USERPROFILE%\Desktop\ROXYMASTER\PCBOT\scripts"
pip install websockets requests playwright -q
playwright install chromium
python pcbot.py
pause
