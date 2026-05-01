@echo off
taskkill /F /IM python.exe >nul 2>&1
timeout /t 2 /nobreak >nul
netstat -ano | findstr :5006
echo FIN