@echo off
chcp 65001 >nul
title ROXYMASTER PCBOT v8.0

echo.
echo ============================================================
echo   🤖  ROXYMASTER v8.0 — PCBOT CLIENT
echo ============================================================
echo.

cd /d "%~dp0.."
set "PYTHONPATH=%~dp0.."

echo [*] Usuario detectado: %USERNAME%
echo [*] PC: %COMPUTERNAME%

echo [*] Verificando Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [X] Python no encontrado. Instala Python 3.10+
    pause
    exit /b 1
)

echo [*] Verificando dependencias...
python -c "import websockets, requests, psutil, json" >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Instalando dependencias...
    pip install websockets requests psutil --quiet
)

echo [*] Verificando RoxyBrowser en http://127.0.0.1:50000...
curl -s http://127.0.0.1:50000/ >nul 2>&1
if %errorlevel% neq 0 (
    echo [⚠] RoxyBrowser no detectado. Inícialo manualmente con tus perfiles.
) else (
    echo [✓] RoxyBrowser detectado.
)

echo.
echo [*] Iniciando PCBOT...
echo [*] Portal local: http://localhost:8087
echo ============================================================
echo.

start http://localhost:8087
python -m pcbot.scripts.main

pause