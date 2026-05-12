@echo off
cd /d "C:\Users\PCMASTER\Desktop\roxymaster\pcmaster\scripts"
start "RoxymasterServer" /min "C:\Users\PCMASTER\AppData\Local\Programs\Python\Python310\python.exe" server.py
timeout /t 5 /nobreak >nul
start "Cloudflared" /min "C:\cloudflared\cloudflared.exe" tunnel run mi-portal-publico


